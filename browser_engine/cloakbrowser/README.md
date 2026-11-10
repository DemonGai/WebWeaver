# CloakBrowser（容器化内核）

基于 Chromium 源码级补丁的反检测内核，在容器里跑，对外只露两个口：CDP（给后端 /
Playwright）和 noVNC（给人看画面）。

## 和隔壁 ungoogled-chromium 那套的区别

目录结构、构建方式、端口桥接、profile 清理全部沿用，**只有三处不一样，都是
CloakBrowser 自己的特性决定的**：

| | ungoogled-chromium | CloakBrowser |
|---|---|---|
| 启动参数 | 纯净 Chromium，无指纹逻辑 | 必须带 `--fingerprint=<种子>`，否则等于没伪装 |
| 字体 | 装个 `fonts-noto-cjk` 就够（不伪装平台） | **必须装真实 Windows 字体**，否则伪装 Windows 一戳就破 |
| WebGL | 容器里没有真 GPU，能用就行 | 有头模式必须 `--ignore-gpu-blocklist`，否则 WebGL 指纹直接变 not supported |
| 指纹来源 | 无 | 运行时动态注入，镜像里不烤任何值 |

> 关于 `--ignore-gpu-blocklist`：官方代码里**特意抑制**了
> `--enable-unsafe-swiftshader`，因为那会把 WebGL renderer 字符串写成
> "SwiftShader"，真实用户浏览器没有这个值，反而成了新的特征。两个参数别搞混。

## 从 CloakBrowser-Manager 学到的

