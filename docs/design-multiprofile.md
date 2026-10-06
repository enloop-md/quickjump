# QuickJump — shared bar across profiles and browsers

Status: **A implemented** (2026-10-01) in `agent/` and `lib/agent.js`, with these changes from the proposal below: profiles are named by finding the extension's storage directory that contains the profile id (no `identity` permission), no first-use approval prompt (the `Origin` check stays), and the agent owns global hotkeys and a tray icon. **B not implemented.** Written 2026-08-04.

Two things are specified here:

- **A** — one floating bar shared by every Chrome profile (and, optionally, other browsers).
- **B** — user-renamable entries with template variables (`$TITLE`, `$PROFILE`, …).

They are independent. **B can ship on the current single-profile extension without any of A**, and probably should — it is small, and it fixes a live annoyance on its own.

---

## 1. Why A needs something outside the browser

Three constraints, all hard:

1. **`chrome.storage` is per-profile.** `storage.sync` syncs *one profile across devices*; there is no cross-profile channel on one machine.
2. **`chrome.tabs` / `chrome.windows` are profile-scoped.** This is the real blocker. Even given a shared list, Profile 1's extension cannot activate a tab in Profile 3 — the tab is not addressable to it.
3. **Each profile runs its own extension instance** with its own service worker. No shared memory, no cross-instance messaging.

So the merged list and the window both have to live in a process the browser does not own.

## 2. Architecture

```
 Chrome "Default"   ─┐
 Chrome "Profile 1"  ├──► ws://127.0.0.1:8787 ──►  quickjumpd  ──► Qt window
 Chrome "Profile 3"  │                              (merge, persist,   (always
 Firefox (optional) ─┘         ◄── activate ──      route, launch)      on top)
```

**Transport: localhost WebSocket, not native messaging.** Native messaging auto-spawns the host, which is its one real advantage. Against it: Chrome spawns *one host process per profile*, so the host would have to be a thin bridge to a singleton daemon anyway — the daemon does not disappear, it just gains a hop. It also needs a host manifest installed per browser directory, and a different manifest dialect for Firefox. A WebSocket is identical code in every Chromium browser and Firefox, with nothing to install per browser.

Costs of that choice, accepted: the daemon must be autostarted (systemd user unit or XDG autostart), and the port needs guarding (§8).

One thing it buys for free: Chrome ≥116 treats WebSocket activity as service-worker activity, so the SW stays alive while connected. That removes the usual MV3 keepalive hack.

**The window belongs to the daemon.** Qt's `WindowStaysOnTopHint` is real always-on-top, so the KWin rule stops being load-bearing and the design becomes portable. PyQt6 6.9.1 is already on this machine.

## 3. State ownership

The split that matters — get this wrong and everything else gets confusing:

| State | Owner | Why |
|---|---|---|
| `tabId`, live `title`, `favIconUrl`, alive/dead | the **profile** that reported it | only that extension can observe or resolve it |
| user **label**, ordering, profile label/colour | the **daemon** | global user intent; must outlive any one browser |
| merged view | the **daemon** | it renders the window |

Each profile owns a *shard*. The daemon holds the shards plus a side-table of user intent keyed by `jumpId`.

Daemon persists to `~/.local/share/quickjump/state.json` (labels, order, profile registry, last-known shards). Survives browser restart, daemon restart, and reboot.

Extensions keep their own `storage.local` copy so the fallback bar (§9) still works with correct labels when the daemon is down.

## 4. Wire protocol

JSON, one object per WebSocket message. `v` is the protocol version; daemon rejects unknown majors.

**Extension → daemon**

```jsonc
{ "t": "hello", "v": 1, "profileId": "uuid", "browser": "chrome",
  "browserVersion": "150.0.7871.128", "extVersion": "0.2.0",
  "accountEmail": "…" }          // optional, see §5

{ "t": "jumps", "jumps": [
    { "jumpId": "uuid", "tabId": 42, "url": "https://…",
      "title": "live page title", "favIconUrl": "https://…", "alive": true }
  ]}

{ "t": "activated", "jumpId": "uuid", "ok": true, "reason": null }
```

**Daemon → extension**

