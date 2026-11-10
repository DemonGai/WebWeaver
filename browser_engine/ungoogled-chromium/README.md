# ungoogled-chromium 内核容器

把 `browser_engine/ungoogled-chromium/` 下的某个版本目录打包成可运行的容器。
目录结构很简单，**版本号就是文件夹名，也是构建参数**：

```
ungoogled-chromium/
├── Dockerfile
├── docker-compose.yaml
├── entrypoint.sh
├── .env.example
├── .dockerignore
└── 156.0.8078.79/          <- Linux x64 内核本体（chrome / *.pak / *.so）
    ├── chrome
    ├── chrome-wrapper
    └── ...
```

以后加新版本，直接把解压好的目录放进来，不需要改任何文件：

```
157.0.8100.1/
```

## 从 Docker Hub 直接拉（跳过本地构建）

镜像已推到 [`demon1315132284/browser_engine`](https://hub.docker.com/r/demon1315132284/browser_engine)，
一个内核一个 tag：

| tag | 内容 |
|---|---|
| `ungoogled-chromium-156.0.8078.79` | 固定版本，可复现 |
| `ungoogled-chromium` | 滚动标签，始终指向该内核最近一次构建 |

```bash
docker pull demon1315132284/browser_engine:ungoogled-chromium-156.0.8078.79
```

不用 compose 也能直接跑：

```bash
docker run -d --name wv-ungoogled \
  -p 9222:9222 -p 6080:6080 \
  -e MODE=vnc \
  -e START_URL=about:blank \
  --shm-size=1g --init --restart unless-stopped \
  -v "$PWD/data:/data" \
  demon1315132284/browser_engine:ungoogled-chromium-156.0.8078.79
```

`--shm-size=1g` 不能省（默认 64MB 会让渲染进程随机崩）。

想继续用 compose 里的端口/卷配置、只是不本地构建：把 `docker-compose.yaml`
的 `build:` 整段删掉，`image:` 改成上面那个名字，再 `docker compose up -d`。

## 构建与运行

```bash
cd browser_engine/ungoogled-chromium

# 默认版本
docker compose up -d --build

# 指定版本
CHROMIUM_VERSION=157.0.8100.1 docker compose up -d --build

# 或者写进 .env 长期生效
cp .env.example .env && vi .env
```

`CHROMIUM_VERSION` 同时决定四件事：COPY 哪份二进制、镜像 tag、
容器名、profile 挂载目录。所以多版本不会互相覆盖镜像。

### 构建慢的时候

默认 apt 走清华源（`APT_MIRROR=mirrors.tuna.tsinghua.edu.cn`），比 `deb.debian.org` 快一个数量级。
海外机器或公司内网有代理时换掉：

```bash
APT_MIRROR=deb.debian.org docker compose build
# 或者阿里云
APT_MIRROR=mirrors.aliyun.com docker compose build
```

**如果还是慢，瓶颈一般不在 apt，而在 767MB 的 COPY。** 三个可换的方向：

1. **给 Docker 配镜像加速**（Docker Desktop → Settings → Docker Engine 里加
   `"registry-mirrors"`，填阿里云/腾讯云给你的专属加速地址）。这一步只影响拉取
   基础镜像，对 COPY 无效，但第一次构建能省几分钟。
2. **把内核目录搬到 WSL2 内部**。Docker Desktop 用 WSL2 后端时，`G:\` 是 9p 挂载，
   逐文件读很慢；放到 `\\wsl$\Ubuntu\home\...` 下构建会快好几倍。
3. **不用 Dockerfile 的 COPY，改成 `docker cp`**：先用小镜像起容器，再把二进制
   拷进去 `docker commit`。折腾，一般不推荐。

正常情况下 apt 一两分钟、COPY 两三分钟就能出镜像。如果卡在 COPY 十几分钟不动，
基本可以确定是 Windows 文件系统这一层的问题，按第 2 条处理。

### 同时跑两个版本

compose 的服务名是固定的，同项目下再 `up` 会把上一个容器删掉。要用不同的项目名：

```bash
CHROMIUM_VERSION=156.0.8078.79 docker compose -p uc156 up -d --build
CHROMIUM_VERSION=157.0.8100.1 CDP_HOST_PORT=9223 NOVNC_HOST_PORT=6081 \
  docker compose -p uc157 up -d --build
```

## 两种模式

**默认走 `vnc`** —— 这个项目需要人工看浏览器界面（过验证码、登录、确认代理通不通），
没有画面基本没法用。

| MODE | 说明 | 端口 |
|---|---|---|
| `vnc`（默认） | Xvfb 虚拟屏 + x11vnc + noVNC，浏览器里能看实时画面 | 9222 + 6080 |
| `headless` | 无界面，只开 CDP，给后端 / Playwright 跑自动化 | 9222 |

启动后直接开：

```
http://localhost:6080/vnc.html?autoconnect=1&resize=scale
```

只想跑自动化、省掉 Xvfb 那套：

```bash
MODE=headless docker compose up -d
```

## 后端怎么连

**这里有个必须知道的坑**：Chromium 从 143 起不再认 `--remote-debugging-address=0.0.0.0`，
实测 156 无论如何都只绑 `127.0.0.1:9222`，容器外（宿主机、后端、别的容器）一律连不上。

所以 entrypoint 里做了端口桥接：Chrome 监听内部的 `127.0.0.1:9223`，
用 socat 把 `0.0.0.0:9222` 转过去。走这条路还顺带绕过了 DevTools 的 Host 头校验，
而且 `/json/version` 返回的 `webSocketDebuggerUrl` 会跟随请求的 Host 头，
所以外面拿到的 `ws://` 地址是可直接连的（已实测）。

后端不再本地 launch，而是接管一个已经在跑的浏览器：

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = (await browser.new_context()).new_page()
    await page.goto("https://example.com")
```

验证端口通不通：

```bash
curl http://127.0.0.1:9222/json/version
# 应该返回 Chrome/156.0.8078.79 和 ws://... 地址
```

`MODE=headless` 时同理，只是没有画面。

## 几个容器里跑 Chromium 的坑（都已在配置里处理）

- **执行位丢失**：从 Windows 解压出来的 `chrome` 是 644，Dockerfile 里显式 `chmod +x`
- **只绑 localhost**：Chromium 143+ 忽略 `--remote-debugging-address`，用 socat 桥接（见上一节）
- **profile 被锁**：容器重建后 hostname 变了，Chromium 认为 profile 被别的机器占用会直接退出，
  entrypoint 每次启动前清掉 `SingletonLock/Cookie/Socket`
- **restart 后 Xvfb 起不来（崩溃循环）**：`docker restart` / `docker compose restart`
  **不会重建容器**，`/tmp` 里的东西还在 —— 上次的 `/tmp/.X99-lock` 和
  `/tmp/.X11-unix/X99` 残留，Xvfb 第二次启动直接报
  `Server is already active for display 99` 退出；如果就绪检测先看 socket 再看进程，
  残留的 socket 会让循环立刻放行，于是 x11vnc 连不上、Chrome 报
  `Missing X server or $DISPLAY`，容器进入 `Restarting` 循环。现在启动前会先
  `rm -f` 这两个文件，并把检测顺序改成「先看进程活着没有」
- **`/dev/shm` 太小**：默认 64MB 会让渲染进程随机崩，compose 里设了 `shm_size: 1gb`，
  启动参数也加了 `--disable-dev-shm-usage`
- **字体缺失**：不装中文字体的话所有实例字体指纹一致，反而更容易被风控识别，
  镜像里装了 `fonts-noto-cjk`
- **僵尸进程**：Chromium 会 fork 很多子进程，`init: true` 让 tini 收尸
- **沙箱**：容器内一般起不来，默认 `--no-sandbox`；要保留就用 `CHROME_NO_SANDBOX=0`
- **窗口只占半屏**：容器里没有窗口管理器，Xvfb 只是块裸画布，Chromium 于是按自己的
  启发式挑窗口尺寸 —— 实测在 1920x1080 的屏上开了 **945x1060**，noVNC 里就是
  「只有左半边」。`MODE=vnc` 时 entrypoint 现在显式传
  `--window-size=<屏宽>,<屏高> --window-position=0,0`，实测窗口 1919x1079 正好铺满。
  想自己指定就用 `CHROME_ARGS="--window-size=1280,800"`，检测到就不再覆盖

日志里那串 `Failed to connect to the bus` 是容器没有 systemd/dbus 的常态，不影响使用。

## 镜像大小

| 配置 | 实测 |
|---|---|
| 默认（WITH_VNC=1） | 2.07 GB |
| `WITH_VNC=0`（只留 CDP） | 约 1.2 GB |

内核本身 767MB，Debian slim + Chromium 运行时依赖约 450MB。
剩下的 900MB 基本都花在 noVNC 那套上：Debian 的 `novnc` 包会拖进
python3、numpy、PIL、oslo 一整串依赖。如果只跑自动化、不需要看画面，
用 `--build-arg WITH_VNC=0` 能砍掉将近一半体积。
