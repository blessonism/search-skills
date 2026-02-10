# ⚠️ This repository has been merged into [openclaw-skills](https://github.com/blessonism/openclaw-skills)

本仓库的所有内容（search-layer、content-extract、mineru-extract）已合并到统一仓库：

👉 **https://github.com/blessonism/openclaw-skills**

请前往新仓库获取最新版本。本仓库不再更新。

---

# OpenClaw Search Skills

一组 [OpenClaw](https://github.com/openclaw/openclaw) 技能（Skills），提供 **多源搜索** 和 **内容提取** 能力。

主要为 [github-explorer](https://github.com/blessonism/github-explorer-skill) 提供底层支撑，也可以独立使用。

## 包含什么

| Skill | 干什么的 |
|-------|---------| 
| **[search-layer](./search-layer/)** | 多源搜索（Exa + Tavily）+ 意图感知评分 + 自动去重。Brave 由 OpenClaw 内置的 `web_search` 提供。 |
| **[content-extract](./content-extract/)** | URL → 干净的 Markdown。遇到反爬站点（微信、知乎）自动降级到 MinerU 解析。 |
| **[mineru-extract](./mineru-extract/)** | [MinerU](https://mineru.net) 官方 API 的封装层。把 PDF、Office 文档、HTML 页面转成 Markdown。 |

## 它们之间的关系

```
github-explorer（独立 repo）
├── search-layer ──── Exa + Tavily 并行搜索 + 意图评分   ← 本仓库
├── content-extract ── 智能 URL → Markdown                ← 本仓库
│   └── mineru-extract ── MinerU API（重活）              ← 本仓库
└── OpenClaw 内置工具 ── web_search, web_fetch, browser
```

## search-layer v2 新特性

v2 借鉴了 [Anthropic knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) 的 enterprise-search 设计，新增：

- **意图分类**：7 种查询意图（factual / status / comparison / tutorial / exploratory / news / resource），自动调整搜索策略和评分权重
- **多查询并行**：`--queries "q1" "q2" "q3"` 同时执行多个子查询
- **意图感知评分**：`score = w_keyword × keyword_match + w_freshness × freshness_score + w_authority × authority_score`，权重由意图类型决定
- **域名权威性评分**：内置四级域名评分表（60+ 域名 + 模式匹配规则）
- **Freshness 过滤**：`--freshness pd/pw/pm/py` 实际传递给 Tavily
- **Domain Boost**：`--domain-boost github.com,stackoverflow.com` 提升特定域名权重
- **完全向后兼容**：不带新参数时行为与 v1 一致

## 安装

### 方式一：让 OpenClaw 帮你装（推荐 🚀）

直接在对话里告诉你的 OpenClaw agent：

> 帮我安装这个 skill：https://github.com/blessonism/openclaw-search-skills

### 方式二：手动安装

```bash
# 1. Clone 到任意位置
mkdir -p ~/.openclaw/workspace/_repos
git clone https://github.com/blessonism/openclaw-search-skills.git \
  ~/.openclaw/workspace/_repos/openclaw-search-skills

# 2. 链接到你的 skills 目录
cd ~/.openclaw/workspace/skills

ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/search-layer search-layer
ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/content-extract content-extract
ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/mineru-extract mineru-extract
```

> 💡 skills 目录因安装方式不同可能不同，常见的是 `~/.openclaw/workspace/skills/` 或 `~/.openclaw/skills/`。

## 配置

### 搜索 API Keys（search-layer 需要）

**环境变量：**

```bash
export BRAVE_API_KEY="your-brave-key"    # https://brave.com/search/api/ （OpenClaw 内置 web_search 使用）
export EXA_API_KEY="your-exa-key"        # https://exa.ai
export TAVILY_API_KEY="your-tavily-key"  # https://tavily.com
```

**或写到 TOOLS.md（OpenClaw workspace 根目录）：**

```markdown
### Search
- **Brave**: `your-brave-key`
- **Exa**: `your-exa-key`
- **Tavily**: `your-tavily-key`
```

### MinerU Token（可选，content-extract 需要）

只有当你需要抓取微信/知乎/小红书等反爬站点时才需要：

```bash
cp mineru-extract/.env.example mineru-extract/.env
# 编辑 .env，填入你的 MinerU token（从 https://mineru.net/apiManage 获取）
```

### Python 依赖

```bash
pip install requests  # 唯一的外部依赖
```

## 单独使用

### search-layer

```bash
# v1 兼容模式（无意图评分）
python3 search-layer/scripts/search.py "RAG framework comparison" --mode deep --num 5

# v2 意图感知模式
python3 search-layer/scripts/search.py "RAG framework comparison" --mode deep --intent exploratory --num 5

# 多查询并行 + 对比意图
python3 search-layer/scripts/search.py --queries "Bun vs Deno" "Bun advantages" "Deno advantages" \
  --mode deep --intent comparison --num 5

# 最新动态 + 时间过滤
python3 search-layer/scripts/search.py "Deno 2.0 latest" --mode deep --intent status --freshness pw

# 域名加权
python3 search-layer/scripts/search.py "Rust CLI tutorial" --mode answer --intent tutorial \
  --domain-boost dev.to,realpython.com
```

模式：`fast`（仅 Exa）、`deep`（Exa + Tavily 并行）、`answer`（Tavily 带 AI 摘要）

意图：`factual`、`status`、`comparison`、`tutorial`、`exploratory`、`news`、`resource`

### content-extract

```bash
python3 content-extract/scripts/content_extract.py --url "https://mp.weixin.qq.com/s/some-article"
```

### mineru-extract

```bash
python3 mineru-extract/scripts/mineru_extract.py "https://example.com/paper.pdf" --model pipeline --print
```

## 环境要求

- [OpenClaw](https://github.com/openclaw/openclaw)（agent 运行时）
- Python 3.10+
- `requests`（pip install）
- API Keys：Exa 和/或 Tavily（用于 search-layer），MinerU token（可选，用于 content-extract）

## License

MIT
