#!/usr/bin/env bash
# fingerprint-chromium 容器入口。
#
# 两种模式，用环境变量 MODE 切：
#   vnc（默认）       Xvfb 虚拟屏 + x11vnc + noVNC，浏览器里能看见实时画面
#   headless          无界面，只开 CDP 端口，给后端 / Playwright 连
#
# 默认走 vnc：这个项目要人工看浏览器界面（验证码、登录、代理连通性），
# 没有画面等于没法用。只想跑自动化时用 MODE=headless 省掉 Xvfb 那套。
#
# ── 指纹是动态的 ────────────────────────────────────────────────────
# 镜像里不烤任何指纹。指纹在容器启动时装配，四种来源按优先级：
#
#   1. 环境变量      FINGERPRINT_SEED / _PLATFORM / _TIMEZONE / _LOCALE ...
#   2. 指纹文件      FINGERPRINT_FILE（默认 /data/fingerprint.json）
#                    后端按画像挂一份进来即可，字段见 fingerprint.example.json
#   3. profile 里上次用的种子（保证重启后人格不变）
#   4. 都没有 → 随机一个
#
# ── 和隔壁 CloakBrowser 的参数差异（别照抄，会静默失效）─────────────
# fingerprint-chromium 的参数集比 CloakBrowser 宽，但**名字不一样**：
#
#   CloakBrowser                      fingerprint-chromium
#   --fingerprint-timezone=<tz>   →   --timezone=<tz>
#   --fingerprint-locale=<l>      →   --lang=<l> + --accept-lang=<l>
#   --fingerprint-webrtc-ip=<ip>  →   没有这个参数。WebRTC 走
#                                     --disable-non-proxied-udp（默认已开），
#                                     IP 只能靠代理本身保证
#   （无）                        →   --fingerprint-brand / -brand-version /
#                                     -platform-version / -hardware-concurrency
#   （无）                        →   --disable-spoofing=font,audio,canvas,...
#
# 传错名字不会报错，Chromium 只是忽略不认识的参数 —— 表面上一切正常，
# 实际上指纹没生效。所以这里严格按官方参数表拼，不猜。
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
FINGERPRINT_FILE="${FINGERPRINT_FILE:-/data/fingerprint.json}"
SEED_FILE="${USER_DATA_DIR}/.fingerprint-seed"

if [ ! -x "$CHROME" ]; then
  echo "找不到可执行的内核：$CHROME" >&2
  exit 1
fi

# AppRun 里原本做两件事：把 ${APPDIR}/usr/lib 塞进 LD_LIBRARY_PATH、
# 把 CHROME_WRAPPER 指向自己。我们是直接从解包目录跑的，没有 AppRun，
# 这两件事在这里补上——CHROME_WRAPPER 会影响 Chrome 内部的
# 「是否由 wrapper 启动」判断，缺了某些补丁路径不会走。
export CHROME_WRAPPER="$CHROME"
export LD_LIBRARY_PATH="${CHROME_DIR:-/opt/chromium}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

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

# 种子是 32 位整数（官方文档就写 "32-bit integer"），下限取 1：
# --fingerprint=0 会被内核当成「没启用指纹」，是静默失效的经典坑。
#
# 上限 2147483647 是为了兼容 5 位种子——CloakBrowser 用 10000–99999，
# 后端同一套种子生成逻辑可以两边复用，不用给两个内核维护两套范围。
valid_seed() {
  case "${1:-}" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "${#1}" -le 10 ] || return 1
  [ "$1" -ge 1 ] && [ "$1" -le 2147483647 ]
}

# 先只从文件里取一遍，用来判断"文件到底有没有给出有效指纹"
F_SEED="$(fget seed)"
F_PLATFORM="$(fget platform)"
F_PLATFORM_VER="$(fget platform_version)"
F_BRAND="$(fget brand)"
F_BRAND_VER="$(fget brand_version)"
F_HW="$(fget hardware_concurrency)"
F_TZ="$(fget timezone)"
F_LOCALE="$(fget locale)"
F_LANG="$(fget lang)"
F_ACCEPT_LANG="$(fget accept_lang)"
F_NOSPOOF="$(fget disable_spoofing)"