```jsonc
{ "t": "welcome", "v": 1, "profileLabel": "Work", "colour": "#6aa8ff" }
{ "t": "activate", "jumpId": "uuid" }
{ "t": "drop",     "jumpId": "uuid" }    // user removed it from the bar
```

**`jumps` is always a full snapshot, never a delta.** Idempotent, self-healing on reconnect, and trivially correct — at tens of entries the bandwidth argument for deltas does not apply.

`jumpId` is a UUID minted by the extension, so it is globally unique and no composite key is needed on the wire. The daemon still stores `profileId` beside it, for routing and for `$PROFILE`.

**Reconnect:** exponential backoff 1s → 30s, jittered. On reconnect the extension re-sends `hello` + a full `jumps`; the daemon *replaces* that profile's shard wholesale.

## 5. Profile identity

An extension cannot read its own profile directory name. So:

- On first run the extension mints a UUID → `storage.local`. That is `profileId`, stable across restarts.
- The daemon window lets the user label each profile (`Work`, `Personal`) and assigns a colour from a fixed palette. That label is what `$PROFILE` renders.
- **Auto-seeding the label:** with the `identity` permission, `chrome.identity.getProfileUserInfo()` returns the signed-in account email. The daemon can read `~/.config/google-chrome/*/Preferences` → `profile.name` and `account_info[].email`, and correlate. That gives a correct pre-filled label *and* — more importantly — resolves `profileId` → profile **directory**, which §7 needs.

  Trade-off: `identity` is a heavier permission than the current set, and it only works when the profile is signed in. Treat auto-seed as best-effort, always overridable by hand.

## 6. Labels and template variables

### Model

Each jump carries `label: string | null`.

- `label === null` → display the live title, falling back to host, falling back to `Untitled`. Today's behaviour.
- `label` set → it is a **template**, rendered against current values on every change.

**Rename pre-fills the box with the currently rendered text, as a literal.** So the common case — "this title keeps changing under me, pin it" — is just: rename, Enter, done. It is now frozen text. Variables are the opt-in escape hatch for people who want live values back. This is the whole design in one sentence.

### Grammar

```
template := (literal | escape | var)*
escape   := "$$"                                  → literal "$"
var      := "$" NAME | "${" NAME [":-" default] "}"
NAME     := [A-Z][A-Z0-9_]*
```

Uppercase-only names, so ordinary text like `$12.99` or `$total` is never mistaken for a variable. `${…}` exists for adjacency: `${HOST}/stats`.

### Variables

| Variable | Value | Stable? |
|---|---|---|
| `$TITLE` | current page title | **no** — this is the one JS rewrites |
| `$TITLE0` | page title captured when the jump was added | yes |
| `$PROFILE` | owning profile's label | yes |
| `$BROWSER` | `Chrome`, `Firefox`, … | yes |
| `$HOST` | hostname, `www.` stripped | yes |
| `$PATH` | URL path | yes |
| `$URL` | full URL | yes |
| `$SLOT` | 1-based position in the bar | changes on reorder |

`$TITLE0` is the direct answer to "the title may be changed by JS": it pins the title as it was at add time while staying a variable, so it still reads as data rather than as a hand-typed string.

Examples:

```
$PROFILE · $TITLE              →  Work · Daily standup — Google Meet
${PROFILE}: ${TITLE:-$HOST}    →  Work: meet.google.com     (when title is empty)
Standup                        →  Standup                   (plain literal, frozen)
$TITLE0                        →  (3) Slack | eng            (frozen at add time)
```

### Rendering rules

- Unknown variable → rendered **literally** (`$TITLNE` shows as `$TITLNE`), and flagged in the editor. Silently emptying a typo is worse than showing it.
- `${NAME:-default}` supplies the default when the value is empty or missing. The default is itself a template, so `${TITLE:-$HOST}` works.
- If the whole template renders empty → fall back to `$HOST`, then `Untitled`. **A row must never render blank.**
- Re-render on any input change (title, profile label, reorder). Trivially cheap at this scale.

### Editing UX

Double-click a row, or right-click → Rename. Inline edit showing the **raw template**, with the rendered result previewed live beneath. Enter commits, Esc cancels. A "reset to default" clears `label` back to `null`.

### Considered and rejected

