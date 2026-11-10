#!/usr/bin/env bash
# 从本机 Windows 的 C:\Windows\Fonts 收集 CloakBrowser 需要的字体，放进 ./fonts/，
# 供 Dockerfile 打进镜像。
#
# 为什么需要这一步：CloakBrowser 在 Linux 容器里默认伪装成 Windows
# （--fingerprint-platform=windows），但字体是内核从宿主系统字体渲染出来的。
# 真实 Windows 上有 Segoe UI / Calibri / Consolas / Marlett 这些微软专有字体，
# 国产 Linux 镜像里一个都没有，字体指纹（画 canvas 量宽度、枚举 font-family）
# 一问就露馅。官方 README 也明确说 apt 的 ttf-mscorefonts-installer 不够用 ——
# 它只有 XP 那批（Arial / Times / Verdana），缺的正是最关键的这几个。
#
# 用法（在本目录执行）：
#   ./collect-windows-fonts.sh                    # 默认从 /c/Windows/Fonts 取
#   ./collect-windows-fonts.sh /d/Fonts-backup    # 从别处取
#
# 字体是微软的专有资产：自己用没问题，**不要提交到仓库、不要随镜像分发**。
# fonts/ 已经在 .gitignore 里了。
set -euo pipefail

CDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${1:-/c/Windows/Fonts}"
DST="${CDIR}/fonts"

if [ ! -d "$SRC" ]; then
  echo "找不到字体源目录：$SRC" >&2
  echo "Windows 上一般就是 /c/Windows/Fonts（Git Bash 的写法）。" >&2
  exit 1
fi

mkdir -p "$DST"

# 文件名 pattern。用通配而不是精确文件名，是因为不同 Windows 版本的字重
# 文件名不完全一样（比如 Segoe UI Semilight 有的机器叫 seguisli、有的是 seguisel）。
PATTERNS=(
  # Segoe UI 全家族 —— CloakBrowser 的 8 个探针里占了两个
  "segoeui*.ttf"
  # Segoe UI Symbol / Emoji，emoji 哈希检测要用
  "seguisym.ttf" "seguiemj.ttf"
  # Calibri 全家族
  "calibri*.ttf"
  # Marlett：Windows 用于窗口按钮符号的字体，Linux 上完全没有替代品
  "marlett.ttf"
  # MS UI Gothic：日文，算在 Windows 标配里
  "msgothic.ttc"
  # Franklin Gothic Medium
  "framd*.ttf"
  # Consolas 等宽 —— 8 个探针之一，也是 monospace 家族在 Windows 上的落点
  "consola*.ttf"
  # Courier New 等宽
  "cour*.ttf"
  # Arial / Times New Roman / Verdana / Tahoma / Georgia：最常见的 font-family，
  # 少一个，页面排版就和其他机器长得不一样
  "arial*.ttf" "times*.ttf" "verdana*.ttf" "tahoma*.ttf" "georgia*.ttf"
  "trebuc*.ttf" "impact.ttf" "comic*.ttf" "pala*.ttf" "book*.ttf"
  # 其它常在默认字体栈里的
  "micross.ttf" "symbol.ttf" "wingding.ttf" "lucon.ttf"
  "candara*.ttf" "corbel*.ttf" "constan*.ttf" "cambria*.ttf" "cambriab.ttf"
  "segoepr.ttf" "segoesc.ttf"
)

copied=0
for pat in "${PATTERNS[@]}"; do
  # 用 nullglob 语义：没有匹配就跳过，不要报错
  for f in "$SRC"/$pat; do
    [ -e "$f" ] || continue
    base="$(basename "$f")"
    if [ ! -e "$DST/$base" ]; then
      cp -f "$f" "$DST/$base"
      copied=$((copied + 1))
    fi
  done
done

# ── 验收：CloakBrowser 真正会去查的那 8 个探针 ──────────────────────
# 对应 cloakbrowser/browser.py 的 _WINDOWS_FONT_TELLS，缺一个都会一直告警。
check() {
  local file="$1" name="$2"
  if [ -e "$DST/$file" ]; then
    printf '  [ok]   %-16s %s\n' "$name" "$file"
    return 0
  fi
  printf '  [缺失] %-16s %s\n' "$name" "$file"
  return 1
}

echo
echo "字体已复制到：$DST（本次新增 ${copied} 个文件）"
echo
echo "CloakBrowser 的 8 个字体探针："
missing=0
check "segoeui.ttf"   "Segoe UI"        || missing=$((missing + 1))
check "segoeuil.ttf"  "Segoe UI Light"  || missing=$((missing + 1))
check "calibri.ttf"   "Calibri"         || missing=$((missing + 1))
check "marlett.ttf"   "Marlett"         || missing=$((missing + 1))
check "msgothic.ttc"  "MS UI Gothic"    || missing=$((missing + 1))
check "framd.ttf"     "Franklin Gothic" || missing=$((missing + 1))
check "consola.ttf"   "Consolas"        || missing=$((missing + 1))
check "cour.ttf"      "Courier New"     || missing=$((missing + 1))

total=$(du -sh "$DST" 2>/dev/null | cut -f1)
echo
echo "目录体积：${total}｜总文件数：$(find "$DST" -type f | wc -l | tr -d ' ')"

if [ "$missing" -gt 0 ]; then
  echo
  echo "有 ${missing} 个探针字体没找到。多数情况是这台机器真的没装（比如某些 Windows N 版），"
  echo "可以继续构建，只是字体指纹会缺这几项；也可以从别的 Windows 机器上把它们拷过来。"
  exit 0
fi

echo
echo "8 个探针全部就位，可以构建镜像了：docker compose up -d --build"
