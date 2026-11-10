# fingerprint-chromium（容器化内核）

基于 ungoogled-chromium 打源码级指纹补丁的内核，在容器里跑，对外只露两个口：
CDP（给后端 / Playwright）和 noVNC（给人看画面）。

它的定位和隔壁两个不一样：**一个整数种子决定整套人格**，同种子 → 同指纹，
可复现。适合固定指纹做回归测试、复现某个站点的拦截问题。

## 和隔壁两个内核的区别

目录结构、端口桥接、profile 清理、noVNC 那套全部沿用，
**真正的差异只有三处**：

| | ungoogled-chromium | CloakBrowser | fingerprint-chromium |
|---|---|---|---|
| Linux 包格式 | 扁平目录（tar.xz 解开） | 扁平目录（tar.gz 解开） | **只有 AppImage** |
| 启动参数前缀 | 无指纹逻辑 | `--fingerprint-*` 六个 | `--fingerprint-*` 但**名字不同**（见下） |
| 字体要求 | 装 `fonts-noto-cjk` 就够 | 必须装真实 Windows 字体 | 自带 font spoofing，**可选** |

> **最容易踩的坑**：两个内核的指纹参数名不一样，传错不会报错 —— Chromium 只是
> 忽略不认识的参数，表面上一切正常、实际指纹没生效。对照表见下面「指纹参数」。

## AppImage 怎么进容器的

官方 Linux 包只有 AppImage（`ELF 头 + squashfs`），运行时靠 FUSE 把自己挂载
起来再执行。容器里默认没有 `/dev/fuse`，直接跑会报：

```
Cannot mount AppImage, please check your FUSE setup.
```

所以 `Dockerfile` 走 multi-stage，分两步：

1. **unpack 阶段**：`./xxx.AppImage --appimage-extract`。这条路径不碰 FUSE，
   由 AppImage runtime 自己读 squashfs，解出 `squashfs-root/opt/ungoogled-chromium/`
2. **运行阶段**：把那个目录（714MB）当成普通 Chromium 目录 `COPY` 进镜像

好处是最终镜像里既没有 188MB 的 AppImage，也没有解包残留。
`AppRun` 那三行本质就是 `export LD_LIBRARY_PATH` + `export CHROME_WRAPPER` + `exec chrome`，
这两件事改到 `entrypoint.sh` 里做了，所以不需要 AppRun。

## 从 Docker Hub 直接拉（跳过本地构建）

