# 12 · 资源池：账号 / 代理 / 指纹

三个资源池的共同点：都是「给实例绑定的外部条件」，都有导入 / 校验 / 健康度；不同点是
账号与代理目前**没有删除接口**，指纹有完整的增删改与下发链路。

## 1. 账号池

### 1.1 数据与状态

表 `accounts`，一条记录是一个平台账号：

| 字段 | 说明 |
|---|---|
| `login_url` | 登录页地址（用户填），平台由它推导 |
| `platform` | 推导值，不手工指定 |
| `username` / `email` / `password_encrypted` | 登录名、邮箱、加密后的密码 |
| `cookies` | JSON 数组，导入时可带；详情接口返回 |
| `status` | `logged_in` / `in_session` / `restricted` / `unbound` |
| `health` | 0–100 |
| `region` / `group_id` / `note` | 归属与备注 |
| `registered_at` / `last_login_at` | 时间信息 |

唯一键是 `(login_url, username)`：同一个登录页下账号名不能重复；不同站点可以有同名账号。

### 1.2 平台识别

`services/platforms.py`，**不发网络请求**：

1. 取主机名的注册域主体：`sellercentral.amazon.co.uk` → `amazon`；
2. 查内置映射（Amazon / Shopify / TikTok / Meta / Shopee / eBay / 淘宝 / 天猫 / Temu 等）；
3. 未收录的域名把主体首字母大写当平台名（`mysite.example` → `Example`），不返回「未知」。

`GET /api/accounts/detect?login_url=` 返回 `{login_url, platform, known}`，`known=false`
表示走了兜底命名。URL 不合法返回 422。

### 1.3 导入

`POST /api/accounts/import`，body `{text, overwrite}`。解析规则：

- 每行一条，跳过空行与 `#` 注释；
- 分隔符：制表符 > 逗号 > 分号 > 竖线；没有分隔符时整行当一个字段（会失败）；
- 列序：`login_url, username, email, region, health, note`；
- 表头可省略；中文列名与常见别名（账号 / 用户名 / 邮箱 / 地区 / 备注 / url 等）都认；
- 去重键 `(login_url, username)`；同一批内重复直接跳过；
- `overwrite=false`：已存在则跳过，提示「勾选覆盖可更新」；
- `overwrite=true`：只更新 `email` / `region` / `health` / `note`，**保留 Cookie、状态与绑定关系**
  ——重新导一份名单不该把已采集的登录态冲掉；
- Cookie 接受数组或 Playwright `storage_state` 整个对象（`{"cookies": [...]}`），上限 500 条。

返回 `{created, updated, skipped, failed, rows[]}`，`rows` 只回失败/跳过行及原因。

### 1.4 状态与健康

- 新建时 `status` 不传：有 Cookie 视为 `logged_in`，否则 `unbound`；
- `in_session` 表示账号正被实例使用；`restricted` 表示平台风控/受限；
- `health` 由用户或后续采集维护，总览的「账号健康度」是全部账号的算术平均。

### 1.5 与实例的关系

`browsers.account_id` 指向账号；一个账号同时只应绑定一台实例。写操作在
`browser_pool._ensure_free` 里检查占用，接口层返回 409 并说明被哪台实例占用。
绑定/解绑会写 `browser_account_bindings` 流水。

### 1.6 接口

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/accounts` | 匿名（已知缺口） |
| GET | `/api/accounts/template` | 匿名 |
| GET | `/api/accounts/detect` | 匿名 |
| GET | `/api/accounts/{id}` | 匿名（含明文 Cookie） |
| POST | `/api/accounts` | `account:create` |
| PATCH | `/api/accounts/{id}` | `account:update` |
| POST | `/api/accounts/import` | `account:create` |

**没有删除接口**：账号可能已经产生审计与绑定历史，当前设计不允许直接删。需要清理时先解绑，
再评估是否直接改库（并自行承担审计断链的后果）。

## 2. 代理池

### 2.1 数据

表 `ips`：

| 字段 | 说明 |
|---|---|
| `address` / `port` | 代理地址与端口；`port=0` 用协议默认端口 |
| `protocol` | `http` / `https` / `socks5` |
| `kind` | `residential` / `datacenter` / `mobile` |
| `supplier` / `country_code` / `region` / `city` | 归属信息 |
| `username` / `password` | 认证信息，**明文存储**（前端要复制带认证的地址） |
| `latency_ms` / `health` / `status` | 探测结果 |
| `expires_at` / `last_checked_at` | 到期与检测时间 |

唯一键 `(address, port)`。

> `ips.password` 是明文，这是为了「复制 `socks5://user:pass@host:port`」这个使用场景。
> 不要把这张表当密码库复用；导出/备份要按敏感数据处理。

