#!/usr/bin/env bash
# CloakBrowser 容器入口。
#
# 两种模式，用环境变量 MODE 切：
#   vnc（默认）       Xvfb 虚拟屏 + x11vnc + noVNC，浏览器里能看见实时画面
#   headless          无界面，只开 CDP 端口，给后端 / Playwright 连
#
# 默认走 vnc：这个项目要人工看浏览器界面（验证码、登录、代理连通性），
# 没有画面等于没法用。只想跑自动化时用 MODE=headless 省掉 Xvfb 那套。
#
# ── 指纹是动态的 ────────────────────────────────────────────────────
# 镜像里不烤任何指纹。指纹在容器启动时装配，三种来源按优先级：
#
#   1. 环境变量      FINGERPRINT_SEED / FINGERPRINT_PLATFORM /
#                    FINGERPRINT_TIMEZONE / FINGERPRINT_LOCALE /
#                    FINGERPRINT_WEBRTC_IP / FINGERPRINT_LANG
#   2. 指纹文件      FINGERPRINT_FILE（默认 /data/fingerprint.json）
#                    后端按画像挂一份进来即可，字段见 fingerprint.example.json
#   3. profile 里上次用的种子（保证重启后人格不变）
#   4. 都没有 → 随机一个
#
# 后端要按画像下发指纹，只需要写 /data/fingerprint.json 再重启容器，
# 或者直接把上面几个环境变量传进来。
#
# 常用环境变量：
#   MODE=vnc|headless        运行模式
#   CDP_PORT=9222            DevTools 端口
#   NOVNC_PORT=6080          noVNC 网页端口（vnc 模式）
#   SCREEN=1920x1080x24      虚拟屏分辨率（vnc 模式）
#   START_URL=about:blank    启动打开的页面
#   CHROME_ARGS=""           追加给 chrome 的原始参数，空格分隔
set -euo pipefail

CHROME="${CHROME_DIR:-/opt/cloakbrowser}/chrome"
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
FINGERPRINT_FILE="${FINGERPRINT_FILE:-/data/fingerprint.json}"
SEED_FILE="${USER_DATA_DIR}/.fingerprint-seed"

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

# ── 指纹装配 ────────────────────────────────────────────────────────
# 读指纹文件里的一个字段；文件不存在 / 不是 JSON / 字段缺失都返回空串，
# 由调用方继续往下兜。
#
# 镜像里装了 jq，正常走 jq 分支。但这里必须留一条不依赖 jq 的路径：
# 指纹是"静默生效"的东西，解析失败如果直接回落成随机种子，表面上一切正常、
# 实际上每个人格都错位了，排查起来极其困难。所以没有 jq 时用扁平正则兜底，
# 并且明确告警 —— 宁可吵，也不要悄悄跑歪。
fget() {
  local key="$1"
  [ -f "$FINGERPRINT_FILE" ] || { echo ""; return 0; }

  if command -v jq >/dev/null 2>&1; then
    jq -r --arg k "$key" \
      'if type == "object" and has($k) and (.[$k] != null) then (.[$k] | tostring) else "" end' \
      "$FINGERPRINT_FILE" 2>/dev/null || echo ""
    return 0
  fi

  # 兜底：只认顶层的 "key": "value" / "key": 123，够用（我们的契约是扁平的）
  sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"?([^\"#,}]*)\"?.*/\1/p" \
    "$FINGERPRINT_FILE" 2>/dev/null | head -1 | sed -E 's/[[:space:]]+$//' | tr -d '\r'
}

# 种子必须是 10000..99999 的整数（CloakBrowser 的 SEED_MIN/SEED_MAX），
# 离线算出来的越界值一律当无效处理，避免把坏数据传进内核
valid_seed() {
  case "${1:-}" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$1" -ge 10000 ] && [ "$1" -le 99999 ]
}

# 先只从文件里取一遍，用来判断"文件到底有没有给出有效指纹"
F_SEED="$(fget seed)"
F_PLATFORM="$(fget platform)"
F_TZ="$(fget timezone)"
F_LOCALE="$(fget locale)"
F_LANG="$(fget lang)"
F_WEBRTC="$(fget webrtc_ip)"

