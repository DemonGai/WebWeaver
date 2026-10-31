#!/usr/bin/env bash
# 拉 aria2c 到 backend/bin/。
#
# 为什么需要它：内核包 500MB 起，单条连接会被限速到 ~30 KB/s（直连、走代理、
# 走加速站实测都一样），536MB 要 5 小时，页面上看起来就是卡死。aria2 开 16 条
# 连接后同一文件能到 400~800 KB/s，20 分钟量级。
#
# 后端找不到 aria2c 时会自动退回单连接（慢，但能跑），所以这个脚本是可选的。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/backend/bin"
VERSION="${ARIA2_VERSION:-1.37.0}"

if [[ -x "$DEST/aria2c.exe" || -x "$DEST/aria2c" ]]; then
  echo "aria2c 已存在：$DEST"
  exit 0
fi

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) ASSET="aria2-$VERSION-win-64bit-build1.zip" ;;
  Darwin) ASSET="aria2-$VERSION-osx-darwin.zip" ;;
  *) ASSET="aria2-$VERSION-x86_64-linux.tar.gz" ;;
esac

URL="https://github.com/aria2/aria2/releases/download/release-$VERSION/$ASSET"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$DEST"
echo "下载 $ASSET …"
curl -fsSL --retry 3 -o "$TMP/$ASSET" "$URL"

case "$ASSET" in
  *.zip) unzip -q "$TMP/$ASSET" -d "$TMP/x" ;;
  *) tar -xzf "$TMP/$ASSET" -C "$TMP/x" ;;
esac

BIN="$(find "$TMP/x" -type f \( -name 'aria2c.exe' -o -name 'aria2c' \) | head -1)"
if [[ -z "$BIN" ]]; then
  echo "解压后没找到 aria2c，安装包结构可能变了" >&2
  exit 1
fi
cp "$BIN" "$DEST/"
cp "$(dirname "$BIN")/COPYING" "$DEST/aria2-COPYING.txt" 2>/dev/null || true
chmod +x "$DEST/$(basename "$BIN")" 2>/dev/null || true
echo "已安装：$DEST/$(basename "$BIN")"