镜像已推到 [`demon1315132284/browser_engine`](https://hub.docker.com/r/demon1315132284/browser_engine)，
一个内核一个 tag：

| tag | 内容 |
|---|---|
| `fingerprint-chromium-148.0.7778.215` | 固定版本，可复现 |
| `fingerprint-chromium` | 滚动标签，始终指向该内核最近一次构建 |

```bash
docker pull demon1315132284/browser_engine:fingerprint-chromium-148.0.7778.215
```

不用 compose 也能直接跑（指纹照样运行时下发）：

```bash
docker run -d --name wv-fingerprint-chromium \
  -p 9242:9222 -p 6084:6080 \
  -e MODE=vnc \
  -e FINGERPRINT_SEED=42817 \
  -e FINGERPRINT_TIMEZONE=Asia/Shanghai \
  -e FINGERPRINT_LOCALE=zh-CN \
  -e FINGERPRINT_BRAND=Chrome \
  --shm-size=1g --init --restart unless-stopped \
  -v "$PWD/data:/data" \
  demon1315132284/browser_engine:fingerprint-chromium-148.0.7778.215
```

`--shm-size=1g` 不能省（默认 64MB 会让渲染进程随机崩）。

> 镜像里**不含** Windows 字体（微软字体不能重新分发）。这个内核自带 font
> spoofing，所以从 Hub 拉下来直接能用；想补真实字体就本地重新构建，见下文。

想继续用 compose 里的端口/卷配置、只是不本地构建：把 `docker-compose.yaml`
的 `build:` 整段删掉，`image:` 改成上面那个名字，再 `docker compose up -d`。

## 换版本

版本号 = AppImage 文件名里的版本 = 构建参数，同一个来源：

```bash
docker compose up -d --build                                   # 默认 148.0.7778.215
FP_VERSION=150.0.7871.186 docker compose up -d --build         # 换版本
```

AppImage 的文件名必须是 `fingerprint-chromium-<FP_VERSION>*.AppImage`。
官方打包序号会变（`-1`、`-1.1`、无后缀都有），所以 Dockerfile 用通配匹配，
你不用改文件也能换。

同时跑两个版本要换项目名和端口，否则会互相删容器：

```bash
FP_VERSION=148.0.7778.215 FPC_CDP_HOST_PORT=9242 FPC_NOVNC_HOST_PORT=6084 \
  docker compose -p fpc148 up -d --build
```

### 版本从哪来

```
https://github.com/adryfish/fingerprint-chromium/releases/download/<版本>/fingerprint-chromium-<版本>-1-x86_64.AppImage
# 同版本还有 tar.xz（后端安装器目前只解 zip，用不上）：
https://github.com/adryfish/fingerprint-chromium/releases/download/<版本>/ungoogled-chromium-<版本>-1-x86_64_linux.tar.xz
```

注意 **AppImage 叫 `fingerprint-chromium-*`，tar.xz 叫 `ungoogled-chromium-*`**，
两个前缀不一样，别照抄。

`release-assets.githubusercontent.com` 在部分网络下会被代理解析成 127.0.0.1，
直连必然 "actively refused"。单加速站会越跑越慢（实测 580 → 70 KB/s），
把几个站拼给 aria2 并行才跑得动（实测 200–400 KB/s，188MB 约 10 分钟）：

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
aria2c -x8 -s16 -k1M -c --file-allocation=none --show-console-readout=false \
  -o fingerprint-chromium-148.0.7778.215-1-x86_64.AppImage \
  "https://gh-proxy.com/https://github.com/adryfish/fingerprint-chromium/releases/download/148.0.7778.215/fingerprint-chromium-148.0.7778.215-1-x86_64.AppImage" \
  "https://ghproxy.net/https://github.com/adryfish/fingerprint-chromium/releases/download/148.0.7778.215/fingerprint-chromium-148.0.7778.215-1-x86_64.AppImage" \
  "https://gh.tryxd.cn/https://github.com/adryfish/fingerprint-chromium/releases/download/148.0.7778.215/fingerprint-chromium-148.0.7778.215-1-x86_64.AppImage"
```

上游**不公示 sha256**，只能校验下载完整性，无法校验来源一致性（`engine.json` 里也
记成了 `null`）。同版本多站下载可以互相比对大小是否为 188811768 字节。

## 指纹：运行时动态注入

**镜像里不烤任何指纹。** 指纹在容器启动时装配，优先级从高到低：

```
1. 环境变量  FINGERPRINT_SEED / _PLATFORM / _TIMEZONE / _LOCALE ...
2. 指纹文件  /data/fingerprint.json（宿主机 ./data/<版本>/fingerprint.json）
3. profile 里上次用的种子（/data/profile/.fingerprint-seed）
4. 都没有 → 随机生成一个（10000–99999，和 CloakBrowser 同范围）
```

启动日志会打印最终生效的值和来源：

```
[entrypoint] 指纹：seed=42817 platform=windows brand=<内核默认> tz=Asia/Shanghai lang=zh-CN
[entrypoint] 种子来源：外部下发（环境变量或指纹文件）
```

### 为什么第 3 条重要

没下发新指纹时，沿用 profile 上次的种子。否则容器每次重启都是
「同一个账号、换了台新设备」—— 这比不换更容易被风控标记。
清空人格的办法是换种子或删掉 `/data/profile/.fingerprint-seed`。

## 指纹参数

这是和 CloakBrowser 唯一需要仔细看的地方。**下面每一行都是实测能用的名字**：

| 环境变量 | 传给内核的参数 | 说明 |
|---|---|---|
| `FINGERPRINT_SEED` | `--fingerprint=<int>` | **核心**，1–2147483647（官方是 32 位整数；`0` 会被当成「没启用」） |
| `FINGERPRINT_PLATFORM` | `--fingerprint-platform=` | `windows`（默认）/ `macos` / `linux` |
| `FINGERPRINT_PLATFORM_VERSION` | `--fingerprint-platform-version=` | 留空 = 内核按平台给默认值 |
| `FINGERPRINT_BRAND` | `--fingerprint-brand=` | `Chrome` / `Edge` / `Opera` / `Vivaldi`，留空 = Chromium |
| `FINGERPRINT_BRAND_VERSION` | `--fingerprint-brand-version=` | 留空 = 内核按品牌给默认值 |
| `FINGERPRINT_HARDWARE_CONCURRENCY` | `--fingerprint-hardware-concurrency=` | 留空 = 由种子派生 |
| `FINGERPRINT_TIMEZONE` | `--timezone=` | ⚠️ **不是** `--fingerprint-timezone` |
| `FINGERPRINT_LOCALE` | `--lang=` | 留空 `FINGERPRINT_LANG` 时由它顶上 |
| `FINGERPRINT_LANG` | `--lang=` | 一般和 locale 填一样 |
| `FINGERPRINT_ACCEPT_LANG` | `--accept-lang=` | 留空 = 由 `--lang` 派生（`zh-CN` → `zh-CN,zh`） |
| `FINGERPRINT_DISABLE_SPOOFING` | `--disable-spoofing=` | 只关个别项：`font,audio,canvas,clientrects,gpu` |
| `FINGERPRINT_WEBRTC_IP` | **无此参数** | 填了只会打印一条告警，见下 |

entrypoint 还会固定加两个包里不暴露的开关：

- `--disable-non-proxied-udp`：禁止 WebRTC 绕过代理直连。这是 IP 泄漏最主要的一条路。
  要 WebRTC 直连就设 `ALLOW_NON_PROXIED_UDP=1`
- `--ignore-gpu-blocklist`（仅 vnc 模式）：容器里没有真 GPU，不加这个 WebGL
  fingerprint 直接变 `not supported`，比不伪装还显眼。**别**换成
  `--enable-unsafe-swiftshader`，那个会把 renderer 写成 `SwiftShader`

### 三个版本相关的差异（148 vs 144 以下）

| 参数 | 状态 |
|---|---|
| `--fingerprint-gpu-vendor` / `--fingerprint-gpu-renderer` | **Chrome 144 起移除**，传了无效 |
| `--disable-gpu-fingerprint` | **Chrome 144 起移除**，改用 `--disable-spoofing=gpu` |
| `--disable-spoofing` | **Chrome 144 起新增** |

148 属于「144+」，所以这里只支持新参数。

### 为什么不伪装 WebRTC IP

CloakBrowser 有 `--fingerprint-webrtc-ip=<ip>`，fingerprint-chromium **没有**。
它的策略是另一个方向：默认就禁止非代理 UDP，让 WebRTC 拿不到候选地址。
所以真实出口 IP 只能靠代理本身保证 —— 这也是为什么 `CHROME_ARGS` 里一定要带
`--proxy-server`，否则 WebRTC 和页面请求都是本机 IP。

## 实测（148.0.7778.215，1920x1080，vnc 模式）

同一个种子重启两次，逐项一致 —— 这正是这个内核存在的意义：

| 项 | `seed=42817` | 备注 |
|---|---|---|
| `navigator.userAgent` | `... Chrome/148.0.0.0 Safari/537.36` | `platform=windows` |
| `navigator.platform` | `Win32` | |
| `navigator.webdriver` | `false` | |
| `hardwareConcurrency` | `24` | 由种子派生，不可单独设 |
| WebGL renderer | `ANGLE (Intel, Intel(R) Arc(TM) Graphics (0x00007D55) Direct3D11 vs_5_0 ps_5_0, D3D11)` | 伪装成 Windows D3D11 |
| canvas `toDataURL` | 长度 `15418`，哈希 `367316564` | 重启后完全一致 |
| 窗口 / 视口 | `1919x1079 @ (0,0)` / `1919x906` | 铺满虚拟屏 |

换成 `seed=90001` 后：`hardwareConcurrency` 24 → 12、GPU 变成
`NVIDIA GeForce RTX 3060 Laptop GPU`、canvas 哈希 `-991151691`。
**同一个种子 → 同一个浏览器；换数字 → 换机器。**

指纹文件通道也验过：`data/148.0.7778.215/fingerprint.json` 里写
`brand: "Edge"`、`timezone: "Europe/London"`、`locale: "en-GB"`，重启后
UA 末尾出现 `Edg/148.0.0.0`、`Intl` 时区变 `Europe/London`、`navigator.languages`
变 `["en-GB","en"]`。

> 查这些值不用装 Playwright，走 CDP 就够：`curl 127.0.0.1:9242/json/list`
> 拿 `webSocketDebuggerUrl`，连上去 `Runtime.evaluate` 一段 JS 即可。


## 指纹库 → fingerprint-chromium 格式

和 CloakBrowser 一样，它是「一个种子推导一切」，**不是逐项指定**。区别是它比
CloakBrowser 多几个能单独调的开关（brand、platform-version、hardware-concurrency）。

转换器的真实形态是 **映射 + 校验**：

| 指纹库里的字段 | 转换方式 |
|---|---|
| `seed` / 设备主键 | 哈希成整数。CloakBrowser 用 10000–99999，这个内核接受 1–2147483647，**建议统一取 10000–99999**，这样同一份种子能在两个内核之间直接搬家做 A/B |
| `os` / `platform` | 直接映射（`win*` → `windows`），只能三选一 |
| `timezone` / `tz` | 直接映射，最好由代理 IP 反查得到 |
| `locale` / `language` | 取主语言，如 `zh-CN`；`accept_lang` 可以留给脚本按 `--lang` 派生 |
| `brand` | 有就映射（`chrome` → `Chrome`），没有就不传，让内核报 Chromium |
| `hardwareConcurrency` | **一般不要搬**。不传时由种子派生，和种子的其它属性自洽 |
| `userAgent` | **不搬**。由 seed + brand 派生，硬填会和 seed 打架 |
| `screen` / `viewport` | **不搬**。有头模式取虚拟屏真实尺寸 |
| `canvas` / `webgl` / `audio` 噪声 | **不搬**，seed 已包含 |
| `fonts` | **不搬**，可选地装真实 Windows 字体（见下） |

**同一份指纹文件，两个内核都能吃**：字段名 `seed / platform / timezone / locale /
lang` 是共用的，`fingerprint.example.json` 里多出来的
`platform_version / brand / accept_lang` 在 CloakBrowser 那边会被忽略。
所以后端只要维护**一份 JSON**，按内核决定挂给谁。

落地方式两种：

```bash
# 方式一：环境变量（最直接）
FINGERPRINT_SEED=42817 FINGERPRINT_TIMEZONE=Asia/Shanghai \
FINGERPRINT_LOCALE=zh-CN FINGERPRINT_BRAND=Chrome \
  docker compose up -d

# 方式二：挂一份 json（字段见 fingerprint.example.json）
cp fingerprint.example.json ./data/148.0.7778.215/fingerprint.json
docker compose restart
```

## Windows 字体（可选）

CloakBrowser 那边是**必须**，这边是**可选**：fingerprint-chromium 从 Chrome 144
起内置字体指纹伪造（`--disable-spoofing=font` 就是关它的开关），枚举出来的字体列表
由补丁改写，不依赖容器里真装了什么。

但如果页面直接拿 canvas 量字形宽度，量到的还是真实装着的字体，补上更稳：

```bash
cp -r ../cloakbrowser/fonts ./fonts     # 复用已经收集好的
docker compose up -d --build
```

不补也照常构建，`fonts/` 里只有一个 `.gitkeep`。`fonts/` 在 `.gitignore` 里
（微软字体不能重新分发，只在自己机器上用）。

## 后端怎么连

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9242")
    page = (await browser.new_context()).new_page()
    await page.goto("https://example.com")
```

端口和另外两个错开（默认 9242），想统一改 `FPC_CDP_HOST_PORT`。

```bash
curl http://127.0.0.1:9242/json/version     # 验证端口通不通
```

查当前窗口/视口尺寸（排查 noVNC 只显示一半时用）：

```bash
curl -s http://127.0.0.1:9242/json/list | jq -r '.[0].webSocketDebuggerUrl'
```

## 几个容器里跑 Chromium 的坑（都已在配置里处理）

- **AppImage 需要 FUSE**：容器里没有，所以构建时 `--appimage-extract` 解开，
  运行的是解包目录，不是 AppImage 本身
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
  `Server is already active for display 99` 退出。更隐蔽的是：如果就绪检测先看
  socket 再看进程，残留的 socket 会让循环立刻放行，于是 x11vnc 连不上、
  Chrome 报 `Missing X server or $DISPLAY`，容器进入 `Restarting` 循环。
  现在启动前会先 `rm -f` 这两个文件，并且把检测顺序改成「先看进程活着没有」
- **僵尸进程**：Chromium 会 fork 很多子进程，`init: true` 让 tini 收尸
- **沙箱**：容器里一般起不来，默认 `--no-sandbox`（官方默认也是关的）
- **中文字体**：不装 `fonts-noto-cjk` 的话中文页面是豆腐块，noVNC 里看着就是方块
- **窗口只占半屏**：容器里没有窗口管理器，Xvfb 只是块裸画布，Chromium 于是按自己的
  启发式挑窗口尺寸 —— 实测在 1920x1080 的屏上开了 **945x1060**，noVNC 里就是
  「只有左半边」。entrypoint 现在在 vnc 模式下显式传
  `--window-size=<屏宽>,<屏高> --window-position=0,0`。想自己指定就用
  `CHROME_ARGS="--window-size=1280,800"`，脚本检测到就不再覆盖

## 文件

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 两阶段：解 AppImage + 构建运行镜像，版本由 `ARG FP_VERSION` 控制 |
| `docker-compose.yaml` | 编排：端口、卷、shm、init、指纹环境变量 |
| `entrypoint.sh` | 启动逻辑：指纹装配、参数映射、CDP 桥接、vnc/headless 两种模式 |
| `fingerprint.example.json` | 指纹文件格式示例（和 CloakBrowser 共用字段） |
| `.env.example` | 全部可配项 |