# 指纹文件在那儿、但没给出任何有效字段 —— 几乎一定是格式问题（不是 JSON、
# 或者字段嵌在子对象里）。这比"没提供指纹"危险得多：不说的话就是静默跑随机人格。
if [ -f "$FINGERPRINT_FILE" ]; then
  file_ok=0
  valid_seed "$F_SEED" && file_ok=1
  [ -n "${F_PLATFORM}${F_TZ}${F_LOCALE}${F_LANG}${F_WEBRTC}" ] && file_ok=1
  if [ "$file_ok" = "0" ]; then
    echo "[entrypoint] 警告：$FINGERPRINT_FILE 存在但没解析出任何有效指纹字段。" >&2
    echo "[entrypoint] 检查它是否是合法 JSON，且字段在顶层：seed / platform / timezone / locale / lang / webrtc_ip。" >&2
  fi
fi

# 环境变量 > 文件
SEED="${FINGERPRINT_SEED:-$F_SEED}"
PLATFORM="${FINGERPRINT_PLATFORM:-$F_PLATFORM}"
FP_TZ="${FINGERPRINT_TIMEZONE:-$F_TZ}"
FP_LOCALE="${FINGERPRINT_LOCALE:-$F_LOCALE}"
FP_LANG="${FINGERPRINT_LANG:-$F_LANG}"
WEBRTC_IP="${FINGERPRINT_WEBRTC_IP:-$F_WEBRTC}"

if valid_seed "$SEED"; then
  SEED_SOURCE="外部下发（环境变量或指纹文件）"
elif [ -s "$SEED_FILE" ] && valid_seed "$(tr -d '[:space:]' < "$SEED_FILE")"; then
  # 没下发新指纹，就沿用这个 profile 上次的种子：换一台机器/重启后人格不回滚，
  # 否则同一个画像是「同一个账号、每两天换一套设备」，反而更可疑
  SEED="$(tr -d '[:space:]' < "$SEED_FILE")"
  SEED_SOURCE="沿用 profile 上次的种子"
else
  SEED="$(( (RANDOM % 90000) + 10000 ))"
  SEED_SOURCE="随机生成"
fi
printf '%s\n' "$SEED" > "$SEED_FILE"

# 平台默认 windows：CloakBrowser 在 Linux 上官方就是伪装 Windows（见
# get_default_stealth_args）。显式给值才改，留空不要传空参数。
PLATFORM="${PLATFORM:-windows}"

echo "[entrypoint] 指纹：seed=${SEED} platform=${PLATFORM} tz=${FP_TZ:-<系统>} locale=${FP_LOCALE:-<系统>} webrtc=${WEBRTC_IP:-<不设>}"
echo "[entrypoint] 种子来源：${SEED_SOURCE}"

# ── 复用 profile 前先清锁 ───────────────────────────────────────────
# 容器每次重建 hostname 都会变，而 Chromium 会把「谁占着这个 profile」写进
# SingletonLock（内容形如 <hostname>-<pid>）。下次容器起来发现 hostname 对不上，
# 就判定 profile 被另一台机器占用，直接拒绝启动并退出。
# profile 挂在宿主机卷上，这个文件会跨容器残留，所以每次启动前清掉。
rm -f "${USER_DATA_DIR}/SingletonLock" \
      "${USER_DATA_DIR}/SingletonCookie" \
      "${USER_DATA_DIR}/SingletonSocket"

args=(
  # Chromium 143 起不再认 --remote-debugging-address=0.0.0.0，实测 146/156 也只绑
  # 127.0.0.1。所以这里让它用内部端口，对外由下面 socat 转发到 0.0.0.0。
  "--remote-debugging-address=127.0.0.1"
  "--remote-debugging-port=${CDP_INTERNAL_PORT}"
  "--remote-allow-origins=*"
  "--user-data-dir=${USER_DATA_DIR}"
  "--no-first-run"
  "--no-default-browser-check"
  # 容器 /dev/shm 默认只有 64MB，不关掉这个 Chromium 会随机崩渲染进程
  "--disable-dev-shm-usage"
  # ── 指纹（CloakBrowser 专有）────────────────────────────────────
  # 一个整数种子决定整套人格：UA、平台、硬件并发、显卡、屏幕、字体渲染、
  # canvas/WebGL/audio 噪声。同一个种子 → 同一套指纹，换数字 → 换人格。
  "--fingerprint=${SEED}"
  "--fingerprint-platform=${PLATFORM}"
)

