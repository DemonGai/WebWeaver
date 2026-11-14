# 05 · 实例运行时

## 1. 一个实例是什么

实例 = **数据库一行 `browsers`** + **一个 Docker 容器** + **一个命名卷** + **一对发布端口**。

| 组成 | 值 | 说明 |
|---|---|---|
| 容器名 | `str(browser.id)` | 就是 UUID，`docker ps` 与页面 ID 对得上 |
| 容器标签 | `webweaver.instance=<id>` | 不依赖名字前缀，能筛出本系统管理的容器 |
| 数据卷 | `wv-data-<id>` → `/data` | profile、指纹文件、seed 文件都在这里 |
| noVNC | 宿主 `6080` 起顺延 → 容器 `6080` | `http://<host>:<port>/vnc.html?autoconnect=1&resize=scale` |
| CDP | 宿主 `9180` 起 → 容器 `9222` | `http://<host>:<cdp_port>`，Playwright `connectOverCDP` |
| 镜像 | `<registry>:<slug>-<version>` | 解析规则见 [06 内核池](06-kernels.md) |

为什么容器名用 ID 而不是实例名：

1. Docker 只接受 `[a-zA-Z0-9][a-zA-Z0-9_.-]*`，实例名允许中文，`docker run` 会直接拒绝；
2. 实例可以改名，容器名跟着改就得迁移容器；用 ID 改名不影响运行中的容器。

代价是名字不可读，排查时要在页面上用 ID 徽标对照。`IdBadge` 点击可复制完整 ID。

## 2. `docker run` 的实际参数

`backend/app/services/browser_runtime.py`：

```bash
docker run -d \
  --name <实例 UUID> \
  --label webweaver.instance=<实例 UUID> \
  -p <宿主 CDP>:9222 \
  -p <宿主 noVNC>:6080 \
  -e MODE=vnc \
  -e SCREEN=1920x1080x24 \
  -e CHROME_ARGS=--proxy-server=<协议://认证@host:port>   # 仅代理模式
  --shm-size=1g \
  --init \
  -v wv-data-<实例 UUID>:/data \
  <image_ref>
```

- `MODE=vnc` 才会装 Xvfb + x11vnc + noVNC；只跑自动化可以改 `headless`，但当前应用固定用
  `vnc`，因为 noVNC 是产品能力。
- `--shm-size=1g`：Chromium 多进程默认 `/dev/shm` 太小会崩。
- `--init`：避免 Chromium 的子进程留下僵尸。
- 代理认证内联进 URL；IPv6 地址会加方括号。Socks5 的认证在部分内核版本上会被忽略，
  这是内核侧限制。

## 3. 启动流程

```
校验内核 / 出口 / 指纹
  → 看容器是否已在跑（Docker 是事实）
      ├─ 在跑：读真实发布端口，只回写库，不重建
      ├─ 已停止：端口若仍空闲就沿用，否则重新分配
      └─ 不存在：分配一对端口，docker run
  → 等容器进入 running（上限 40 秒）
  → 有指纹模板：写 /data/fingerprint.json 并重启一次
  → 写回 status=running / started_at / cdp_url / vnc_url / vnc_port
```

顺序是刻意的：**先起容器，再落库**。反过来的话，容器失败会留下一个自称运行中的实例，
用户点进去连不上，还要手工纠正。

## 4. 端口分配

`browser_pool._allocate_ports()`：

1. 从 `VNC_PORT_BASE = 6080` 开始；
2. CDP 端口 = VNC + `CDP_PORT_OFFSET = 3100`（即 9180 起）；
3. 同时满足三个条件才采用：
   - 不在数据库里已被其他实例占用的 `vnc_port` 中；
   - 宿主机上 VNC 和 CDP 都没有人监听；
   - 不在 `docker ps` 已发布的宿主端口里（容器内 `bind` 看不到宿主端口）；
4. 最多扫描 200 个端口，失败返回 409。

