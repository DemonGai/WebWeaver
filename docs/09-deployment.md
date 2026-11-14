# 09 · 部署

## 1. 三种拓扑

| 拓扑 | 组成 | 适用 | 复杂度 |
|---|---|---|---|
| **单容器**（默认） | `webweaver` = PostgreSQL + uvicorn + 前端 dist + docker CLI | 单机、内网、演示与中小规模 | 低 |
| **分离部署** | 独立 PostgreSQL + 后端进程 + 静态站点 / Nginx | 已有数据库与反代，或需要独立扩缩容 | 中 |
| **开发** | PG 容器 + `uvicorn --reload` + Vite | 本机开发 | 低 |

单容器的关键不是「三个进程塞一起」，而是**实例容器是兄弟容器**：

```
宿主机 Docker
├── webweaver（本应用）
│     └── 挂载 /var/run/docker.sock
└── <实例 UUID>（浏览器）  ← 由 webweaver 里的 docker CLI 创建
```

`docker ps` 在宿主机上能直接看到实例容器。删除 `webweaver` 容器不会自动删除实例容器，
需要先在页面里删除实例（或手工 `docker rm -f`）。

## 2. 镜像构建

`Dockerfile` 三段：

1. **`node:22-bookworm-slim`**：`npm install` + `npm run build`，产出 `dist`。
   这里故意不用 `npm ci`：仓库里的 `package-lock.json` 在 Windows 上生成，缺
   `@rollup/rollup-linux-x64-gnu` 等平台条目，容器里 `npm ci` 会报 `MODULE_NOT_FOUND`。
   让容器按自己的平台现场解析依赖。
2. **`docker:27-cli`**：只取静态 `docker` 二进制，拷进运行镜像。
3. **`python:3.12-slim-bookworm`**：装 PostgreSQL 15（bookworm 自带）、curl、tini；
   拷前端 `dist` 与后端代码；`pip install -r requirements.txt`。

镜像约 830MB。构建时默认把 apt 源换成清华镜像，可用 `APT_MIRROR` / `PIP_INDEX_URL` 覆盖。

```bash
docker compose build                 # 或 docker build -t webweaver:latest .
docker compose up -d
```

## 3. 启动脚本

`docker/entrypoint.sh` 在容器启动时按顺序做：

1. 找 PostgreSQL 可执行目录（`/usr/lib/postgresql/*/bin`）；
2. `PGDATA` 为空目录时 `initdb`（`trust` 认证，只监听 127.0.0.1）；
3. 起 PostgreSQL，`pg_isready` 最多等 60 秒；
4. 设置数据库口令，库不存在则创建；
5. `alembic upgrade head`；
6. `python -m app.services.seed`（幂等：工作区、权限、角色、超管、四个内核登记）；
7. 起 `uvicorn --host 0.0.0.0 --port $APP_PORT --proxy-headers`；
8. 收到 SIGTERM：先停 uvicorn，再 `pg_ctl -m fast` 停库。

`tini` 作为 PID 1 负责转发信号与回收僵尸进程。

## 4. 环境变量

