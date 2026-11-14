# 06 · 内核池

## 1. 两个数据源

| 数据 | 来源 | 作用 |
|---|---|---|
| **台账** | `kernels` 表 | 名称、引擎、当前生效版本、通道、通过率、仓库地址 |
| **版本真相** | 本地 `docker image ls` | 有哪些版本、多大、什么时候构建、架构 |

代码里没有「已登记但未下载」这种中间态：镜像在就算可用，不在就是未获取。
`backend/browser_engine/` 下的目录只保存镜像构建源码与说明文档，**不再参与版本判定**。

## 2. 镜像命名

仓库由 `KERNEL_IMAGE_REGISTRY` 指定，默认 `demon1315132284/browser_engine`。

```
<registry>:cloakbrowser                    滚动 tag，指向该内核最近一次构建
<registry>:cloakbrowser-146.0.7680.177.5   固定 tag，钉死一个版本
<registry>:fingerprint-chromium-148.0.7778.215
<registry>:ungoogled-chromium-156.0.8078.79
```

- slug 由内核名推导：`CloakBrowser → cloakbrowser`（小写、非字母数字转 `-`）。
- 滚动 tag 会被下次构建覆盖，**生产应钉固定版本**。
- 镜像只提供 `linux/amd64`。Camoufox 还没有镜像，页面标记「暂未支持」。

版本号优先读镜像的 OCI 标签 `org.opencontainers.image.version`，缺失时才从 tag 名里切。
滚动 tag 的名字里没有版本号，只能靠标签。

## 3. 扫描与合并

`kernel_scan.scan_versions()`：

1. `docker image ls` 一次列出 registry 下所有镜像；
2. 按 slug 解析 tag（从长到短匹配，避免 `fingerprint-chromium` 被 `chromium` 截走）；
3. 按 `image_id` **去重**：同一个镜像常同时挂着滚动 tag 和固定 tag，合并成一条版本，
   `tags` 收全部 tag；
4. 首选引用优先用固定 tag（滚动 tag 不适合钉住）；
5. 版本号按数字/字母分段比较排序（`148.0.7778.9 < 148.0.7778.10`），从新到旧。

合并后的 `KernelVersion` 字段：

| 字段 | 说明 |
|---|---|
| `version` / `tag` / `image_ref` | 版本号、首选 tag、完整镜像名 |
| `image_id` / `digest` / `size` / `created_at` | 镜像元数据 |
| `rolling` / `pinned` / `tags` | 是否有滚动 tag / 固定 tag / 全部 tag |
| `current` / `instances` | 是否当前生效版本、多少实例钉在这个版本 |

## 4. 内核卡片

`kernel_pool.payload()` 把台账与镜像拼成 `KernelCard`：

| 字段 | 含义 |
|---|---|
| `installed` | 本地至少有一个该内核的镜像 |
| `current_version` | 台账里的 `kernels.version`；为空或本地缺失时退到最新可用 |
| `current_ref` | 当前版本对应的完整镜像名，复制 `docker run` 命令用 |
| `latest_version` | 本地最新可用版本 |
| `update_available` | `latest > current` |
| `stale_count` | 还留在旧版本上的实例数 |
| `version_count` / `total_size` | 版本数量与镜像合计体积 |
| `docker_ok` / `docker_error` | Docker 不可用时页面顶部直接说明原因 |

