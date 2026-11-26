from __future__ import annotations

import importlib
import io
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from providers import grok


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class GrokParserTests(unittest.TestCase):
    def test_nested_message_and_action_sources_are_merged(self):
        parsed = grok.parse_grok_responses(fixture("nested-message.json"), "grok-4.5", num=5)
        self.assertEqual(2, len(parsed["results"]))
        first = parsed["results"][0]
        self.assertEqual("https://x.ai/news/grok-4-5", grok.canonicalize_url(first["url"]))
        self.assertEqual("url_citation", first["meta"]["citationKind"])
        self.assertEqual("Official Grok 4.5 announcement", first["snippet"])
        self.assertEqual("2026-07-08", first["published_date"])
        self.assertTrue(first["meta"]["providerGrounded"])

    def test_top_level_output_text(self):
        parsed = grok.parse_grok_responses(fixture("top-level-output-text.json"), "grok-4.5")
        self.assertEqual("Top-level response text.", parsed["answer"])
        self.assertEqual("https://example.com/top-level", parsed["results"][0]["url"])

    def test_action_sources_without_annotations(self):
        parsed = grok.parse_grok_responses(fixture("action-sources.json"), "grok-4.5")
        self.assertEqual(2, len(parsed["results"]))
        self.assertTrue(all(item["meta"]["citationKind"] == "action_source" for item in parsed["results"]))

    def test_x_search_sources_are_grounded(self):
        parsed = grok.parse_grok_responses(fixture("x-search-sources.json"), "grok-4.3")
        self.assertEqual(1, len(parsed["results"]))
        self.assertEqual("x_action_source", parsed["results"][0]["meta"]["citationKind"])
        self.assertEqual("x.com", grok.urlparse(parsed["results"][0]["url"]).hostname)

    def test_responses_sse_completed_event(self):
        lines = (FIXTURES / "responses-stream.sse").read_text(encoding="utf-8").splitlines()
        data = grok.parse_responses_sse(lines)
        parsed = grok.parse_grok_responses(data, "grok-4.3")
        self.assertEqual("Streamed answer.", parsed["answer"])
        self.assertEqual("https://example.com/stream", parsed["results"][0]["url"])
        self.assertIn("response.completed", data["_stream_event_types"])

    def test_legacy_fallback(self):
        parsed = grok.parse_grok_responses(fixture("legacy-output-text.json"), "grok-4.5")
        self.assertEqual("Legacy response text.", parsed["answer"])
        self.assertEqual("legacy", parsed["results"][0]["meta"]["citationKind"])

    def test_missing_citations_produces_no_results(self):
        parsed = grok.parse_grok_responses(fixture("missing-citations.json"), "grok-4.5")
        self.assertEqual([], parsed["results"])
        self.assertEqual(0, parsed["citation_count"])

    def test_markdown_links_require_separate_provider_metadata(self):
        linked_url = "https://example.com/cited"
        body = f"[URL in body]({linked_url}) and [body only](https://example.com/other)"
        block = {"type": "output_text", "text": body}
        response = {"output": [{"type": "message", "content": [block]}]}
        for ungrounded in (response, {"output_text": body}):
            parsed = grok.parse_grok_responses(ungrounded, "grok-4.5")
            self.assertEqual(body, parsed["answer"])
            self.assertEqual([], parsed["results"])
            self.assertEqual(0, parsed["citation_count"])

        block["annotations"] = [{"type": "url_citation", "url": linked_url}]
        parsed = grok.parse_grok_responses(response, "grok-4.5")
        self.assertEqual([linked_url], [item["url"] for item in parsed["results"]])
        self.assertEqual(1, parsed["citation_count"])
        self.assertTrue(parsed["results"][0]["meta"]["providerGrounded"])

    def test_partial_sse_takes_provider_annotation_but_not_inline_link(self):
        events = [{
            "type": "response.output_text.delta",
            "delta": "Text [label](https://example.com/body-only)",
        }]

        def parse():
            data = grok.parse_responses_sse(f"data: {json.dumps(event)}" for event in events)
            return grok.parse_grok_responses(data, "grok-4.5")

        self.assertEqual([], parse()["results"])
        events.append({
            "type": "response.output_text.annotation.added",
            "annotation": {"type": "url_citation", "url": "https://example.com/provider"},
        })
        self.assertEqual(["https://example.com/provider"], [item["url"] for item in parse()["results"]])

    def test_unknown_blocks_are_ignored(self):
        parsed = grok.parse_grok_responses(
            {"output": [{"type": "future_block", "payload": {"anything": True}}]},
            "grok-4.5",
        )
        self.assertEqual([], parsed["results"])