`_port_free()` 在 Windows 上不能只用 `bind`：docker-proxy 用 `SO_REUSEADDR`，纯 `bind`
会把已占用端口误判为空闲。所以先 `connect_ex` 探是否有监听，再 `bind` 兜底。

**库里的端口不是真相**。容器可能被手工起过、端口被改过，所以：

- 启动 / 重启后都用 `docker port` 读真实发布端口并回写；
- 停止时清空 `vnc_port` / `cdp_url` / `vnc_url`；
- noVNC 是否可接管看 `vnc_port` 是否有值，而不是只看 `status`。

## 5. 状态机与一致性

```
                 start                stop
  stopped ───────────────► running ───────────► stopped
     ▲                        │  ▲
     │       restart          │  │ 容器丢失后 restart = 重建
     └────────────────────────┘  └──────────────
```

| 动作 | 语义 | 幂等性 |
|---|---|---|
| `start` | 容器在跑就复用；不在就重建（卷保留） | 重复调用不会重建运行中的容器 |
| `stop` | `docker stop -t 10`；容器本来不在也算成功 | 是 |
| `restart` | 容器在：`docker restart`（保留创建参数）；不在：按当前配置重建 | 是 |
| `delete` | 必须先是 stopped（否则 409）；删容器，**保留卷** | 容器不存在也继续删库 |

数据库状态是容器的**投影**，不是唯一真相：

- 停止失败不改状态（「界面显示已停止、容器还在跑」是最坏的一种谎）；
- 启动时如果发现容器已在运行，以 Docker 的真实端口为准，不重新分配；
- 容器被外部删掉后，点「重启」会走重建分支。

`fps` / `latency_ms` 目前是占位读数（`30` 与 `18 + vnc_port % 40`），真实值要等画面通道
接入采集后回写。总览的负载与趋势也不是实时监控数据。

## 6. noVNC

### 6.1 能不能接管由镜像决定

三个内核镜像的 Dockerfile 都有 `ARG WITH_VNC`，`=1` 装 Xvfb + x11vnc + noVNC，`=0` 只留
无头内核，6080 上根本没有服务。所以先问镜像，再看实例在不在跑。

判定顺序（`browser_novnc.detect`）：

1. 镜像标签 `com.webweaver.novnc`（新镜像写 `1` / `0`）——最可靠；
2. 镜像层历史里出现 `novnc` / `websockify`——老镜像没有标签，但装包层还在；
3. 都不满足 → 不支持，并给出原因。

结果按镜像引用缓存在进程内；重新拉取镜像后由 `forget()` 清掉。

### 6.2 四种可接管状态

| `availability` | 含义 | 用户下一步 |
|---|---|---|
| `ready` | 镜像支持且容器在跑 | 直接看画面 |
| `stopped` | 镜像支持，但实例没启动（`vnc_port` 为空） | 启动实例 |
| `unsupported` | 镜像没有 noVNC | 换内核或重建镜像 |
| `blocked` | 缺内核 / 本地没有该版本镜像 | 去内核管理拉取 |

不可接管时，接口返回 `reason`，前端原地展示，不给出一个点进去必然白屏的入口。

### 6.3 地址与 Host

```python
base_url(host, port) = f"http://{host}:{port}/vnc.html?autoconnect=1&resize=scale"
```

Host 解析优先级：

1. `settings.novnc_host`（环境变量 `NOVNC_HOST`）；
2. 请求的 `request.url.hostname`；
3. `127.0.0.1`。

用请求 Host 是为了从另一台机器打开控制台时，画面地址也指向同一台宿主机。反代 / 跨机
部署请显式设 `NOVNC_HOST`。

> **HTTPS 限制**：地址固定按 `http://` 拼。控制台走 HTTPS 时，浏览器会把 `http://` 的
> iframe 当作混合内容拦截。解决方式：给 noVNC 端口加 TLS 反代，或把控制台也放在 http
> 内网。当前代码没有同源路径代理。

