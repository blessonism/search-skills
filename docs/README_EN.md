![OpenClaw Search Skills Banner](../images/openclaw-search-skills-banner.png)

<div align="center">

# OpenClaw Search Skills

English | [简体中文](../README.md)

**A production-ready set of OpenClaw Skills for multi-source search, thread pulling, and high-fidelity content extraction.**

[![OpenClaw](https://img.shields.io/badge/OpenClaw-Skills-0A84FF)](https://github.com/openclaw/openclaw)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![search-layer](https://img.shields.io/badge/search--layer-v3.1-7C3AED)](../search-layer/SKILL.md)
[![content-extract](https://img.shields.io/badge/content--extract-MinerU%20Fallback-14B8A6)](../content-extract/SKILL.md)

</div>

> 📦 This repository is also included in [openclaw-skills](https://github.com/blessonism/openclaw-skills), the aggregate repo that contains more Skills. If you want the full capability set, star that repo first.

---

## 1. Overview

`openclaw-search-skills` is a composable capability pack for [OpenClaw](https://github.com/openclaw/openclaw) agents. It covers the full workflow from **finding sources**, **pulling context**, and **extracting clean content** to **following citation chains**.

These skills were originally built as the foundation for [github-explorer](https://github.com/blessonism/github-explorer-skill). They were later split into a standalone repository because they became reusable across many workflows.

```text
OpenClaw Agent
├── search-layer       Multi-source search orchestration / intent-aware scoring / thread pulling
├── content-extract    URL → clean Markdown / automatic fallback for anti-bot sites
│   └── mineru-extract High-fidelity parsing (PDF / Office / HTML / OCR)
└── OpenClaw built-ins web_search / web_fetch / browser
```

### Good fits

- **Research and fact checking**: query several sources in parallel to reduce single-source bias
- **GitHub investigations**: read beyond the issue body by pulling comments, references, and follow-up threads
- **Knowledge capture**: convert articles, PDFs, and Office documents into clean Markdown
- **Anti-bot websites**: automatically fall back to MinerU when normal extraction becomes unreliable

### Included skills

| Skill | What it does |
|-------|--------------|
| **[search-layer](../search-layer/)** | Four-source parallel search (Brave + Exa + Tavily + Grok) + academic mode (OpenAlex + Semantic + Tavily) + intent-aware scoring + deduplication + citation-chain tracking. Brave comes from OpenClaw's built-in `web_search`. |
| **[content-extract](../content-extract/)** | URL → clean Markdown. Automatically falls back to MinerU for anti-bot sites such as WeChat and Zhihu. |
| **[mineru-extract](../mineru-extract/)** | A wrapper around the official [MinerU](https://mineru.net) API for converting PDFs, Office files, and HTML pages into Markdown. |

### How they relate

```text
github-explorer (separate repo)
├── search-layer ───── Exa + Tavily + Grok parallel search + intent scoring + citation tracking   ← this repo
├── content-extract ── smart URL → Markdown                                                       ← this repo
│   └── mineru-extract ─ MinerU API for heavy extraction                                           ← this repo
└── OpenClaw built-ins ─ web_search (Brave), web_fetch, browser
```

---

## search-layer v3.1 highlights (latest)

v3.1 builds on the deep citation-tracking workflow from v3.0 and adds an **Academic search mode** plus **export support**.

### Academic mode (v3.1)

- Adds `--mode academic`: runs `OpenAlex + Semantic Scholar + Tavily` in parallel
- Adds `--intent academic`: shifts scoring weights toward authority
- Adds `--export`: supports `bibtex`, `csv`, `markdown`, and `citations`
- Extends `--source` to support `openalex,semantic_scholar` (with `semantic` as an alias)

```bash
# Academic search
python3 search-layer/scripts/search.py "transformer architecture" \
  --mode academic --intent academic --num 5

# Export BibTeX
python3 search-layer/scripts/search.py "transformer architecture" \
  --mode academic --intent academic --export bibtex
```

---

v3.0 introduced **deep citation-chain tracking** on top of the existing multi-source search stack, so an agent can follow references instead of stopping at the first layer of results.

### New tools

**`fetch_thread.py`** — structured deep-fetching for multi-platform threads and discussions:

| Platform | Method | Retrieved content |
|----------|--------|-------------------|
| GitHub Issue/PR | REST API | Body + all comments + cross-linked PRs/issues + commit references |
| Hacker News | Algolia API | Post + recursive comment tree (unlimited depth, capped at 200 comments) |
| Reddit | `.json` endpoint | Post + comment tree (depth ≤ 4, capped at 200 comments) |
| V2EX | API | Topic + all replies |
| Generic webpage | trafilatura → BS4 → regex fallback chain | Main content + links |

```bash
# GitHub issue or PR
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/issues/123"
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/pull/456" --format markdown

# Extract references only (fast mode)
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/issues/123" --extract-refs-only

# HN / Reddit / arbitrary webpage
python3 search-layer/scripts/fetch_thread.py "https://news.ycombinator.com/item?id=43197966"
python3 search-layer/scripts/fetch_thread.py "https://www.reddit.com/r/Python/comments/abc123/title/"
python3 search-layer/scripts/fetch_thread.py "https://example.com/blog/post"
```

**`chain_tracker.py`** — breadth-first traversal over reference graphs with configurable `max_depth`.

**`relevance_gate.py`** — relevance scoring for candidate URLs during traversal, to filter low-value nodes and avoid runaway expansion.

### search.py — Phase 3.5: Thread pulling

Automatically extracts reference graphs from search result URLs:

```bash
# Search + auto extract references
python3 search-layer/scripts/search.py "OpenClaw config validation bug" \
  --mode deep --intent status --extract-refs

# Skip search and extract references from known URLs directly
python3 search-layer/scripts/search.py --extract-refs-urls \
  "https://github.com/owner/repo/issues/123" \
  "https://github.com/owner/repo/issues/456"
```

The output now includes a `refs` field. Fetching is parallelized with `ThreadPoolExecutor` (up to 4 workers, up to 20 URLs).

### Agent citation-tracking workflow

```text
1. search.py → initial result set
2. --extract-refs → build the reference graph
3. Agent selects high-value nodes
4. fetch_thread.py → deep-fetch each node
5. Repeat until the information closes (recommended `max_depth=3`)
```

### Output schema (`fetch_thread.py`)

```json
{
  "url": "...",
  "type": "github_issue | github_pr | hn_item | reddit_post | v2ex_topic | web_page",
  "title": "...",
  "body": "...",
  "comments": [{"author": "...", "date": "...", "body": "..."}],
  "comments_tree": [{"author": "...", "depth": 0, "replies": [...]}],
  "refs": ["#123", "owner/repo#456", "https://..."],
  "links": [{"url": "...", "anchor": "...", "context": "..."}],
  "metadata": {}
}
```

`comments` remains a flat list for backwards compatibility. `comments_tree` contains the full nested structure when available (HN and Reddit).

---

## search-layer v2.2 highlights

v2.2 improved Grok source stability and added source filtering:

- **Source filtering**: use `--source grok,exa` to limit execution to specific sources for testing or comparison
- **Default model upgrade**: the default Grok model changed from `grok-4.1` to `grok-4.1-fast`
- **Thinking tag stripping**: automatically removes `<think>` tags from Grok thinking-model outputs
- **Stronger JSON extraction**: handles cases where Grok emits natural-language text before JSON (`raw_decode` + `rfind` fallback)
- **Credentials file**: centralizes search credentials in `~/.openclaw/credentials/search.json`

## search-layer v2.1 highlights

v2.1 added **Grok (xAI)** as the fourth search source via the Completions API, with support for proxy endpoints:

- **Grok as a search source**: uses Grok's realtime knowledge to return structured search results, especially good for timely queries and authority recognition
- **Four-source parallel search**: deep mode runs Exa + Tavily + Grok, plus Brave at the OpenClaw agent layer
- **Graceful fallback**: if Grok config is missing, the flow degrades to Exa + Tavily without breaking the existing workflow
- **SSE compatibility**: automatically detects and handles proxy endpoints that force streaming
- **Security hardening**: query injection protection via `<query>` isolation and URL scheme validation (`http/https` only)
- **Date extraction**: Grok results include `published_date`, which participates in freshness scoring

## search-layer v2 highlights

v2 borrowed ideas from [Anthropic knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins), especially the enterprise-search design:

- **Intent classification**: supports 8 query intents (including `academic`) and adjusts strategy and scoring weights automatically
- **Multi-query parallelism**: use `--queries "q1" "q2" "q3"` to run several subqueries at once
- **Intent-aware scoring**: `score = w_keyword × keyword_match + w_freshness × freshness_score + w_authority × authority_score`, with weights determined by intent type
- **Domain authority scoring**: built-in four-level domain scoring table (60+ domains + pattern rules)
- **Freshness filtering**: passes `--freshness pd/pw/pm/py` through to Tavily
- **Domain boost**: use `--domain-boost github.com,stackoverflow.com` to raise the weight of selected domains
- **Backwards compatibility**: behavior remains compatible with v1 when no new parameters are used

---

## Installation

### Option 1: let OpenClaw install it for you (recommended 🚀)

Just tell your OpenClaw agent:

> Install this skill for me: https://github.com/blessonism/openclaw-search-skills

### Option 2: manual installation

```bash
# 1. Clone the repo anywhere you like
mkdir -p ~/.openclaw/workspace/_repos
git clone https://github.com/blessonism/openclaw-search-skills.git \
  ~/.openclaw/workspace/_repos/openclaw-search-skills

# 2. Symlink the skills into your skills directory
cd ~/.openclaw/workspace/skills

ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/search-layer search-layer
ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/content-extract content-extract
ln -s ~/.openclaw/workspace/_repos/openclaw-search-skills/mineru-extract mineru-extract
```

> 💡 The skills directory may vary depending on how your OpenClaw setup was installed. Common locations are `~/.openclaw/workspace/skills/` and `~/.openclaw/skills/`.

---

## Configuration

### Search API keys (`search-layer`)

**Option 1: credentials file (recommended)**

Create `~/.openclaw/credentials/search.json`:

```json
{
  "exa": "your-exa-key",
  "tavily": "your-tavily-key",
  "grok": {
    "apiUrl": "https://api.x.ai/v1",
    "apiKey": "your-grok-key",
    "model": "grok-4.1-fast"
  },
  "openalex": "your-openalex-key-optional",
  "semantic": "your-semantic-scholar-key-optional",
  "semantic_scholar": "your-semantic-scholar-key-optional"
}
```

> 💡 `openalex` and `semantic(_scholar)` are optional. If they are missing, `academic` mode degrades automatically to whatever source combination is available.

**Option 2: environment variables (compatible)**

```bash
export EXA_API_KEY="your-exa-key"        # https://exa.ai
export TAVILY_API_KEY="your-tavily-key"  # https://tavily.com
export GROK_API_URL="https://api.x.ai/v1"  # optional
export GROK_API_KEY="your-grok-key"      # optional
export GROK_MODEL="grok-4.1-fast"        # optional, defaults to grok-4.1-fast
export OPENALEX_API_KEY="your-openalex-key"      # optional
export SEMANTIC_API_KEY="your-semantic-key"      # optional
export SEMANTIC_SCHOLAR_API_KEY="your-semantic-key"  # optional, equivalent alias
```

Environment variables override credentials-file values when both are present.

Brave API keys are managed by OpenClaw's built-in `web_search` tool, so you do not configure them here.

### MinerU token (optional, for `content-extract`)

You only need this if you want reliable extraction from anti-bot sites such as WeChat, Zhihu, or Xiaohongshu:

```bash
cp mineru-extract/.env.example mineru-extract/.env
# Then edit .env and fill in your MinerU token from https://mineru.net/apiManage
```

### Python dependencies

```bash
# Base dependency set (search-layer v2.x)
pip install requests

# Extra dependencies for v3.0 citation tracking
pip install trafilatura beautifulsoup4 lxml
```

---

## Usage examples

### `search-layer`

```bash
# Basic search (v1-compatible mode)
python3 search-layer/scripts/search.py "RAG framework comparison" --mode deep --num 5

# Intent-aware mode (v2+)
python3 search-layer/scripts/search.py "RAG framework comparison" --mode deep --intent exploratory --num 5

# Multi-query parallel search
python3 search-layer/scripts/search.py --queries "Bun vs Deno" "Bun advantages" "Deno advantages" \
  --mode deep --intent comparison --num 5

# Latest updates + freshness filter
python3 search-layer/scripts/search.py "Deno 2.0 latest" --mode deep --intent status --freshness pw

# Single-source test
python3 search-layer/scripts/search.py "OpenAI latest news" --mode deep --source grok --num 5

# Search + citation tracking (v3.0)
python3 search-layer/scripts/search.py "OpenClaw config bug" --mode deep --intent status --extract-refs

# Academic search (v3.1)
python3 search-layer/scripts/search.py "transformer architecture" --mode academic --intent academic --num 5

# Academic export (v3.1)
python3 search-layer/scripts/search.py "transformer architecture" --mode academic --intent academic --export bibtex
```

Modes: `fast` (Exa first), `deep` (Exa + Tavily + Grok in parallel), `answer` (Tavily with AI summary), `academic` (OpenAlex + Semantic + Tavily)

Intents: `factual`, `status`, `comparison`, `tutorial`, `exploratory`, `news`, `resource`, `academic`

### `fetch_thread.py` (new in v3.0)

```bash
# GitHub issue / PR
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/issues/123"
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/pull/456" --format markdown

# Extract references only (fast)
python3 search-layer/scripts/fetch_thread.py "https://github.com/owner/repo/issues/123" --extract-refs-only

# HN / Reddit / V2EX / arbitrary webpage
python3 search-layer/scripts/fetch_thread.py "https://news.ycombinator.com/item?id=43197966"
python3 search-layer/scripts/fetch_thread.py "https://www.reddit.com/r/Python/comments/abc123/title/"
```

### `content-extract`

```bash
python3 content-extract/scripts/content_extract.py --url "https://mp.weixin.qq.com/s/some-article"
```

### `mineru-extract`

```bash
python3 mineru-extract/scripts/mineru_extract.py "https://example.com/paper.pdf" --model pipeline --print
```

---

## Requirements

- [OpenClaw](https://github.com/openclaw/openclaw) (agent runtime)
- Python 3.10+
- `requests` (base dependency)
- `trafilatura`, `beautifulsoup4`, `lxml` (v3.0 citation-tracking dependencies)
- API keys: Exa/Tavily (base `search-layer` setup), Grok (optional), OpenAlex/Semantic Scholar (optional for academic mode), MinerU token (optional for `content-extract`)

## License

MIT
