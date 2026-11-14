# 注意：这里故意不写 `# syntax=docker/dockerfile:1.7`。
# 那行会让构建先去 docker.io 拉一个 12MB 的前端镜像，国内经常只有 20KB/s，
# 十几分钟都进不了真正构建。Docker 23+ 自带的 BuildKit 前端已经支持下面用到的
# `RUN --mount=type=cache`，不需要外拉。
#
# ─────────────────────────────────────────────────────────────────────
# ungoogled-chromium 内核镜像
#
# 换版本只改这一个 ARG，目录名必须和 browser_engine/ungoogled-chromium/ 下的
# 版本目录完全一致（例如 156.0.8078.79）：
#
#   docker build --build-arg CHROMIUM_VERSION=156.0.8078.79 -t wv-uc:156 .
#   CHROMIUM_VERSION=156.0.8078.79 docker compose up -d --build
#
# 这个值同时决定两件事：COPY 哪份二进制、镜像打什么 tag。
# ─────────────────────────────────────────────────────────────────────
ARG CHROMIUM_VERSION=156.0.8078.79
# 基础镜像和 apt 源都能换。默认走清华源，国内构建比 deb.debian.org 快一个数量级；
# 海外机器可以传 --build-arg APT_MIRROR=deb.debian.org 用官方源。
ARG BASE_IMAGE=debian:bookworm-slim
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

FROM ${BASE_IMAGE}

# FROM 之前声明的 ARG 在 FROM 之后要重新声明一次才可见
ARG CHROMIUM_VERSION
ARG APT_MIRROR
# WITH_VNC=1 装 Xvfb + x11vnc + noVNC，可以用浏览器看实时画面；=0 只留 CDP，镜像小约 90MB
ARG WITH_VNC=1
ARG DEBIAN_FRONTEND=noninteractive

# com.webweaver.novnc：给后端判定「这个镜像能不能看画面」用，取值跟 WITH_VNC 一致
LABEL org.opencontainers.image.title="ungoogled-chromium" \
      org.opencontainers.image.description="ungoogled-chromium ${CHROMIUM_VERSION} 内核运行时" \
      org.opencontainers.image.version="${CHROMIUM_VERSION}" \
      com.webweaver.novnc="${WITH_VNC}"

ENV CHROME_DIR=/opt/chromium \
    HOME=/home/browser \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai

# ── 运行时依赖 ────────────────────────────────────────────────────────
# 这份清单来自 `ldd chrome` 的实际输出，不是抄 Chromium 官方的模板：
# 包里带了 libEGL.so / libGLESv2.so / libvulkan.so.1，所以 libgl1、libvulkan1
# 反而不用装；缺的是 X11、ATK/AT-SPI、CUPS、ALSA、GBM 这几族。
# fonts-noto-cjk 不能省：容器里没有中文字体时，所有实例的字体指纹完全一致，
# 反而比不伪装更容易被风控识别。
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
      ca-certificates curl socat \
      fonts-liberation fonts-noto-cjk fonts-noto-color-emoji \
      libasound2 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
      libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 \
      libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 \
      libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
      libxrandr2 libxshmfence1 libxss1; \
    if [ "$WITH_VNC" = "1" ]; then \
      apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify dbus-x11 procps; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# ── 内核本体 ──────────────────────────────────────────────────────────
# 目录名就是版本号，构建上下文是这个 Dockerfile 所在的目录。
#
# 这里刻意不用 COPY --chown：767MB / 687 个文件逐个改属主，在 Windows + WSL2
# 上要多花好几分钟，而内核目录本来就只需要读权限（root:root 644/755 足够，
# 容器以 uid=1000 运行照样能读能执行）。真正需要写的只有 /data，见下面。
#
# 从 Windows 解压出来的文件会丢掉执行位（chrome 变成 644），必须显式补回来，
# 否则容器一起来就是 "Permission denied"。
COPY ${CHROMIUM_VERSION}/ ${CHROME_DIR}/

RUN chmod +x "${CHROME_DIR}/chrome" \
             "${CHROME_DIR}/chrome-wrapper" \
             "${CHROME_DIR}/chrome_crashpad_handler" \
             "${CHROME_DIR}/chromedriver" \
 && if [ ! -x "${CHROME_DIR}/chrome" ]; then \
      echo "构建失败：${CHROME_DIR}/chrome 不可执行，检查版本目录 ${CHROMIUM_VERSION} 是否完整" >&2; \
      exit 1; \
    fi \
 && "${CHROME_DIR}/chrome" --version > /tmp/ver.txt 2>&1 || true \
 && cat /tmp/ver.txt \
 && rm -f /tmp/ver.txt

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
