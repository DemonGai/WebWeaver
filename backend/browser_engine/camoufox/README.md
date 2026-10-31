# Camoufox

基于 Firefox 的反检测内核，指纹在 C++ 实现层注入，不靠 JS 补丁。

## 怎么拿

两条路，档案里默认用第一条：

1. **官方便携包**（推荐，版本最明确）：从 GitHub Releases 下 `camoufox-<版本>-win.x86_64.zip`
2. **pip 通道**：`pip install camoufox` 后执行 `python -m camoufox fetch`

解压后**顶层目录就是内核根目录**，没有再套一层，直接整体放进 `<版本号>/`。

## 什么时候选它

- 需要一套非 Chromium 的指纹做对照：Chromium 系被识别得太明显时，Firefox 的行为特征完全不同
- 站点只做基础检测，不需要 Chromium 专属能力
- 机器内存紧张（每个实例约 200MB，而 Chromium 系 800MB 起）

## 什么时候别选

- 目标会校验 `window.chrome`、`navigator.userAgentData` 这类 Chromium 专属特征 —— Camoufox 伪装不出来，这本身就是破绽
- 要求商业 SLA 与稳定维护 —— 官方 README 自己写了「维护者长期缺位、可能不适合稳定生产」
- 需要大量并发 —— 每个上下文 200MB+，并发受内存限制比受目标限制更早

## 已知注意点

- 上游发的是 **beta 通道**（`-beta.NN`），档案登记版本号必须带后缀，否则找不到对应 release
- GeoIP 从 GeoLite2 换成了 AIO 源，老脚本里写死 GeoLite2 配置的会报错
- 包有 1.2GB，解压过程比较慢，安装任务给的进度是粗粒度的