# 指纹文件在那儿、但没给出任何有效字段 —— 几乎一定是格式问题（不是 JSON、
# 或者字段嵌在子对象里）。这比"没提供指纹"危险得多：不说的话就是静默跑随机人格。
if [ -f "$FINGERPRINT_FILE" ]; then
  file_ok=0
  valid_seed "$F_SEED" && file_ok=1
  [ -n "${F_PLATFORM}${F_TZ}${F_LOCALE}${F_LANG}${F_BRAND}" ] && file_ok=1
  if [ "$file_ok" = "0" ]; then
    echo "[entrypoint] 警告：$FINGERPRINT_FILE 存在但没解析出任何有效指纹字段。" >&2
    echo "[entrypoint] 检查它是否是合法 JSON，且字段在顶层：seed / platform / timezone / locale / lang ..." >&2
  fi
fi

# 环境变量 > 文件
SEED="${FINGERPRINT_SEED:-$F_SEED}"
PLATFORM="${FINGERPRINT_PLATFORM:-$F_PLATFORM}"
PLATFORM_VER="${FINGERPRINT_PLATFORM_VERSION:-$F_PLATFORM_VER}"
BRAND="${FINGERPRINT_BRAND:-$F_BRAND}"
BRAND_VER="${FINGERPRINT_BRAND_VERSION:-$F_BRAND_VER}"
HW="${FINGERPRINT_HARDWARE_CONCURRENCY:-$F_HW}"
FP_TZ="${FINGERPRINT_TIMEZONE:-$F_TZ}"
FP_LOCALE="${FINGERPRINT_LOCALE:-$F_LOCALE}"
FP_LANG="${FINGERPRINT_LANG:-$F_LANG}"
FP_ACCEPT_LANG="${FINGERPRINT_ACCEPT_LANG:-$F_ACCEPT_LANG}"
NOSPOOF="${FINGERPRINT_DISABLE_SPOOFING:-$F_NOSPOOF}"

if valid_seed "$SEED"; then
  SEED_SOURCE="外部下发（环境变量或指纹文件）"
elif [ -s "$SEED_FILE" ] && valid_seed "$(tr -d '[:space:]' < "$SEED_FILE")"; then
  # 没下发新指纹，就沿用这个 profile 上次的种子：换一台机器/重启后人格不回滚，
  # 否则同一个画像是「同一个账号、每两天换一套设备」，反而更可疑
  SEED="$(tr -d '[:space:]' < "$SEED_FILE")"
  SEED_SOURCE="沿用 profile 上次的种子"
else
  # 随机范围和 CloakBrowser 对齐（10000–99999），种子可以在两个内核之间互搬
  SEED="$(( (RANDOM % 90000) + 10000 ))"
  SEED_SOURCE="随机生成"
fi
printf '%s\n' "$SEED" > "$SEED_FILE"

# 平台默认 windows：这个内核的卖点就是「在 Linux 上装作一台 Windows」，
# 不给这个值它就老实承认自己是 Linux，指纹没意义。显式给值才改。
PLATFORM="${PLATFORM:-windows}"

# 前端已经明确给了 locale 却没给 lang 时，把 locale 同时当 --lang 用；
# 反过来只给 lang 就只传 --lang。
if [ -z "$FP_LANG" ] && [ -n "$FP_LOCALE" ]; then
  FP_LANG="$FP_LOCALE"
fi
# --accept-lang 是 HTTP Accept-Language，和 --lang 是两套东西。
# 没单独指定时按 "--lang,主语言" 派生（zh-CN → zh-CN,zh），比只传 --lang 更像真人。
if [ -z "$FP_ACCEPT_LANG" ] && [ -n "$FP_LANG" ]; then
  FP_ACCEPT_LANG="${FP_LANG%%,*}"
  case "$FP_ACCEPT_LANG" in
    *-*) FP_ACCEPT_LANG="${FP_ACCEPT_LANG},${FP_ACCEPT_LANG%%-*}" ;;
  esac
fi

