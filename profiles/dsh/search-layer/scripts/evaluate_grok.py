#!/usr/bin/env python3
"""Run grounded Grok evaluation cases against the configured provider."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import search
from providers.grok import config_from_keys, search_grok_grounded


DEFAULT_CASES = SCRIPT_DIR.parent / "references" / "grok-eval-cases.json"


def domain_matches(hostname: str, expected: str) -> bool:
    hostname = hostname.lower().removeprefix("www.")
    expected = expected.lower().removeprefix("www.")
    return hostname == expected or hostname.endswith("." + expected)


def run_case(case: dict, config, num: int) -> dict:
    started = time.monotonic()
    results = search_grok_grounded(case["query"], config, num=num)
    seconds = round(time.monotonic() - started, 2)
    urls = [item.get("url", "") for item in results]
    hosts = [urlparse(url).hostname or "" for url in urls]
    required = case.get("required_domains") or []
    required_hit = not required or any(
        domain_matches(host, expected) for host in hosts for expected in required
    )
    grounded = all(item.get("meta", {}).get("providerGrounded") is True for item in results)
    passed = (
        len(results) >= int(case.get("min_citations") or 1)
        and required_hit
        and grounded
        and seconds <= float(case.get("max_seconds") or 45)
    )
    return {
        "id": case["id"],
        "intent": case.get("intent"),
        "passed": passed,
        "seconds": seconds,
        "resultCount": len(results),
        "requiredDomainHit": required_hit,
        "grounded": grounded,
        "urls": urls,
    }


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile_value * len(ordered)) - 1))
    return round(ordered[index], 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.get("id") in selected]
    if args.limit > 0:
        cases = cases[: args.limit]
    if not cases:
        parser.error("no evaluation cases selected")

    config = config_from_keys(search.get_keys())
    if config.transport != "responses":
        parser.error("Grok transport must be 'responses' for grounded evaluation")

    worker_count = max(1, min(args.workers, len(cases)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(lambda case: run_case(case, config, args.num), cases))
    passed = sum(1 for result in results if result["passed"])
    latencies = [float(result["seconds"]) for result in results]
    output = {
        "model": config.search_model,
        "count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "passRate": round(passed / len(results), 4),
        "workers": worker_count,
        "latencySeconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 2),
        },
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
