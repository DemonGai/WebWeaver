# 注意：这里故意不写 `# syntax=docker/dockerfile:1.7`。
# 那行会让构建先去 docker.io 拉一个 12MB 的前端镜像，国内经常只有 20KB/s，
# 十几分钟都进不了真正构建。Docker 23+ 自带的 BuildKit 前端已经支持下面用到的
# `RUN --mount=type=cache`，不需要外拉。
#
# ─────────────────────────────────────────────────────────────────────
# CloakBrowser 内核镜像
#
# CloakBrowser 和 ungoogled-chromium 的区别不在「怎么启动」，而在「它需要什么
# 才能骗过人」——这两个差异决定了这个 Dockerfile 和隔壁那份不一样：
#
#   1. 它会伪装成 Windows，但字体来自宿主 Linux。字体对不上，字体指纹就是硬伤，
#      所以必须把真实的 Windows 字体装进镜像（见下面的 fonts/ 段）。
#   2. 有头模式下 WebGL 会因为软件渲染被 GPU blocklist 拦掉，必须加
#      --ignore-gpu-blocklist，这条写在 entrypoint.sh 里。
#
# 换版本只改这一个 ARG，目录名必须和 browser_engine/cloakbrowser/ 下的版本目录
# 完全一致（例如 146.0.7680.177.5）：
#
#   docker build --build-arg CLOAKBROWSER_VERSION=146.0.7680.177.5 -t wv-cb:146 .
#   CLOAKBROWSER_VERSION=146.0.7680.177.5 docker compose up -d --build
#
# 这个值同时决定两件事：COPY 哪份二进制、镜像打什么 tag。
# ─────────────────────────────────────────────────────────────────────
ARG CLOAKBROWSER_VERSION=146.0.7680.177.5
# 基础镜像和 apt 源都能换。默认走清华源，国内构建比 deb.debian.org 快一个数量级；
# 海外机器可以传 --build-arg APT_MIRROR=deb.debian.org 用官方源。
ARG BASE_IMAGE=debian:bookworm-slim
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

FROM ${BASE_IMAGE}

# FROM 之前声明的 ARG 在 FROM 之后要重新声明一次才可见
ARG CLOAKBROWSER_VERSION
ARG APT_MIRROR
# WITH_VNC=1 装 Xvfb + x11vnc + noVNC，可以用浏览器看实时画面；=0 只留 CDP
ARG WITH_VNC=1
ARG DEBIAN_FRONTEND=noninteractive

# com.webweaver.novnc：给后端判定「这个镜像能不能看画面」用。没有这个标签时后端
# 只能翻构建历史，有了它就是确定值（WITH_VNC=0 构建出来的镜像不该出现 noVNC 入口）
LABEL org.opencontainers.image.title="cloakbrowser" \
      org.opencontainers.image.description="CloakBrowser ${CLOAKBROWSER_VERSION} 反检测内核运行时" \
      org.opencontainers.image.version="${CLOAKBROWSER_VERSION}" \
      com.webweaver.novnc="${WITH_VNC}"

ENV CHROME_DIR=/opt/cloakbrowser \
    HOME=/home/browser \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    # CloakBrowser 官方的字体告警检查走 fc-list；容器里已经装好，不必再打印
    CLOAKBROWSER_SUPPRESS_FONT_WARNING=1

# ── 运行时依赖 ────────────────────────────────────────────────────────
# CloakBrowser 也是 Chromium，X11 / ATK / CUPS / ALSA / GBM 这几族一个都不能少。
# 字体这块按官方 README 的「基线层」装：
#   - fonts-noto-color-emoji：有些风控会在隐藏 canvas 上画 emoji 再哈希像素，
#     没有彩色 emoji 字体，所有实例算出来的哈希完全一样，等于自报家门
#   - fonts-wqy-zenhei / fonts-unifont：CJK 与兜底字形，否则中文页面是豆腐块
#   - libfontconfig1：fc-list / fc-cache 的前提
# 真正的 Windows 字体不在这里装 —— apt 拿不到（微软专有），见下一段。
#
# 先把 apt 源换掉再 update：bookworm 用的是 deb822 格式的 debian.sources，
# 老镜像才是 sources.list，两种都改一遍。
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
      [ -f "$f" ] || continue; \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" "$f"; \
    done; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl socat jq \
      libfontconfig1 fontconfig \
      fonts-liberation fonts-noto-cjk fonts-noto-color-emoji \
      fonts-freefont-ttf fonts-unifont fonts-wqy-zenhei \
      libasound2 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
      libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 \
      libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 \
      libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
      libxrandr2 libxshmfence1 libxss1 libxtst6 libxkbcommon-x11-0; \
    if [ "$WITH_VNC" = "1" ]; then \
      apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify dbus-x11 procps xauth; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# ── Windows 字体（CloakBrowser 专用，别删）───────────────────────────
