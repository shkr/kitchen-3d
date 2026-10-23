#!/bin/sh
# Rebuild the self-contained viewer and push it to GitHub Pages (https://shkr.github.io/kitchen-3d/).
set -e
cd "$(dirname "$0")/.."
python3 web/build.py
tmp=$(mktemp -d)
git clone -q https://github.com/shkr/kitchen-3d.git "$tmp"
python3 - "$tmp/index.html" <<'PY'
import sys
s = open("out/kitchen-viewer.html").read()   # artifact pages get their skeleton at publish time; a plain host needs it
open(sys.argv[1], "w").write(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
    'body{margin:0;font:14px system-ui,sans-serif}[hidden]{display:none!important}</style>\n'
    '</head>\n<body>\n' + s + '\n</body>\n</html>\n')
PY
git -C "$tmp" commit -qam "${1:-Update kitchen model}"
git -C "$tmp" push -q
rm -rf "$tmp"
echo "pushed to https://shkr.github.io/kitchen-3d/"