class GrokRequestTests(unittest.TestCase):
    def config(self, **overrides):
        values = {
            "api_url": "https://proxy.example/v1",
            "api_key": "secret",
            "transport": "responses",
            "search_model": "grok-4.5",
            "model_discovery": False,
        }
        values.update(overrides)
        return grok.GrokProviderConfig(**values)

    def test_endpoint_resolution(self):
        self.assertEqual("https://proxy.example/v1/responses", grok.resolve_api_endpoint("https://proxy.example/v1", "responses"))
        self.assertEqual("https://proxy.example/v1/responses", grok.resolve_api_endpoint("https://proxy.example/v1/responses", "responses"))

    def test_payload_contract(self):
        payload = grok.build_responses_payload("latest release", self.config(), "pw")
        self.assertEqual("grok-4.5", payload["model"])
        self.assertFalse(payload["stream"])
        self.assertEqual({"effort": "low"}, payload["reasoning"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual([{"type": "web_search"}], payload["tools"])
        self.assertNotIn("include", payload)
        self.assertIn("<query>latest release</query>", payload["input"][1]["content"])

    def test_stream_is_opt_in(self):
        payload = grok.build_responses_payload("query", self.config(stream=True))
        self.assertTrue(payload["stream"])

    def test_structured_output_uses_responses_text_format(self):
        payload = grok.build_responses_payload("query", self.config(structured_output=True))
        self.assertNotIn("response_format", payload)
        self.assertEqual("json_schema", payload["text"]["format"]["type"])
        self.assertEqual(["answer"], payload["text"]["format"]["schema"]["required"])

    def test_x_search_is_opt_in(self):
        payload = grok.build_responses_payload("query", self.config(x_search=True))
        self.assertEqual([{"type": "web_search"}, {"type": "x_search"}], payload["tools"])

    def test_legacy_model_maps_to_chat_model(self):
        config = grok.config_from_keys({"grok_model": "legacy-model"})
        self.assertEqual("legacy-model", config.chat_model)
        self.assertEqual("grok-4.5", config.search_model)
        self.assertEqual((), config.fallback_search_models)

    def test_legacy_reasoning_format_is_explicit(self):
        payload = grok.build_responses_payload(
            "query",
            self.config(reasoning_format="legacy"),
        )
        self.assertEqual("low", payload["reasoning_effort"])
        self.assertNotIn("reasoning", payload)

    def test_fallback_model_string_is_parsed(self):
        config = grok.config_from_keys({"grok_fallback_search_models": "grok-4.3,grok-4.5"})
        self.assertEqual(("grok-4.3", "grok-4.5"), config.fallback_search_models)


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=None, content_type="application/json"):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.text = text if text is not None else json.dumps(self._data)
        self.headers = {"content-type": content_type}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise grok.requests.HTTPError(response=self)

    def iter_lines(self, decode_unicode=False):
        for line in self.text.splitlines():
            yield line


class GrokGatewayCompatibilityTests(unittest.TestCase):
    def config(self, **overrides):
        values = {
            "api_url": "https://relay.example/v1",
            "api_key": "secret",
            "transport": "responses",
            "search_model": "grok-4.5",
            "fallback_search_models": (),
            "model_discovery": False,
        }
        values.update(overrides)
        return grok.GrokProviderConfig(**values)

    def test_unknown_provider_is_a_routing_failure(self):
        response = FakeResponse(
            status_code=502,
            data={
                "error": {
                    "message": "unknown provider for model grok-4.5",
                    "type": "server_error",
                    "code": "internal_server_error",
                }
            },
        )
        failure = grok.classify_http_failure(response)
        self.assertEqual("provider_unavailable", failure["category"])
        self.assertEqual(502, failure["http_status"])
        self.assertEqual("internal_server_error", failure["error_code"])

    def test_route_not_found_is_responses_unsupported(self):
        failure = grok.classify_http_failure(
            FakeResponse(status_code=404, data={"error": "route not found"})
        )
        self.assertEqual("responses_unsupported", failure["category"])

    def test_canonical_model_resolves_to_spaced_client_id(self):
        models = [
            {"id": "Grok 4.5", "owned_by": "xai"},
            {"id": "Grok Build 0.1", "owned_by": "xai"},
        ]
        self.assertEqual("Grok 4.5", grok.resolve_model_name("grok-4.5", models))
        self.assertEqual(
            "Grok Build 0.1",
            grok.resolve_model_name("grok-build-0.1", models),
        )

    def test_force_refresh_ignores_cached_model_list(self):
        config = self.config(model_discovery=True)
        cached = {
            "modelLists": {
                grok._api_cache_key(config): {
                    "checkedAt": int(grok.time.time()),
                    "models": [{"id": "grok-4.5"}],
                }
            }
        }
        live = FakeResponse(data={"data": [{"id": "Grok 4.5", "owned_by": "xai"}]})
        with (
            patch.object(grok, "_load_cache", return_value=cached),
            patch.object(grok, "_save_cache") as save,
            patch.object(grok.requests, "get", return_value=live) as get,
        ):
            models = grok.list_grok_models(config, force_refresh=True)
        self.assertEqual("Grok 4.5", models[0]["id"])
        get.assert_called_once()
        save.assert_called_once()

    @patch.object(grok, "_load_cache")
    def test_legacy_model_visibility_negative_is_ignored(self, load_cache):
        config = self.config()
        load_cache.return_value = {
            "entries": {
                grok._cache_key(config): {
                    "supportsResponsesSearch": False,
                    "checkedAt": int(grok.time.time()),
                    "detail": "model_not_visible",
                }
            }
        }
        self.assertIsNone(grok.cached_capability(config))

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_provider_failure_is_not_negative_cached(self, post, _cached, record):
        post.return_value = FakeResponse(
            status_code=502,
            data={"error": {"message": "unknown provider for model grok-4.5"}},
        )
        attempts = []
        with patch.object(grok.time, "sleep"), redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses(
                "query",
                self.config(),
                attempts=attempts,
            )
        self.assertEqual([], results)
        self.assertEqual("provider_unavailable", attempts[-1]["error"])
        record.assert_not_called()

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_missing_responses_route_is_negative_cached(self, post, _cached, record):
        post.return_value = FakeResponse(status_code=404, data={"error": "route not found"})
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", self.config())
        self.assertEqual([], results)
        record.assert_called_once_with(self.config(), False, "http_404")

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok, "resolve_visible_model")
    @patch.object(grok.requests, "post")
    def test_unknown_provider_refreshes_catalog_and_reroutes_alias(
        self,
        post,
        resolve_visible_model,
        _cached,
        _record,
    ):
        resolve_visible_model.side_effect = ["grok-4.5", "Grok 4.5"]
        post.side_effect = [
            FakeResponse(
                status_code=502,
                data={"error": {"message": "unknown provider for model grok-4.5"}},
            ),
            FakeResponse(data=fixture("action-sources.json")),
        ]
        attempts = []
        config = self.config(model_discovery=True)
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", config, attempts=attempts)

        self.assertEqual(2, len(results))
        self.assertEqual("grok-4.5", post.call_args_list[0].kwargs["json"]["model"])
        self.assertEqual("Grok 4.5", post.call_args_list[1].kwargs["json"]["model"])
        self.assertEqual("rerouted", attempts[0]["status"])
        self.assertEqual("Grok 4.5", attempts[0]["resolved_model"])
        self.assertEqual("ok", attempts[-1]["status"])


class GrokCacheTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache_path = Path(directory.name) / "grok-capabilities.json"
        self.config = grok.GrokProviderConfig(
            api_url="https://cache-user:cache-password@relay.example/secret-path?token=secret-query",
            api_key="test-api-key",
        )
        patcher = patch.object(grok, "_cache_path", return_value=self.cache_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_concurrent_writers_have_unique_temporary_files(self):
        barrier = threading.Barrier(2)
        seen = []
        original_replace = Path.replace

        def replace(path, target):
            seen.append(path)
            barrier.wait(timeout=5)
            return original_replace(path, target)

        with patch.object(Path, "replace", replace), ThreadPoolExecutor(max_workers=2) as pool:
            # Call the writer directly so the process-local lock cannot mask contention.
            list(pool.map(grok._save_cache, [{"writer": 1}, {"writer": 2}]))
        self.assertEqual(2, len(set(seen)))
        self.assertIn(json.loads(self.cache_path.read_text()), ({"writer": 1}, {"writer": 2}))
        self.assertEqual([self.cache_path], list(self.cache_path.parent.iterdir()))

    def test_read_only_cache_keeps_live_catalog_and_grounded_results(self):
        catalog = FakeResponse(data={"data": [{"id": "Grok 4.5"}]})
        search = FakeResponse(data=fixture("nested-message.json"))
        with (
            patch.object(Path, "replace", side_effect=PermissionError("readonly")),
            patch.object(grok.requests, "get", return_value=catalog) as get,
            patch.object(grok.requests, "post", return_value=search) as post,
            redirect_stderr(io.StringIO()),
        ):
            results = grok.search_grok_responses("query", self.config)
        get.assert_called_once()
        self.assertEqual("Grok 4.5", post.call_args.kwargs["json"]["model"])
        self.assertEqual(2, len(results))
        self.assertEqual([], list(self.cache_path.parent.iterdir()))

    def test_invalid_cache_entries_are_discarded(self):
        for record in (None, [], {"entries": []}, {"entries": {
            grok._cache_key(self.config): {"checkedAt": "invalid", "supportsResponsesSearch": False},
        }}):
            with self.subTest(record=record):
                self.cache_path.write_text(json.dumps(record))
                self.assertIsNone(grok.cached_capability(self.config))

    def test_cache_rewrite_drops_legacy_urls_and_unneeded_model_fields(self):
        old = {"entries": {grok._cache_key(self.config): {
            "apiUrl": self.config.api_url, "checkedAt": int(grok.time.time()),
            "supportsResponsesSearch": True, "detail": self.config.api_url,
        }}}
        self.cache_path.write_text(json.dumps(old))
        model = {"id": "Grok 4.5", "aliases": ["grok-4.5", self.config.api_url],
                 "metadata": self.config.api_url}
        with patch.object(grok.requests, "get", return_value=FakeResponse(data={"data": [model]})) as get:
            grok.list_grok_models(self.config, force_refresh=True)
            self.assertEqual("grok-4.5", grok.resolve_visible_model(self.config))
            get.assert_called_once()
        written = self.cache_path.read_text()
        self.assertNotIn("apiUrl", written)
        self.assertNotIn("cache-password", written)
        self.assertNotIn("secret-path", written)
        self.assertNotIn("secret-query", written)
        self.assertTrue(grok.cached_capability(self.config))


class GrokTransportTests(unittest.TestCase):
    def config(self):
        return grok.GrokProviderConfig(
            api_url="https://proxy.example/v1",
            api_key="secret",
            transport="responses",
            search_model="grok-4.3",
            fallback_search_models=("grok-4.5",),
            model_discovery=False,
            timeout_seconds=60,
        )

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_success_returns_grounded_results(self, post, _cached, _record):
        post.return_value = FakeResponse(data=fixture("nested-message.json"))
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", self.config(), num=3)
        self.assertEqual(2, len(results))
        self.assertTrue(all(item["meta"]["providerGrounded"] for item in results))
        sent = post.call_args.kwargs["json"]
        self.assertFalse(sent["stream"])

    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_ungrounded_attempt_reports_server_tool_usage(self, post, _cached):
        post.return_value = FakeResponse(
            data={
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "no sources"}]}],
                "usage": {"num_server_side_tools_used": 0, "num_sources_used": 0},
            }
        )
        attempts = []
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", self.config(), attempts=attempts)
        self.assertEqual([], results)
        self.assertEqual("ungrounded", attempts[-1]["status"])
        self.assertEqual(0, attempts[-1]["server_tools_used"])
        self.assertEqual(0, attempts[-1]["sources_used"])

    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post", side_effect=grok.requests.Timeout("timeout"))
    def test_timeout_returns_empty(self, _post, _cached):
        with redirect_stderr(io.StringIO()):
            self.assertEqual([], grok.search_grok_responses("query", self.config()))

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_retry_on_429(self, post, _cached, _record):
        post.side_effect = [
            FakeResponse(status_code=429, data={"error": "rate"}),
            FakeResponse(data=fixture("action-sources.json")),
        ]
        with patch.object(grok.time, "sleep"), redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", self.config())
        self.assertEqual(2, post.call_count)
        self.assertEqual(2, len(results))

    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_unexpected_sse_returns_empty(self, post, _cached):
        post.return_value = FakeResponse(text="event: response.created", content_type="text/event-stream")
        with redirect_stderr(io.StringIO()):
            self.assertEqual([], grok.search_grok_responses("query", self.config()))

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_nonstream_request_accepts_completed_sse(self, post, _cached, _record):
        post.return_value = FakeResponse(
            text=(FIXTURES / "responses-stream.sse").read_text(encoding="utf-8"),
            content_type="text/event-stream",
        )
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", self.config())
        self.assertEqual(1, len(results))
        self.assertFalse(post.call_args.kwargs["stream"])

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_streaming_sse_returns_grounded_results(self, post, _cached, _record):
        post.return_value = FakeResponse(
            text=(FIXTURES / "responses-stream.sse").read_text(encoding="utf-8"),
            content_type="text/event-stream",
        )
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses("query", grok.replace(self.config(), stream=True))
        self.assertEqual(1, len(results))
        self.assertTrue(post.call_args.kwargs["stream"])

    @patch.object(grok, "_record_capability")
    @patch.object(grok, "cached_capability", return_value=None)
    @patch.object(grok.requests, "post")
    def test_structured_output_400_retries_without_schema(self, post, _cached, _record):
        post.side_effect = [
            FakeResponse(status_code=400, data={"error": "unsupported"}),
            FakeResponse(data=fixture("action-sources.json")),
        ]
        with redirect_stderr(io.StringIO()):
            results = grok.search_grok_responses(
                "query", grok.replace(self.config(), structured_output=True)
            )
        self.assertEqual(2, len(results))
        self.assertIn("text", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("text", post.call_args_list[1].kwargs["json"])

    def test_doctor_redacts_url_credentials_and_limits_gateway_metadata(self):
        api_url = "https://test-user:test-password@relay.example:8443/private-path?token=private-query#private-fragment"
        source_url = "https://public-user:public-password@example.com/private-source?token=source-query"
        config = grok.replace(self.config(), api_url=api_url, fallback_search_models=())
        catalog = FakeResponse(data={"data": [{"id": "Grok 4.3"}, {"id": api_url}]})
        live = FakeResponse(data={
            "citations": [source_url],
            "usage": {"num_server_side_tools_used": api_url, "num_sources_used": {"token": "raw-usage"}},
        })
        with (
            patch.object(grok, "_save_cache"),
            patch.object(grok, "_load_cache", return_value={}),
            patch.object(grok.requests, "get", return_value=catalog),
            patch.object(grok.requests, "post", return_value=live),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            report = grok.doctor(config)
        self.assertEqual("https://relay.example:8443", report["apiUrl"])
        self.assertEqual(["https://example.com"], report["sources"])
        self.assertEqual(["Grok 4.3"], report["grokModels"])
        self.assertTrue(report["groundingObserved"])
        serialized = json.dumps(report) + stderr.getvalue()
        for marker in (
            "test-user", "test-password", "private-path", "private-query", "private-fragment",
            "public-user", "public-password", "private-source", "source-query", "raw-usage",
        ):
            self.assertNotIn(marker, serialized)

    def test_unrecognized_gateway_error_code_and_header_are_not_echoed(self):
        leaked_code = "dummy-sensitive-code"
        leaked_header = "application/json; value=dummy-sensitive-header"
        failure = FakeResponse(status_code=400, data={"error": {"code": leaked_code, "message": leaked_code}})
        non_streaming = FakeResponse(data={}, content_type=leaked_header)
        attempts = []
        with (
            patch.object(grok, "cached_capability", return_value=None),
            patch.object(grok.requests, "post", side_effect=[failure, non_streaming]),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            grok.search_grok_responses("query", self.config(), attempts=attempts)
            grok.search_grok_responses("query", grok.replace(self.config(), stream=True), attempts=attempts)
        self.assertEqual(["request_rejected", "expected_sse"], [attempt["error"] for attempt in attempts])
        serialized = json.dumps(attempts) + stderr.getvalue()
        self.assertNotIn(leaked_code, serialized)
        self.assertNotIn(leaked_header, serialized)

    def test_grounded_search_uses_model_fallback(self):
        config = self.config()
        with patch.object(
            grok,
            "search_grok_responses",
            side_effect=[[], [{"url": "https://example.com", "meta": {"providerGrounded": True}}]],
        ) as call, redirect_stderr(io.StringIO()):
            results = grok.search_grok_grounded("query", config)
        self.assertEqual(2, call.call_count)
        self.assertEqual("grok-4.5", call.call_args_list[1].args[1].search_model)
        self.assertEqual(25, call.call_args_list[1].args[1].timeout_seconds)
        self.assertEqual(1, len(results))


class SearchRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.search = importlib.import_module("search")

    def test_responses_router(self):
        keys = {
            "grok_url": "https://proxy.example/v1",
            "grok_key": "secret",
            "grok_transport": "responses",
            "grok_search_model": "grok-4.5",
            "grok_model_discovery": False,
        }
        with patch.object(self.search, "search_grok_grounded", return_value=[{"url": "https://example.com"}]) as call:
            results = self.search.search_grok("query", keys)
        self.assertEqual([{"url": "https://example.com"}], results)
        self.assertEqual("grok-4.5", call.call_args.args[1].search_model)

    def test_responses_router_overrides_optional_features(self):
        keys = {
            "grok_url": "https://proxy.example/v1",
            "grok_key": "secret",
            "grok_transport": "responses",
            "grok_model_discovery": False,
        }
        with patch.object(self.search, "search_grok_grounded", return_value=[]) as call:
            self.search.search_grok(
                "query", keys, x_search_override=True, stream_override=True,
                structured_output_override=True,
            )
        config = call.call_args.args[1]
        self.assertTrue(config.x_search)
        self.assertTrue(config.stream)
        self.assertTrue(config.structured_output)

    def test_chat_router_is_explicit(self):
        keys = {
            "grok_url": "https://proxy.example/v1",
            "grok_key": "secret",
            "grok_transport": "chat",
            "grok_chat_model": "legacy",
            "grok_fallback_policy": "legacy-chat",
        }
        with patch.object(self.search, "search_grok_chat", return_value=[]) as call:
            self.search.search_grok("query", keys)
        self.assertEqual("legacy", call.call_args.args[3])

    def test_chat_router_is_blocked_by_default(self):
        keys = {
            "grok_url": "https://proxy.example/v1",
            "grok_key": "secret",
            "grok_transport": "chat",
        }
        with patch.object(self.search, "search_grok_chat", return_value=[]) as call, redirect_stderr(io.StringIO()):
            results = self.search.search_grok("query", keys)
        self.assertEqual([], results)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