## 7. 指纹下发

内核只在**启动时**读一次指纹参数（entrypoint 拼 chrome 参数），没有热更新。所以流程是：

```
docker cp fingerprint.json <容器>:/data/fingerprint.json
docker restart <容器>
等容器重新 running（上限 60 秒）
```

- 文件里的字段由 `fingerprint_caps.render()` 按内核能力矩阵生成，参数名不通用；
- profile 在 `/data` 上，重启不丢登录态；
- **环境变量会遮蔽文件**：entrypoint 的顺序是「环境变量 > 指纹文件」。如果容器启动时带了
  `-e FINGERPRINT_SEED=...`，写文件等于没写。`fingerprint_apply` 会先检查环境变量，有冲突
  直接拒绝，并告诉用户去掉环境变量或按新参数重建容器。
- 启动时装配失败会删掉容器并回滚，不留一台「看着在跑、其实没套模板」的实例。

## 8. 指纹采集

`fingerprint_probe` 起一个**临时容器**，让内核自己把人格跑出来：

```bash
docker run -d --rm \
  -e MODE=vnc -e FINGERPRINT_SEED=<seed> \
  -p 127.0.0.1:0:9222 \
  <image>
docker port <name> 9222        # 宿主机随机端口，避开 9222 被占
GET  http://127.0.0.1:<port>/json/list
WS   Runtime.evaluate(COLLECT_JS)
docker rm -f <name>
```

- 端口用 `127.0.0.1:0` 让 Docker 分配，绑定回环，不把带指纹的浏览器暴露到局域网；
- 用 `MODE=vnc` 而不是 headless：headless 没有虚拟屏，`screen.width/height` 会报 800×600，
  与实际运行时的 Xvfb 1920×1080 对不上，等于白采；
- 镜像没有 VNC 时降级到 headless，并把差异写进告警，不装作没差；
- 采集结果写 `fingerprints.probe`、`probed_at`、`probed_digest`；参数改了摘要就对不上，
  页面提示实测值已过期。

## 9. CDP 接管

库里的 `cdp_url` 是 `http://127.0.0.1:<宿主端口>`，面向「后端 / 浏览器在同一台机器」的场景。
从别的机器接管时，用宿主 IP 替换：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://192.168.1.10:9181")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://example.com")
```

- 一个实例一个 CDP，端口与 noVNC 一起分配；
- 不要同时让两个人接管同一实例：页面导航、Tab 开关会互相打架；
- 需要多开请新建实例，而不是在同一个 CDP 上开多个 context 绕开隔离。

## 10. 排障

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 启动报「端口分配失败」 | 6080–6280 被占满 | 释放端口，或清理无用实例容器 |
| 启动报镜像不存在 | 本地没有该版本镜像 | 内核管理页拉取，或把实例版本改为「跟随当前」 |
| 启动成功但 noVNC 白屏 | 镜像 `WITH_VNC=0`；或端口漂移 | 看 `docker logs <ID>`；确认镜像标签；重启回写端口 |
| noVNC 页显示「待启动」但容器在跑 | 库里的 `vnc_port` 为空（被外部改过） | 点一次重启，会回写真实端口 |
| 容器起来就退出 | 内核启动参数错误 / 镜像损坏 | `docker logs <ID> --tail 100`，按提示修 |
| 指纹没生效 | 环境变量遮蔽文件；内核不支持 | 查 `docker inspect` 的 `FINGERPRINT_*`；看能力矩阵 |
| 删除实例报 409 | 实例还在运行 | 先停止再删除 |
| 卷越积越多 | 删除实例保留卷是设计行为 | 用 `docker volume ls` 过滤 `wv-data-`，确认后手工清理 |

常用命令：

```bash
docker ps -a --filter label=webweaver.instance
docker inspect <实例 ID> --format '{{json .Config.Env}}'
docker port <实例 ID>
docker logs <实例 ID> --tail 100
docker volume ls | grep wv-data-
```
