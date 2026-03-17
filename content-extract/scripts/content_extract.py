#!/usr/bin/env python3
"""content-extract: deterministic MinerU-only extractor for OpenClaw.

Why this exists:
- OpenClaw's `web_fetch` is a tool, not available inside scripts.
- This script provides a stable "fallback engine" that the agent can call
  after probing with `web_fetch`.

It wraps mineru-extract's MCP-aligned script and returns a compact JSON contract.

Usage:
  python3 scripts/content_extract.py --url <URL> [--model MinerU-HTML]

Output (stdout):
  { ok, source_url, engine, markdown, artifacts, sources, notes }

"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys


def _error_output(source_url: str, notes: list[str]) -> dict:
    """
    Builds a standardized error response dictionary for MinerU extraction failures.
    
    Parameters:
        source_url (str): The original source URL related to the failure.
        notes (list[str]): One or more diagnostic or error messages describing the failure.
    
    Returns:
        dict: An error response with the following keys:
            - "ok": `False`
            - "source_url": the provided source_url
            - "engine": "mineru"
            - "markdown": `None`
            - "artifacts": empty dict for artifact placeholders
            - "sources": list containing the provided source_url
            - "notes": the provided notes list
    """
    return {
        "ok": False,
        "source_url": source_url,
        "engine": "mineru",
        "markdown": None,
        "artifacts": {},
        "sources": [source_url],
        "notes": notes,
    }


def _find_mineru_wrapper() -> str:
    """
    Locate the mineru_parse_documents.py wrapper script.
    
    Searches in this order: the MINERU_WRAPPER_PATH environment variable, a monorepo sibling at ../mineru-extract/scripts/mineru_parse_documents.py, and the default OpenClaw workspace under ~/.openclaw/workspace/skills/mineru-extract/scripts/mineru_parse_documents.py.
    
    Returns:
        wrapper_path (str): Filesystem path to the located mineru_parse_documents.py script.
    
    Raises:
        FileNotFoundError: If the wrapper cannot be found in any of the searched locations.
    """
    # 1. Env override
    if v := os.environ.get("MINERU_WRAPPER_PATH"):
        return v

    here = pathlib.Path(__file__).resolve().parent
    # 2. Monorepo sibling: ../mineru-extract/scripts/mineru_parse_documents.py
    candidate = here.parent.parent / "mineru-extract" / "scripts" / "mineru_parse_documents.py"
    if candidate.exists():
        return str(candidate)

    # 3. OpenClaw workspace default
    default = pathlib.Path.home() / ".openclaw" / "workspace" / "skills" / "mineru-extract" / "scripts" / "mineru_parse_documents.py"
    if default.exists():
        return str(default)

    raise FileNotFoundError(
        "Cannot find mineru_parse_documents.py. "
        "Set MINERU_WRAPPER_PATH env or install mineru-extract skill as a sibling directory."
    )


def main() -> int:
    """
    Run the MinerU extraction wrapper with command-line options and emit a compact JSON contract to stdout.
    
    Parses CLI options (requires --url; optional --model, --language, --emit-markdown, --max-chars, --force), locates the mineru_parse_documents wrapper, executes it, and interprets its JSON output. On success writes a standardized success JSON containing fields such as ok, source_url, engine, markdown, artifacts, sources, and notes. On failure writes a standardized error JSON (ok: False, engine: "mineru", notes, etc.).
    
    Returns:
        int: Process exit code:
            0 on successful extraction and output,
            2 if the wrapper is missing, crashes, or returns non-JSON,
            the wrapper's return code (or 1 if the wrapper returned 0) when no items are produced.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", default="MinerU-HTML")
    ap.add_argument("--language", default="ch")
    ap.add_argument("--emit-markdown", action="store_true", default=True)
    ap.add_argument("--max-chars", type=int, default=20000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    try:
        wrapper = _find_mineru_wrapper()
    except FileNotFoundError as e:
        out = _error_output(args.url, [str(e)])
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        return 2

    cmd = [
        sys.executable,
        wrapper,
        "--file-sources",
        args.url,
        "--model-version",
        args.model,
        "--language",
        args.language,
        "--emit-markdown",
        "--max-chars",
        str(args.max_chars),
    ]
    if args.force:
        cmd.append("--force")

    p = subprocess.run(cmd, capture_output=True, text=True)

    try:
        j = json.loads(p.stdout)
    except Exception:
        j = None

    if j is None:
        if p.returncode not in (0, 1):
            out = _error_output(
                args.url,
                [
                    "mineru wrapper crashed",
                    (p.stderr or "").strip()[:500],
                ],
            )
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
            return 2

        out = _error_output(
            args.url,
            ["mineru wrapper returned non-json", (p.stdout or "")[:300]],
        )
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        return 2

    if not j.get("items"):
        notes = []
        if error := j.get("error"):
            notes.append(str(error))
        if errors := j.get("errors"):
            notes.append(json.dumps(errors, ensure_ascii=False)[:800])
        if not notes:
            notes.append("no items")
        out = _error_output(args.url, notes)
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        return p.returncode if p.returncode else 1

    item = j["items"][0]
    sources = [args.url]
    if item.get("full_zip_url"):
        sources.append(item["full_zip_url"])
    if item.get("markdown_path"):
        sources.append(item["markdown_path"])

    out = {
        "ok": True,
        "source_url": args.url,
        "engine": "mineru",
        "markdown": item.get("markdown"),
        "artifacts": {
            "out_dir": item.get("out_dir"),
            "markdown_path": item.get("markdown_path"),
            "zip_path": item.get("zip_path"),
            "task_id": item.get("task_id"),
            "cache_key": item.get("cache_key"),
        },
        "sources": sources,
        "notes": ["mcp-aligned: mineru_parse_documents"],
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