echo "[entrypoint] 指纹：seed=${SEED} platform=${PLATFORM} brand=${BRAND:-<内核默认>} tz=${FP_TZ:-<系统>} lang=${FP_LANG:-<系统>}"
echo "[entrypoint] 种子来源：${SEED_SOURCE}"

if [ -n "${FINGERPRINT_WEBRTC_IP:-}" ]; then
  echo "[entrypoint] 注意：fingerprint-chromium 没有 --fingerprint-webrtc-ip 参数，" >&2
  echo "[entrypoint]       FINGERPRINT_WEBRTC_IP=${FINGERPRINT_WEBRTC_IP} 被忽略。" >&2
  echo "[entrypoint]       WebRTC 只靠 --disable-non-proxied-udp + 代理本身收敛出口 IP。" >&2
fi

# ── 复用 profile 前先清锁 ───────────────────────────────────────────
# 容器每次重建 hostname 都会变，而 Chromium 会把「谁占着这个 profile」写进
# SingletonLock（内容形如 <hostname>-<pid>）。下次容器起来发现 hostname 对不上，
# 就判定 profile 被另一台机器占用，直接拒绝启动并退出。
# profile 挂在宿主机卷上，这个文件会跨容器残留，所以每次启动前清掉。
rm -f "${USER_DATA_DIR}/SingletonLock" \
      "${USER_DATA_DIR}/SingletonCookie" \
      "${USER_DATA_DIR}/SingletonSocket"

args=(
  # Chromium 143 起不再认 --remote-debugging-address=0.0.0.0，实测 148 也只绑
  # 127.0.0.1。所以这里让它用内部端口，对外由下面 socat 转发到 0.0.0.0。
  "--remote-debugging-address=127.0.0.1"
  "--remote-debugging-port=${CDP_INTERNAL_PORT}"
  "--remote-allow-origins=*"
  "--user-data-dir=${USER_DATA_DIR}"
  "--no-first-run"
  "--no-default-browser-check"
  # 容器 /dev/shm 默认只有 64MB，不关掉这个 Chromium 会随机崩渲染进程
  "--disable-dev-shm-usage"
  # ── 指纹（fingerprint-chromium 专有）───────────────────────────────
  # 一个整数种子决定整套人格：UA、平台、硬件并发、显卡、屏幕、canvas/
  # WebGL/audio 噪声、字体枚举。同一个种子 → 同一套指纹，换数字 → 换人格。
  "--fingerprint=${SEED}"
  "--fingerprint-platform=${PLATFORM}"
)

# 下面都是"留空就不传"的可选项：传空值比不传更糟，Chromium 会当成空字符串。
if [ -n "$PLATFORM_VER" ]; then
  args+=("--fingerprint-platform-version=${PLATFORM_VER}")
fi
if [ -n "$BRAND" ]; then
  args+=("--fingerprint-brand=${BRAND}")
fi
if [ -n "$BRAND_VER" ]; then
  args+=("--fingerprint-brand-version=${BRAND_VER}")
fi
if [ -n "$HW" ]; then
  args+=("--fingerprint-hardware-concurrency=${HW}")
fi
if [ -n "$FP_TZ" ]; then
  args+=("--timezone=${FP_TZ}")
fi
if [ -n "$FP_LANG" ]; then
  args+=("--lang=${FP_LANG}")
fi
if [ -n "$FP_ACCEPT_LANG" ]; then
  args+=("--accept-lang=${FP_ACCEPT_LANG}")
fi
# 只用来关掉个别伪造项（font / audio / canvas / clientrects / gpu）。
# 默认全开，不要习惯性传值——关错了反而更容易被认出来。
if [ -n "$NOSPOOF" ]; then
  args+=("--disable-spoofing=${NOSPOOF}")
fi

# 禁止非代理 UDP（WebRTC 绕过代理直连、暴露真实 IP 的主要路径）。
# 官方说这是默认策略，这里显式写出来，免得哪天内核改默认值。
# 需要 WebRTC 直连时用 ALLOW_NON_PROXIED_UDP=1 关掉。
if [ "${ALLOW_NON_PROXIED_UDP:-0}" != "1" ]; then
  args+=("--disable-non-proxied-udp")
fi

