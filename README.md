# 影视仓 / TVBox 配置聚合（GitHub Actions 版）

![配置状态](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fwangfdsa/tvbox-ysc-config%2Fmain%2Foutput%2Fshield.json)
![更新频率](https://img.shields.io/badge/%E6%9B%B4%E6%96%B0-%E6%AF%8F%E5%A4%A9%202%20%E6%AC%A1-blue)

聚合 40+ 个知名 TVBox / 影视仓接口，通过 **GitHub Actions 云端定时自动更新**，结果提交回本仓库。已开启成人内容过滤、缓存容错、中文域名 punycode 兼容。

> 所有配置来自互联网公开分享，版权归原作者所有；本仓库仅做聚合与镜像，仅供学习交流，请勿商用。

---

## 一、订阅地址（填进 TVBox / 影视仓）

| 类型 | 地址 |
| --- | --- |
| **多仓订阅（推荐）** | `https://gh-proxy.org/https://raw.githubusercontent.com/wangfdsa/tvbox-ysc-config/main/output/多仓订阅.json` |
| **单仓聚合（所有站点合并）** | `https://gh-proxy.org/https://raw.githubusercontent.com/wangfdsa/tvbox-ysc-config/main/output/单仓聚合.json` |
| 运行状态 | `https://gh-proxy.org/https://raw.githubusercontent.com/wangfdsa/tvbox-ysc-config/main/output/status.json` |
| 单独源 | `https://gh-proxy.org/https://raw.githubusercontent.com/wangfdsa/tvbox-ysc-config/main/output/sources/源ID.json` |

> 国内直连 `raw.githubusercontent.com` 若慢，可套加速前缀，如 `https://gh-proxy.com/` + 上面的完整地址。

---

## 二、源可用性状态

<!-- STATUS_START -->
> 🔄 最近更新：2026-11-26 06:54:27（北京时间） · 成功 **23/25** 个源 · 聚合 1056 站点

| 配置源 | 状态 | 详情 |
| --- | --- | --- |
| 王二小 | ✅ 成功 | 95 站 · 682ms |
| 老刘备 | ✅ 成功 | 234 站 · 240ms |
| 小马 | ✅ 成功 | 62 站 · 1065ms |
| 肥猫 | ✅ 成功 | 41 站 · 82ms |
| 饭太硬 | ❌ 失败 | 全部地址尝试失败 |
| 讴歌/欧歌 | ❌ 失败 | 全部地址尝试失败 |
| 聚玩盒子4K | ✅ 成功 | 53 站 · 256ms |
| 聚玩盒子单仓 | ✅ 成功 | 54 站 · 413ms |
| 聚玩盒子多仓 | ✅ 成功 | 18 站 · 268ms |
| 拾光多仓 | ✅ 成功 | 54 站 · 403ms |
| 挺好分享 | ✅ 成功 | 32 站 · 1451ms |
| 嗷呜 | ✅ 成功 | 84 站 · 670ms |
| 摸鱼儿 | ✅ 成功 | 111 站 · 635ms |
| 潇洒 | ✅ 成功 | 127 站 · 1225ms |
| 南风 | ✅ 成功 | 93 站 · 240ms |
| 菜妮丝/采妮诗 | ✅ 成功 | 55 站 · 2983ms |
| 小米CatVod | ✅ 成功 | 44 站 · 202ms |
| 茄子库 | ✅ 成功 | 1 站 · 1499ms |
| 俊佬 | ✅ 成功 | 24 站 · 758ms |
| 荐片 | ✅ 成功 | 36 站 · 180ms |
| 无邪多仓 | ✅ 成功 | 3 站 · 281ms |
| 东篱 | ✅ 成功 | 93 站 · 87ms |
| 周J | ✅ 成功 | 26 站 · 116ms |
| 盒子迷 | ✅ 成功 | 29 站 · 461ms |
| 荐片/俊哥备用 | ✅ 成功 | 24 站 · 702ms |
<!-- STATUS_END -->

---

## 三、自动更新机制

- `.github/workflows/update.yml` 每天 **02:00 / 14:00 UTC**（北京 10:00 / 22:00）自动运行。
- 也可在 **Actions → Auto Update → Run workflow** 手动触发。
- 用内置 `GITHUB_TOKEN` 自动提交 `output/`，无需任何密钥。
- push 只监听 `config/`、`scripts/`，自动提交 `output/` 不会死循环。

## 四、自定义源

编辑 `config/sources.json`，每个源格式：

```json
{"id": "mysource", "name": "我的源", "enabled": true, "urls": ["主地址", "备用地址"]}
```

推送后自动触发更新。失效源会保留记录，恢复后自动启用。
