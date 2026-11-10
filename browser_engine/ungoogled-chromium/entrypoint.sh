#!/usr/bin/env bash
# ungoogled-chromium 容器入口。
#
# 两种模式，用环境变量 MODE 切：
#   vnc（默认）       Xvfb 虚拟屏 + x11vnc + noVNC，浏览器里能看见实时画面
#   headless          无界面，只开 CDP 端口，给后端 / Playwright 连
#
# 默认走 vnc：这个项目要人工看浏览器界面（验证码、登录、代理连通性），
# 没有画面等于没法用。只想跑自动化时用 MODE=headless 省掉 Xvfb 那套。
#
# 常用环境变量：
#   MODE=vnc|headless        运行模式
#   CDP_PORT=9222            DevTools 端口
#   NOVNC_PORT=6080          noVNC 网页端口（vnc 模式）
#   SCREEN=1920x1080x24      虚拟屏分辨率（vnc 模式）
#   START_URL=about:blank    启动打开的页面
#   CHROME_ARGS=""           追加给 chrome 的原始参数，空格分隔
#   CHROME_NO_SANDBOX=1      容器里默认关沙箱；=0 则保留
set -euo pipefail

CHROME="${CHROME_DIR:-/opt/chromium}/chrome"
MODE="${MODE:-vnc}"
CDP_PORT="${CDP_PORT:-9222}"
# Chrome 自己只肯监听 127.0.0.1，所以它用内部端口，对外由 socat 转发
CDP_INTERNAL_PORT="${CDP_INTERNAL_PORT:-9223}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
SCREEN="${SCREEN:-1920x1080x24}"
START_URL="${START_URL:-about:blank}"
USER_DATA_DIR="${USER_DATA_DIR:-/data/profile}"
DISPLAY_NUM="${DISPLAY_NUM:-99}"

if [ ! -x "$CHROME" ]; then
  echo "找不到可执行的内核：$CHROME" >&2
  exit 1
fi

# 镜像有可能是 WITH_VNC=0 构建的，这时候没有 Xvfb，vnc 模式必须先说清楚原因，
# 否则报错是 "Xvfb: command not found" 这种看不懂的东西
if [ "$MODE" = "vnc" ] && ! command -v Xvfb >/dev/null 2>&1; then
  echo "这个镜像构建时用了 WITH_VNC=0，没有安装 Xvfb/x11vnc/noVNC。" >&2
  echo "要么重新构建（默认 WITH_VNC=1），要么把 MODE 改成 headless 只用 CDP。" >&2
  exit 1
fi

mkdir -p "$USER_DATA_DIR"

# 容器每次重建 hostname 都会变，而 Chromium 会把「谁占着这个 profile」写进
# SingletonLock（内容形如 <hostname>-<pid>）。下次容器起来发现 hostname 对不上，
# 就判定 profile 被另一台机器占用，直接拒绝启动并退出。
# profile 挂在宿主机卷上，这个文件会跨容器残留，所以每次启动前清掉。
# 同一个 volume 不会被两个容器同时挂（compose 里是命名路径 + 固定 container_name），
# 所以这里删是安全的。
rm -f "${USER_DATA_DIR}/SingletonLock" \
      "${USER_DATA_DIR}/SingletonCookie" \
      "${USER_DATA_DIR}/SingletonSocket"

args=(
  # Chromium 143 起不再认 --remote-debugging-address=0.0.0.0，实测 156 也只绑
  # 127.0.0.1。所以这里让它用内部端口，对外由下面 socat 转发到 0.0.0.0。
  "--remote-debugging-address=127.0.0.1"
  "--remote-debugging-port=${CDP_INTERNAL_PORT}"
  "--remote-allow-origins=*"
  "--user-data-dir=${USER_DATA_DIR}"
  "--no-first-run"
  "--no-default-browser-check"
  # 容器 /dev/shm 默认只有 64MB，不关掉这个 Chromium 会随机崩渲染进程
  "--disable-dev-shm-usage"
)

# 容器内通常没有 user namespace，沙箱起不来；默认关掉，需要时用 =0 打开
if [ "${CHROME_NO_SANDBOX:-1}" = "1" ]; then
  args+=("--no-sandbox")
fi

# 附加参数按空格切开。这里故意不加引号：就是要让它支持
# CHROME_ARGS="--lang=zh-CN --proxy-server=socks5://1.2.3.4:1080" 这种写法
# shellcheck disable=SC2206
if [ -n "${CHROME_ARGS:-}" ]; then
  args+=(${CHROME_ARGS})
fi

# ── CDP 端口桥接 ──────────────────────────────────────────────────────
# Chromium 143+ 忽略 --remote-debugging-address，只绑 127.0.0.1，容器外
# （宿主机、后端、别的容器）一律连不上。用 socat 把 0.0.0.0:<对外端口>
# 转到 127.0.0.1:<内部端口>。
#
# 顺带解决两件事：
#   1. socat 是从回环发起连接，天然过了 DevTools 的 Host 头校验；
#   2. /json/version 返回的 webSocketDebuggerUrl 会跟随请求的 Host 头，
#      所以外面拿到的 ws://... 地址是可直接连的（已验证）。
if command -v socat >/dev/null 2>&1; then
  socat "TCP-LISTEN:${CDP_PORT},fork,reuseaddr,bind=0.0.0.0" \
        "TCP:127.0.0.1:${CDP_INTERNAL_PORT}" &
  echo "[entrypoint] CDP 桥接：0.0.0.0:${CDP_PORT} -> 127.0.0.1:${CDP_INTERNAL_PORT}"
else
  echo "[entrypoint] 警告：镜像里没有 socat，CDP 只能在容器内部访问" >&2
fi

case "$MODE" in
  headless)
    args+=("--headless=new")
    echo "[entrypoint] headless 模式"
    exec "$CHROME" "${args[@]}" "$START_URL"
    ;;

  vnc)
    export DISPLAY=":${DISPLAY_NUM}"
    echo "[entrypoint] vnc 模式，屏幕 ${SCREEN}"
    echo "[entrypoint] 看画面：http://<宿主机IP>:${NOVNC_PORT}/vnc.html?autoconnect=1&resize=scale"
    echo "[entrypoint] CDP 端口：0.0.0.0:${CDP_PORT}"

    Xvfb "$DISPLAY" -screen 0 "$SCREEN" -nolisten tcp -ac &
    XVFB_PID=$!
    # 等 X socket 就绪再起 x11vnc，否则第一次连接会失败；
    # 同时盯着 Xvfb 有没有当场退出（多半是 /tmp/.X11-unix 不可写）
    for _ in $(seq 1 50); do
      [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ] && break
      if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "Xvfb 启动失败，检查 /tmp/.X11-unix 是否可写" >&2
        exit 1
      fi
      sleep 0.1
    done

    x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport "$VNC_PORT" -quiet -noxdamage &
    websockify --web=/usr/share/novnc "$NOVNC_PORT" "localhost:${VNC_PORT}" &

    exec "$CHROME" "${args[@]}" "$START_URL"
    ;;

  *)
    echo "MODE 只能是 headless 或 vnc，当前是：${MODE}" >&2
    exit 2
    ;;
esac
