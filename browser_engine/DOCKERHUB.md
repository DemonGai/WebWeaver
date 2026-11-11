# Browser Engine

WebWeaver 使用的浏览器内核运行时镜像。每个镜像都是「一个 Chromium 内核 + CDP 远程调试端口 + 可选 noVNC 可视化界面」的组合，可以用 Playwright / Puppeteer 通过 `connectOverCDP` 直接接管，也可以打开网页看浏览器在做什么。

三个内核的差别在于**反检测的实现路线**，不是版本新旧。

## 镜像

| 内核 | 固定标签 | 体积 | CDP | noVNC | 特点 |
|---|---|---|---|---|---|
| ungoogled-chromium | `ungoogled-chromium-156.0.8078.79` | 529MB | 9222 | 6080 | 移除 Google 集成的纯净构建，无内置指纹伪装 |
| cloakbrowser | `cloakbrowser-146.0.7680.177.5` | 558MB | 9232 | 6082 | 一个整数 seed 派生全部硬件指纹 |
| fingerprint-chromium | `fingerprint-chromium-148.0.7778.215` | 521MB | 9242 | 6084 | 指纹参数最细，支持 canvas / 字体级伪装 |

不带版本号的同名标签（如 `cloakbrowser`）是滚动标签，始终指向该内核最近一次构建。**生产环境请钉死版本号**，滚动标签会被覆盖。

仅支持 `linux/amd64`。

## 快速开始

```bash
docker run -d --name ungoogled \
  -p 9222:9222 -p 6080:6080 \
  -e MODE=vnc -e SCREEN=1920x1080x24 \
  --shm-size=1g --init \
  demon1315132284/browser_engine:ungoogled-chromium-156.0.8078.79
```

带指纹的内核，把种子传进去即可：

```bash
docker run -d --name cloak \
  -p 9232:9222 -p 6082:6080 \
  -e MODE=vnc \
  -e FINGERPRINT_SEED=42817 \
  -e FINGERPRINT_PLATFORM=windows \
  -e FINGERPRINT_TIMEZONE=Asia/Shanghai \
  -e FINGERPRINT_LOCALE=zh-CN \
  --shm-size=1g --init \
  demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5
```

起来之后：

- 浏览器画面：<http://localhost:6082/vnc.html?autoconnect=1&resize=scale>
- 调试端点：<http://localhost:9232/json/version>

Playwright 接管：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9232")
    page = browser.contexts[0].pages[0]
    page.goto("https://example.com")
```

## 环境变量

三个镜像通用：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MODE` | `vnc` | `vnc` 开 Xvfb + x11vnc + noVNC；`headless` 只开 CDP，内存占用更低 |
| `SCREEN` | `1920x1080x24` | 虚拟屏分辨率，浏览器窗口会自动铺满 |
| `START_URL` | `about:blank` | 启动时打开的页面 |
| `CHROME_ARGS` | 空 | 追加的 Chromium 参数，如 `--proxy-server=socks5://1.2.3.4:1080` |
| `CHROME_NO_SANDBOX` | `1` | 容器内默认关沙箱 |
| `TZ` | `Asia/Shanghai` | 容器时区，影响 `Date` |

指纹相关（`cloakbrowser` / `fingerprint-chromium`）：

| 变量 | 说明 |
|---|---|
| `FINGERPRINT_SEED` | 指纹种子，10000–99999。同一种子每次启动结果完全一致 |
| `FINGERPRINT_PLATFORM` | `windows` / `macos` / `linux` |
| `FINGERPRINT_TIMEZONE` | 如 `Asia/Shanghai`，同时作用于 `Intl` 和 JS `Date` |
| `FINGERPRINT_LOCALE` / `_LANG` | 如 `zh-CN`，作用于 `navigator.language` 和 `Accept-Language` |
| `FINGERPRINT_FILE` | 改从 JSON 文件读全部字段，容器内路径如 `/data/fingerprint.json` |

两个内核的字段名一致，同一份 `fingerprint.json` 可以挂给两者做 A/B 对比。

## 注意事项

**镜像里不含 Windows 字体。** 微软字体不允许重新分发，所以字体指纹只能靠内核自身派生。需要真实字体覆盖时，在本地准备字体目录后自行构建镜像（构建文件见源码仓库 `browser_engine/`）。

**容器需要 `--shm-size=1g`。** 默认的 64MB `/dev/shm` 会让 Chromium 渲染进程崩溃，表现为页面白屏或标签页闪退。

**`MODE=vnc` 需要宿主有窗口可看。** 纯服务端部署用 `MODE=headless` 更省资源，CDP 功能完全一致。

**请只在获得授权的目标上使用。** 这些镜像用于自动化测试、兼容性验证和反爬策略研究。

三个内核都可以自行构建，`Dockerfile` / `entrypoint.sh` / `docker-compose.yaml` 随项目源码维护，
支持用 `ARG` 指定内核版本重编。
