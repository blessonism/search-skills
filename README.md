# ⚠️ This repository has been merged into [openclaw-skills](https://github.com/blessonism/openclaw-skills)

本仓库的所有内容（search-layer、content-extract、mineru-extract）已合并到统一仓库：

👉 **https://github.com/blessonism/openclaw-skills**

请前往新仓库获取最新版本。本仓库不再更新。

---

<details>
<summary>原始 README（存档）</summary>

# OpenClaw Search Skills

一组 [OpenClaw](https://github.com/openclaw/openclaw) 技能（Skills），提供 **多源搜索** 和 **内容提取** 能力。

## 包含什么

| Skill | 干什么的 |
|-------|---------| 
| **search-layer** | 多源搜索（Exa + Tavily）+ 意图感知评分 + 自动去重。Brave 由 OpenClaw 内置的 `web_search` 提供。 |
| **content-extract** | URL → 干净的 Markdown。遇到反爬站点（微信、知乎）自动降级到 MinerU 解析。 |
| **mineru-extract** | [MinerU](https://mineru.net) 官方 API 的封装层。把 PDF、Office 文档、HTML 页面转成 Markdown。 |

</details>
