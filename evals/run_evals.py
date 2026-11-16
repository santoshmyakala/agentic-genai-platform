"""Run the behavioural eval set against the real model.

    python evals/run_evals.py --dry-run          # validate the case file only (no API calls, used in CI)
    python evals/run_evals.py --out evals/report.json

Each case is one agent run (several model calls). Check the cost of a full run on a few cases first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from opscopilot.agent import OpsCopilot
from opscopilot.config import Settings
from opscopilot.retrieval import BM25Index
from opscopilot.tools import build_tools

CASES = Path(__file__).with_name("cases.yaml")
KNOWN_KEYS = {"id", "question", "tools_required", "citations_any", "must_include", "must_not_include", "side_effect"}


def load_cases() -> list[dict]:
    cases = yaml.safe_load(CASES.read_text())["cases"]
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in cases:
        assert set(c) <= KNOWN_KEYS, f"{c['id']}: unknown keys {set(c) - KNOWN_KEYS}"
        assert c.get("side_effect") in {"proposed", "none"}, f"{c['id']}: side_effect must be proposed|none"
    return cases


def grade(case: dict, answer) -> dict[str, bool]:
    called = {t.name for t in answer.tool_calls}
    low = answer.text.lower()
    checks = {
        "tools": set(case.get("tools_required", [])) <= called,
        "must_include": all(s.lower() in low for s in case.get("must_include", [])),
        "must_not_include": not any(s.lower() in low for s in case.get("must_not_include", [])),
        "side_effect": ("cordon_gpu_node" in called) == (case["side_effect"] == "proposed"),
        "completed": answer.stop_reason == "end_turn",
    }
    if case.get("citations_any"):
        checks["citation"] = bool(set(case["citations_any"]) & set(answer.citations))
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cases = load_cases()
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    if args.dry_run:
        print(f"{len(cases)} cases valid")
        return 0

    settings = Settings()
    agent = OpsCopilot(settings, build_tools(settings, BM25Index.from_dir(settings.knowledge_dir)))
    results, total_in, total_out = [], 0, 0
    for case in cases:
        answer = agent.ask(case["question"])
        checks = grade(case, answer)
        total_in, total_out = total_in + answer.input_tokens, total_out + answer.output_tokens
        results.append(
            {
                "id": case["id"],
                "passed": all(checks.values()),
                "checks": checks,
                "tools": [t.name for t in answer.tool_calls],
                "citations": answer.citations,
                "tokens": [answer.input_tokens, answer.output_tokens],
                "answer": answer.text,
            }
        )
        print(f"{'PASS' if results[-1]['passed'] else 'FAIL'}  {case['id']}  {checks}")
    passed = sum(r["passed"] for r in results)
    summary = {
        "model": settings.model,
        "effort": settings.effort,
        "passed": passed,
        "total": len(results),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "results": results,
    }
    print(f"\n{passed}/{len(results)} passed · tokens in={total_in} out={total_out}")
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
