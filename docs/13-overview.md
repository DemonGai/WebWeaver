# 13 · 总览与指标口径

总览页（`/`）只做「基础设施健康」这一件事：实例、出口、账号、指纹。没有任务队列，
也没有调度器待办——自动化由使用者通过 CDP 接管。

## 1. 数据来源

一次 `GET /api/overview?range=7d` 取齐：

| 部分 | 来源 | 计算位置 |
|---|---|---|
| `cluster` | `browsers` / `accounts` / `ips` | `cluster.overview()` |
| `health_parts` | 四类资源的比率与均值 | `cluster._health_parts()` |
| `pool_status` | 实例状态计数 | `cluster.overview()` |
| `cards` | 账号 / 出口 / 指纹的汇总 | `cluster.overview()` |
| `instances` | 实例摘要（按状态优先级排序） | `_sorted_browsers()` + `_summary()` |
| `events` | 最近审计记录 | `audit.recent()` → `_event_of()` |
| `trend` / `trend_stats` | 审计活跃度分桶 | `audit.activity()` |

读的是 `Snapshot`（一次请求读 6 张业务表），不是逐项 SQL。

## 2. 健康分

总分 = 四个分项加权平均，权重相加 100：

| 分项 | 权重 | 口径 |
|---|---:|---|
| 实例可用性 | 45 | `(running + idle) / total` |
| 出口可用性 | 25 | `(ip_total - failed) / ip_total` |
| 账号健康度 | 20 | 全部账号 `health` 的算术平均 |
| 指纹覆盖 | 10 | `active / fp_total` |

分项颜色（`_grade`）：

| 分数 | 颜色 |
|---|---|
| ≥ 95 | 蓝（正常） |
| ≥ 85 | 绿 |
| ≥ 70 | 琥珀 |
| < 70 | 玫瑰（需要处理） |

前端「需要处理」取 `score < 90` 的分项，按 `HEALTH_HREF` 跳到对应页面。这样健康分不是
一个无法解释的数字：用户能看到哪一块拉低了总分、该去哪里修。

**没有数据时的口径**：分母为 0 的比率记 0，总分不会被「未配置」抬高。空集群显示 0 分，
页面给出「先到浏览器池新建一台」的空态。

## 3. 资源水位（6 格）

| 格 | 值 | 说明 |
|---|---|---|
| 账号会话 | `accounts_used / accounts_total` | 使用中的平台账号 / 总数 |
| 出口占用 | `ip_used / ip_total` | 被实例绑定的代理 / 总数 |
| 指纹模板 | `cards[fingerprints].value` | 模板总数 |
| 平均响应 | `avg_latency_ms` | 有 `latency_ms` 的实例平均 |
| noVNC 帧率 | `novnc_fps` | 有 `fps` 的实例平均 |
| 状态更新 | `updated_seconds` | 最近一次实例更新时间 |

> 延迟与帧率目前是占位读数：实例启动时写入 `30` 与 `18 + vnc_port % 40`，没有真实采集。
> 页面上的「平均响应」「帧率」只能作为界面演示，不要作为运维指标。

## 4. 趋势

- `range=24h`：24 个小时桶；
- `range=7d` / `30d`：按天分桶；
- 分桶在 Python 侧做（`audit.activity`），不用 SQL `date_trunc`：`occurred_at` 是
  `timestamptz`，SQL 按 UTC 截断会让东八区用户的「今天」整体偏移 8 小时；
- `series` = 操作总量，`companion` = 失败数；
- 横轴标签抽稀到 7 个刻度（`_tick_labels`），否则 30 个桶会糊成一片；
- `trend_stats`：操作总量 / 失败操作 / 活跃操作人。

## 5. 事件流

`events` 来自最近审计记录（`audit.recent`），每条映射成：

| 字段 | 规则 |
|---|---|
| `title` | `操作人 + 动作 + 资源名`；认证类没有资源名，主语换成操作人 |
| `tone` | 失败一律 `rose`；成功按动作危险程度取色 |
| `detail` | 优先 `error_message`，否则 `detail` |
| `tag` | 资源类型中文名 |
| `time` | 「3 分钟前」这类相对时间 |

不是独立的事件表，也不做持久化订阅。要接真实事件流，替换 `audit.recent` 的数据源即可，
接口形状不变。

## 6. 实例摘要

`instances` 按状态优先级排序：运行中 → 空闲 → 排队 → 异常 → 已停止；同状态按名字。
前端自己按 tab 过滤，不再为每个 tab 发一次请求——当前规模（几百台）一次下发更省事。

`_summary` 拼的字段：`id` / `name` / `status` / `group` / `account` / `ip` / `region` /
`fingerprint` / `fps` / `latency_ms` / `started_at` / `note`。都来自外键 join，不是硬编码。

## 7. 页面结构

四层，刻意做出主次：

1. **深色主卡**：健康分、在线 / 未运行、平均延迟、帧率、分段容量条；右栏「需要处理」
   与「其余分项」；
2. **一张卡 6 格**：资源水位，不做成一排同质小卡；
3. **活跃实例表 + 最近操作**：两栏等高（`xl:items-stretch`），标题 12.5px；
4. **趋势图**：置底，高度 128。

页头只有时间范围、自动刷新、导出报表；没有「新建实例」——总览是查看面，入口在浏览器池。
30 秒静默刷新，失败保留旧数据，不闪骨架。

## 8. 扩展建议

- 接真实监控：把 `fps` / `latency_ms` / 负载的占位值换成采集侧回写，**不要**在
  `cluster.overview` 里直接调外部系统；
- 接任务系统：先加任务表与接口，再在总览加「待办」区域；当前没有任务模型，不要先画 UI；
- 改健康分权重：只改 `_health_parts` 的 `weight`，前端自动跟随；权重和必须为 100；
- 新增分项：`HealthPart` 加一条，前端「需要处理」会自动包含它，记得补 `HEALTH_HREF` 映射；
- 新增趋势指标：在 `audit.activity` 增加序列，保持 `labels` / `series` / `companion` 同长度，
  否则图表会错位。
