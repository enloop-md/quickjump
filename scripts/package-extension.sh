#!/usr/bin/env bash
# Zip the extension for the Chrome Web Store: only the files Chrome loads,
# named after the manifest version. Output: dist/quickjump-extension-<version>.zip
set -euo pipefail
cd "$(dirname "$0")/.."

version=$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
out="dist/quickjump-extension-$version.zip"

mkdir -p dist
rm -f "$out"
zip -qr -X "$out" manifest.json background.js lib popup overlay hub settings icons \
  -x '*.DS_Store' '*~'
echo "$out"
unzip -l "$out" | tail -1