[NorwayXZ/CloakBrowser-Manager](https://github.com/NorwayXZ/CloakBrowser-Manager)
是社区做的 CloakBrowser 图形管理器，它的 Dockerfile 里有几处值得照抄：

| 它的做法 | 采纳情况 |
|---|---|
| 装 KasmVNC 而不是 noVNC+x11vnc | **没采纳**。KasmVNC 画质和剪贴板更好，但要从 GitHub 拉 150MB 的 deb，国内构建经常失败；noVNC 这套在隔壁已经跑通 |
| 把 Windows 字体装进镜像 | **采纳**，但换成了更彻底的做法，见下 |
| 启动前清 `SingletonLock/SingletonCookie/SingletonSocket` | **采纳**，这是 profile 挂卷后容器必踩的坑 |
| `/data` 作为唯一持久卷 | **采纳**，profile 和指纹文件都放这里 |
| 镜像里 `pip install cloakbrowser` + `ensure_binary()` 预下二进制 | **没采纳**。它能用是因为 pin 了 `0.6.x`（该版本不需要 license key），但下载地址对免费包是 301 跳回 GitHub，速度问题一点没解决。我们是把二进制目录直接 `COPY` 进镜像，构建可离线、可复现 |
| Playwright `install-deps` | **没采纳**，直接按 `ldd chrome` 列依赖更可控，也少装一堆用不上的包 |

### Windows 字体：为什么不能只靠 apt

CloakBrowser 在 Linux 上默认伪装成 Windows（`--fingerprint-platform=windows`），
但字体是内核从**宿主系统**渲染出来的。官方在 `browser.py` 里留了一组探针，启动时会
用 `fc-list` 检查这 8 个字体：

```
Segoe UI / Segoe UI Light / Calibri / Marlett / MS UI Gothic
Franklin Gothic / Consolas / Courier New
```

少一个就会一直打印告警。而官方 README 明确说 `ttf-mscorefonts-installer`
**不够用** —— 它只有 XP 时代的 Arial / Times / Verdana，上面这几个恰恰都不在里面。

所以这里改成从你自己的 Windows 机器上拷：

```bash
./collect-windows-fonts.sh          # 从 C:\Windows\Fonts 收集到 ./fonts/
docker compose up -d --build        # 构建时 COPY 进 /usr/local/share/fonts/windows/
```

脚本会逐个核对那 8 个探针，缺哪个会直接告诉你。

`fonts/` 在 `.gitignore` 里：微软字体不能重新分发，**只在自己机器上用**。

## 从 Docker Hub 直接拉（跳过本地构建）

镜像已推到 [`demon1315132284/browser_engine`](https://hub.docker.com/r/demon1315132284/browser_engine)，
一个内核一个 tag：

| tag | 内容 |
|---|---|
| `cloakbrowser-146.0.7680.177.5` | 固定版本，可复现 |
| `cloakbrowser` | 滚动标签，始终指向该内核最近一次构建 |

```bash
docker pull demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5
```

不用 compose 也能直接跑（指纹照样运行时下发）：

```bash
docker run -d --name wv-cloakbrowser \
  -p 9232:9222 -p 6082:6080 \
  -e MODE=vnc \
  -e FINGERPRINT_SEED=42817 \
  -e FINGERPRINT_TIMEZONE=Asia/Shanghai \
  -e FINGERPRINT_LOCALE=zh-CN \
  --shm-size=1g --init --restart unless-stopped \
  -v "$PWD/data:/data" \
  demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5
```

`--shm-size=1g` 不能省（默认 64MB 会让渲染进程随机崩）。

> 镜像里**不含** Windows 字体（微软字体不能重新分发），从 Hub 拉下来的版本
> 字体指纹只靠内核自己派生。要补就本地重新构建，见下文。

想继续用 compose 里的端口/卷配置、只是不本地构建：把 `docker-compose.yaml`
的 `build:` 整段删掉，`image:` 改成上面那个名字，再 `docker compose up -d`。

## 换版本

版本号 = 文件夹名 = 构建参数，三者同一个来源：

```bash
docker compose up -d --build                                  # 默认 146.0.7680.177.5
CLOAKBROWSER_VERSION=147.0.8000.1 docker compose up -d --build # 换版本
```

同时跑两个版本要换项目名和端口，否则会互相删容器：

```bash
CLOAKBROWSER_VERSION=146.0.7680.177.5 CB_CDP_HOST_PORT=9232 \
  docker compose -p cb146 up -d --build
```

### 版本从哪来

官方 release 的包名是固定规律的，Linux 是 `tar.gz`（不是 zip）：

```
https://github.com/CloakHQ/cloakbrowser/releases/download/chromium-v{版本}/cloakbrowser-linux-x64.tar.gz
```

校验值在**官方 CDN** 上有独立清单（这个地址不受 GitHub 域名劫持影响，很快）：

```bash
curl https://cloakbrowser.dev/chromium-v146.0.7680.177.5/SHA256SUMS
# 4a12bcde95fa1bb1beef2b41ab5e5c27c36be78e3be3d0dac8c64d705216670e  cloakbrowser-linux-x64.tar.gz
# b213795cb32c3169f766c74ce1d0275fc89d3df256de39c04da7fb4c23b7fdbe  cloakbrowser-windows-x64.zip
```

下载解压后，把里面的目录整体改名成版本号放进本目录：

```bash
# 这个仓库的 release 资产域名（release-assets.githubusercontent.com）在部分网络下
# 会被代理解析成 127.0.0.1，直连必然 "actively refused"。
#
# 注意 cloakbrowser.dev 对**免费包**只是 301 跳回 GitHub，不提供加速，
# 所以走加速站。单站会被限速到 60KB/s 左右，把几个站拼给 aria2 并行才跑得动
# （实测 200–400KB/s，206MB 约 16 分钟）。
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
aria2c -x8 -s16 -k1M -c --file-allocation=none --show-console-readout=false \
  -o cloakbrowser-linux-x64.tar.gz \
  "https://gh-proxy.com/https://github.com/CloakHQ/cloakbrowser/releases/download/chromium-v146.0.7680.177.5/cloakbrowser-linux-x64.tar.gz" \
  "https://ghproxy.net/https://github.com/CloakHQ/cloakbrowser/releases/download/chromium-v146.0.7680.177.5/cloakbrowser-linux-x64.tar.gz" \
  "https://gh.tryxd.cn/https://github.com/CloakHQ/cloakbrowser/releases/download/chromium-v146.0.7680.177.5/cloakbrowser-linux-x64.tar.gz"

sha256sum cloakbrowser-linux-x64.tar.gz      # 和上面的 SHA256SUMS 对一遍
mkdir -p 146.0.7680.177.5 && tar xzf cloakbrowser-linux-x64.tar.gz -C 146.0.7680.177.5
```

解压后 `chrome` 在版本目录根下（没有套一层子目录），和 Windows 版一样是扁平的。

### 为什么不用 `pip install cloakbrowser` 来拿包

也能拿到，但**必须锁 0.6.x**，两个版本的取包逻辑不一样：

| wrapper 版本 | 无 license key 时 |
|---|---|
| `0.6.x`（如 0.6.5） | 直接下免费包，**不需要领 key** |
| `0.7.x`（当前 latest） | `ensure_binary()` 里 `resolve_license_key() or _claim_free_key()`，会去邮箱领一个免费 key，非交互环境下直接报错 |

社区项目 [CloakBrowser-Manager](https://github.com/NorwayXZ/CloakBrowser-Manager) 的
Dockerfile 里就是 `RUN python -c "...ensure_binary()"` 而没配任何 key —— 因为它 pin 的是
`cloakbrowser[geoip]>=0.6.2,<0.7`。

但要注意它省掉的只是「领 key」，**没省下载时间**：0.6.x 的首选地址仍是
`https://cloakbrowser.dev/chromium-v{版本}/cloakbrowser-linux-x64.tar.gz`，
而这个地址对免费包是 `301` 跳回 GitHub Releases —— 落到的还是同一个慢资产。

另外一个坑：**pip 走清华源会拿到 HTTP 403**（直接 curl 同一个 URL 是 200，看起来是
对 pip 客户端的限流），换阿里源 `https://mirrors.aliyun.com/pypi/simple` 正常。


## 指纹：运行时动态注入

**镜像里不烤任何指纹。** 指纹在容器启动时装配，优先级从高到低：

```
1. 环境变量  FINGERPRINT_SEED / _PLATFORM / _TIMEZONE / _LOCALE / _LANG / _WEBRTC_IP
2. 指纹文件  /data/fingerprint.json（宿主机 ./data/<版本>/fingerprint.json）
3. profile 里上次用的种子（/data/profile/.fingerprint-seed）
4. 都没有 → 随机生成一个
```

启动日志会打印最终生效的值和来源：

```
[entrypoint] 指纹：seed=42817 platform=windows tz=Asia/Shanghai locale=zh-CN webrtc=203.0.113.10
[entrypoint] 种子来源：外部下发（环境变量或指纹文件）
```

### 为什么第 3 条重要

没下发新指纹时，沿用 profile 上次的种子。否则容器每次重启都是
「同一个账号、换了台新设备」—— 这比不换更容易被风控标记。清空人格的办法是
换种子或删掉 `/data/profile/.fingerprint-seed`。

### 六个字段

| 字段 | 是什么 | 取值范围 |
|---|---|---|
| `seed` | **一个整数决定整套人格**：UA、平台、硬件并发、显卡、屏幕、字体渲染、canvas/WebGL/audio 噪声 | 10000–99999，越界视为无效 |
| `platform` | 伪装成哪个系统 | `windows`（默认）/ `macos` / `linux` |
| `timezone` | 时区 | IANA 名，如 `Asia/Shanghai` |
| `locale` | 界面语言 | 如 `zh-CN` |
| `lang` | `--lang` 参数 | 一般与 `locale` 相同 |
| `webrtc_ip` | WebRTC 对外 IP | 出口代理的 IP |

## 指纹库 → CloakBrowser 格式

这一节是给后面写转换器用的：**你现在的指纹库字段，绝大多数塞不进
CloakBrowser 的参数**，因为它是「一个种子推导一切」，不是「逐项指定」。

CloakBrowser 全部可用的指纹参数就这六个：

```
--fingerprint=<seed>              种子，10000–99999
--fingerprint-platform=<os>       windows | macos | linux
--fingerprint-timezone=<tz>       IANA 时区
--fingerprint-locale=<locale>     语言
--fingerprint-webrtc-ip=<ip>      WebRTC 出口 IP
--lang=<locale>                   同 locale
```

除此之外**没有任何** `--fingerprint-canvas` / `--fingerprint-webgl` /
`--fingerprint-hardware-concurrency` 之类的单项开关。canvas 噪声、WebGL vendor、
`navigator.hardwareConcurrency`、`screen` 尺寸、UA 串、字体列表这些，全部由
seed 在 C++ 层派生，外部改不了。

所以转换器的真实形态是**映射 + 校验**，不是逐字段搬运：

| 指纹库里的字段 | 转换方式 |
|---|---|
| 设备指纹的 `seed` / 主键 | 哈希成一个 10000–99999 的整数。**同一个画像必须稳定映射到同一个数**，否则每次重启换人格 |
| `os` / `platform` | 直接映射（`win*` → `windows`），注意只能三选一 |
| `timezone` / `tz` | 直接映射，最好由代理 IP 反查得到 |
| `locale` / `language` / `acceptLanguage` | 取主语言，如 `zh-CN` |
| `webRTC` / 出口 IP | 取代理出口 IP |
| `userAgent` | **不搬**。由 seed 派生，硬填会和 seed 的其它属性打架 |
| `screen` / `viewport` | **不搬**。有头模式下取虚拟屏真实尺寸，硬填会破坏 `outerWidth >= innerWidth` 的一致性 |
| `hardwareConcurrency` / `deviceMemory` | **不搬**，同上 |
| `canvas` / `webgl` / `audio` 噪声 | **不搬**，seed 已包含 |
| `fonts` | **不搬**，但要在镜像里装对 Windows 字体（见上文） |

一句话：**指纹库只需要给出「一个稳定的种子 + 平台 + 时区 + 语言 + 出口 IP」，
剩下的交给内核。** 把 UA、屏幕、并发数硬写进去，反而会造出自相矛盾的指纹。

### 落地方式

后端按画像起容器时，两种都行：

```bash
# 方式一：环境变量（最直接）
FINGERPRINT_SEED=42817 FINGERPRINT_TIMEZONE=Asia/Shanghai \
FINGERPRINT_LOCALE=zh-CN FINGERPRINT_WEBRTC_IP=203.0.113.10 \
  docker compose up -d

# 方式二：挂一份 json（字段见 fingerprint.example.json）
cp fingerprint.example.json ./data/146.0.7680.177.5/fingerprint.json
docker compose restart
```

## 后端怎么连

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9232")
    page = (await browser.new_context()).new_page()
    await page.goto("https://example.com")
```

端口和隔壁错开了（默认 9232），想统一改 `CB_CDP_HOST_PORT`。

验证端口通不通：

```bash
curl http://127.0.0.1:9232/json/version
```

## 几个容器里跑 Chromium 的坑（都已在配置里处理）

- **执行位丢失**：从 Windows 解压出来的 `chrome` 是 644，Dockerfile 里显式 `chmod +x`
- **`/dev/shm` 太小**：默认 64MB 会让渲染进程随机崩，compose 里设了 `shm_size: 1gb`，
  启动参数也加了 `--disable-dev-shm-usage`
- **`--remote-debugging-address` 无效**：Chromium 143+ 起官方忽略这个参数，只绑
  `127.0.0.1`，容器外连不上。解法是 Chrome 监听内部 9223，socat 把 `0.0.0.0:9222`
  桥过去。已验证 `/json/version` 返回的 `webSocketDebuggerUrl` 会跟随 Host 头
- **profile 锁**：容器重建后 hostname 变，`SingletonLock` 会让 Chromium 拒绝启动，
  entrypoint 每次启动前清掉
- **restart 后 Xvfb 起不来（崩溃循环）**：`docker restart` / `docker compose restart`
  **不会重建容器**，`/tmp` 里的东西还在 —— 上次的 `/tmp/.X99-lock` 和
  `/tmp/.X11-unix/X99` 残留，Xvfb 第二次启动直接报
  `Server is already active for display 99` 退出；如果就绪检测先看 socket 再看进程，
  残留的 socket 会让循环立刻放行，于是 x11vnc 连不上、Chrome 报
  `Missing X server or $DISPLAY`，容器进入 `Restarting` 循环。现在启动前会先
  `rm -f` 这两个文件，并把检测顺序改成「先看进程活着没有」
- **僵尸进程**：Chromium 会 fork 很多子进程，`init: true` 让 tini 收尸
- **沙箱**：容器里一般起不来，默认 `--no-sandbox`（官方默认也是关的）
- **中文字体**：不装 `fonts-noto-cjk` 的话中文页面是豆腐块，noVNC 里看着就是方块
- **窗口只占半屏**：容器里没有窗口管理器，Xvfb 只是块裸画布，Chromium 于是按自己的
  启发式挑窗口尺寸 —— 实测在 1920x1080 的屏上开了 **945x1060**，noVNC 里就是
  「只有左半边」。entrypoint 现在在 vnc 模式下显式传
  `--window-size=<屏宽>,<屏高> --window-position=0,0`，实测窗口 1919x1079 正好铺满。
  想自己指定就用 `CHROME_ARGS="--window-size=1280,800"`，脚本检测到就不再覆盖。
  另一种解法是装个轻量 WM（openbox）用 `--start-maximized`，但为一次布局多装一套
  窗口系统不值得

## 文件

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 构建镜像，版本由 `ARG CLOAKBROWSER_VERSION` 控制 |
| `docker-compose.yaml` | 编排：端口、卷、shm、init、指纹环境变量 |
| `entrypoint.sh` | 启动逻辑：指纹装配、CDP 桥接、vnc/headless 两种模式 |
| `collect-windows-fonts.sh` | 从本机 Windows 收集字体到 `fonts/` |
| `fingerprint.example.json` | 指纹文件格式示例 |
| `.env.example` | 全部可配项 |
