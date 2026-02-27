# openclaw-search-skills

Multi-source search + deep thread extraction for AI agents.

## Overview

Two complementary tools:

- **search.py** — Intent-aware multi-source search (Brave + Exa + Tavily + Grok), with optional reference extraction
- **fetch_thread.py** — Deep structured fetch for GitHub issues/PRs, HN, Reddit, V2EX, and generic web pages

## fetch_thread.py

### Supported Platforms

| Platform | Method | What you get |
|----------|--------|--------------|
| GitHub issue/PR | REST API | Full body + all comments + timeline cross-refs + commit refs |
| Hacker News | Algolia API | Post + recursive `comments_tree` (depth unlimited, max 200) |
| Reddit | `.json` endpoint | Post + comment tree (depth ≤ 4, max 200 comments) |
| V2EX | API | Post + replies |
| Generic web | trafilatura → BS4 → regex | Clean body text + links |

### Usage

```bash
# GitHub issue or PR
python3 scripts/fetch_thread.py "https://github.com/owner/repo/issues/123"
python3 scripts/fetch_thread.py "https://github.com/owner/repo/pull/456" --format markdown

# Extract refs only (fast, no full body)
python3 scripts/fetch_thread.py "https://github.com/owner/repo/issues/123" --extract-refs-only

# HN thread
python3 scripts/fetch_thread.py "https://news.ycombinator.com/item?id=43197966"

# Reddit post
python3 scripts/fetch_thread.py "https://www.reddit.com/r/Python/comments/abc123/title/"

# Any web page
python3 scripts/fetch_thread.py "https://example.com/blog/post"
```

### Output Schema

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

`comments` is always a flat backward-compatible list. `comments_tree` is the full nested structure (HN and Reddit).

### Web Page Extraction (P0)

`fetch_web_page()` uses a 3-layer fallback:

1. **trafilatura** — main content extraction (preferred)
2. **BeautifulSoup** — fallback if trafilatura returns < 200 chars
3. **regex** — last resort

Link extraction uses BeautifulSoup + `urljoin` for correct relative URL resolution.

## search.py — Phase 3.5: Thread Pulling

After a search, automatically extract the reference graph from result URLs:

```bash
# Search + extract refs from results
python3 scripts/search.py "OpenClaw config validation bug" --mode deep --intent status --extract-refs

# Skip search, extract refs from known URLs directly
python3 scripts/search.py --extract-refs-urls \
  "https://github.com/owner/repo/issues/123" \
  "https://github.com/owner/repo/issues/456"
```

The output gains a `refs` field per result URL. Parallel fetch with `ThreadPoolExecutor` (max 4 workers, cap 20 URLs).

### Agent Chain-Tracking Flow

```
1. search.py → initial results
2. --extract-refs → reference graph
3. Agent selects high-value refs
4. fetch_thread.py → deep fetch each ref
5. Repeat until closure (recommended max_depth=3)
```

## Dependencies

```
trafilatura
beautifulsoup4
lxml
requests
```

## Branch

Active development on `feature/chain-tracking-v2`.
