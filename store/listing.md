# Chrome Web Store submission — QuickJump

Extension ID `ghjpaalofbdajafokhaecblmmaeidhep` · listing: https://chromewebstore.google.com/detail/ghjpaalofbdajafokhaecblmmaeidhep

Every text field the Developer Dashboard asks for, in dashboard order, ready to
paste. Package: `scripts/package-extension.sh` →
`dist/quickjump-extension-<version>.zip`.

---

## 1. Package

**Name** and **Summary** come from `manifest.json`:

- Name: `QuickJump – Return instantly to important tab from any app or screen`
- Summary (≤132 chars): `Pin tabs to an always-on-top floating bar and jump back to them with one click.`

---

## 2. Store listing

### Description (plain text, ≤16,000 chars)

```
On a call, you wander off into other windows, someone asks you a question, and the meeting tab is nowhere to be found. QuickJump fixes that.

Pin the tabs you need to get back to (a call, a doc, a dashboard, a ticket) to a small bar that floats above your other windows. Click an entry and Chrome raises that window and switches to that tab, even when it is minimised or on another desktop.

HOW IT WORKS
• Right-click any page and choose "Add to Quick Jump". Right-click a link to save it without opening it.
• Click an entry to jump straight to it.
• Drag entries to reorder them. Remove one with × or a middle-click.
• Closed a pinned tab? The entry stays (dimmed) and reopens its page with one click. Entries also survive a browser restart.
• The bar floats above other apps using Chrome's Picture-in-Picture, with no setup needed.
• Auto-hide: the bar stays out of the way while Chrome is focused and comes back as soon as you switch to another app.

OPTIONAL DESKTOP AGENT
The free, open-source QuickJump agent adds:
• one shared window for every Chrome profile and other Chromium browsers,
• global keyboard shortcuts to jump to any item from any app,
• a tray icon that jumps straight to the newest item,
• starting a closed browser profile right at the saved page.
Linux is fully supported; macOS and Windows builds are in preview. Download: https://github.com/enloop-md/quickjump

PRIVATE BY DESIGN
No account, no analytics, no servers. Your list stays in your browser. If you use the agent, the extension talks only to it, on your own computer (127.0.0.1). The code is open source under the MIT license.

Created by enloop.md: https://enloop.md
```

### Category / Language

- Category: **Productivity → Tools** (Workflow & Planning also fits)
- Language: **English**

### Graphic assets

| Asset | Size | File |
|---|---|---|
| Store icon | 128×128 | `icons/128.png` |
| Screenshots (≥1, up to 5) | 1280×800 | `store/screenshots/out/1-floating-bar.png`, `2-add-from-menu.png`, `3-agent.png`, `4-popup.png` |
| Small promo tile | 440×280 | `store/promo-small-440x280.png` |
| Marquee promo tile (optional) | 1400×560 | not needed |

The screenshots show the real extension and agent UI with mocked data
(`store/screenshots/mock-data.js`). Rebuild them after a UI change with
`store/screenshots/render.sh`, which also refreshes `site/img/`.

### Additional fields

- Official URL: *none* (needs a verified domain in Search Console)
- Homepage URL: `https://enloop-md.github.io/quickjump/`
- Support URL: `https://github.com/enloop-md/quickjump/issues`
- Mature content: **No**

---

## 3. Privacy practices

### Single purpose description (≤1,000 chars)

```
QuickJump keeps a short list of browser tabs the user has chosen and lets them switch back to any of those tabs with one click from a floating bar.
```

### Permission justifications

**tabs**
```
Needed to read the URL, title and favicon of the tab the user adds to QuickJump, to find that tab again later (by tab ID, or by URL after a browser restart), and to activate it and focus its window when the user clicks the entry.
```

**contextMenus**
```
Adds the right-click menu entries "Add to Quick Jump", "Add link to Quick Jump" and "Show Quick Jump bar", which are the main way users add pages and open the bar.
```

**storage**
```
Stores the user's list of pinned tabs and their QuickJump settings locally in chrome.storage.local, so they persist across browser restarts. Nothing is synced or sent anywhere.
```

**alarms**
```
A periodic alarm (every 30 seconds) checks whether the user's optional QuickJump desktop agent is running on their own computer (127.0.0.1) and reconnects to it. An alarm is used because the service worker can be suspended between attempts.
```

**Host permissions:** none requested.

### Remote code

Select **No, I am not using remote code**. All JavaScript ships in the package;
there are no remote scripts, no `eval` and no `new Function`.

### Data usage

What user data do you plan to collect from users now or in the future?

- [ ] Personally identifiable information
- [ ] Health information
- [ ] Financial and payment information
- [ ] Authentication information
- [ ] Personal communications
- [ ] Location
- [x] **Web history**: the URLs and titles of the tabs the user explicitly adds (stored only on the device)
- [ ] User activity
- [ ] Website content

Certify all three:

- [x] I do not sell or transfer user data to third parties, outside of the approved use cases
- [x] I do not use or transfer user data for purposes that are unrelated to my item's single purpose
- [x] I do not use or transfer user data to determine creditworthiness or for lending purposes

### Privacy policy URL

```
https://github.com/enloop-md/quickjump/blob/main/PRIVACY.md
```

---

## 4. Distribution

- Payments: **Free**
- Visibility: **Public**
- Regions: **All regions**

---

## 5. Test instructions (for the reviewer)

Username / password: *leave empty, no login.*

Additional instructions:
```
No account or setup is needed.

1. Open any web page, right-click it and choose "Add to Quick Jump".
2. Click the QuickJump toolbar icon. The popup lists the page; click it to jump to that tab from any other tab or window.
3. Toolbar icon → "Floating bar" opens the bar as a small window. "Always on top (PiP)" opens a pinned tab; press "Float the bar" there to float it above other windows.

The extension tries to connect to an optional companion desktop app at ws://127.0.0.1:8787 (the user's own computer). When the app is not installed, the connection fails silently and the extension works on its own. It makes no other network requests.
```

---

## Before each upload

1. Bump `version` in `manifest.json` (the store rejects a version it has already seen).
2. Run `scripts/package-extension.sh`.
3. Unzip into a clean profile, load it unpacked and smoke-test it.
