#!/bin/sh
# 一体化容器的启动脚本：起 PostgreSQL → 跑迁移 → 初始化 → 起 uvicorn。
#
# 设计取向：
#   * 数据库只监听 127.0.0.1，容器外连不上，端口也不映射出去；
#   * 数据落在 PGDATA（compose 里挂命名卷），重建容器不丢；
#   * 迁移与 seed 都在启动时跑，seed 幂等，重复启动是安全的；
#   * 收到 SIGTERM 先优雅停 uvicorn，再让 PostgreSQL 做一次干净 shutdown。
set -eu

PGBIN=${PGBIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
PGDATA=${PGDATA:-/var/lib/postgresql/data}
DB_NAME=${DB_NAME:-webweaver}
DB_USER=${DB_USER:-webweaver}
DB_PASSWORD=${DB_PASSWORD:-webweaver}
DB_PORT=${DB_PORT:-5432}
APP_PORT=${APP_PORT:-8000}
BACKEND_DIR=${BACKEND_DIR:-/app/backend}

export PGDATA
export DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}}
export FRONTEND_DIST=${FRONTEND_DIST:-/app/frontend/dist}

log() { echo "[webweaver] $*"; }

if [ ! -x "$PGBIN/postgres" ]; then
    log "找不到 PostgreSQL 可执行文件（PGBIN=$PGBIN），镜像构建有问题"
    exit 1
fi

mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql

# ── 首次启动：初始化数据库目录 ────────────────────────────────────────
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    log "初始化数据库目录：$PGDATA"
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    # 只监听回环，认证用 trust：容器内除了本进程没人能连，密码只用于拼连接串
    su postgres -c "$PGBIN/initdb -D '$PGDATA' -U '$DB_USER' --auth-local=trust --auth-host=trust -E UTF8 --locale=C"
else
    chown -R postgres:postgres "$PGDATA" 2>/dev/null || true
fi

# ── 起 PostgreSQL（日志直接进容器 stdout） ────────────────────────────
log "启动 PostgreSQL（port=$DB_PORT）"
su postgres -c "exec $PGBIN/postgres -D '$PGDATA' \
    -c listen_addresses=127.0.0.1 \
    -c port=$DB_PORT \
    -c timezone=Asia/Shanghai \
    -c logging_collector=off" &

ready=0
i=0
while [ $i -lt 60 ]; do
    if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" -q; then
        ready=1
        break
    fi
    i=$((i + 1))
    sleep 1
done
if [ "$ready" -ne 1 ]; then
    log "数据库在 60 秒内没起来，退出"
    exit 1
fi

# ── 库与口令 ──────────────────────────────────────────────────────────
psql_super() {
    psql -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 "$@"
}

psql_super -c "ALTER USER \"$DB_USER\" WITH PASSWORD '$DB_PASSWORD'" >/dev/null

if [ "$(psql_super -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")" != "1" ]; then
    log "创建数据库 $DB_NAME"
    psql_super -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\""
fi

# ── 迁移 + 初始化数据 ─────────────────────────────────────────────────
cd "$BACKEND_DIR"
log "应用数据库迁移"
alembic upgrade head

log "写入初始化数据（工作区 / 权限 / 超管）"
python -m app.services.seed

# ── uvicorn ───────────────────────────────────────────────────────────
log "启动 API 与页面：http://0.0.0.0:$APP_PORT"
uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" --proxy-headers &
APP_PID=$!

shutdown() {
    log "收到停止信号，正在关闭……"
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
    su postgres -c "$PGBIN/pg_ctl -D '$PGDATA' -m fast -w stop" >/dev/null 2>&1 || true
    log "已停止"
    exit 0
}
trap shutdown TERM INT

wait "$APP_PID"
