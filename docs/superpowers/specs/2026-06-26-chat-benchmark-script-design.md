# Chatbot performance benchmark script — Design

## Context

The thesis needs a "performance evaluation" section with reproducible numbers
(latency p50/p95/p99, throughput, success rate, per-intent breakdown). The system
records `agent_traces.latency_ms` per request and the `/api/v1/chat` response
exposes `request_id` + `agents_used`, but there is no one-command way to fire a
controlled question set and produce an aggregate table. This script provides that.

Scope is **performance only** — latency / throughput / success / intent
distribution. Answer-quality scoring (the LLM-judge `eval_scores`) is explicitly
out of scope (separate concern; chosen by the user).

## Approach

A standalone Python script that drives the **public HTTP API** (`/api/v1/chat`),
so it runs anywhere that can reach the backend (on the server against
`localhost:8000`, or remotely). No direct DB access — latency is measured
client-side (true end-to-end), and the per-category breakdown uses each
question's known intent tag rather than the runtime-classified intent.

To stay under the chat quota (anonymous = 20/day, authenticated = 200/day), the
script authenticates as **one** reusable benchmark user (try `/auth/login`,
register via `/auth/register` on failure) and sends requests with that token.

## Components (all in `scripts/benchmark_chat.py`)

1. **`QUESTIONS`** — a list of `(intent_tag, question)` tuples, ~40 items covering
   `property_search`, `market`, `legal`, `investment`, `project`, `news`, `mixed`.
   Vietnamese, using areas/projects that exist in the data (Nam Từ Liêm, Cầu Giấy,
   Vinhomes Smart City, ...).
2. **`authenticate(base_url) -> str`** — returns a bearer token: POST
   `/auth/login` with the benchmark creds; on failure POST `/auth/register`; return
   the token from `TokenResponse`. Returns `None` to fall back to anonymous (capped
   run) if auth endpoints are unavailable.
3. **`run_benchmark(base_url, token, questions) -> list[Result]`** — for each
   question: record `t0 = perf_counter()`, POST `/api/v1/chat` (`{message, session_id:null}`),
   record latency, HTTP status / exception, and `agents_used` from the response.
   `Result = {intent_tag, question, latency_s, ok: bool, agents_used}`. Sequential
   (one at a time) so latency is clean.
4. **`aggregate(results) -> dict`** — **pure function** computing, overall and per
   `intent_tag`: count, success_rate, and latency avg / p50 / p95 / p99 / min / max.
   Percentiles via `statistics.quantiles` or a small nearest-rank helper.
5. **Output** — print a formatted table (overall row + one row per intent tag) to
   the console, and write the same to `benchmark_<UTC-timestamp>.csv`.

**CLI args:** `--base-url` (default `http://localhost:8000/api/v1`), `--out`
(default auto-timestamped CSV), `--limit N` (run only the first N questions, for a
quick smoke run).

## Data flow

```
authenticate() ─► token
for (tag, q) in QUESTIONS[:limit]:
    t0; POST /chat {message=q}; latency = now-t0; ok = (200 and no error)
        └─► Result{tag, latency, ok, agents_used}
aggregate(results) ─► {overall:{...}, by_tag:{tag:{...}}}
print table  +  write CSV
```

## Error handling

- A request that errors/times out → `ok=False`, latency still recorded; counted in
  success_rate, excluded from latency percentiles? **No** — include its latency
  (it reflects real cost) but mark not-ok; report success_rate separately.
- Auth failure → warn and continue anonymously; if the run exceeds the anon quota
  the script reports the 429s as failures (and the user can supply a token).
- Network/connection error to base_url → exit with a clear message.

## Testing

- **Unit (offline, deterministic):** `aggregate()` on a fixed list of `Result`s
  asserts the percentile/avg/success_rate math (e.g. latencies [0.1,0.2,...,1.0] →
  known p50/p95). Place in `backend/tests/` or a `tests/` next to the script;
  run with `python -m pytest`.
- **Manual:** `python scripts/benchmark_chat.py --limit 3` against the running
  server prints a 3-question table and writes a CSV.

## Out of scope / follow-ups

- LLM-judge quality scores (groundedness/helpfulness/...) — separate eval.
- Concurrency / load testing (this is sequential latency, not stress).
- Reading server-side `agent_traces` (client-side latency is sufficient and
  portable).