# 容器里没有 user namespace，沙箱起不来（官方默认也是关掉的）
if [ "${CHROME_NO_SANDBOX:-1}" = "1" ]; then
  args+=("--no-sandbox")
fi

# 有头模式下 Chromium 会因为「软件渲染」把 WebGL 拦进 blocklist，容器里没有
# 真 GPU，结果 WebGL 指纹直接变成 not supported —— 比不伪装还容易被认出来。
# 注意不要用 --enable-unsafe-swiftshader，那个会把 renderer 字符串写成
# "SwiftShader"，真实用户浏览器不会是这个值。
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

# ── 伪移动 ────────────────────────────────────────────────────────
# 内核的 --fingerprint-platform 只认 windows / linux / macos：写 android 不会
# 报错，只会静默回落成 Linux 桌面人格（实测 UA 变 "X11; Linux x86_64"、
# maxTouchPoints 仍是 0）。所以「移动」只能伪 —— 内核照桌面族起人格，这里
# 再把 UA / 视口 / DPR 换成移动端。
#
# 硬边界（别对用户吹过头）：navigator.platform、Client Hints、TLS 指纹仍然是
# 桌面。骗得过只看 UA 的站点，骗不过带风控的。界面上的提示就是从这句来的。
MOBILE="${FINGERPRINT_MOBILE:-$(fget mobile)}"
if [ -n "$MOBILE" ]; then
  # UA 里的主版本必须跟二进制一致，否则 UA 和 sec-ch-ua 的版本对不上，
  # 比不改还容易被抓。所以现取，不写死。
  CHROME_MAJOR="$("$CHROME" --version 2>/dev/null | grep -oE '[0-9]+' | head -1)"
  CHROME_MAJOR="${CHROME_MAJOR:-148}"
  case "$MOBILE" in
    ios)
      # iPad 而不是 iPhone：X 下 Chromium 的窗口有 500 左右的最小宽度，
      # 390 那种手机宽度会被撑到 501，窗口比 screen 还宽，反而露馅。
      # 另一个原因是 iPad 桌面版 UA 本来就把 navigator.platform 报成 MacIntel，
      # 和我们实际的 macOS 桌面人格刚好对得上。
      MOBILE_UA="Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/${CHROME_MAJOR}.0.0.0 Mobile/15E148 Safari/604.1"
      MOBILE_VIEW="744,1133"     # CSS 视口（iPad mini）
      MOBILE_SCREEN="1488x2266"  # 设备像素 = CSS × DPR
      MOBILE_DPR="2"
      ;;
    *)
      # 540 而不是 412：同上，窗口最小宽度会把 412 撑到 501，
      # 窗口比屏幕宽是能被查出来的矛盾。540(DIP) × 2 = 1080，屏幕也说得通。
      MOBILE_UA="Mozilla/5.0 (Linux; Android 13; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${CHROME_MAJOR}.0.0.0 Mobile Safari/537.36"
      MOBILE_VIEW="540,960"
      MOBILE_SCREEN="1080x1920"
      MOBILE_DPR="2"
      ;;
  esac
  # 虚拟屏也换成手机尺寸：Xvfb 用的是设备像素，浏览器再按 DPR 折算成 CSS。
  # 不换的话 screen 还是 1920x1080，采集回来的分辨率会跟移动人格自相矛盾。
  # 这里在 Xvfb 之前赋值，vnc 分支读的就是新值。
  SCREEN="${MOBILE_SCREEN}x24"
  # 放在 CHROME_ARGS 之后：同一个参数出现两次时后写的赢，手填的窗口尺寸
  # 也就跟着改成移动端了 —— 这是有意的，移动端不该配桌面视口。
  args+=(
    "--user-agent=${MOBILE_UA}"
    "--window-size=${MOBILE_VIEW}"
    "--force-device-scale-factor=${MOBILE_DPR}"
  )
  echo "[entrypoint] 伪移动：${MOBILE}，UA / 视口 / DPR 已换成移动端；platform、Client Hints、TLS 仍是桌面"
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
    # 容器里只有这一个 X server，删是安全的 —— 这一步和上面清 SingletonLock 同理。
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
