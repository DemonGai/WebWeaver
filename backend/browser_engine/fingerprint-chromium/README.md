# fingerprint-chromium

基于 ungoogled-chromium 的指纹定制构建，主打「指纹可指定、结果可复现」。

## 怎么拿

GitHub Releases 直接下 Windows 便携包：

```
ungoogled-chromium_<版本>-1.1_windows_x64.zip
```

解压后主程序是 `chrome.exe`，位于包顶层目录，整体放进 `<版本号>/` 即可。Linux 有 tar.xz 与 AppImage，但安装器目前只解压 zip。

## 什么时候选它

- 要复现某个站点的拦截问题 —— 固定指纹种子，每次结果一致，问题能稳定重现
- 内网 / 离线环境 —— 有完整便携包，不像 CloakBrowser 必须联网拉二进制
- 需要一个不带 Google 依赖的干净 Chromium 做基线对照

## 什么时候别选

- 目标风控很强 —— 这套是编译期指纹补丁，强度不如商业级源码补丁内核
- 要求版本跟 Chromium 主线同步 —— 更新节奏跟随作者个人，当前在 150.x

## 已知注意点

- 上游**没有公示 sha256**，控制台只能校验下载完整性（体积、zip 结构），校验不了来源一致性；要严格校验就自己下一份算哈希填进档案
- 便携包不写注册表，删目录即卸载
- 和 ungoogled-chromium 的资产名很像（都叫 `ungoogled-chromium_*`），别从索引站抓错包
