"""P4 eval runner: drive the agent service over a fixed question set, collect
latency + retrieval + judge scores, print a table and save JSON.

Run ON the box where the agent service is reachable (e.g. the GCloud VM):

    python -m scripts.eval_runner \
        --base-url http://localhost:8100 \
        --key "$AGENT_INTERNAL_KEY" \
        --questions data/eval/questions.jsonl \
        --out data/eval/results-$(date +%Y%m%d-%H%M).json \
        [--judge]

--judge additionally calls /internal/agent/evaluate (LLM-as-judge, 5 metrics).
Without it you still get latency/agents/source_count/retry per question.

No new deps: uses httpx (already required by the services).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid

import httpx


def load_questions(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_chat(client: httpx.Client, base_url: str, key: str, query: str) -> tuple[dict, float]:
    """POST /internal/agent/chat; return (response_json, wall_clock_ms)."""
    payload = {
        "request_id": str(uuid.uuid4()),
        "message": query,
        "session_id": f"eval-{uuid.uuid4()}",
        "requested_trace_level": "full",
    }
    started = time.perf_counter()
    resp = client.post(
        f"{base_url}/internal/agent/chat",
        json=payload,
        headers={"X-Internal-Agent-Key": key},
        timeout=120,
    )
    wall_ms = (time.perf_counter() - started) * 1000
    resp.raise_for_status()
    return resp.json(), wall_ms


def run_judge(client: httpx.Client, base_url: str, key: str, question: str, chat: dict) -> dict:
    body = {
        "question": question,
        "answer": chat.get("final_response", ""),
        "sources": chat.get("sources", []),
        "trace": chat.get("full_trace", {}),
    }
    resp = client.post(
        f"{base_url}/internal/agent/evaluate",
        json=body,
        headers={"X-Internal-Agent-Key": key},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def detect_retry(chat: dict) -> bool:
    """Did the self-correction loop fire? full_trace.correction_round > 0."""
    return (chat.get("full_trace") or {}).get("correction_round", 0) > 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8100")
    ap.add_argument("--key", required=True, help="AGENT_INTERNAL_KEY")
    ap.add_argument("--questions", default="data/eval/questions.jsonl")
    ap.add_argument("--out", default="data/eval/results.json")
    ap.add_argument("--judge", action="store_true", help="also run LLM-as-judge")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    rows: list[dict] = []

    with httpx.Client() as client:
        for q in questions:
            qid, query = q["id"], q["query"]
            try:
                chat, wall_ms = run_chat(client, args.base_url, args.key, query)
            except Exception as exc:  # keep going; record the failure
                print(f"[{qid}] CHAT FAILED: {exc}", file=sys.stderr)
                rows.append({"id": qid, "probe": q.get("probe"), "error": str(exc)[:200]})
                continue

            trace = chat.get("trace_summary") or {}
            row = {
                "id": qid,
                "probe": q.get("probe"),
                "wall_ms": round(wall_ms, 1),
                "trace_latency_ms": round(trace.get("latency_ms", 0.0), 1),
                "agents": chat.get("agents_used", []),
                "source_count": len(chat.get("sources", [])),
                "retried": detect_retry(chat),
                "answer_len": len(chat.get("final_response", "")),
            }
            if args.judge:
                try:
                    judged = run_judge(client, args.base_url, args.key, query, chat)
                    scores = judged.get("scores", {})
                    row["judge"] = {
                        m: round(v.get("score", 0.0), 3) if isinstance(v, dict) else v
                        for m, v in scores.items()
                    }
                except Exception as exc:
                    print(f"[{qid}] JUDGE FAILED: {exc}", file=sys.stderr)
                    row["judge_error"] = str(exc)[:200]

            rows.append(row)
            print(f"[{qid}] {row['wall_ms']}ms agents={row['agents']} "
                  f"sources={row['source_count']} retried={row['retried']}")

    # Aggregate
    lat = [r["wall_ms"] for r in rows if "wall_ms" in r]
    summary = {
        "n": len(rows),
        "n_ok": len(lat),
        "wall_ms_p50": round(statistics.median(lat), 1) if lat else None,
        "wall_ms_max": round(max(lat), 1) if lat else None,
        "answer_rate": round(sum(1 for r in rows if r.get("source_count", 0) > 0) / len(rows), 3) if rows else 0,
        "retry_rate": round(sum(1 for r in rows if r.get("retried")) / len(rows), 3) if rows else 0,
    }
    out = {"summary": summary, "rows": rows}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nSaved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