### 2.2 导入格式

`POST /api/ip-pool/import`，body `{text, default_kind, default_supplier, overwrite}`。

支持的写法（按优先级）：

1. **带表头**：`ip,port,protocol,username,password,type,supplier,country,region,city`，列序可换；
2. **URL**：`socks5://user:pass@host:port`、`http://host:port`；
3. **CSV 全列**：≥6 列时按模板列序硬对；
4. **位置约定**：`host:port[:protocol][:user[:pass]][:type][:supplier][:country][:region][:city]`。

冒号形式的密码不能含冒号（有歧义）；密码含冒号请用 CSV 或 URL。字段缺失时用
`default_kind` / `default_supplier` 兜底。

### 2.3 可达性检测

`POST /api/ip-pool/check`：对全部代理跑一轮 TCP 连接（4 秒超时，并发 16），回写：

- 成功：`latency_ms` = 握手耗时，`health=100`；之前 `failed` 的恢复 `available`；
  占用中的 `in_use` 不动（它还被实例绑着）；
- 失败：`latency_ms=null`，`health -= 25`；`available` 且 `health<=50` 才标 `failed`
  ——住宅代理常有抖动，一次失败就判死太激进。

写一条审计（`resource_type=ip`）。检测只验证端口可达，不验证认证与出口地区。

### 2.4 与实例的关系

`browsers.ip_id` + `ip_mode=proxy` 表示走代理；`ip_mode=direct` 表示直连（`ip_id` 为空）。
绑定时 `browser_runtime.proxy_argument()` 拼 `--proxy-server`：

```
protocol://[user:pass@]host:port
```

IPv6 会加方括号。绑定/解绑写 `browser_ip_bindings`，直连也写一条 `mode=direct` 的流水，
`resolved_address` 记录当时的出口地址快照。

