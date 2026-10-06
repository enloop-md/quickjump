#!/usr/bin/env bash
# Rebuild the store screenshots (1280×800) and the website images from the
# real extension and agent UI, filled with mock-data.js. Needs google-chrome,
# PyQt6 and ImageMagick.
#   store/screenshots/out/*.png  → Chrome Web Store
#   site/img/*.png               → website
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="$here/out"
port=8765
mkdir -p "$out" "$root/site/img"

python3 -m http.server "$port" --bind 127.0.0.1 --directory "$root" >/dev/null 2>&1 &
server=$!
trap 'kill $server' EXIT
sleep 1

# The agent window, rendered by the agent's own Qt code.
export QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2
python3 "$here/agent_window.py" "$out/agent-window.png" dark 2>/dev/null
python3 "$here/agent_window.py" "$out/agent-window-armed.png" dark armed 2>/dev/null
python3 "$here/agent_window.py" "$out/agent-window-light.png" light 2>/dev/null

shot() { # url width height scale file
  google-chrome --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=4000 \
    --force-device-scale-factor="$4" --window-size="$2,$3" --screenshot="$5" "$1" 2>/dev/null
}

for scene in "$here"/scenes/*.html; do
  name="$(basename "$scene" .html)"
  shot "http://127.0.0.1:$port/store/screenshots/scenes/$name.html" 960 600 1.3333333 "$out/$name.png"
  magick "$out/$name.png" -resize '1280x800!' -alpha off "$out/$name.png"
done

# The bare extension bar, for the website.
shot "http://127.0.0.1:$port/store/screenshots/harness.html?view=bar&agent=none&n=5&hover=j1" 290 182 2 "$out/bar.png"

cp "$out"/[0-9]-*.png "$out/agent-window.png" "$out/bar.png" "$root/site/img/"
ls -1 "$out"
