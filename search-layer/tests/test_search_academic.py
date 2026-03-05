import importlib.util
import pathlib
import subprocess
import sys
import unittest


def _load_search_module():
    search_path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "search.py"
    spec = importlib.util.spec_from_file_location("search_module", search_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, search_path


search, SEARCH_PATH = _load_search_module()


class SearchAcademicTests(unittest.TestCase):
    def test_decode_openalex_abstract_inverted_index(self):
        inverted = {
            "Transformer": [0],
            "models": [1],
            "work": [2],
            "well": [3],
        }
        text = search.decode_openalex_abstract(inverted)
        self.assertEqual(text, "Transformer models work well")

    def test_build_paper_identity_priority(self):
        with_doi = {"doi": "https://doi.org/10.1000/ABC.1", "url": "https://x"}
        self.assertEqual(search.build_paper_identity(with_doi), ("doi", "10.1000/abc.1"))

        with_arxiv = {"arxiv_id": "2401.12345v2", "url": "https://x"}
        self.assertEqual(search.build_paper_identity(with_arxiv), ("arxiv_id", "2401.12345v2"))

        with_semantic = {"semantic_scholar_id": "abc123", "url": "https://x"}
        self.assertEqual(search.build_paper_identity(with_semantic), ("semantic_scholar_id", "abc123"))

        fallback = {"url": "https://example.com/p?q=1&utm_source=x"}
        self.assertEqual(search.build_paper_identity(fallback), ("url", "https://example.com/p?q=1"))

    def test_source_alias_semantic_to_semantic_scholar(self):
        parsed = search._parse_source_filter("semantic,openalex")
        self.assertEqual(parsed, {"semantic_scholar", "openalex"})

    def test_dedup_prefers_paper_identity(self):
        a = {
            "title": "paper-a",
            "url": "https://doi.org/10.1145/1",
            "doi": "10.1145/1",
            "source": "openalex",
            "citation_count": 10,
            "paper_id": "10.1145/1",
        }
        b = {
            "title": "paper-b",
            "url": "https://www.semanticscholar.org/paper/xyz",
            "doi": "10.1145/1",
            "source": "semantic_scholar",
            "citation_count": 20,
            "paper_id": "10.1145/1",
            "semantic_scholar_id": "xyz",
        }
        deduped = search.dedup([a, b], prefer_paper_identity=True)
        self.assertEqual(len(deduped), 1)
        merged = deduped[0]
        self.assertIn("openalex", merged["source"])
        self.assertIn("semantic_scholar", merged["source"])
        self.assertEqual(merged["citation_count"], 20)

    def test_export_record_uses_structured_fields(self):
        record = search.build_export_record(
            {
                "title": "Attention Is All You Need",
                "authors": ["Ashish Vaswani", "Noam Shazeer"],
                "published_date": "2017-06-12",
                "venue": "NeurIPS",
                "doi": "https://doi.org/10.5555/3295222.3295349",
                "url": "https://papers.nips.cc/paper/7181",
                "source": "semantic",
                "area": "nlp",
                "paper_id": "10.5555/3295222.3295349",
            }
        )
        self.assertEqual(record["authors_text"], "Ashish Vaswani, Noam Shazeer")
        self.assertEqual(record["year"], "2017")
        self.assertEqual(record["doi"], "10.5555/3295222.3295349")
        self.assertEqual(record["source"], "semantic_scholar")

    def test_cli_invalid_source_exit_code_2(self):
        proc = subprocess.run(
            [sys.executable, str(SEARCH_PATH), "test", "--source", "bad_source"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Unknown sources", proc.stderr)


if __name__ == "__main__":
    unittest.main()
