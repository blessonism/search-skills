"""Offline DSH contract tests; credentials and provider responses are synthetic."""

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import runtime_config as cfg
import search
import relevance_gate


def hit(source, path="doc", **fields):
    return {"title": path, "url": "https://docs.example/" + path, "snippet": "", "source": source, **fields}


def cli(*argv):
    out = io.StringIO()
    with patch.object(sys, "argv", ["search.py", *argv]), redirect_stdout(out):
        code = search.main()
    return code, json.loads(out.getvalue())


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "dsh"
        self.file = self.home / "credentials/search.json"
        self.file.parent.mkdir(parents=True)
        self.env = patch.dict(os.environ, {"DSH_HOME": str(self.home), "HOME": str(self.root)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def save(self, data, path=None, mode=0o600):
        path = path or self.file
        path.write_text(json.dumps(data), encoding="utf-8")
        path.chmod(mode)
        return path

    def test_explicit_file_wins_and_environment_overrides_each_field(self):
        self.save({"exa": "wrong-profile", "tavily": "wrong-profile"})
        explicit = self.save({"exa": {"apiKey": "file", "baseUrl": "https://relay.example"},
                              "tavily": "fixture", "grok": {"model": "legacy", "stream": False}}, self.root / "chosen")
        with patch.dict(os.environ, {"SEARCH_LAYER_CREDENTIALS": str(explicit), "EXA_API_KEY": "from-env"}):
            keys = cfg.get_keys()
        self.assertEqual(("from-env", "https://relay.example", "fixture", False),
                         (keys['exa'], keys['exa_url'], keys['tavily'], keys['grok_stream']))

    def test_cwd_and_legacy_candidates_cannot_shadow_profile(self):
        legacy = self.root / ".codex/credentials/search.json"
        legacy.parent.mkdir(parents=True)
        self.save({"exa": "wrong-client"}, legacy)
        project = self.root / "project/credentials/search.json"
        project.parent.mkdir(parents=True)
        self.save({"exa": "wrong-project"}, project)
        cwd = Path.cwd()
        try:
            os.chdir(project.parent.parent)
            self.assertEqual({}, cfg.get_keys())
            self.save({"exa": "right-profile"})
            self.assertEqual("right-profile", cfg.get_keys()["exa"])
        finally:
            os.chdir(cwd)

    def test_relevance_gate_uses_same_profile_and_chat_override(self):
        self.save({"grok": {"apiUrl": "https://relay.example", "apiKey": "fixture", "chatModel": "A"}})
        with patch.dict(os.environ, {"GROK_CHAT_MODEL": "B"}):
            self.assertEqual({"grok_url": "https://relay.example", "grok_key": "fixture", "grok_model": "B"},
                             relevance_gate._load_creds())

    def test_explicit_missing_file_is_actionable_without_fallback(self):
        self.save({"exa": "this-should-never-appear"})
        with patch.dict(os.environ, {"SEARCH_LAYER_CREDENTIALS": str(self.root / "typo")}):
            code, data = cli("--doctor")
        self.assertEqual((2, "explicit_credentials_file_missing"), (code, data["reason"]))
        self.assertNotIn("this-should-never-appear", str(data))

    def test_relative_override_not_interpreted_in_cwd(self):
        with patch.dict(os.environ, {"SEARCH_LAYER_CREDENTIALS": "relative.json"}):
            self.assertRaises(cfg.ConfigError, cfg.get_keys)

    def test_insecure_permissions_or_invalid_json_fails_closed(self):
        self.save({"exa": "fixture"}, mode=0o644)
        self.assertEqual("credentials_require_private_owner_access", cli("--doctor")[1]["reason"])
        self.file.chmod(0o600)
        self.file.write_text('{"private-marker":', encoding="utf-8")
        code, data = cli("--doctor")
        self.assertEqual((2, "credentials_unreadable_or_invalid_json"), (code, data["reason"]))
        self.assertNotIn("private-marker", str(data))

    def test_private_fifo_rejected_without_wait(self):
        os.mkfifo(self.file, mode=0o600)
        self.assertEqual("credentials_not_regular_file", cli("--doctor")[1]["reason"])

    def test_doctor_no_network_no_values_and_env_only(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "synthetic-marker"}), patch.object(search, "retrieve") as run:
            code, doctor = cli("--doctor")
        run.assert_not_called()
        self.assertEqual((0, False, False), (code, doctor['network'], doctor['filePresent']))
        self.assertEqual({"exa": False, "tavily": True, "grok": False}, doctor["configured"])
        self.assertNotIn("synthetic-marker", str(doctor))


class RetrievalTests(unittest.TestCase):
    def test_default_deep_parallel_deterministic_source_merge(self):
        barrier = threading.Barrier(3, timeout=2)
        def exa(*a, **kw):
            barrier.wait()
            return [hit('exa', 'doc/?utm_source=e', title='', meta={'exaType': 'auto'})]
        def tav(*a, **kw):
            barrier.wait()
            return {'results': [hit('tavily', 'doc', title='Primary title', snippet='primary evidence')]}
        def grok(*a, **kw):
            barrier.wait()
            return [hit('grok', 'doc#section', meta={'providerGrounded': True, 'citationKind': 'action_source'})]
        with (patch.object(search, 'get_keys', return_value={'exa': 'e', 'tavily': 't', 'grok_url':'https://g.example','grok_key':'g'}),
              patch.object(search, 'search_exa', side_effect=exa), patch.object(search, 'search_tavily', side_effect=tav),
              patch.object(search, 'search_grok', side_effect=grok)):
            code, data = cli('doc', '--intent', 'resource')
        self.assertEqual((0, 'ok', 'deep', 1, 1), (code, data['status'], data['mode'], data['count'], data['totalUnique']))
        self.assertEqual([('exa',1), ('tavily',1), ('grok',1)], [(r['source'],r['count']) for r in data['providers']])
        row = data['results'][0]
        self.assertEqual(['exa','tavily','grok'], row['sources'])
        self.assertEqual('Primary title', row['title'])
        self.assertEqual('primary evidence', row['snippet'])
        self.assertTrue(row['sourceMeta']['grok']['providerGrounded'])
        self.assertIn('?utm_source=e', row['url'])

    def test_partial_http_failure_is_not_zero_and_does_not_leak(self):
        response = search.requests.Response(); response.status_code = 429
        with (patch.object(search, 'get_keys', return_value={'exa': 'e', 'tavily': 't'}),
              patch.object(search, 'search_exa', side_effect=search.requests.HTTPError('private-marker', response=response)),
              patch.object(search, 'search_tavily', return_value={'results':[hit('tavily')]})):
            code, data = cli('doc')
        self.assertEqual((0, 'partial', 1), (code, data['status'], data['count']))
        self.assertEqual(['failed','ok','missing_config'], [r['status'] for r in data['providers']])
        self.assertEqual('http_429', data['providers'][0]['reason'])
        self.assertNotIn('private-marker', str(data))

    def test_empty_is_a_success_and_all_down_is_exit_three(self):
        args = ('q', '--mode', 'fast')
        with patch.object(search, 'get_keys', return_value={'exa':'x'}), patch.object(search, 'search_exa', return_value=[]):
            code, data = cli(*args)
            self.assertEqual((0,'empty',0),(code,data['status'],data['count']))
        with patch.object(search, 'get_keys', return_value={'exa':'x'}), patch.object(search, 'search_exa', side_effect=search.requests.Timeout()):
            code, data = cli(*args)
            self.assertEqual((3,'unavailable','timeout'),(code,data['status'],data['providers'][0]['reason']))
        with patch.object(search, 'get_keys', return_value={}):
            code, data = cli('q')
            self.assertEqual((3,'unavailable'), (code,data['status']))

    def test_ungrounded_or_explicit_chat_is_not_dsh_evidence(self):
        keys = {'grok_url':'https://g.example','grok_key':'g'}
        with patch.object(search, 'get_keys', return_value=keys), patch.object(search, 'search_grok', return_value=[hit('grok')]):
            code, data = cli('q','--source','grok')
            self.assertEqual((3, 'ungrounded'), (code, data['providers'][0]['reason']))
        with patch.object(search, 'get_keys', return_value=dict(keys,grok_transport='chat',grok_fallback_policy='legacy-chat')), patch.object(search, 'search_grok') as call:
            code, data = cli('q','--source','grok'); call.assert_not_called()
            self.assertEqual((3,'grounded_transport_required'),(code,data['providers'][0]['reason']))

    def test_query_dedup_limit_and_stable_order(self):
        def exa(query, *a, **kw): return [hit('exa', query)]
        with patch.object(search, 'get_keys', return_value={'exa':'e'}), patch.object(search, 'search_exa', side_effect=exa) as call:
            _, data = cli('--queries','first','second',' first ', '--mode','fast','--limit','1')
        self.assertEqual(2, call.call_count)
        self.assertEqual((['first','second'],[0,1],2,1,'first'),
                         (data['queries'],[r['queryIndex'] for r in data['providers']],data['totalUnique'],data['count'],data['results'][0]['title']))

    def test_answer_explicitly_calls_tavily_only(self):
        with patch.object(search, 'get_keys', return_value={'exa':'e','tavily':'t'}), patch.object(search, 'search_exa') as exa, patch.object(search, 'search_tavily', return_value={'results':[hit('tavily')], 'answer':'summary'}) as tav:
            _, data = cli('q','--mode','answer')
        exa.assert_not_called()
        self.assertTrue(tav.call_args.kwargs['include_answer'])
        self.assertEqual(('summary',['tavily']), (data['answer'],[r['source'] for r in data['providers']]))

    def test_research_requires_opt_in_and_successful_exa(self):
        args = ('A vs B','--intent','comparison')
        with (patch.object(search, 'get_keys', return_value={'exa':'e','tavily':'t'}),
              patch.object(search, 'search_exa', return_value=[hit('exa')]) as exa,
              patch.object(search, 'search_tavily', return_value={'results':[hit('tavily')]}),
              patch.object(search, '_run_exa_research_light', return_value={'profile':'research-light'}) as research):
            cli(*args); research.assert_not_called()
            exa.reset_mock(); cli(*args,'--research','--source','tavily'); exa.assert_not_called(); research.assert_not_called()
            _, data = cli(*args,'--research','--source','exa'); research.assert_called_once()
            self.assertEqual('research-light', data['research']['profile'])

    def test_validation_rejects_unknown_sources_and_excess_budget(self):
        with patch.object(search, 'get_keys', return_value={}), patch.object(search, 'retrieve') as run, redirect_stderr(io.StringIO()):
            for args in [('q','--source','typo'),('q','--source','grok','--mode','fast'),('q','--num','11'),('--queries',*map(str,range(7)))]:
                with self.subTest(args=args), self.assertRaises(SystemExit) as ex:
                    cli(*args)
                self.assertEqual(2, ex.exception.code)
            run.assert_not_called()

    def test_protocol_error_200_is_not_a_successful_empty_search(self):
        response = Mock(status_code=200); response.json.return_value={'error':'private-marker'}
        with patch.object(search, 'get_keys', return_value={'exa':'e','tavily':'t'}), patch.object(search.requests,'post',return_value=response):
            code,data = cli('q','--source','exa,tavily')
        self.assertEqual((3,['invalid_response','invalid_response']), (code,[r['reason'] for r in data['providers']]))
        self.assertNotIn('private-marker', str(data))

    def test_tavily_freshness_applies_to_general_topic(self):
        response = Mock(status_code=200); response.json.return_value={'results':[]}
        with patch.object(search.requests,'post',return_value=response) as post:
            search.search_tavily('q','fixture',freshness='pw')
        self.assertEqual('week',post.call_args.kwargs['json']['time_range'])
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_ref_extraction_skips_arbitrary_domains_without_fetching(self):
        module = Mock(); module._parse_github_url.return_value=None
        with patch.object(search,'_load_fetch_thread',return_value=module):
            data = search._run_extract_refs(['https://example.org','file:///synthetic'])
        self.assertEqual(('skipped_non_github_thread','invalid_http_url'),(data[0]['status'],data[1]['error']))
        module.fetch_web_page.assert_not_called(); module._find_github_token.assert_not_called()


class ReleaseTests(unittest.TestCase):
    def test_copy_only_release_manifest_preserves_target_files(self):
        import sync_skill_copy as sync
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'a/search-layer'; dst = Path(temp) / 'b/search-layer'
            for name in sync.MANIFEST:
                f = src / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_text('fixture')
            (src / '.env').write_text('local-only')
            (src / 'credentials').mkdir(); (src / 'credentials/search.json').write_text('local-only')
            dst.mkdir(parents=True); (dst / 'operator-note').write_text('keep')
            self.assertEqual(len(sync.MANIFEST), len(sync.compare(src,dst)))
            self.assertFalse((dst / 'scripts').exists())
            sync.synchronize(src,dst)
            self.assertEqual([], sync.compare(src,dst))
            self.assertEqual('keep', (dst / 'operator-note').read_text())
            self.assertFalse((dst/'.env').exists()); self.assertFalse((dst/'credentials').exists())

    def test_copy_rejects_nested_or_symlinked_tree(self):
        import sync_skill_copy as sync
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'a/search-layer'; dst = Path(temp) / 'b/search-layer'
            src.mkdir(parents=True); dst.mkdir(parents=True)
            with self.assertRaises(ValueError): sync.compare(src, src / 'nested/search-layer')
            (src / 'SKILL.md').symlink_to(Path(temp) / 'outside')
            with self.assertRaises(ValueError): sync.compare(src,dst)


class RankingTests(unittest.TestCase):
    def test_canonical_key_merges_tracking_but_keeps_semantic_query(self):
        normalize = search.normalize_url
        self.assertEqual(normalize('https://EXAMPLE.com:443/path/?z=1&UTM_SoUrCe=hi&a=#section'), normalize('https://example.com/path?a=&z=1'))
        self.assertNotEqual(normalize('https://example.com/p?id=1'),normalize('https://example.com/p?id=2'))
        self.assertNotEqual(normalize('https://example.com/#/article/1'),normalize('https://example.com/#/article/2'))
        for url in ('file:///fixture', 'https://test:fixture@example.org', 'http://[invalid', None):
            self.assertFalse(normalize(url))

    def test_real_publication_date_only(self):
        self.assertEqual(0.5, search.get_freshness_score({'snippet':str(datetime.now(timezone.utc).year)}))
        dt = datetime.now(timezone.utc) - timedelta(days=4)
        for stamp in (dt.isoformat(),format_datetime(dt)):
            self.assertEqual(0.9, search.get_freshness_score({'published_date':stamp}))

    def test_chinese_bigrams_give_partial_match(self):
        score = search.get_keyword_score({'title':'多源检索', 'snippet':'技术说明'}, '多源检索教程')
        self.assertGreater(score, 0); self.assertLess(score, 1)


if __name__ == '__main__':
    unittest.main()
