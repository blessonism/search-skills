# Multi-source search for DeepSeek Harness (DSH)

这是可选的 DSH 版本：把 `search-layer` 安装进 DSH 用户技能目录，并在已有全局规则中指定默认入口。仓库顶层的 OpenClaw 技能保持原样。以下命令从本仓库根目录运行。

The DSH profile discovers pages through Exa, Tavily and provider-cited Grok. It uses `bash` to run a Python CLI and DSH `web_fetch` to read a **known URL**. It does not require a separate native search engine. Install this profile **instead of**, not alongside, another skill named `search-layer` in the same DSH skill directory.

## Install the skill

Requirements: Linux, Python 3.10+ with `requests` available to the DSH agent, and at least one configured provider for a live search. From the repository root:

```bash
export DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
source_skill="$PWD/profiles/dsh/search-layer"
target_skill="$DSH_HOME/skills/search-layer"
python3 "$source_skill/scripts/sync_skill_copy.py" --source "$source_skill" --target "$target_skill" --apply
python3 "$source_skill/scripts/sync_skill_copy.py" --source "$source_skill" --target "$target_skill" --check
```

`--apply` installs or updates only the release manifest; target-only files are preserved. To preview an existing installation first, run `--check` before `--apply`. Exit 1 on that check means files differ or are missing. Use real source and target directories, not symlinks. The installer never edits your global instructions or creates credentials.

## Make it the default

Add this paragraph to your **existing** `$DSH_HOME/AGENTS.md`:

> For public web discovery, load the `search-layer` skill and execute its `scripts/search.py` CLI via `bash`. Default to `--mode deep` for Exa, Tavily and provider-cited Grok in parallel. Use `web_fetch` for known URLs and cite original pages. Distinguish a provider outage from an empty search.

This is an agent instruction, not a replacement of DSH's web-provider API. A project-level instruction or a higher-priority skill of the same name can change the effective route. Verify in a new session by asking an ordinary public lookup without naming the skill.

## Configure providers privately

Set provider environment variables (`EXA_API_KEY`, `TAVILY_API_KEY`, `GROK_API_URL` and `GROK_API_KEY`), or create `$DSH_HOME/credentials/search.json` privately outside this checkout. The file must be owned by the DSH user; use mode `0600` on Linux. Example **schema** with empty values:

```json
{
  "exa": "",
  "tavily": "",
  "grok": {"apiUrl": "https://api.x.ai/v1", "apiKey": "", "transport": "responses"}
}
```

Fill only the providers you have. Set `grok.searchModel` or `GROK_SEARCH_MODEL` to the Responses/search-capable model available on your endpoint. `SEARCH_LAYER_CREDENTIALS` may point to one explicit absolute file. Per-provider environment variables override individual fields. The CLI does not scan the current project or another client's config. No credentials, operator configuration, or caches are distributed here.

## Verify and use

```bash
# Offline regression: uses synthetic configuration and mocked provider responses.
python3 -B -m unittest discover -s "$target_skill/scripts/tests"

# Offline presence check; exit 3 if no providers have been configured.
python3 "$target_skill/scripts/search.py" --doctor

# Live query: only run after configuring the providers you intend to use.
python3 "$target_skill/scripts/search.py" --intent resource --num 3 --limit 6 'Python tomllib documentation'
```

The default `deep` mode queries the configured sources in parallel; `fast` (Exa only) and `answer` (Tavily only) are explicit choices. Inspect `providers`, `totalUnique`, `count` and each hit's `sources`. An upstream error can yield `partial`; a successful zero-hit search yields `empty`; if every selected source is unavailable the exit code is 3. A Grok answer containing only prose or inline Markdown links contributes no grounded hits. [Skill instructions](search-layer/SKILL.md) · [Design and maintenance](search-layer/references/dsh-adaptation.md) · [Grok provider contract](search-layer/references/grok-provider-contract.md).
