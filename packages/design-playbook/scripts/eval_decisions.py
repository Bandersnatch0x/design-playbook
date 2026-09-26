#!/usr/bin/env python3
"""Decision-point eval runner (M-001 design-io-speedup, T-055).

Replays a labeled decision suite (``*.jsonl``) against a target chooser and
reports accuracy / cost-weighted confusion / latency. Offline measurement
tool — never wired into validate.py gates (T-055 Q4).

Suite rows (10-field schema, T-055 Q1)::

    {"id", "stage", "decision", "options": [...], "gold", "cost_class",
     "context": [{"path", "sha256", "lines": [start, end] | null, "note"}],
     "baseline": {"choice", "wall_seconds"}, "engine": null}

Targets:

- ``mock``        deterministic seeded chooser (smoke / CI; no network)
- ``baseline``    free-form LLM answer, choice extracted from text
- ``constrained`` same model, reply-with-label-only prompt
- ``engine``      reserved for the small decision model; exits until the
                  benchmark verdict wires one in

LLM targets read an OpenAI-compatible endpoint from env:
``EVAL_LLM_BASE_URL`` / ``EVAL_LLM_API_KEY`` / ``EVAL_LLM_MODEL``.

Cost classes (T-054 Q2): ``symmetric`` weight 1, ``asymmetric-high`` 3,
``critical`` 5 — weighted accuracy is the headline number.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

COST_WEIGHTS = {"symmetric": 1, "asymmetric-high": 3, "critical": 5}
TARGETS = ("mock", "baseline", "constrained", "engine")

_REQUIRED = ("id", "stage", "decision", "options", "gold", "cost_class", "context")


class SuiteError(ValueError):
    """Malformed suite row or unreadable context reference."""


class StaleContext(Exception):
    """Context reference failed its integrity check; sample is skipped."""


def load_suite(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SuiteError(
            f"suite not a file: {path} (expected a *.jsonl decision suite)"
        )
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SuiteError(f"{path.name}:{line_no} invalid JSON: {exc}") from exc
        missing = [k for k in _REQUIRED if k not in row]
        if missing:
            raise SuiteError(
                f"{path.name}:{line_no} missing fields {missing}; "
                f"required: {list(_REQUIRED)}"
            )
        if not isinstance(row["options"], list) or not row["options"]:
            raise SuiteError(f"{path.name}:{line_no} options must be a non-empty list")
        if row["gold"] not in row["options"] and not any(
            str(row["gold"]).startswith(str(o)) or str(o).startswith(str(row["gold"]))
            for o in row["options"]
        ):
            # gold may carry a compound label (e.g. "T1/T2/T1+5xT4"); keep it,
            # scoring below decides correctness per row semantics
            pass
        if row["cost_class"] not in COST_WEIGHTS:
            raise SuiteError(
                f"{path.name}:{line_no} cost_class must be one of "
                f"{sorted(COST_WEIGHTS)}"
            )
        rows.append(row)
    return rows


def resolve_context(sample: dict[str, Any]) -> str:
    parts: list[str] = []
    for ref in sample["context"]:
        path = Path(ref["path"])
        if not path.is_file():
            raise StaleContext(f"{sample['id']}: context file gone: {path}")
        raw = path.read_bytes()
        expected = ref.get("sha256")
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise StaleContext(f"{sample['id']}: sha256 drift on {path}")
        text = raw.decode("utf-8", errors="replace")
        lines = ref.get("lines")
        if lines:
            start, end = lines
            text = "\n".join(text.splitlines()[start - 1 : end])
        parts.append(text)
    return "\n\n".join(parts)


def _letters(options: list[str]) -> dict[str, str]:
    return {chr(ord("A") + i): opt for i, opt in enumerate(options)}


def build_prompt(sample: dict[str, Any], context: str, constrained: bool) -> str:
    labeled = "\n".join(f"{k}. {v}" for k, v in _letters(sample["options"]).items())
    ask = (
        "Reply with exactly one letter and nothing else."
        if constrained
        else "Which option is correct? Answer briefly, then give the letter."
    )
    return (
        "You are replaying one decision point from a UI design pipeline run.\n"
        f"Stage: {sample['stage']}\nDecision point: {sample['decision']}\n\n"
        f"Context:\n{context}\n\nOptions:\n{labeled}\n\n{ask}"
    )


def _extract_choice(reply: str, options: list[str]) -> str | None:
    labeled = _letters(options)
    for line in reversed(reply.strip().splitlines()):
        token = line.strip().strip("**.:").strip()
        if token in labeled:
            return labeled[token]
    for opt in options:
        if str(opt) in reply:
            return opt
    return None


def choose_mock(sample: dict[str, Any], context: str) -> tuple[str | None, None]:
    # ponytail: deterministic stand-in; hash picks vary per sample so smoke
    # exercises both hit and miss paths
    digest = hashlib.sha256(sample["id"].encode()).digest()
    return sample["options"][digest[0] % len(sample["options"])], None


def _chat(prompt: str) -> str:
    base = os.environ.get("EVAL_LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("EVAL_LLM_API_KEY", "")
    model = os.environ.get("EVAL_LLM_MODEL", "")
    if not (base and key and model):
        raise SuiteError(
            "LLM targets need EVAL_LLM_BASE_URL / EVAL_LLM_API_KEY / "
            "EVAL_LLM_MODEL (OpenAI-compatible chat endpoint)"
        )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read())
    return payload["choices"][0]["message"]["content"]


def _make_llm_chooser(constrained: bool) -> Callable[[dict, str], tuple[str | None, None]]:
    def choose(sample: dict[str, Any], context: str) -> tuple[str | None, None]:
        reply = _chat(build_prompt(sample, context, constrained))
        return _extract_choice(reply, sample["options"]), None

    return choose


def _correct(sample: dict[str, Any], choice: str | None) -> bool:
    if choice is None:
        return False
    gold = str(sample["gold"])
    if choice == gold:
        return True
    # compound golds ("T1/T2/T1+5xT4", "17 app/2 n-a") match on membership
    return any(part.strip() == str(choice) for part in gold.split("/"))


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return round(sorted_vals[idx], 3)


def run_suite(
    suite_path: Path, target: str
) -> dict[str, Any]:
    samples = load_suite(suite_path)
    if target == "engine":
        raise SuiteError(
            "engine target not wired yet — pending benchmark verdict (M-001)"
        )
    chooser: Callable[[dict, str], tuple[str | None, None]] = {
        "mock": choose_mock,
        "baseline": _make_llm_chooser(False),
        "constrained": _make_llm_chooser(True),
    }[target]

    results: list[dict[str, Any]] = []
    stale: list[str] = []
    for sample in samples:
        try:
            context = resolve_context(sample)
        except StaleContext as exc:
            stale.append(str(exc))
            continue
        started = time.perf_counter()
        choice, confidence = chooser(sample, context)
        wall = time.perf_counter() - started
        results.append({
            "id": sample["id"],
            "cost_class": sample["cost_class"],
            "gold": sample["gold"],
            "choice": choice,
            "correct": _correct(sample, choice),
            "confidence": confidence,
            "wall_seconds": round(wall, 3),
        })

    total_w = sum(COST_WEIGHTS[s["cost_class"]] for s in samples if s["id"] in {r["id"] for r in results})
    got_w = sum(COST_WEIGHTS[r["cost_class"]] for r in results if r["correct"])
    per_class: dict[str, dict[str, Any]] = {}
    for r in results:
        bucket = per_class.setdefault(r["cost_class"], {"n": 0, "correct": 0, "confusion": {}})
        bucket["n"] += 1
        bucket["correct"] += int(r["correct"])
        if not r["correct"]:
            key = f"{r['gold']} -> {r['choice']}"
            bucket["confusion"][key] = bucket["confusion"].get(key, 0) + 1
    latencies = sorted(r["wall_seconds"] for r in results)

    return {
        "suite": str(suite_path),
        "target": target,
        "total": len(samples),
        "evaluated": len(results),
        "stale": stale,
        "accuracy": round(sum(r["correct"] for r in results) / max(1, len(results)), 4),
        "weighted_accuracy": round(got_w / max(1, total_w), 4),
        "cost_weights": COST_WEIGHTS,
        "per_class": per_class,
        "latency": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "results": results,
    }


def _report_path(suite_path: Path, target: str) -> Path:
    return suite_path.with_name(f"{suite_path.stem}.report-{target}.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_decisions.py",
        description="Replay a labeled decision suite against a target chooser "
                    "and report accuracy / weighted confusion / latency.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one suite against one target")
    run.add_argument("--suite", required=True, type=Path,
                     help="path to the suite *.jsonl file itself (not its directory)")
    run.add_argument("--target", required=True, choices=TARGETS,
                     help="mock=offline smoke; baseline/constrained need "
                          "EVAL_LLM_* env; engine is reserved")
    args = parser.parse_args(argv)

    try:
        report = run_suite(args.suite, args.target)
    except SuiteError as exc:
        print(f"eval_decisions: {exc}", file=sys.stderr)
        return 2

    out = _report_path(args.suite, args.target)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"target={report['target']} evaluated={report['evaluated']}/{report['total']} "
        f"stale={len(report['stale'])} accuracy={report['accuracy']} "
        f"weighted={report['weighted_accuracy']} "
        f"p50={report['latency']['p50']}s p95={report['latency']['p95']}s"
    )
    for cls, bucket in sorted(report["per_class"].items()):
        print(f"  {cls}: {bucket['correct']}/{bucket['n']} correct")
        for confusion, count in bucket["confusion"].items():
            print(f"    miss {confusion} x{count}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    # One pipe-encoding seam (T-105): UTF-8 on piped stdout/stderr
    # regardless of the host code page. See scripts/stdio_encoding.py.
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
