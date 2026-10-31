#!/usr/bin/env bash
# 一键启动 WebWeaver 开发环境：后端 FastAPI(8010) + 前端 Vite(5173)。
#
# 用法（在 WorkBuddy 右侧终端 / 任意 Git Bash 里，项目根目录执行）：
#   bash scripts/dev.sh
#
# 为什么不用 `bun scripts/dev.mjs`：本机 bun / node 只装在 WorkBuddy 自带的
# binaries 目录里，普通 Git Bash 的 PATH 找不到它们（会报 bun: command not found）。
# 这个脚本自己把运行时目录补进 PATH，找不到就退回 node 直接跑 vite。
#
# 日志带前缀：[api] 后端，[web] 前端。Ctrl+C 会把两个进程一起收掉。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

# Windows 控制台默认 GBK：Python 输出中文经过管道到 UTF-8 终端会变成「□□□」。
# 这两个变量让子进程从解释器启动起就用 UTF-8（后端代码里也有一层兜底）。
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export LANG="${LANG:-zh_CN.UTF-8}"

API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-5173}"

# ── 1. 找运行时 ────────────────────────────────────────────
# WorkBuddy 自带的 node/bun 目录（版本号会变，取最新的一个）
WT_BIN=""
for dir in "$HOME"/.workbuddy/binaries/node/versions/*/; do
  [ -d "$dir" ] || continue
  WT_BIN="${dir%/}"
done
if [ -n "$WT_BIN" ] && [ -x "$WT_BIN/node" ]; then
  case ":$PATH:" in
    *":$WT_BIN:"*) ;;
    *) PATH="$WT_BIN:$PATH" ;;
  esac
fi

UV="${UV:-C:/Users/Demon/.local/bin/uv.exe}"
if [ ! -x "$UV" ]; then
  UV="$(command -v uv || true)"
fi
if [ -z "$UV" ] || [ ! -x "$UV" ]; then
  echo "× 找不到 uv（试过 C:/Users/Demon/.local/bin/uv.exe 和 PATH）"
  exit 1
fi

if command -v bun >/dev/null 2>&1; then
  WEB_RUNNER="bun run dev"
elif command -v node >/dev/null 2>&1; then
  WEB_RUNNER="node node_modules/vite/bin/vite.js"
else
  echo "× 找不到 bun 或 node，无法启动前端"
  echo "  试试把运行时目录加进 PATH：export PATH=\"\$HOME/.workbuddy/binaries/node/versions/22.22.2-6:\$PATH\""
  exit 1
fi

# ── 2. 端口占用检查（避免静默起在别的端口）────────────────
port_pid() {
  netstat -ano 2>/dev/null | awk -v p=":$1" '$0 ~ p && /LISTENING/ {print $NF; exit}'
}

busy=()
for port in "$API_PORT" "$WEB_PORT"; do
  pid="$(port_pid "$port")"
  if [ -n "${pid:-}" ] && [ "$pid" != "0" ]; then
    busy+=("$port(PID $pid)")
  fi
done
if [ ${#busy[@]} -gt 0 ]; then
  echo
  echo "× 端口已被占用：${busy[*]}"
  echo "  先结束占用进程：taskkill //PID <PID> //T //F"
  echo "  或者换端口启动：API_PORT=8020 WEB_PORT=5180 bash scripts/dev.sh"
  echo
  exit 1
fi

# ── 3. 收尾：按端口找 Windows 进程树强杀 ──────────────────
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "正在停止前后端…"
  for port in "$API_PORT" "$WEB_PORT"; do
    pid="$(port_pid "$port")"
    if [ -n "${pid:-}" ] && [ "$pid" != "0" ]; then
      taskkill //PID "$pid" //T //F >/dev/null 2>&1
    fi
  done
  exit 0
}
trap cleanup INT TERM EXIT

# ── 4. 启动 ────────────────────────────────────────────────
echo "▶ 后端  FastAPI  http://127.0.0.1:$API_PORT   （--reload：改后端代码自动重载）"
echo "▶ 前端  Vite     http://127.0.0.1:$WEB_PORT   （$WEB_RUNNER）"
echo "  Ctrl+C 一次停掉两个服务，日志在下方实时输出。"
echo

(
  cd "$ROOT/backend" || exit 1
  "$UV" run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --reload 2>&1 |
    sed -u 's/^/[api] /'
) &
API_JOB=$!

(
  cd "$ROOT/frontend" || exit 1
  $WEB_RUNNER 2>&1 | sed -u 's/^/[web] /'
) &
WEB_JOB=$!

# 任意一个挂掉就整体退出（不留半套服务）
wait -n "$API_JOB" "$WEB_JOB" 2>/dev/null
echo
echo "有一个服务已退出，正在停掉另一个…"
cleanup
