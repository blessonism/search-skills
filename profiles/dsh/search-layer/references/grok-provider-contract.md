# Grok Provider Contract

## Retrieval invariant

Only URLs returned by xAI provider citations, `web_search_call.action.sources`, or `x_search_call.action.sources` may become `source="grok"` search results. Free-form model text is synthesis, not retrieval evidence.

`searchModel` is a canonical preference, not an assumption that every CPA catalog exposes the same spelling. The client resolves it against exact `/models` `id` / `aliases` values using exact, case-insensitive, then separator-insensitive matching. Human-only `display_name` is never treated as routable unless the relay actually returns it as `id` or `aliases`.

## Default production profile

```json
{
  "transport": "responses",
  "searchModel": "grok-4.5",
  "fallbackSearchModels": [],
  "chatModel": "grok-4.5",
  "reasoningEffort": "low",
  "reasoningFormat": "nested",
  "webSearch": true,
  "xSearch": false,
  "stream": false,
  "structuredOutput": false,
  "timeoutSeconds": 35,
  "modelDiscovery": true,
  "modelCacheTtlSeconds": 21600,
  "fallbackPolicy": "empty"
}
```

## Response parsing order

Text:

1. `output[].type=message -> content[].type=output_text`
2. top-level `output[].type=output_text`
3. legacy top-level `output_text`

Sources are accepted only from provider metadata:

- `output_text.annotations[]` URL citations
- `web_search_call.action.sources[]` and `x_search_call.action.sources[]`
- Legacy message-block and top-level `citations`

Markdown links and URLs in the body stay in the answer text. The same URL yields a search result only when it independently appears in provider metadata. This also applies to SSE and structured output.

## Optional capabilities

- Reasoning defaults to the current Responses shape `reasoning={"effort":"low"}`. Set `reasoningFormat=legacy` only for gateways that require top-level `reasoning_effort`.
- Streaming is opt-in through `stream=true` or `--grok-stream`. The SSE parser prefers the complete `response.completed.response` object and only reconstructs deltas when that event is absent.
- A complete SSE response is accepted even when a relay ignores `stream=false`; this is a transport compatibility path, not permission to accept ungrounded text.
- Structured output is opt-in through `structuredOutput=true` or `--grok-structured-output`. Responses uses `text.format.type=json_schema`; `response_format` is not sent. A 400 on the schema path triggers one retry without structured output.
- X search is opt-in through `xSearch=true` or `--grok-x-search`. X URLs must still come from provider annotations or action sources. Diagnostics distinguish requested capability from observed `x_search_calls`.

## Failure behavior

- 408, 429, and 5xx: retry once with jitter.
- Only a confirmed 404/405/501 Responses route failure records a short-lived negative transport capability.
- `unknown provider for model`, `auth_unavailable`, model visibility failures, request rejection, and generic gateway errors are classified separately and never poison the Responses capability cache.
- A cached model catalog miss triggers one live refresh. An `unknown provider for model` response also triggers one live catalog refresh and retry when the refreshed exact alias differs from the attempted model.
- `/models` visibility is catalog evidence only. `providerRoutable` becomes true only after the data plane returns a valid response, including an ungrounded 200 response.
- Grok Build relays may provide successful model inference without executing native `web_search` / `x_search`. A 200 response with no provider sources remains `ungrounded`; textual search plans, tool-like prose, and model-generated URLs are discarded.
- Primary timeout, malformed JSON, or missing citations may try explicitly configured Responses fallback models; the fallback timeout is capped at 25 seconds.
- If all Responses models fail, return no Grok results.
- Never fall back from grounded Responses search to Chat-generated URLs.
- Exa and Tavily continue when Grok fails.

## Diagnostics

Diagnostics are emitted as one-line redacted JSON on stderr. They may contain provider, transport, model, latency, HTTP status, result count, citation count, retry count, an allowlisted provider error code, and error category. They omit raw headers, provider error messages, page content, reasoning text, and arbitrary usage fields.

`--grok-doctor` reports catalog visibility and data-plane health separately through `modelVisible`, `resolvedSearchModel`, `providerRoutable`, `responsesCapability`, `groundingObserved`, and an `attempts` list. Attempts include observed web/X call counts and integer provider usage counters when present. The doctor exposes only HTTP(S) origins for the API endpoint and sources; user info, paths, queries and fragments are omitted. A visible model with `providerRoutable=false` indicates relay auth/registry routing failure, not a client payload incompatibility.

## Disposable cache

The optional per-user cache (`~/.cache/search-layer/grok-capabilities.json`) stores capability flags and model IDs/aliases under hashed keys, without raw endpoint URLs. A successful cache update also drops legacy endpoint fields. Each writer uses a unique temporary file in the cache directory and atomically replaces the cache. Concurrent writes may replace one another's entries; a missing, malformed, or unwritable cache is treated as unavailable and never discards valid results from the provider.

## Maintenance commands on DSH Linux

Offline regression tests (mocked API requests):

```bash
python3 -B -m unittest discover -s "${DSH_HOME:-$HOME/.dsh}/skills/search-layer/scripts/tests" -p 'test_grok_provider.py'
```

Live checks, with the provider already configured:

```bash
python3 -B "${DSH_HOME:-$HOME/.dsh}/skills/search-layer/scripts/search.py" --grok-doctor

python3 -B "${DSH_HOME:-$HOME/.dsh}/skills/search-layer/scripts/search.py" \
  --queries "Grok 4.5 official announcement" \
  --mode deep --intent resource --source grok --num 3

python3 -B "${DSH_HOME:-$HOME/.dsh}/skills/search-layer/scripts/search.py" \
  "latest official @xai post" --mode deep --intent status --source grok \
  --grok-x-search --grok-stream --grok-structured-output
```
