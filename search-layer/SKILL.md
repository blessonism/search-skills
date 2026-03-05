---
name: search-layer
description: >
  DEFAULT search tool for ALL search/lookup needs. Multi-source search and deduplication
  layer with intent-aware scoring. Integrates Brave Search (web_search), Exa, Tavily,
  Grok, OpenAlex, and Semantic Scholar to provide high-coverage, high-quality results.
  Includes thread/reference extraction for deep investigation workflows.
  Use for factual lookups, status checks, comparisons, tutorials, news, resources,
  and academic research. Do NOT use raw web_search directly; always route through this skill.
---

# Search Layer v3.1 — 意图感知多源检索协议

六源协同：Brave (`web_search`) + Exa + Tavily + Grok + OpenAlex + Semantic。
在 v3.0 链式追踪基础上新增 academic 检索与导出。

## 执行流程

```
用户查询
    ↓
[Phase 1] 意图分类 → 确定搜索策略
    ↓
[Phase 2] 查询分解 & 扩展 → 生成子查询
    ↓
[Phase 3] 多源并行检索 → Brave + search.py
    ↓
[Phase 3.5] 线索追踪（可选）→ extract-refs / fetch_thread
    ↓
[Phase 4] 结果合并 & 排序 → 去重 + 意图加权评分
    ↓
[Phase 5] 知识合成 → 结构化输出
```

---

## Phase 1: 意图分类

收到搜索请求后，先判断意图类型，再决定模式。

| 意图 | 识别信号 | Mode | Freshness | 权重偏向 |
|------|---------|------|-----------|---------|
| **Factual** | "什么是 X"、"X 的定义"、"What is X" | answer | — | 权威 0.5 |
| **Status** | "X 最新进展"、"X 现状"、"latest X" | deep | pw/pm | 新鲜度 0.5 |
| **Comparison** | "X vs Y"、"X 和 Y 区别" | deep | py | 关键词 0.4 + 权威 0.4 |
| **Tutorial** | "怎么做 X"、"X 教程"、"how to X" | answer | py | 权威 0.5 |
| **Exploratory** | "深入了解 X"、"X 生态"、"about X" | deep | — | 权威 0.5 |
| **News** | "X 新闻"、"本周 X"、"X this week" | deep | pd/pw | 新鲜度 0.6 |
| **Resource** | "X 官网"、"X GitHub"、"X 文档" | fast | — | 关键词 0.5 |
| **Academic** | "X 论文"、"X 研究"、"X paper" | academic | py | 权威 0.7 |

> 详细分类指南见 `references/intent-guide.md`

---

## Phase 2: 查询分解 & 扩展

根据意图扩展子查询：
- 技术同义词：k8s→Kubernetes，JS→JavaScript，Go→Golang
- 中文技术查询：同时生成英文变体
- Comparison：拆分成 `A vs B` + `A 优势` + `B 优势`
- Academic：追加 `paper/research/study` 与年份范围

---

## Phase 3: 多源并行检索

### Step 1: Brave（所有模式）

对关键子查询调用 `web_search`；有时效要求时传 `freshness`。

### Step 2: search.py（脚本并行）

```bash
python3 /home/node/.openclaw/workspace/skills/search-layer/scripts/search.py \
  --queries "子查询1" "子查询2" \
  --mode deep \
  --intent status \
  --freshness pw \
  --num 5
```

**模式源矩阵**：
| 模式 | Exa | Tavily | Grok | OpenAlex | Semantic | 说明 |
|------|-----|--------|------|----------|----------|------|
| fast | ✅ | ❌ | fallback | ❌ | ❌ | Exa 优先；无 Exa key 时 Grok |
| deep | ✅ | ✅ | ✅ | ❌ | ❌ | 三源并行 |
| answer | ❌ | ✅ | ❌ | ❌ | ❌ | 仅 Tavily（含 AI answer） |
| academic | ❌ | ✅ | ❌ | ✅ | ✅ | 学术检索并行 |

**参数说明**：
| 参数 | 说明 |
|------|------|
| `--queries` | 多子查询并行 |
| `--mode` | `fast` / `deep` / `answer` / `academic` |
| `--intent` | 意图类型，影响评分 |
| `--freshness` | `pd` / `pw` / `pm` / `py` |
| `--domain-boost` | 域名加权（+0.2） |
| `--source` | 限定来源：`exa,tavily,grok,openalex,semantic_scholar`（兼容别名 `semantic`） |
| `--num` | 每源结果数 |
| `--export` | `json/bibtex/csv/markdown/citations` |

**密钥来源**：
- 首选 `~/.openclaw/credentials/search.json`
- 环境变量可覆盖：`EXA_API_KEY`、`TAVILY_API_KEY`、`GROK_*`、`OPENALEX_API_KEY`、`SEMANTIC_API_KEY`

---

## Phase 3.5: 引用追踪（Thread Pulling）

当需要深挖 issue/PR 或讨论串时，使用：

```bash
# 搜索后自动提取引用
python3 search.py "OpenClaw config validation bug" --mode deep --intent status --extract-refs

# 直接对已知 URL 提取引用
python3 search.py --extract-refs-urls \
  "https://github.com/owner/repo/issues/123" \
  "https://github.com/owner/repo/pull/456"
```

也可单独调用 `fetch_thread.py` 深抓内容与评论树。

---

## Phase 4: 结果排序

评分公式：

```
score = w_keyword × keyword_match + w_freshness × freshness_score + w_authority × authority_score
```

Academic intent 使用质量优先固定公式：

```
score = 0.30*authority + 0.30*venue + 0.20*keyword + 0.10*freshness + 0.10*artifact
```

推荐 domain boost：
- Academic（CS）：`arxiv.org,openreview.net,openaccess.thecvf.com,ieeexplore.ieee.org,dl.acm.org,dblp.org,usenix.org,aaai.org,ijcai.org`
- Tutorial：`dev.to,freecodecamp.org,realpython.com,baeldung.com`
- Resource：`github.com`

---

## Phase 5: 知识合成

- 先给结论，再给来源
- 按主题聚合，不按来源分组
- 冲突信息显式标注
- Academic 场景建议附 DOI/引用数/年份

---

## 降级策略

- Exa 失败 → 继续 Tavily/Grok（deep）
- Tavily 失败 → 继续 Exa/Grok（deep）
- Grok 失败 → 继续 Exa/Tavily（deep）
- OpenAlex 失败 → 继续 semantic_scholar/Tavily（academic）
- semantic_scholar 失败 → 继续 OpenAlex/Tavily（academic）
- search.py 失败 → 回退 Brave `web_search`
- 任何单源失败都不得阻塞主流程

---

## 向后兼容

- 不带 `--intent` 时保持 v1 行为（不评分）
- v3.0 的 `--extract-refs` / `--extract-refs-urls` 完整保留
