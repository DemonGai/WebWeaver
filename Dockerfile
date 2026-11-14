# WebWeaver 一体化镜像：数据库 + 后端 + 前端页面装在同一个容器里。
#
# 容器内三个东西：
#   1. PostgreSQL（数据落在挂载的卷上）
#   2. FastAPI（uvicorn，同时托管前端 dist）
#   3. docker CLI（通过挂进来的 /var/run/docker.sock 操作宿主机 Docker，
#      浏览器实例容器因此和本容器是「兄弟」，不是嵌套）
#
# 构建：docker compose build   或   docker build -t webweaver:latest .

# ── 前端构建 ──────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS web

WORKDIR /web
# 只拷 package.json：仓库里的 package-lock 是在 Windows 上生成的，里面没有
# @rollup / @esbuild 的 linux 二进制条目，npm ci 装完 rollup 会报 MODULE_NOT_FOUND。
# 让容器按自己的平台现场解析依赖。
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── docker CLI：静态二进制，直接拷进运行镜像 ──────────────────────────
FROM docker:27-cli AS dockercli

# ── 运行镜像 ──────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Debian bookworm 自带 PostgreSQL 15；数据库只监听 127.0.0.1，不对外
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    PGDATA=/var/lib/postgresql/data \
    FRONTEND_DIST=/app/frontend/dist \
    APP_PORT=8000

RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends \
        postgresql \
        postgresql-client \
        curl \
        ca-certificates \
        tzdata \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 容器里调 docker 靠这个（配合挂载的 docker.sock）
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

# 前端产物：FastAPI 用 FRONTEND_DIST 找到它
COPY --from=web /web/dist /app/frontend/dist

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY backend/ ./
COPY docker/entrypoint.sh /usr/local/bin/webweaver-entrypoint
RUN chmod +x /usr/local/bin/webweaver-entrypoint \
    && mkdir -p /app/backend/logs

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/webweaver-entrypoint"]
