#!/usr/bin/env bash
#
# Builds QuickJump_Agent-<version>-x86_64.AppImage into dist/.
#
#   agent/packaging/linux/build-appimage.sh            # in a Docker container (default)
#   agent/packaging/linux/build-appimage.sh --native   # on this machine (what CI does)
#
# The bundle carries its own Python and Qt, so the only thing that decides
# which distros it runs on is the glibc it was built against. Docker builds on
# Ubuntu 22.04 (glibc 2.35): Ubuntu 22.04+, Debian 12+, Fedora 36+, … all work.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE=ubuntu:22.04
PYTHON=3.12

if [[ "${1:-}" != --native ]]; then
  exec docker run --rm \
    -v "$REPO:/src:ro" -v "$REPO/dist:/out" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    "$IMAGE" bash -c '
      set -euo pipefail
      apt-get update -qq
      DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
        ca-certificates curl file binutils libglib2.0-0 libgl1 libegl1 libfontconfig1 libdbus-1-3 \
        libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libwayland-client0 \
        libwayland-cursor0 libwayland-egl1 >/dev/null
      cp -r /src /build && cd /build
      OUT=/out agent/packaging/linux/build-appimage.sh --native
      chown -R "$HOST_UID:$HOST_GID" /out
    '
fi

cd "$REPO"
OUT="${OUT:-$REPO/dist}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VERSION="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" agent/quickjump_agent/__init__.py)"
ARCH="$(uname -m)"

# --- Python + PyInstaller, isolated -------------------------------------------
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$WORK/uv" sh >/dev/null
  export PATH="$WORK/uv:$PATH"
fi
uv venv -q --python "$PYTHON" "$WORK/venv"
uv pip install -q --python "$WORK/venv/bin/python" -r agent/packaging/requirements.txt

"$WORK/venv/bin/pyinstaller" --noconfirm --log-level WARN \
  --distpath "$WORK/dist" --workpath "$WORK/build" agent/packaging/quickjump-agent.spec

# --- AppDir -------------------------------------------------------------------
APPDIR="$WORK/QuickJump_Agent.AppDir"
mkdir -p "$APPDIR/usr/lib"
cp -a "$WORK/dist/quickjump-agent" "$APPDIR/usr/lib/"
install -m 755 agent/packaging/linux/AppRun "$APPDIR/AppRun"
cp icons/128.png "$APPDIR/quickjump-agent.png"
ln -s quickjump-agent.png "$APPDIR/.DirIcon"
cat >"$APPDIR/quickjump-agent.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=QuickJump agent
Comment=One floating QuickJump window for every browser profile
Exec=quickjump-agent
Icon=quickjump-agent
Categories=Utility;
Terminal=false
X-AppImage-Version=$VERSION
EOF

# --- AppImage -----------------------------------------------------------------
# appimagetool from AppImage/appimagetool embeds the static type-2 runtime, so
# the result runs without libfuse2 on the host.
TOOL="$WORK/appimagetool"
curl -LsSf -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
chmod +x "$TOOL"

mkdir -p "$OUT"
TARGET="$OUT/QuickJump_Agent-$VERSION-$ARCH.AppImage"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$TARGET" >/dev/null
echo "Built $TARGET ($(du -h "$TARGET" | cut -f1))"
