# QuickJump

*Created by [enloop.md](https://enloop.md).*

Pin the tabs you need to get back to — a call, a doc, a dashboard — into a small
bar that floats above every other window, on every virtual desktop. Click an
entry and Chrome raises that window and activates that tab.

Built for the "I'm on a call, I wandered off into other windows, now I'm being
asked something and can't find the tab" problem.

Two pieces:

- **The QuickJump agent** (`agent/`, recommended) — a small desktop app with
  **one window for every Chrome profile** (and other Chromium browsers running
  the extension), **global hotkeys**, and a **tray icon** that jumps straight
  to the newest item: add the call when it starts, click the tray when it
  needs you.
- **The extension** — feeds the agent. Without the agent it falls back to its
  own per-profile floating bar.

By default both windows **auto-hide**: they disappear while a browser window is
focused (your tabs are right there) and pop back up the moment you switch to
another application.

---

## Install the extension

From the [Chrome Web Store](https://chromewebstore.google.com/detail/ghjpaalofbdajafokhaecblmmaeidhep), or from source:

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. **Load unpacked** → select this directory.

That's it — no build step, no dependencies.

To build the Chrome Web Store zip: `scripts/package-extension.sh` (submission
notes in [store/listing.md](store/listing.md), privacy policy in
[PRIVACY.md](PRIVACY.md)). Website: `site/`, published to
<https://enloop-md.github.io/quickjump/> by `.github/workflows/pages.yml`.

After updating the files, click **⟳** on QuickJump in `chrome://extensions` —
in **every** profile. Its pages pick up new files on their own, but its
background worker does not; the settings page warns when a reload is due.

## The agent

### Install

| | |
|---|---|
| **Linux** (any distro from ~2022 on) | Download `QuickJump_Agent-<version>-x86_64.AppImage`, `chmod +x` it, run it. |
| **macOS** | `QuickJump_Agent-<version>-macos.dmg` — preview, see the status table. |
| **Windows** | `QuickJump_Agent-<version>-windows.zip`, run `quickjump-agent.exe` — preview. |
| **From source** | `python3 agent/quickjump-agent` — needs only PyQt6 (`sudo apt install python3-pyqt6`). |

On first start the agent asks whether to **start at login** (on by default),
and adds itself to the app menu. Both can be changed later in its settings
(⚙); *Uninstall…* there removes everything it added to the desktop (menu
entry, autostart, hotkeys, window rule) — then delete the AppImage. Moving or
replacing the AppImage is fine: the entries are re-pointed on its next start.

Builds come from `.github/workflows/agent.yml` (tag `vX.Y.Z` → draft release).
Locally: `agent/packaging/linux/build-appimage.sh` (in Docker, on Ubuntu 22.04
for glibc compatibility), `agent/packaging/macos/build.sh`,
`agent/packaging/windows/build.ps1`.

### Desktop support

| Desktop | Window above others | Global hotkeys | Tray icon |
|---|---|---|---|
| **KDE Plasma** (Wayland, X11) | KWin rule, added automatically | KGlobalAccel, both styles | yes |
| **GNOME** (Wayland, X11) | yes (runs via XWayland) | written to GNOME's custom shortcuts; single strike | needs the *AppIndicator* extension (Ubuntu ships it) |
| **Cinnamon, Xfce, Budgie** | yes | written to the desktop's custom shortcuts; single strike | yes |
| **MATE, LXQt, other X11 WMs** | yes | bind `quickjump-cmd` yourself (below) | usually |
| **Sway, Hyprland, i3, …** | add a window rule (below) | bind `quickjump-cmd` yourself | with a bar that has a tray |
| **macOS** (preview) | yes | not yet | menu bar |
| **Windows** (preview) | yes | not yet | yes |

*Double strike* (arm key, then a digit) needs the window to take keyboard focus
from a hotkey; only KDE allows that reliably, so elsewhere the default is
*single strike* (one chord per item).

**Binding hotkeys yourself.** The agent installs a small helper,
`~/.local/share/quickjump/quickjump-cmd`, that hands a command to the running
agent in a few milliseconds (or starts it):

```
quickjump-cmd newest | toggle | show | arm | slot N | settings | quit
```

Sway / i3:

```
bindsym Mod1+Shift+r exec ~/.local/share/quickjump/quickjump-cmd newest
bindsym Mod1+Shift+j exec ~/.local/share/quickjump/quickjump-cmd toggle
for_window [class="quickjump-agent"] floating enable, sticky enable, border none
```

Hyprland:

```
bind = ALT SHIFT, R, exec, ~/.local/share/quickjump/quickjump-cmd newest
bind = ALT SHIFT, J, exec, ~/.local/share/quickjump/quickjump-cmd toggle
windowrulev2 = float, pin, noborder, class:^(quickjump-agent)$
```

The same commands work as `quickjump-agent --cmd newest` (slower to start).

### Using it

- **Adding** — *Add to Quick Jump* in any profile goes straight to the agent,
  and its window shows with the new item highlighted. Adding an entry that is
  already listed moves it back to the top.
- **Tray icon** — click: jump to the newest item. Middle-click: show / hide
  the window. Right-click: menu.
- **Profiles** — every item shows its browser profile's name (read from the
  browser's own profile list; rename it in the agent settings). With more than
  one profile, chips on top filter the list; in the window, `Tab` / arrows
  cycle them and `0` shows all.
- **Global hotkeys**, set in the agent settings (and visible in the desktop's
  own keyboard settings, see the table above):

  | Default | Action |
  |---|---|
  | `Alt+Shift+Q`, then `1`–`9` | **double strike**: jump to item N; `Q` again = newest item (the letter is a setting), `Esc` cancels |
  | `Meta+Alt+1`…`9` | **single strike** instead, if chosen in settings |
  | `Alt+Shift+R` | jump to the newest item |
  | `Alt+Shift+J` | show / hide the window |

  Bare `1`–`9` also jump while the window itself is focused (can be switched off).
- **Closed browser** — its items stay, dimmed; clicking one starts that browser
  profile with the URL.
- **Window** — drag the header to move, the side edges to resize. On KDE the
  agent adds a KWin rule (*QuickJump agent window*) on first start that keeps
  it above other windows, on all desktops, out of the taskbar, remembers its
  position, and lets the arm hotkey give it focus.

### How the extension and the agent find each other

The agent listens on `ws://127.0.0.1:8787`, accepting browser extensions only
(the `Origin` header is checked, web pages get a 403). The port can be changed
in the agent settings and in each profile's extension settings; they must
match.

- **Agent never seen** by this profile — the bar shows a small **(i)** that
  explains what the agent adds. On first install, the settings page opens with
  the same note.
- **Agent seen before but not running** — the bar comes back with an alert:
  *Falling back to profile QuickJump. Run the agent for global hotkeys and other
  improvements.*
- **Agent starts** — every profile hands its fallback list over, merged by the
  time each item was added, and the fallback bar closes.

State lives in `~/.local/share/quickjump/state.json`, settings in
`~/.config/quickjump/agent.json` (macOS: `~/Library/Application Support/QuickJump/`,
Windows: `%APPDATA%\QuickJump\`). Protocol and design:
[docs/design-multiprofile.md](docs/design-multiprofile.md).

---

## The fallback bar (no agent)

### Why there are two floating modes

A Chrome extension cannot make a window always-on-top — there is no API for it.
Something outside the extension has to do it, so QuickJump ships both options
and they share the same UI and the same list:

| | Popup-window mode | Picture-in-Picture mode |
|---|---|---|
| How it floats | a KWin rule pins the window | Chrome's Document PiP is natively always-on-top |
| Setup | run one script (KDE only) | none |
| Portability | needs a per-OS equivalent | works on Linux / macOS / Windows |
| Cost | none | one pinned tab must stay open |
| Best for | your KDE 6 desktop | laptops, other machines, other OSes |

Popup-window mode is the better daily driver on KDE. PiP is the fallback that
needs no window-manager cooperation.

---

## Set up the floating bar on KDE (Plasma 6)

```bash
./kde/install-kwin-rules.sh
```

This writes two rules into `~/.config/kwinrulesrc` and reloads KWin:

- **QuickJump floating bar** — any window titled `QuickJump Bar` is forced above
  other windows, shown on all virtual desktops, and hidden from the task
  manager, pager and Alt+Tab. Its position and size are *remembered*, which
  matters on Wayland: a browser cannot place its own windows there, so KWin has
  to be the one that puts the bar back where you left it. The window is also
  drawn **without a titlebar or border**, and KWin is told to ignore Chrome's
  minimum-size hints, so the bar can be shrunk to a sliver. Move it with
  **Meta+drag**, resize with **Meta+right-drag** (KDE defaults). The bar stops
  auto-sizing to its content once you resize it by hand; double-click the
  header (or empty space) to shrink-wrap it again.
- **Let Chrome raise its own windows** — sets focus-stealing prevention to
  *None* for Chrome. Without this, clicking a quick jump switches the tab but
  the browser window does not actually come to the front.

Undo with `./kde/install-kwin-rules.sh --uninstall`, or skip the second rule
with `--no-focus-rule`. Prefer the GUI? Import `kde/quickjump.kwinrule` under
*System Settings → Window Management → Window Rules → Import*.

### Other platforms

The extension itself is platform independent; only the pinning is not.

- **GNOME** — the *Always on Top (Window Switcher)* extension, or set it
  per-window from the titlebar menu.
- **Windows** — [PowerToys](https://github.com/microsoft/PowerToys) *Always On
  Top* (Win+Ctrl+T), or an AutoHotkey `WinSet, AlwaysOnTop`.
- **macOS** — no clean equivalent; use PiP mode.

Or just use PiP mode everywhere and skip all of this.

---

## Using it

- **Add a tab** — right-click anywhere on a page → **Add to Quick Jump**.
  Right-clicking a link offers **Add link to Quick Jump**, which stores a link
  you have not opened yet.
- **Jump** — click an entry. Chrome activates the tab, un-minimises its window
  and raises it.
- **Remove** — hover an entry and click ×, or middle-click it.
- **Reorder** — drag entries.
- **Show the bar** — toolbar icon → *Floating bar*, or right-click → *Show Quick
  Jump bar*.
- **Float it above everything (PiP)** — toolbar icon → *Always on top (PiP)*,
  then press **Float the bar** on the pinned tab that opens.

### No keyboard shortcuts in the extension

Keyboard shortcuts live in the agent only. The extension deliberately declares
no Chrome commands: on Wayland, Chrome hands every extension command to the
desktop's global-shortcuts portal, and KDE then asks for approval in a
*Global shortcuts requested* dialog each time the extension reloads.

### Settings

Open with the ⚙ button in the bar header or toolbar popup, or via
`chrome://extensions` → QuickJump → *Extension options*:

- **Agent port** — and whether the agent is connected right now.
- **Auto-hide** for the fallback bar.
- **Put new items at the top of the list** (on by default) — new jumps land at
  the top instead of the bottom.

### When a pinned tab gets closed

The entry stays, dimmed and italic. Clicking it reopens the URL in a new tab.
QuickJump also re-finds tabs by URL, so entries survive a browser restart even
though tab IDs do not.

---

## Layout

```
manifest.json              MV3 manifest, permissions, keyboard commands
background.js              service worker: context menu, jump logic, window management
lib/store.js               the jump list in chrome.storage.local
lib/agent.js               WebSocket link to the agent
overlay/overlay.js         the bar UI — shared by all three hosts
overlay/overlay.html       popup-window host (title drives the KWin rule)
overlay/standalone.js      shrink-wraps the popup window around its content
hub/                       pinned tab that owns the Picture-in-Picture window
popup/                     toolbar-button popup
settings/                  options page: auto-hide, list order
kde/install-kwin-rules.sh  KWin rule installer / uninstaller
kde/quickjump.kwinrule     same rules, importable from System Settings
agent/quickjump-agent      the agent's launcher (run from source)
agent/quickjump_agent/     the agent (PyQt6): server, merge, window, tray, hotkeys
agent/packaging/           PyInstaller recipe; AppImage, macOS and Windows builds
.github/workflows/agent.yml  CI builds and releases of the agent
```

`overlay/overlay.js` renders into any element. In PiP mode that element is
physically moved into the PiP document while the script keeps running in the
hub page's realm, so every listener stays bound and nothing is re-created.

## Known limits

- **PiP needs its tab.** Closing or navigating the pinned hub tab closes the
  floating window. Chrome allows only one PiP window at a time, browser-wide.
- **Wayland ignores requested window positions.** The KWin rule's *remember*
  setting covers this in popup mode; in PiP mode Chrome handles placement.
- **Raising windows depends on the compositor.** If a jump switches the tab but
  does not bring Chrome forward, the focus-stealing rule is missing — rerun the
  installer without `--no-focus-rule`.
- Chrome does not show context menus on `chrome://` pages, so those cannot be
  added by right-click. Use the **+** button in the bar.

## License

[MIT](LICENSE). Release builds of the agent bundle PyQt6, which is GPLv3.
