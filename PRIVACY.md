# QuickJump — Privacy Policy

*Last updated: 2026-10-13*

QuickJump does not collect, transmit, sell or share any personal data. It has
no analytics, no telemetry, no accounts and no servers.

## What the extension handles

When you add a tab to QuickJump, the extension stores that tab's **URL, title,
favicon URL** and the time it was added, so it can show the entry and jump back
to it. It also stores your QuickJump settings and a random identifier for the
browser profile.

All of this is kept in `chrome.storage.local` on your own computer. It is not
synced to your Google account and is never sent to the developer or to any
third party.

## The optional desktop agent

If you run the optional QuickJump agent, the extension sends the same entries
to it over a local connection to `127.0.0.1` (your own machine — by default
port 8787). The agent stores them in a file in your home directory. Nothing
leaves your computer.

## Call controls on Google Meet and Microsoft Teams

On `meet.google.com`, `teams.microsoft.com`, `teams.live.com` and
`teams.cloud.microsoft` the extension runs a small script that watches the
call's **microphone and camera buttons**, so the bar can show whether you are
muted and let you toggle them without switching to the tab. The script reads
only those two buttons' state (on/off) and clicks them when you ask. It does
not read the meeting's content, participants, chat or anything else on the
page, and it stores nothing beyond that on/off state next to the entry.

## Permissions

- **tabs** — read the title and URL of the tab you add, and find and activate it later.
- **contextMenus** — the *Add to Quick Jump* right-click menu.
- **storage** — keep your list and settings locally.
- **alarms** — periodically check whether the local agent is running.
- **Access to meet.google.com and the Teams sites** — the call controls described above.
- **scripting** — after an install or update, start that same call-controls script in
  Meet and Teams tabs that are already open, so they need no reload.

## Removing your data

Remove an entry with its × button, or uninstall the extension to delete
everything it stored. The agent's data can be removed from its settings
(*Uninstall…*).

## Contact

QuickJump is made by [enloop.md](https://enloop.md).

Questions: open an issue at <https://github.com/enloop-md/quickjump/issues>.
