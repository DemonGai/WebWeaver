# 注意：这里故意不写 `# syntax=docker/dockerfile:1.7`。
# 那行会让构建先去 docker.io 拉一个 12MB 的前端镜像，国内经常只有 20KB/s，
# 十几分钟都进不了真正构建。Docker 23+ 自带的 BuildKit 前端已经支持下面用到的
# `RUN --mount=type=cache`，不需要外拉。
#
# ─────────────────────────────────────────────────────────────────────
# fingerprint-chromium 内核镜像
#
# 这个内核和隔壁两个最大的不同：**官方 Linux 包只有 AppImage**（没有扁平目录）。
# AppImage 是「ELF 头 + squashfs」，运行时靠 FUSE 把自己挂载起来再执行 ——
# 容器里默认没有 FUSE，直接跑会报 "Cannot mount AppImage"。
#
# 所以这里走 multi-stage：先在一个临时阶段用 `--appimage-extract` 把 squashfs
# 解开（这条路径不碰 FUSE，直接读 squashfs），把 714MB 的 Chromium 目录取出来，
# 再拷进正式镜像。好处是最终镜像里既没有 188MB 的 AppImage，也没有解包残留。
#
# 换版本只改这一个 ARG，AppImage 文件名必须是
# fingerprint-chromium-<版本>*.AppImage（官方带 -1 / -1.1 这类打包序号，
# 所以这里用通配匹配后缀）：
#
#   docker build --build-arg FP_VERSION=148.0.7778.215 -t wv-fpc:148 .
#   FP_VERSION=148.0.7778.215 docker compose up -d --build
#
# 这个值同时决定三件事：COPY 哪份 AppImage、镜像 tag、容器名。
# ─────────────────────────────────────────────────────────────────────
ARG FP_VERSION=148.0.7778.215
# 基础镜像和 apt 源都能换。默认走清华源，国内构建比 deb.debian.org 快一个数量级；
# 海外机器可以传 --build-arg APT_MIRROR=deb.debian.org 用官方源。
ARG BASE_IMAGE=debian:bookworm-slim
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

# ── 阶段 1：拆 AppImage ───────────────────────────────────────────────
# 用同一个 base 镜像，不多拉任何东西：AppImage 的 runtime 只依赖 glibc，
# bookworm 的 2.36 足够。`--appimage-extract` 由 runtime 自己实现，不需要
# 装 squashfs-tools，也不需要 FUSE。
FROM ${BASE_IMAGE} AS unpack

ARG FP_VERSION

WORKDIR /tmp/fc
# 通配是为了兼容官方的 -1 / -1.1 / 无后缀三种命名
COPY fingerprint-chromium-${FP_VERSION}*.AppImage /tmp/fc/

RUN set -eu; \
    f="$(ls /tmp/fc/*.AppImage | head -1)"; \
    echo "[unpack] $(basename "$f")"; \
    chmod +x "$f"; \
    cd /opt; \
    "$f" --appimage-extract >/dev/null; \
    src=/opt/squashfs-root/opt/ungoogled-chromium; \
    if [ ! -x "${src}/chrome" ]; then \
      echo "构建失败：AppImage 里找不到 ${src}/chrome" >&2; \
      find /opt/squashfs-root -maxdepth 3 -name chrome -o -maxdepth 2 -type d >&2; \
      exit 1; \
    fi; \
    # 只留内核目录，usr/ 里只有图标，AppRun 用不上（启动逻辑我们自己在
    # entrypoint.sh 里写，AppRun 那三行本质就是设置两个环境变量再 exec chrome）
    mv "$src" /opt/chromium; \
    rm -rf /opt/squashfs-root /tmp/fc; \
    du -sh /opt/chromium; \
    ls /opt/chromium | head -20

# ── 阶段 2：运行镜像 ──────────────────────────────────────────────────
FROM ${BASE_IMAGE}

ARG FP_VERSION
ARG APT_MIRROR
# WITH_VNC=1 装 Xvfb + x11vnc + noVNC，可以用浏览器看实时画面；=0 只留 CDP
ARG WITH_VNC=1
ARG DEBIAN_FRONTEND=noninteractive

LABEL org.opencontainers.image.title="fingerprint-chromium" \
      org.opencontainers.image.description="fingerprint-chromium ${FP_VERSION} 指纹种子内核运行时" \
      org.opencontainers.image.version="${FP_VERSION}"