### 2.5 接口

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/ip-pool` | 匿名（已知缺口，含代理口令） |
| GET | `/api/ip-pool/template` | 匿名 |
| POST | `/api/ip-pool/import` | `ip:create` |
| POST | `/api/ip-pool/check` | `ip:update` |

同样**没有删除/编辑接口**；需要改单条代理时目前只能重新导入（`overwrite=true`）或改库。

## 3. 指纹库

### 3.1 能力矩阵（唯一权威）

`services/fingerprint_caps.py` 定义每个内核认哪些参数。传错名字不会报错——Chromium 只是
忽略不认识的参数，表面正常、指纹没生效。所以下发前必须按内核查表。

| 能力 | CloakBrowser | fingerprint-chromium | ungoogled-chromium | Camoufox |
|---|---|---|---|---|
| 指纹补丁 | 有 | 有 | 无 | 无（无镜像） |
| 统一入口 | `--fingerprint=<n>` | `--fingerprint=<n>` | — | — |
| 时区 | `--fingerprint-timezone` | `--timezone` | — | — |
| 界面语言 | `--fingerprint-locale` + `--lang` | `--lang` | — | — |
| Accept-Language | — | `--accept-lang` | — | — |
| 平台版本 / 品牌 | — | ✓ | — | — |
| 硬件并发 | — | ✓ | — | — |
| 单独关噪声 | — | `--disable-spoofing=canvas,audio,gpu` | — | — |
| seed 范围 | 10000–99999 | 1–2147483647 | — | — |

`GET /api/fingerprints/capabilities` 返回 `kernel_id` / `slug` / `supported` / `seed_range` /
`features` / `note` / `reason`。前端据此决定表单字段显隐，不硬编码。

### 3.2 seed 的语义

`seed` 是一个整数，内核用它派生整套人格（GPU、canvas、音频、字体…）。同一个 seed 在不同
内核上**算出的具体人格不同**（两套补丁算法不同），跨内核搬迁只能保证「换个人」，不能保证
「还是同一个人」。

- CloakBrowser 的 seed 范围 10000–99999；
- fingerprint-chromium 是 1–2147483647；
- 留空时新建可以后补，采集前必须填。

### 3.3 平台族与伪移动

`platform_family`：`windows` / `macos` / `linux` / `android` / `ios`。
内核没有真正的移动平台档位：`android` / `ios` 会被映射到最接近的桌面族，靠 `mobile`
字段在 entrypoint 里覆盖 UA / 视口 / DPR。这是**伪移动**：`navigator.platform` 与 Client
Hints 仍是桌面，页面会明确提示边界，不要宣称「真手机」。

### 3.4 采集（probe）

`POST /api/fingerprints/{id}/probe`：

1. `docker run -d --rm -e MODE=vnc -e FINGERPRINT_SEED=... -p 127.0.0.1:0:9222 <image>`；
2. `docker port` 拿宿主机随机端口；
3. `GET /json/list` 找页面 target 的 WebSocket；
4. `Runtime.evaluate(COLLECT_JS)` 一次性读回 UA、屏幕、GPU、语言、canvas hash 等；
5. `docker rm -f` 清理。

用 `MODE=vnc` 而不是 headless：headless 没有虚拟屏，`screen.width/height` 报 800×600，
与实际运行时的 Xvfb 1920×1080 对不上。镜像没有 VNC 时降级 headless 并写告警。

结果写 `probe`（完整人格 JSON）、`probed_at`、`probed_digest`（下发参数摘要）；参数改了但
没重采，摘要对不上，页面提示实测值过期。失败写 `probe_error`，成功清空。

### 3.5 下发（apply）

`POST /api/fingerprints/{id}/apply {"instance_ids": [...]}`：

1. 按实例 ID 找容器（容器名 = 实例 ID）；
2. 检查容器环境变量里是否有 `FINGERPRINT_*`：有就直接拒绝，因为 entrypoint 的取值顺序是
   「环境变量 > 指纹文件」，写文件等于没写；
3. `docker cp` 写 `/data/fingerprint.json`；
4. `docker restart`，等容器重新 running（上限 60 秒）；
5. 逐台返回 `ok` / `message` / `restarted` / `ignored`。

profile 在 `/data` 卷上，重启不丢登录态。运行中的实例也可以下发，但会短暂中断画面。

### 3.6 状态与唯一性

- `code` 唯一，留空时按平台族 + 种子自动生成；
- `status`：`active` / `needs_upgrade` / `expired`；
- `uniqueness`：0–100，无法评估时为空；
- `warning`：异常提示文案；
- 一条指纹可绑定多台实例；`browsers.fingerprint_mode=template` 时才生效，
  `default` 表示用原生指纹。

### 3.7 接口

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/fingerprints` | 匿名（已知缺口） |
| GET | `/api/fingerprints/capabilities` | 匿名 |
| GET | `/api/fingerprints/options` | 匿名 |
| GET | `/api/fingerprints/{id}` | 匿名 |
| POST | `/api/fingerprints` | `fingerprint:create` |
| PATCH | `/api/fingerprints/{id}` | `fingerprint:update` |
| DELETE | `/api/fingerprints/{id}` | `fingerprint:delete` |
| POST | `/api/fingerprints/{id}/probe` | `fingerprint:update` |
| POST | `/api/fingerprints/{id}/apply` | `fingerprint:update` |

## 4. 前端页面

| 页面 | 交互 |
|---|---|
| `/accounts` | 统计条、平台筛选、搜索；卡片展示状态/健康度/绑定实例；新建/编辑弹窗；粘贴导入并展示逐行结果；详情看 Cookie |
| `/ip-pool` | 地区/供应商聚合；表格展示地址、协议、类型、延迟、健康度、绑定实例；导入；一键检测；密码显示/隐藏与复制 |
| `/fingerprints` | 列表 + 能力筛选；新建/编辑按能力动态显隐字段；抽屉展示下发参数、实测人格、采集与下发 |

## 5. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 账号导入全失败 | 用了冒号分隔（账号解析只认制表符/逗号/分号/竖线） | 改用逗号分隔或下载模板 |
| 平台识别成 `Example` | 域名不在内置映射里 | 正常兜底；需要新增映射改 `platforms.py` |
| 覆盖导入后 Cookie 没了 | 误以为覆盖会更新 Cookie | 覆盖只更新 email/region/health/note，Cookie 保留；清空要显式 PATCH `cookies:null` |
| 代理检测全失败 | 端口填错 / 供应商白名单未加本机 IP | 先 `nc -vz host port` 验证；补白名单 |
| 一次检测后代理变 failed | 健康度掉到 50 以下 | 再检测一次成功即可回到 100 |
| 指纹采集失败 | 镜像没有 VNC / 容器起不来 / CDP 超时 | 看 `probe_error`；`docker logs` 临时容器 |
| 指纹下发被拒绝 | 容器带 `FINGERPRINT_*` 环境变量 | 去掉环境变量并按新参数重建实例 |
| 下发成功但指纹没变 | 内核不支持 / seed 未生效 | 查能力矩阵；看容器日志里打印的生效参数 |