`ENGINE_SPECS` 里还有展示用配色、定位语与「手工跑容器」的示例端口
（CloakBrowser 9232/6082、fingerprint-chromium 9242/6084、ungoogled 9222/6080）。
这些端口只用于文档示例；应用创建的实例端口由 `6080 + 3100` 规则动态分配，
见 [05 运行时](05-browser-runtime.md#4-端口分配)。

## 5. 拉取镜像

`POST /api/kernels/{slug}/install`，body 三选一：

```json
{"version": "146.0.7680.177.5"}   // 自动拼 <registry>:<slug>-<version>
{"tag": "cloakbrowser-146.0.7680.177.5"}  // 也接受完整仓库名
{}                                 // 拉滚动 tag
```

实现要点（`kernel_install.py`）：

- `docker pull` 用 `asyncio.to_thread` 包同步子进程（Windows 事件循环限制）；
- 任务放模块级字典，**内存态**，进程重启即丢；最多保留 20 条，超出先清已完成的；
- 并发固定为 1（`asyncio.Semaphore(1)`）：500MB 起的层，并发会把带宽和磁盘 IO 打满；
- 进度按「已完成层数 / 已知层数」估算，非 TTY 下没有进度条，早期总层数还不完整；
- 拉取成功后：
  1. `browser_novnc.forget()` 清掉该镜像的 noVNC 能力缓存；
  2. `kernel_pool.adopt_pulled(slug, version)` 校正悬空台账（见下）。

接口先写审计再开工：审计失败就直接返回，不留一个悄悄在跑的后台任务。Docker 不可用返回
503，参数不合法返回 400。

## 6. 切版本与迁移

### 6.1 切当前版本

`POST /api/kernels/{id}/version {"version": "..."}`

- 只改 `kernels.version` 指针，**旧镜像不删**；
- 旧实例不动，继续留在原版本（`stale`）；
- 写审计（`resource_type=kernel`，`changes` 记录前后版本）；
- 目标版本必须在本地已安装，否则 400。

### 6.2 批量迁移

`POST /api/kernels/{id}/migrate {"version": "...", "browser_ids": []}`

- `browser_ids` 为空 = 该内核下所有**不在目标版本**的实例；
- 只改 `browsers.kernel_version`，**不重启容器**；运行中的实例要下次重启才用新镜像；
- 返回 `migrated` 数量；
- 写一条 `resource_type=browser` 的审计，`resource_id` 是内核 ID（一次操作影响多台）。

`GET /api/kernels/{id}/instances?stale=true&version=...` 是迁移弹窗的候选清单：

- `stale=true` 只看不在当前版本上的；
- `version=` 只看指定版本的。

### 6.3 实例如何解析镜像

`browser_runtime.resolve_image(kernel, browser.kernel_version)`：

1. 实例钉了版本 → 必须找到该版本，找不到报错并列出本地现有版本；
2. 实例没钉版本 → 用台账 `kernel.version`；若该版本本地缺失（种子/历史数据悬空），
   **退到最新可用镜像**并记 warning；
3. 一个镜像都没有 → 报「先到内核管理拉取」。

第 2 条是为了避免「页面显示 156、启动却报缺 124」这种口径打架。

### 6.4 拉取后的台账校正

`adopt_pulled()`：拉取成功后，如果台账登记的版本本地已不存在，就改成当前最新已装版本。
登记版本仍然装着时不动——那可能是用户特意选的旧版本。

> 当前 seed 写入的四个内核登记**版本为空**，页面的「当前版本」直接由本地镜像扫描得出。
> `adopt_pulled` 主要服务老库和手工改过台账的场景。

## 7. 内核镜像源码

`browser_engine/` 下每个引擎一个目录：

```
browser_engine/cloakbrowser/
├── Dockerfile
├── entrypoint.sh
├── docker-compose.yaml
├── fonts/                  # Windows 字体，字体指纹需要
├── fingerprint.example.json
├── README.md               # 内核管理详情页的正文
└── <version>/              # 实际二进制（不入库）
```

### 7.1 构建参数

三个 Dockerfile 共同的参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `WITH_VNC` | `1` | `1` 装 Xvfb + x11vnc + noVNC；`0` 只留 CDP |
| `BASE_IMAGE` | `debian:bookworm-slim` | 基础镜像 |
| `APT_MIRROR` | `mirrors.tuna.tsinghua.edu.cn` | 海外构建可换官方源 |
| 版本参数 | 各引擎不同 | `CLOAKBROWSER_VERSION` / `FP_VERSION` / `CHROMIUM_VERSION` |

镜像标签：

```dockerfile
LABEL org.opencontainers.image.version="${...}"
LABEL com.webweaver.novnc="${WITH_VNC}"
```

`com.webweaver.novnc` 是后端判定 noVNC 能力的第一依据；`WITH_VNC=0` 构建的镜像不会出现
noVNC 入口。

### 7.2 entrypoint 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MODE` | `vnc` | `vnc` 起虚拟屏与 noVNC；`headless` 只留 CDP |
| `SCREEN` | `1920x1080x24` | 虚拟屏分辨率 |
| `CDP_PORT` | `9222` | 容器内 CDP 端口 |
| `NOVNC_PORT` | `6080` | 容器内 noVNC 端口 |
| `START_URL` | `about:blank` | 启动页 |
| `USER_DATA_DIR` | `/data/profile` | profile 目录（在卷上） |
| `FINGERPRINT_FILE` | `/data/fingerprint.json` | 指纹文件 |
| `FINGERPRINT_*` | 空 | 环境变量形式的指纹参数，**优先级高于文件** |
| `CHROME_ARGS` | 空 | 追加给 Chromium 的原始参数，空格分隔 |

### 7.3 构建与推送

```bash
cd browser_engine/cloakbrowser
CLOAKBROWSER_VERSION=146.0.7680.177.5 docker compose up -d --build

# 打固定 tag 与滚动 tag
docker tag webweaver/cloakbrowser:146.0.7680.177.5 \
  demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5
docker tag webweaver/cloakbrowser:146.0.7680.177.5 \
  demon1315132284/browser_engine:cloakbrowser
docker push demon1315132284/browser_engine:cloakbrowser-146.0.7680.177.5
docker push demon1315132284/browser_engine:cloakbrowser
```

`browser_engine/DOCKERHUB.md` 是镜像仓库的说明页，包含三个内核的差异、体积、端口与
最小运行示例。

## 8. 限制与已知问题

- 只有 `linux/amd64`；Apple Silicon 上通过 Rosetta 跑，性能与稳定性未验证。
- 拉取任务无断点续传、无持久化、并发 1；进程重启后任务丢失，但已拉完的层仍在，重新拉
  会复用缓存。
- `docker pull` 的进度是估算值，层数在下载初期不完整，进度可能回退或跳变。
- 切版本不会自动迁移实例，也不会重启实例；需要显式迁移 + 重启。
- 删除镜像没有接口；需要手工 `docker rmi`，删除前先确认没有实例钉在该版本。
- Camoufox 只有台账登记，没有镜像；新建实例时会被标记为不支持。

## 9. 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| 内核页显示 `docker_ok=false` | 容器内没有 docker CLI 或 socket 未挂载 | 检查 `/var/run/docker.sock` 与 `KERNEL_DOCKER_BIN` |
| 拉取一直 0% | 网络到 registry 不通；层太大 | 看 `docker pull` 日志；配置镜像加速 |
| 拉取成功但版本列表没变 | 前端缓存 / 扫描未刷新 | 点「重新扫描」；确认 tag 前缀是 slug |
| 页面「当前版本」与实例实际不符 | 实例钉了 `kernel_version` | 看实例详情；迁移或清空版本跟随当前 |
| 启动报「本地没有 X 版本」 | 实例钉的版本已被删 | 迁移到现有版本，或重新拉取 |
| 滚动 tag 拉下来版本号是 `latest` | 镜像缺 OCI 版本标签 | 重建镜像时补 `org.opencontainers.image.version` |
