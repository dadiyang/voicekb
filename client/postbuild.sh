#!/bin/bash
# 构建后注入 tabler-icons（绕过 vite CSS unicode 破坏）
DIST="dist/build/h5"
mkdir -p "$DIST/static/fonts"
cp src/static/tabler-icons.css "$DIST/static/"
cp src/static/fonts/tabler-icons.woff2 "$DIST/static/fonts/"
sed -i 's|<meta charset="UTF-8"|<link rel="stylesheet" href="/static/tabler-icons.css">\n    <meta charset="UTF-8"|' "$DIST/index.html"
echo "postbuild: tabler-icons injected"