# 下面四个是种子上唯一能单独微调的开关。留空就不传，让内核按平台默认走。
if [ -n "$FP_TZ" ]; then
  args+=("--fingerprint-timezone=${FP_TZ}")
fi
if [ -n "$FP_LOCALE" ]; then
  args+=("--fingerprint-locale=${FP_LOCALE}")
fi
if [ -n "$FP_LANG" ]; then
  args+=("--lang=${FP_LANG}")
fi
if [ -n "$WEBRTC_IP" ]; then
  # WebRTC 会绕过代理直接暴露本机 IP，这是 IP 泄漏最常见的一条路
  args+=("--fingerprint-webrtc-ip=${WEBRTC_IP}")
fi

# 容器里没有 user namespace，沙箱起不来（官方默认也是关掉的）
if [ "${CHROME_NO_SANDBOX:-1}" = "1" ]; then
  args+=("--no-sandbox")
fi

# 有头模式下 Chromium 会因为「软件渲染」把 WebGL 拦掉，容器里没有真 GPU，
# 结果 WebGL 指纹直接变成 not supported —— 比不伪装更容易被认出来。
# 官方在 headed 模式也是这么处理的。注意不能用 --enable-unsafe-swiftshader，
# 那个会把 renderer 字符串写成 SwiftShader，官方明确要抑制。
if [ "$MODE" = "vnc" ]; then
  args+=("--ignore-gpu-blocklist")

  # ── 窗口铺满虚拟屏 ────────────────────────────────────────────────
  # 容器里没有窗口管理器（Xvfb 只提供一块裸画布），Chromium 会按自己的
  # 启发式挑窗口尺寸：实测 1920x1080 的屏上开了 945x1060，noVNC 里看着
  # 就是"只有左半边"。所以显式给尺寸，别让它自己猜。
  #
  # 用户在 CHROME_ARGS 里给了 --window-size 就不覆盖（尊重手动指定）。
  if ! printf '%s' "${CHROME_ARGS:-}" | grep -q -- "--window-size"; then
    SW="${SCREEN%%x*}"                 # 1920x1080x24 -> 1920
    _rest="${SCREEN#*x}"
    SH="${_rest%%x*}"                  # 1920x1080x24 -> 1080
    args+=("--window-size=${SW},${SH}" "--window-position=0,0")
    echo "[entrypoint] 窗口尺寸对齐虚拟屏：${SW}x${SH}"
  fi
fi

# 附加参数按空格切开。这里故意不加引号：就是要让它支持
# CHROME_ARGS="--proxy-server=socks5://1.2.3.4:1080 --window-size=1280,800" 这种写法
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

    # ── 清掉上一次的 X 残留 ───────────────────────────────────────────
    # docker restart / compose restart 不会重建容器，/tmp 里的东西还在：
    # 上次的 /tmp/.X99-lock 和 /tmp/.X11-unix/X99 会残留，Xvfb 第二次启动直接报
    # "Server is already active for display 99" 退出；而下面的就绪检测只要看到
    # socket 存在就放行（残留的 socket 也算），于是 x11vnc 连不上、
    # Chrome 报 "Missing X server or $DISPLAY"，容器进入崩溃循环。
    # 容器里只有这一个 X server，删是安全的 —— 和上面清 SingletonLock 同理。
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"

    Xvfb "$DISPLAY" -screen 0 "$SCREEN" -nolisten tcp -ac &
    XVFB_PID=$!
    # 等 X socket 就绪再起 x11vnc，否则第一次连接会失败。
    # 顺序很重要：先看进程还活着没有，再看 socket —— 反过来的话，残留的
    # socket 会让循环立刻放行，把"Xvfb 已经死了"这件事盖掉。
    for _ in $(seq 1 50); do
      if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "Xvfb 启动失败，检查 /tmp/.X11-unix 是否可写" >&2
        exit 1
      fi
      [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ] && break
      sleep 0.1
    done
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
      echo "Xvfb 启动失败（进程已退出）" >&2
      exit 1
    fi

    x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport "$VNC_PORT" -quiet -noxdamage &
    websockify --web=/usr/share/novnc "$NOVNC_PORT" "localhost:${VNC_PORT}" &

    exec "$CHROME" "${args[@]}" "$START_URL"
    ;;

  *)
    echo "MODE 只能是 headless 或 vnc，当前是：${MODE}" >&2
    exit 2
    ;;
esac
