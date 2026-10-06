#!/usr/bin/env bash
#
# Builds dist/QuickJump_Agent-<version>-macos.dmg on a Mac (CI: macos-14).
# Unsigned for now: first launch needs right-click → Open. Signing and
# notarisation need an Apple Developer ID — add them here when there is one.
#
# Status: the build is wired up; global hotkeys on macOS are not implemented
# yet (the tray icon, window, autostart and browser support are).

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"
VERSION="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" agent/quickjump_agent/__init__.py)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q -r agent/packaging/requirements.txt
"$WORK/venv/bin/pyinstaller" --noconfirm --log-level WARN \
  --distpath "$WORK/dist" --workpath "$WORK/build" agent/packaging/quickjump-agent.spec

mkdir -p dist
hdiutil create -quiet -volname "QuickJump Agent" -srcfolder "$WORK/dist/QuickJump Agent.app" \
  -ov -format UDZO "dist/QuickJump_Agent-$VERSION-macos.dmg"
echo "Built dist/QuickJump_Agent-$VERSION-macos.dmg"
