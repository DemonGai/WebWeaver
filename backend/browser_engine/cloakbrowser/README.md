# CloakBrowser

基于 Chromium 源码级补丁的反检测内核，官方定位是「Playwright / Puppeteer 的 drop-in 替代」。

## 怎么拿

二进制不在 PyPI 包里，要单独下载。Windows x64 直接取官方 release 的 zip：

```
https://github.com/CloakHQ/cloakbrowser/releases/download/chromium-v{版本}/cloakbrowser-windows-x64.zip
```

解开后根目录就是 Chromium（`chrome.exe` 在根下），整体放进本目录的 `<版本号>/` 即可，控制台的「安装」按钮做的就是这件事。

其他平台没有可预测的 zip 地址，走官网的包管理器：

```bash
pip install cloakbrowser==0.5.10
python -m cloakbrowser install     # 拉二进制到 ~/.cloakbrowser
```

这台机器上实测：官方 CLI 是**单连接**下载，跑到 30 KB/s，536MB 要 5 小时；后台改成 16 连接后约 20 分钟。所以优先用上面的 zip 直链。

## 什么时候选它

- 目标站点会查指纹一致性（Cloudflare Turnstile、reCAPTCHA v3、FingerprintJS）
- 现有脚本就是 Playwright，想换内核但不想改代码
- 需要 humanize 这类拟人化行为

## 什么时候别选

- 完全离线、不能联网拉二进制 → 先在一台有网机器上装好，再把缓存目录拷过来
- 需要完全可复现的固定指纹 → 换 `fingerprint-chromium`
- 目标只认 Firefox 系指纹 → 换 `camoufox`

## 已知注意点

- Free / Pro 两档，Pro 需要 `license_key`，能力不一样，别拿 Free 的成绩去对标官方宣传数据
- **免费通道拉到的二进制是 Chromium 146.x**，PyPI 页面上写的 151.x 是 Pro 通道的版本；档案里登记的是免费通道实际下载的版本
- 二进制版本可以用 `CLOAKBROWSER_VERSION` 环境变量固定，升级前建议先固定版本做对比
- 官方建议配住宅代理 + `geoip=True`，数据中心 IP 本身就会拉低通过率