### 4.1 Compose 层

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_PORT` | `8000` | 宿主机端口，映射到容器内 8000 |
| `DB_NAME` / `DB_USER` | `webweaver` | 容器内数据库名与用户 |
| `DB_PASSWORD` | `webweaver` | **生产必改**；同时用于连接串 |
| `AUTH_JWT_SECRET` | 占位值 | **生产必改**，访问令牌签名密钥 |
| `NOVNC_HOST` | 空 | noVNC 地址里的主机名；空则跟随请求 Host |
| `DOCKER_SOCK` | `/var/run/docker.sock` | 宿主 Docker Socket 路径 |
| `PIP_INDEX_URL` | 清华源 | 构建期 pip 源 |
| `TZ` | `Asia/Shanghai` | 容器时区 |

> Compose 的 `environment` 是**显式列表**，宿主上的其他 `AUTH_*` 变量不会自动传进容器。
> 要改 `AUTH_COOKIE_SECURE`、`AUTH_ALLOW_REGISTER` 等，请在 `docker-compose.yml` 的
> `environment:` 里加一行，或用 `env_file:` 引入。

### 4.2 应用层（`backend/app/core/config.py`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_NAME` / `APP_VERSION` | `WebWeaver API` / `0.1.0` | 展示与 OpenAPI |
| `API_PREFIX` | `/api` | 所有业务接口前缀 |
| `DEBUG` | `true` | 调试开关（compose 里设 `false`） |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON 数组 |
| `DATABASE_URL` | `postgresql+asyncpg://webweaver:webweaver@127.0.0.1:5432/webweaver` | 异步连接串；entrypoint 会按 `DB_*` 覆盖 |
| `DB_ECHO` | `false` | 打印 SQL |
| `DB_AUTO_CREATE` | `false` | 启动时按模型建表；生产保持 false，交给 Alembic |
| `DB_POOL_DISABLED` | `false` | 关连接池；测试用 |
| `AUTH_ACCESS_TTL_MINUTES` | `30` | 访问令牌有效期 |
| `AUTH_REFRESH_TTL_MINUTES` | `10080`（7 天） | 刷新令牌 |
| `AUTH_REFRESH_TTL_REMEMBER_MINUTES` | `43200`（30 天） | 勾「记住我」 |
| `AUTH_ABSOLUTE_TTL_MINUTES` | `43200`（30 天） | 会话硬上限 |
| `AUTH_JWT_SECRET` | 开发占位值 | HS256 签名密钥 |
| `AUTH_COOKIE_SECURE` | `false` | HTTPS 必须 `true` |
| `AUTH_COOKIE_SAMESITE` | `lax` | 跨站部署时再评估 |
| `AUTH_COOKIE_DOMAIN` | 空 | 多子域共享登录时设置 |
| `AUTH_MAX_FAILED_LOGINS` | `5` | 连续失败锁定阈值 |
| `AUTH_LOCK_MINUTES` | `15` | 锁定时长 |
| `AUTH_ALLOW_REGISTER` | `true` | 正式环境建议 `false` |
| `AUTH_RESET_TTL_MINUTES` | `30` | 重置链接有效期 |
| `AUTH_EXPOSE_RESET_TOKEN` | `false` | 仅本地联调 `true`，生产必须 `false` |
| `LOG_DIR` | `logs` | 相对 `backend/` |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_DIAGNOSE` | `false` | 异常日志变量快照，含敏感数据时保持 false |
| `KERNEL_IMAGE_REGISTRY` | `demon1315132284/browser_engine` | 内核镜像仓库 |
| `KERNEL_DOCKER_BIN` | `docker` | docker 可执行文件 |
| `KERNEL_IMAGE_PULL_TIMEOUT` | `1800` | 单镜像拉取超时（秒） |
| `NOVNC_HOST` | 空 | noVNC 主机名 |
| `FRONTEND_DIST` | 空 | 前端 dist 目录；单容器设为 `/app/frontend/dist` |

`KERNEL_ROOT` / `KERNEL_PIP_INDEX` / `KERNEL_DOWNLOAD_MIRROR` 是旧磁盘方案遗留字段，
当前逻辑不再读写，保留只为兼容旧部署。

## 5. 数据与卷

| 数据 | 位置 | 备份方式 |
|---|---|---|
| 数据库 | 命名卷 `webweaver-appdata` → `/var/lib/postgresql/data` | `pg_dump` 或卷打包 |
| 实例 profile | 命名卷 `wv-data-<实例 ID>` → `/data` | 卷打包（按需） |
| 内核镜像 | 宿主 Docker 镜像库 | 重新 `docker pull` 即可 |
| 应用日志 | 容器内 `/app/backend/logs`（未挂卷） | 需要留存请自行挂载 |

`docker compose down` 保留卷；`docker compose down -v` 会删除 `appdata`，数据库一起没。

### 5.1 备份

```bash
# 逻辑备份（推荐）
docker exec webweaver pg_dump -h 127.0.0.1 -U webweaver -d webweaver -Fc > webweaver-$(date +%F).dump

# 卷备份（含数据库文件，需短暂停机一致性更好）
docker run --rm \
  -v webweaver-appdata:/data:ro \
  -v "$PWD":/backup \
  alpine tar czf /backup/appdata-$(date +%F).tgz -C /data .
```

### 5.2 恢复

单容器里 PostgreSQL 与应用同生命周期，不能只停应用；建议在维护窗口执行，先让所有客户端
停止操作：

```bash
# 1) 断开现有数据库连接，避免 DROP 被占用
docker exec webweaver psql -h 127.0.0.1 -U webweaver -d postgres -c \
  "select pg_terminate_backend(pid) from pg_stat_activity
   where datname = 'webweaver' and pid <> pg_backend_pid()"

# 2) 覆盖恢复
docker exec -i webweaver pg_restore \
  -h 127.0.0.1 -U webweaver -d webweaver --clean --if-exists < webweaver-2026-11-14.dump

