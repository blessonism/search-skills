# Search Layer v2 — 搜索意图分层增强计划

## 背景

借鉴 Anthropic `knowledge-work-plugins/enterprise-search` 的设计思路，为现有 search-layer skill 增加**意图分类 → 查询分解 → 权重排序 → 结果合成**能力。

当前 search-layer 是一个"三源并行 + 去重"的管道，缺少对用户意图的理解。增强后，它将能根据查询意图自动调整搜索策略和结果排序。

## 现状分析

### 当前架构
```
用户查询 → 模式选择(Fast/Deep/Answer) → 多源并行 → URL去重 → 输出列表
```

### 问题
1. **模式选择太粗** — 只有 Fast/Deep/Answer 三档，靠任务类型硬匹配
2. **无意图理解** — "X 的最新进展"和"X 是什么"走同一条路
3. **无查询扩展** — 用户说"k8s"不会自动搜"Kubernetes"
4. **结果排序原始** — 按源返回顺序排列，无相关性/新鲜度/权威性加权
5. **无合成层** — 只输出链接列表，不做跨源信息合成

## 设计方案

### 新架构
```
用户查询
    ↓
[Phase 1] 意图分类 (SKILL.md 指令，由 agent 执行)
    ↓
[Phase 2] 查询分解 & 扩展 (SKILL.md 指令)
    ↓
[Phase 3] 多源并行检索 (search.py，现有能力)
    ↓
[Phase 4] 结果排序 & 去重 (search.py 增强)
    ↓
[Phase 5] 知识合成 (SKILL.md 指令，由 agent 执行)
    ↓
结构化输出
```

**关键设计决策**：Phase 1/2/5 是 prompt 层（写在 SKILL.md 里，由 agent 的 LLM 能力执行），Phase 3/4 是代码层（search.py）。这样保持了灵活性——意图理解靠 LLM，数据获取靠代码。

### Phase 1: 意图分类

在 SKILL.md 中定义 7 种查询意图，每种对应不同的搜索策略：

| 意图类型 | 示例 | 搜索策略 | 新鲜度权重 | 权威性权重 |
|---------|------|---------|-----------|-----------|
| **Factual** | "X 是什么" "X 的定义" | Answer 模式，优先权威源 | 0.1 | 0.5 |
| **Status** | "X 最新进展" "X 现在怎样了" | Deep 模式，强制 freshness=pw | 0.5 | 0.2 |
| **Comparison** | "X vs Y" "X 和 Y 哪个好" | Deep 模式，多查询变体 | 0.2 | 0.3 |
| **Tutorial** | "怎么做 X" "X 教程" | Answer 模式，优先文档/教程站 | 0.1 | 0.4 |
| **Exploratory** | "关于 X 的一切" "深入了解 X" | Deep 模式，最大覆盖 | 0.2 | 0.3 |
| **News** | "X 的新闻" "最近发生了什么" | Deep 模式，freshness=pd/pw | 0.6 | 0.1 |
| **Resource** | "X 的 GitHub" "X 官网" | Fast 模式，精确匹配 | 0.1 | 0.4 |

### Phase 2: 查询分解 & 扩展

SKILL.md 指导 agent 做：
1. **同义词扩展**：k8s → Kubernetes, JS → JavaScript, React → React.js
2. **多角度子查询**：对 Comparison 类生成 "X advantages", "Y advantages", "X vs Y benchmark"
3. **时间约束推断**：Status/News 类自动加时间过滤
4. **语言适配**：中文查询同时生成英文变体（技术类）

输出格式：一组结构化的子查询，每个带 mode 和 freshness 参数。

### Phase 3: 多源并行检索

**search.py 增强**：
- 支持 `--freshness` 参数传递给 Brave（pd/pw/pm/py）
- 支持 `--domain-boost` 参数提升特定域名权重（如 github.com, stackoverflow.com）
- 支持批量查询：`--queries "q1" "q2" "q3"` 并行执行多个子查询
- 每个结果附带元数据：发布日期（如果有）、域名权威分

### Phase 4: 结果排序 & 去重

**search.py 增强**：
- 现有 URL 去重保留
- 新增评分函数：`score = w_keyword * keyword_match + w_fresh * freshness_score + w_auth * authority_score`
- 权重由 Phase 1 的意图类型决定，通过 `--intent` 参数传入
- 域名权威性预设表：
  - Tier 1 (1.0): 官方文档站、GitHub、Wikipedia
  - Tier 2 (0.8): StackOverflow、MDN、主流媒体
  - Tier 3 (0.6): 技术博客、Medium、Dev.to
  - Tier 4 (0.4): 其他

### Phase 5: 知识合成

SKILL.md 指导 agent 做：
- **小结果集 (≤5)**：逐条展示 + 简要总结
- **中结果集 (5-15)**：按主题聚类 + 每组摘要
- **大结果集 (15+)**：高层综述 + Top 5 源 + "要深入哪个方面？"
- 所有输出带源标注 `[source_tag]`
- 冲突信息显性标注

## 文件变更清单

### 修改文件
1. **`SKILL.md`** — 重写，加入意图分类表、查询分解指令、合成指令
2. **`scripts/search.py`** — 增强：freshness 参数、批量查询、评分排序、intent 参数

### 新增文件
3. **`references/intent-guide.md`** — 意图分类详细指南 + 示例（SKILL.md 引用）
4. **`references/authority-domains.json`** — 域名权威性评分表

### 不变
- API key 读取逻辑不变
- 降级策略不变（源失败 → 跳过继续）
- 对外接口兼容（现有调用方式仍可用）

## 向后兼容

- `search.py` 不带 `--intent` 参数时行为与现在完全一致
- SKILL.md 的新流程是增量的，不破坏现有 Fast/Deep/Answer 模式
- 其他 skill（如 github-explorer）调用 search-layer 时无需修改

## 验证方式

完成后用以下查询测试各意图路径：
1. Factual: "什么是 WebTransport"
2. Status: "Deno 2.0 最新进展"
3. Comparison: "Bun vs Deno 性能对比"
4. Tutorial: "如何用 Rust 写 CLI 工具"
5. News: "AI 领域本周新闻"
6. Resource: "Anthropic MCP 官方文档"
7. Exploratory: "深入了解 RISC-V 生态"

## 实施顺序

1. 先写 `references/authority-domains.json` 和 `references/intent-guide.md`（纯数据/文档）
2. 增强 `scripts/search.py`（代码层）
3. 重写 `SKILL.md`（prompt 层）
4. 端到端测试