- **Truncation syntax** (`${TITLE:40}`) — CSS ellipsis already handles narrow bars. Rejected: syntax cost for no gain.
- **A `clean` filter** to strip notification noise (`(3) `, `● `) — genuinely tempting, since that is half of why titles churn. Rejected *for v1* because it invites a whole filter pipeline (`${TITLE|clean|lower|trim}`). `$TITLE0` plus plain renaming covers the same ground. Revisit if the itch persists.
- **Regex capture from the title** — same reason, much worse.

## 7. Jump routing

1. User clicks a row. Daemon looks up `profileId` for that `jumpId`.
2. **Profile connected** → send `activate`. Extension does `tabs.update({active:true})` + `windows.update({focused:true})`, replies `activated`. On Wayland this still needs focus-stealing prevention off for Chrome — the existing KWin rule (`kde/install-kwin-rules.sh`) already covers it and stays relevant even though the bar's pin rule does not.
3. **Profile not connected** (browser closed) → row is dim. Clicking launches it:
   `google-chrome --profile-directory="Profile 3" <url>`

   This is a capability the current version cannot have: reaching a tab in a profile that is not even running.

   It depends on knowing the profile **directory**, which §5's correlation supplies. **This is the weakest link in the design** — if correlation fails there must be a manual per-profile "launch command" field in the daemon UI. Do not let this block the rest.

4. `activated` with `ok:false` (tab vanished between snapshot and click) → daemon falls back to launching the URL.

## 8. Security

A localhost WebSocket is reachable by any local process *and* by any web page that guesses the port. Both matter.

- Bind `127.0.0.1` only, never `0.0.0.0`.
- **Check `Origin`.** Extension service workers send `Origin: chrome-extension://<id>`; web pages send their own. Allowlist `chrome-extension://` and `moz-extension://` origins, reject the rest. This alone stops the drive-by-website case.
- **Approve new profiles once.** First connection from an unknown `profileId` raises a prompt in the daemon window: *"A Chrome profile wants to join QuickJump — Allow / Deny."* Approved IDs persist. This covers the local-process case and doubles as the profile-labelling moment.
- Daemon state file `0600`.

Origin checking plus first-use approval is proportionate here. A pre-shared token would be stronger, but the extension cannot read a file, so it would have to be pasted by hand into every profile's options page — worse UX for a marginal gain over the two controls above.

## 9. Failure modes

| Situation | Behaviour |
|---|---|
| Daemon not running | Extension falls back to today's in-browser popup bar, showing only that profile's jumps. Keep that code path. |
| Daemon dies while connected | Backoff reconnect; bar reappears on its own. |
| Second daemon started | Fails to bind, logs, exits. |
| Port 8787 taken | Configurable in daemon config *and* extension options; both default to 8787. |
| Browser closed | Shard retained, marked offline, rows dim, click relaunches (§7). |
| Profile never returns | User can evict it from the daemon's profile list, dropping its shard. |

## 10. Phasing

1. **Labels + variables on the current extension.** No daemon. `$PROFILE` renders a self-assigned label from the options page. Ships value immediately, and the template engine is the same module the daemon will later reuse.
2. **Daemon skeleton** — WebSocket server, origin check, approval prompt, merge, `state.json`. No window yet; verify with a CLI dump.
3. **Qt window** — render merged list, drag-reorder, rename, profile dots. Retire the KWin pin rule (keep the focus rule).
4. **Offline profiles** — directory correlation and launch-on-click.
5. **Firefox** — `browser.*` shim, MV3 event-page background, separate manifest. Protocol unchanged. Test flatpak localhost reachability early; it is the one unknown.

Stop after any step and the result is still coherent.

## 11. Open questions

- Does the flatpak Firefox sandbox permit `ws://127.0.0.1`? Untested, and step 5 hinges on it.
- Is `identity` a permission worth adding for profile auto-labelling, or is manual labelling acceptable for four profiles? Manual is probably fine; auto-correlation matters more for §7's launch path than for the label itself.
- Should the daemon own global keyboard shortcuts (jump to slot N from anywhere, not just when Chrome has focus)? It is well positioned to — KGlobalAccel on KDE — and it would be a genuine step up from `chrome.commands`, which only fires when a browser window is focused. Out of scope here, worth its own note.