# 3) 应用连接池有 pre_ping，下个请求会自动重连；不放心就重启容器
docker compose restart webweaver
```

`--clean --if-exists` 会先删对象再重建；恢复前确认备份来自兼容的 schema 版本。
恢复后 `alembic_version` 也在备份里，若版本落后，重启时 `alembic upgrade head` 会继续升级。

### 5.3 重置

```bash
docker compose down -v          # 删容器 + 数据卷
docker compose up -d --build    # 重新初始化：admin/admin + 四个内核登记
```

实例容器与 `wv-data-*` 卷不会被这条命令清理，需要另行处理。

## 6. 升级

```bash
cd webweaver
git pull
docker compose up -d --build
```

- 启动时自动跑迁移与 seed（幂等），不需要手工执行；
- 升级前先备份（`pg_dump`）；
- 迁移只向前，Alembic 脚本都有 `downgrade`，但回滚版本意味着同时回滚代码；
- 镜像只有 `latest`，要保留旧版本请自行打 tag：

```bash
docker tag webweaver:latest webweaver:backup-20261114
```

回滚：`git checkout <旧提交>` → `docker compose up -d --build`，必要时
`alembic downgrade <revision>`（先备份）。

## 7. 反向代理与 HTTPS

控制台是普通 HTTP + SPA，没有 WebSocket（noVNC 是独立端口的 iframe），Nginx 只需转发
HTTP 并保留 Host：

```nginx
server {
    listen 443 ssl;
    server_name wv.example.com;

    ssl_certificate     /etc/nginx/certs/wv.crt;
    ssl_certificate_key /etc/nginx/certs/wv.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

配置要点：

- `proxy_set_header Host $host`：noVNC 地址默认跟随请求 Host，丢了它画面地址会变成
  `127.0.0.1`；
- 或显式设 `NOVNC_HOST=wv.example.com`，不依赖 Host；
- HTTPS 时设 `AUTH_COOKIE_SECURE=true`，否则 Cookie 仍会在 http 下发送；
- **noVNC 是 `http://<host>:<port>`**：控制台走 HTTPS 时，浏览器会按混合内容拦截 iframe。
  需要给 noVNC 端口单独加 TLS 反代，或把控制台放在 http 内网。当前代码不支持同源路径代理。
- 实例端口（6080+ / 9180+）是动态的，逐个反代不现实；更实际的做法是内网直连 +
  防火墙限制来源。

## 8. 安全基线

- [ ] `AUTH_JWT_SECRET` 用随机 64 位 hex；`DB_PASSWORD` 换掉默认值
- [ ] 登录后改掉 `admin` 密码；`AUTH_ALLOW_REGISTER=false`
- [ ] **不要直接把 8000 暴露到公网**：读接口目前匿名可读（见 [04](04-auth-rbac.md#84-接口侧的实际用法)），
      至少加反代认证 / IP 白名单
- [ ] HTTPS + `AUTH_COOKIE_SECURE=true`
- [ ] 限制 `6080+` / `9180+` 端口来源
- [ ] 只挂载必要的宿主路径；`docker.sock` 等于宿主 root
- [ ] 定期备份 `webweaver-appdata`
- [ ] 不把 `.env`、dump、证书提交进仓库

## 9. 资源与容量

| 项 | 参考 |
|---|---|
| 应用镜像 | ~830MB |
| 单个内核镜像 | 500–560MB |
| 每个实例 | 200–500MB 内存（视页面与内核），`--shm-size=1g` |
| 数据库 | 万级审计记录约几十 MB |
| 建议主机 | 2 vCPU / 4GB 起；每增加 3–5 个实例加 1GB 内存 |
| 磁盘 | 系统 + 镜像 + 卷，建议 ≥ 40GB |

PostgreSQL 与应用同容器，CPU / 内存没有独立限额；实例多时建议拆开部署。

## 10. 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| 容器 `unhealthy` | `/api/health` 不通 / 启动未完成 | `docker logs webweaver --tail 100`；首次启动需等迁移 |
| 8000 被占用 | 宿主已有服务 | 改 `APP_PORT=8010` 之类，或停掉占用进程 |
| 启动日志 `找不到 PostgreSQL 可执行文件` | 镜像构建异常 | 重新构建；检查 `PGBIN` |
| `initdb` 权限错误 | 卷属主不是 postgres | `docker compose down -v` 重建，或修卷权限 |
| 页面能开但接口 502 | uvicorn 未起 / 端口不对 | 看日志里 `Uvicorn running on` |
| 容器内 `docker: permission denied` | socket 权限 / 未挂载 | 确认挂载；Linux 上把容器用户加入 docker 组或用 root |
| 构建卡在 apt | 网络到镜像源慢 | 换 `APT_MIRROR` / 代理；重试 |
| 构建卡在 npm install | npm registry 慢 | 配 `npm config set registry https://registry.npmmirror.com` 后重建 |
| noVNC 打不开 | 端口未发布 / 防火墙 / 镜像无 VNC | 从宿主 `curl http://127.0.0.1:<port>/vnc.html` 验证 |
| 时间显示差 8 小时 | 浏览器时区 vs 服务端 UTC | 数据存 UTC 是设计；展示由前端本地化 |

常用命令：

```bash
docker compose ps
docker compose logs -f webweaver
docker exec -it webweaver sh
docker exec webweaver psql -h 127.0.0.1 -U webweaver -d webweaver -c '\dt'
docker inspect webweaver --format '{{json .State.Health}}'
```
