# research-light Regression Samples

P1.5 边界校准后的回归样本集，用于验证 `_detect_research_profile()` 的命中率和误触发控制。

## 设计原则

- **comparison**: 显式对比语言 或 判断词 或 3+ 子查询 bundle → 触发
- **exploratory**: 判断词 或 因果词 或 对比词 → 触发；单纯宽泛主题词不触发
- **status/news**: 判断词 或 因果词 → 触发；单纯时效性或多查询扩展不触发
- **resource/tutorial/factual**: 默认不触发

---

## Should Trigger (6 cases)

| ID | Intent | Mode | Query | Trigger Signal |
|----|--------|------|-------|----------------|
| T1 | comparison | deep | Bun vs Deno | explicit "vs" + multi-query |
| T2 | comparison | deep | React 和 Vue 区别 | explicit "区别" |
| T3 | exploratory | deep | RISC-V 生态现在发展到什么阶段，值得持续关注吗？ | "值得" + "关注" judgment |
| T4 | exploratory | deep | AI coding agents landscape 2026, which one should we adopt? | "adopt" judgment |
| T5 | status | deep | OpenAI operator latest progress and impact on developers | "impact" causal |
| T6 | news | deep | AI browser agents this week: what changed and why it matters | "what changed" + "why" causal |

---

## Should NOT Trigger (12 cases)

| ID | Intent | Mode | Query | Why Not |
|----|--------|------|-------|---------|
| N1 | resource | fast | Anthropic MCP official docs | resource intent excluded |
| N2 | tutorial | answer | Rust CLI tutorial | tutorial intent excluded |
| N3 | factual | deep | What is WebTransport | single factual query |
| N4 | factual | answer | What is Model Context Protocol | answer mode excluded |
| N5 | news | deep | OpenAI latest news | news without analysis signal |
| N6 | news | deep | AI news this week 2026 | ordinary news multi-query, no reasoning signal |
| N7 | status | deep | Deno 2.0 latest status | status without analysis signal |
| N8 | status | deep | PostgreSQL 18 release date | status factual, no reasoning |
| N9 | exploratory | deep | RISC-V ecosystem overview | exploratory without judgment/causal |
| N10 | exploratory | deep | Kubernetes 生态 | broad topic word only |
| N11 | comparison | deep | Bun ecosystem maturity | comparison intent but no compare/judgment signal |
| N12 | status | deep | Deno 2.0 latest 2026 | status multi-query without reasoning signal |

---

## Validation

Run the detection function against all 18 cases:

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path

path = Path('search-layer/scripts/search.py')
spec = importlib.util.spec_from_file_location('search_mod', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cases = [
    {"id":"T1","intent":"comparison","mode":"deep","queries":["Bun vs Deno","Bun advantages","Deno advantages"],"expected":True},
    {"id":"T2","intent":"comparison","mode":"deep","queries":["React 和 Vue 区别"],"expected":True},
    {"id":"T3","intent":"exploratory","mode":"deep","queries":["RISC-V 生态现在发展到什么阶段，值得持续关注吗？"],"expected":True},
    {"id":"T4","intent":"exploratory","mode":"deep","queries":["AI coding agents landscape 2026, which one should we adopt?"],"expected":True},
    {"id":"T5","intent":"status","mode":"deep","queries":["OpenAI operator latest progress and impact on developers"],"expected":True},
    {"id":"T6","intent":"news","mode":"deep","queries":["AI browser agents this week: what changed and why it matters"],"expected":True},
    {"id":"N1","intent":"resource","mode":"fast","queries":["Anthropic MCP official docs"],"expected":False},
    {"id":"N2","intent":"tutorial","mode":"answer","queries":["Rust CLI tutorial"],"expected":False},
    {"id":"N3","intent":"factual","mode":"deep","queries":["What is WebTransport"],"expected":False},
    {"id":"N4","intent":"factual","mode":"answer","queries":["What is Model Context Protocol"],"expected":False},
    {"id":"N5","intent":"news","mode":"deep","queries":["OpenAI latest news"],"expected":False},
    {"id":"N6","intent":"news","mode":"deep","queries":["AI news this week 2026","AI announcement latest"],"expected":False},
    {"id":"N7","intent":"status","mode":"deep","queries":["Deno 2.0 latest status"],"expected":False},
    {"id":"N8","intent":"status","mode":"deep","queries":["PostgreSQL 18 release date"],"expected":False},
    {"id":"N9","intent":"exploratory","mode":"deep","queries":["RISC-V ecosystem overview"],"expected":False},
    {"id":"N10","intent":"exploratory","mode":"deep","queries":["Kubernetes 生态"],"expected":False},
    {"id":"N11","intent":"comparison","mode":"deep","queries":["Bun ecosystem maturity"],"expected":False},
    {"id":"N12","intent":"status","mode":"deep","queries":["Deno 2.0 latest 2026","Deno update release"],"expected":False},
]

misses = []
for c in cases:
    observed = mod._detect_research_profile(c['queries'][0], c['queries'], c['mode'], c['intent']) is not None
    status = '✓' if observed == c['expected'] else '✗'
    if observed != c['expected']:
        misses.append(c)
    print(f"{c['id']}\t{status}")

if misses:
    print("\n=== MISSES ===")
    for m in misses:
        print(f"{m['id']}: {m['queries'][0]}")
    exit(1)
else:
    print("\n✓ All 18 cases passed")
PY
```

Expected output:

```
T1	✓
T2	✓
T3	✓
T4	✓
T5	✓
T6	✓
N1	✓
N2	✓
N3	✓
N4	✓
N5	✓
N6	✓
N7	✓
N8	✓
N9	✓
N10	✓
N11	✓
N12	✓

✓ All 18 cases passed
```

---

## Changelog

### 2026-03-09 P1.5

- 从"有一点复杂味道就触发"收紧为"按 intent 分层判定"
- comparison: 显式对比词 或 判断词 或 3+ 子查询
- exploratory: 判断词 或 因果词 或 对比词（不再因"生态"等宽词误触发）
- status/news: 判断词 或 因果词（不再因普通多查询扩展误触发）
- 新增中文判断词"关注"，覆盖"值得持续关注"类查询
