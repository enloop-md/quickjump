# Chrome Web Store submission — QuickJump

Everything the Developer Dashboard asks for, ready to paste.
Package: `scripts/package-extension.sh` → `dist/quickjump-extension-<version>.zip`.

## Store listing

**Name:** QuickJump

**Summary** (≤132 chars, from manifest):
Pin tabs to an always-on-top floating bar and jump back to them with one click.

**Category:** Productivity → Tools · **Language:** English

**Description:**

On a call, wandered off into other windows, and now someone asks you something
and you can't find the tab? QuickJump keeps the tabs you need to get back to —
a call, a doc, a dashboard — in a small bar that floats above your other
windows. Click an entry and Chrome raises that window and activates that tab.

• Right-click any page → "Add to Quick Jump". Right-click a link to save it
  without opening it.
• Click an entry to jump: the tab is activated and its window un-minimised and
  raised.
• Drag to reorder, × or middle-click to remove.
• Entries survive closed tabs and browser restarts — a closed one reopens its URL.
• Floats above other windows via Chrome's Picture-in-Picture, with no setup.
• Auto-hides while Chrome is focused and comes back when you switch apps.

Optional desktop agent (free, open source): one shared window for every Chrome
profile and Chromium browser, global hotkeys, and a tray icon that jumps to the
newest item. Linux, with macOS and Windows previews:
https://github.com/ryabenko-pro/quickjump

Private by design: no accounts, no analytics, no servers. Your list stays in
your browser and, if you use the agent, on your own computer.

**Homepage / support URL:** https://github.com/ryabenko-pro/quickjump
**Privacy policy URL:** https://github.com/ryabenko-pro/quickjump/blob/main/PRIVACY.md

## Graphic assets

| Asset | Size | File |
|---|---|---|
| Store icon | 128×128 | `icons/128.png` |
| Small promo tile (required) | 440×280 | `store/promo-small-440x280.png` |
| Screenshots (1 required, up to 5) | 1280×800 or 640×400 | **to do** — take them from the real bar |

Suggested screenshots: the floating bar over another app with a few entries;
the right-click "Add to Quick Jump" menu; the agent window with profile chips;
the settings page.

## Privacy practices tab

**Single purpose:**
Keep a short list of tabs the user picked and switch back to any of them with
one click from a floating bar.

**Permission justifications:**

- **tabs** — Read the URL, title and favicon of the tab the user adds, find
  that tab again later (also by URL after a restart), and activate it.
- **contextMenus** — Provides the "Add to Quick Jump", "Add link to Quick Jump"
  and "Show Quick Jump bar" right-click entries, the main way to add items.
- **storage** — Stores the user's list and settings locally in
  chrome.storage.local.
- **alarms** — A 30-second alarm re-checks whether the optional local desktop
  agent (127.0.0.1) is running and reconnects to it, since the service worker
  may be suspended between attempts.

**Remote code:** No. All JavaScript is in the package; no eval, no remote scripts.

**Data usage:** Tick **Web history** only (the URLs and titles of the tabs the
user adds). Certify all three:
- not sold or transferred to third parties outside the approved use cases,
- not used for purposes unrelated to the single purpose,
- not used for creditworthiness or lending.

Note for reviewers (if asked): the extension connects only to
`ws://127.0.0.1:8787` / `http://127.0.0.1:8787` — the user's own optional
desktop agent. No external network requests.

## Before each upload

1. Bump `version` in `manifest.json` (the store rejects a version it has seen).
2. `scripts/package-extension.sh`
3. Load the zip's contents unpacked in a clean profile and smoke-test.