# CloakBrowser 在 Linux 上默认伪装成 Windows（--fingerprint-platform=windows），
# 但字体集来自宿主系统。真实 Windows 装着 Segoe UI / Calibri / Marlett /
# Consolas 这些专有字体，Linux 上一个都没有 —— 字体指纹一抓一个准。
#
# 官方 README 明确说 apt 里的 ttf-mscorefonts-installer **不够**：它只有 XP 时代
# 那批（Arial/Times/Verdana…），缺的正是上面那几个最关键的。
# 所以这里改成从构建上下文 copy 你自己的 Windows 字体：
#
#   ./collect-windows-fonts.sh        # 在 Windows 上跑一次，从 C:\Windows\Fonts 复制
#   docker compose up -d --build
#
# fonts/ 目录在 .gitignore 里（微软字体不能重新分发），空目录也照常 build，
# 只是没有 Windows 字体、字体指纹仍然会露馅。
COPY fonts/ /usr/local/share/fonts/windows/

RUN fc-cache -f >/dev/null 2>&1 || true; \
    n=$(fc-list 2>/dev/null | grep -ciE "segoe|calibri|consolas|marlett" || true); \
    if [ "${n:-0}" -ge 4 ]; then \
      echo "[fonts] 已注册 ${n} 个 Windows 字体条目"; \
    else \
      echo "[fonts] 警告：没有检测到 Windows 字体（Segoe UI / Calibri / Consolas / Marlett）。"; \
      echo "[fonts] 伪装 Windows 时字体指纹会对不上，建议先在宿主机执行 ./collect-windows-fonts.sh"; \
    fi

# ── 内核本体 ──────────────────────────────────────────────────────────
# 目录名就是版本号，构建上下文是这个 Dockerfile 所在的目录。
#
# 这里刻意不用 COPY --chown：几百 MB、上千个文件逐个改属主，在 Windows + WSL2
# 上要多花好几分钟，而内核目录本来就只需要读权限（root:root 644/755 足够，
# 容器以 uid=1000 运行照样能读能执行）。真正需要写的只有 /data，见下面。
#
# 从 Windows 解压出来的文件会丢掉执行位（chrome 变成 644），必须显式补回来，
# 否则容器一起来就是 "Permission denied"。
COPY ${CLOAKBROWSER_VERSION}/ ${CHROME_DIR}/

RUN set -eu; \
    if [ ! -f "${CHROME_DIR}/chrome" ]; then \
      echo "构建失败：${CHROME_DIR}/chrome 不存在，检查版本目录 ${CLOAKBROWSER_VERSION} 是否完整" >&2; \
      ls -la "${CHROME_DIR}" >&2 || true; \
      exit 1; \
    fi; \
    chmod +x "${CHROME_DIR}/chrome"; \
    for f in chrome-wrapper chrome_crashpad_handler chromedriver; do \
      [ -f "${CHROME_DIR}/$f" ] && chmod +x "${CHROME_DIR}/$f" || true; \
    done; \
    if [ ! -x "${CHROME_DIR}/chrome" ]; then \
      echo "构建失败：${CHROME_DIR}/chrome 不可执行" >&2; \
      exit 1; \
    fi; \
    "${CHROME_DIR}/chrome" --version 2>&1 | head -3 || true

# ── 非 root 运行 ──────────────────────────────────────────────────────
# 固定 uid=1000：宿主机挂载 profile 目录时好对齐权限（-v ./data:/data 时
# 目录属主是 1000，容器里正好也是 1000，不会写出 Permission denied）
RUN groupadd -g 1000 browser 2>/dev/null || true \
 && useradd -m -u 1000 -g 1000 -s /bin/bash browser 2>/dev/null || true \
 && mkdir -p /data/profile /tmp/.X11-unix \
 && chmod 1777 /tmp/.X11-unix \
 && chown -R 1000:1000 /data "${HOME}"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER 1000:1000
WORKDIR /data

# 9222 = CDP（后端/Playwright 用），6080 = noVNC 网页，5900 = 原生 VNC
EXPOSE 9222 5900 6080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${CDP_PORT:-9222}/json/version" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