ENV CHROME_DIR=/opt/chromium \
    HOME=/home/browser \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai

# ── 运行时依赖 ────────────────────────────────────────────────────────
# 这份清单是 `ldd chrome` 的实测输出（这个包报 25 个 not found），不是照抄模板：
# 包里自带 libEGL.so / libGLESv2.so / libvulkan.so.1 / libvk_swiftshader.so，
# 所以 libgl1、libvulkan1 反而不用装。缺的是 X11、ATK/AT-SPI、CUPS、ALSA、
# GBM 这几族，外加一个容易被漏掉的 libexpat1（fontconfig 和 Chrome 自己都要）。
# libxtst6 / libxshmfence1 / libxss1 是 dlopen 的，ldd 看不出来，但少了会静默降级。
#
# 字体这层和 CloakBrowser 一样按「基线」装：
#   - fonts-noto-cjk：没有中文页面是豆腐块，noVNC 里看着就是一片方块
#   - fonts-noto-color-emoji：有些风控在隐藏 canvas 上画 emoji 再哈希像素，
#     没有彩色 emoji 字体，所有实例算出的哈希完全一致，等于自报家门
#   - fonts-unifont / fonts-wqy-zenhei：兜底字形，减少「缺字」这类破绽
# 真正的 Windows 字体不在这里（apt 拿不到），见下面的 fonts/ 段。
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
      fonts-unifont fonts-wqy-zenhei \
      libasound2 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
      libcairo2 libcups2 libdbus-1-3 libdrm2 libexpat1 libgbm1 libglib2.0-0 \
      libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 \
      libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
      libxrandr2 libxshmfence1 libxss1 libxtst6 libxkbcommon-x11-0; \
    if [ "$WITH_VNC" = "1" ]; then \
      apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify dbus-x11 procps xauth; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# ── Windows 字体（可选）─────────────────────────────────────────────
# fingerprint-chromium 从 Chrome 144 起内置字体指纹伪造（可用
# --disable-spoofing=font 关掉），所以**不装也不是硬伤**——这点和 CloakBrowser
# 不一样，那个官方明确要求真实字体。
#
# 但如果页面直接拿 canvas 量字形宽度，量到的还是容器里真实装着的字体，
# 补上会更稳。想补就把隔壁那套收集脚本的结果借过来：
#
#   cp -r ../cloakbrowser/fonts ./fonts     # 或者跑 ../cloakbrowser/collect-windows-fonts.sh
#   docker compose up -d --build
#
# fonts/ 在 .gitignore 里（微软字体不能重新分发），空目录（只有 .gitkeep）
# 也照常构建，只是没有 Windows 字体。
COPY fonts/ /usr/local/share/fonts/windows/

RUN fc-cache -f >/dev/null 2>&1 || true; \
    n=$(fc-list 2>/dev/null | grep -ciE "segoe|calibri|consolas|marlett" || true); \
    if [ "${n:-0}" -ge 4 ]; then \
      echo "[fonts] 已注册 ${n} 个 Windows 字体条目"; \
    else \
      echo "[fonts] 提示：没有检测到 Windows 字体，字体指纹交给内核的 font spoofing 处理"; \
    fi

# ── 内核本体 ──────────────────────────────────────────────────────────
# 从 unpack 阶段拿解包结果。刻意不用 COPY --chown：上千个文件逐个改属主，
# 在 Windows + WSL2 上要多花好几分钟，而内核目录只需要读权限（root:root
# 644/755 足够，容器以 uid=1000 运行照样能读能执行）。真正需要写的只有 /data。
COPY --from=unpack /opt/chromium/ ${CHROME_DIR}/

RUN set -eu; \
    if [ ! -f "${CHROME_DIR}/chrome" ]; then \
      echo "构建失败：${CHROME_DIR}/chrome 不存在" >&2; \
      ls -la "${CHROME_DIR}" >&2 || true; \
      exit 1; \
    fi; \
    chmod +x "${CHROME_DIR}/chrome"; \
    for f in chrome-wrapper chrome_crashpad_handler chromedriver; do \
      [ -f "${CHROME_DIR}/$f" ] && chmod +x "${CHROME_DIR}/$f" || true; \
    done; \
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${CDP_PORT:-9222}/json/version" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
