# Self-Corrective Agentic RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng agent RAG (LangGraph) từ linear one-shot thành self-corrective agentic RAG: gỡ bottleneck LLM concurrency, đưa thêm field vào chunk, thêm vòng grade→rewrite→retry, và đo lường trước/sau.

**Architecture:** Giữ nguyên graph `supervisor → specialist(fan-out) → synthesize`, chèn 2 node mới `grade` + `rewrite` giữa specialist và synthesize tạo vòng tự sửa (cap 1 vòng). Bottleneck concurrency gỡ bằng config-driven semaphore + cost-write async. Coverage gỡ bằng bổ sung field vào `build_listing_chunks`.

**Tech Stack:** Python 3.12, LangGraph, google-genai (Gemini 2.5 Flash), pgvector, Redis, pytest với fake-LLM transport.

## Global Constraints

- Test offline: agent tests dùng fake LLM transport / injected httpx, KHÔNG hit Gemini/Redis thật (theo `agent_service/tests/conftest.py`).
- Chạy agent test từ **repo root**: `python -m pytest agent_service/tests -q`.
- Ngôn ngữ: response/prompt tiếng Việt; code/comment tiếng Anh.
- State thật của graph là `GraphState` trong `agent_service/graph/agentic_workflow.py:53` (KHÔNG phải `AgentGraphState` ở `state.py` — đó là legacy graph).
- Concurrent state writes từ `Send` fan-out phải qua reducer (`_merge_dicts`). Field mới ghi bởi 1 node đơn (grade/rewrite) không cần reducer.
- Commit sau mỗi task. Commit message imperative, English, kết thúc bằng `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- KHÔNG normalize property_type (clean.py:147 đã làm). KHÔNG wire committee/query_understanding dead code.

---

## File Structure

- `agent_service/config.py` — thêm 3 flag: `AGENT_MAX_CONCURRENT_LLM_CALLS`, `AGENT_GRADE_MIN_SCORE`, `AGENT_MAX_CORRECTION_ROUNDS`.
- `agent_service/llm/cost.py` — tách estimate (CPU) khỏi Redis-write (I/O); thêm bản async fire-and-forget.
- `agent_service/llm/gemini.py` — semaphore config-driven; call site dùng cost-write async.
- `data_pipeline/chunk.py` — `build_listing_chunks` thêm field vào overview.
- `agent_service/graph/agentic_workflow.py` — thêm `correction_round` vào GraphState, node `_node_grade` + `_node_rewrite`, đổi edge, bỏ `print`.
- `agent_service/tests/test_cost_async.py` (new) — test estimate tách write.
- `agent_service/tests/test_grade_rewrite.py` (new) — test quyết định grade + nới filter.
- `agent_service/tests/test_chunk_fields.py` HOẶC test trong backend — test overview chunk chứa field mới.

---

## Task 1: Config-driven LLM semaphore (P1a)

**STATUS: đã code trước khi có plan — task này VERIFY + hoàn thiện, không viết lại từ đầu.**

**Files:**
- Modify: `agent_service/config.py` (đã thêm `AGENT_MAX_CONCURRENT_LLM_CALLS: int = 6`)
- Modify: `agent_service/llm/gemini.py:20-23` (semaphore đọc từ config)

**Interfaces:**
- Produces: `get_agent_settings().AGENT_MAX_CONCURRENT_LLM_CALLS` (int, default 6).

- [ ] **Step 1: Xác nhận flag đã có trong config**

Run: `grep -n "AGENT_MAX_CONCURRENT_LLM_CALLS" agent_service/config.py`
Expected: 1 dòng khai báo `AGENT_MAX_CONCURRENT_LLM_CALLS: int = 6`

- [ ] **Step 2: Xác nhận semaphore đọc config**

Run: `grep -n "_llm_semaphore" agent_service/llm/gemini.py`
Expected: `_llm_semaphore = asyncio.Semaphore(get_agent_settings().AGENT_MAX_CONCURRENT_LLM_CALLS)` và `get_agent_settings` đã import ở đầu file.

- [ ] **Step 3: Compile check**

Run: `python -m compileall agent_service/config.py agent_service/llm/gemini.py`
Expected: không lỗi.

- [ ] **Step 4: Commit**

```bash
git add agent_service/config.py agent_service/llm/gemini.py
git commit -m "make LLM concurrency limit config-driven"
```

---

## Task 2: Async cost-write (P1b)

**STATUS: cost.py đã tách hàm trước khi có plan; gemini.py import đã đổi nhưng CALL SITES chưa đổi. Task này viết test + hoàn thiện call sites.**

**Files:**
- Modify: `agent_service/llm/cost.py` (đã thêm `estimate_runtime_llm_cost`, `_write_cost_to_redis`, `record_runtime_llm_cost_async`; giữ `record_runtime_llm_cost` cho tương thích)
- Modify: `agent_service/llm/gemini.py:163-167, 263-267` (2 call site: đổi `record_runtime_llm_cost` → `record_runtime_llm_cost_async`)
- Test: `agent_service/tests/test_cost_async.py` (new)

**Interfaces:**
- Consumes: `settings` với `AGENT_LLM_COST_TRACKING_ENABLED`, `AGENT_LLM_INPUT_PRICE_PER_MILLION_USD`, `AGENT_LLM_OUTPUT_PRICE_PER_MILLION_USD`, `REDIS_URL`, `AGENT_LLM_MONTHLY_BUDGET_USD`.
- Produces: `estimate_runtime_llm_cost(settings, *, input_tokens, output_tokens) -> float` (pure, no I/O); `record_runtime_llm_cost_async(settings, *, input_tokens, output_tokens) -> float` (estimate ngay + Redis-write fire-and-forget).

- [ ] **Step 1: Write the failing test**

Tạo `agent_service/tests/test_cost_async.py`:

```python
from types import SimpleNamespace

from agent_service.llm.cost import estimate_runtime_llm_cost


def _settings(**over):
    base = dict(
        AGENT_LLM_COST_TRACKING_ENABLED=True,
        AGENT_LLM_INPUT_PRICE_PER_MILLION_USD=1.0,
        AGENT_LLM_OUTPUT_PRICE_PER_MILLION_USD=2.0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_estimate_is_pure_and_correct():
    # 1M input @ $1 + 0.5M output @ $2 = 1 + 1 = 2.0
    amount = estimate_runtime_llm_cost(
        _settings(), input_tokens=1_000_000, output_tokens=500_000
    )
    assert amount == 2.0


def test_estimate_zero_when_tracking_disabled():
    amount = estimate_runtime_llm_cost(
        _settings(AGENT_LLM_COST_TRACKING_ENABLED=False),
        input_tokens=1_000_000, output_tokens=500_000,
    )
    assert amount == 0.0


def test_estimate_zero_when_tokens_none():
    assert estimate_runtime_llm_cost(_settings(), input_tokens=None, output_tokens=5) == 0.0
```

- [ ] **Step 2: Run test to verify it passes (impl đã tồn tại)**

Run: `python -m pytest agent_service/tests/test_cost_async.py -q`
Expected: 3 passed. (Hàm `estimate_runtime_llm_cost` đã được thêm vào cost.py; nếu FAIL vì import → kiểm cost.py đã có hàm.)

- [ ] **Step 3: Đổi 2 call site trong gemini.py sang bản async**

`agent_service/llm/gemini.py` — trong `generate_text_with_usage` (~dòng 163), đổi:
```python
            estimated_cost_usd=record_runtime_llm_cost(
```
thành:
```python
            estimated_cost_usd=record_runtime_llm_cost_async(
```

Và trong `run_tool_loop` (~dòng 263), đổi:
```python
            record_runtime_llm_cost(
                self.settings,
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
            )
```
thành:
```python
            record_runtime_llm_cost_async(
                self.settings,
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
            )
```

- [ ] **Step 4: Verify không còn call blocking + compile**

Run: `grep -n "record_runtime_llm_cost" agent_service/llm/gemini.py`
Expected: cả 2 chỗ là `record_runtime_llm_cost_async`; import ở đầu file là `record_runtime_llm_cost_async`.

Run: `python -m compileall agent_service/llm/cost.py agent_service/llm/gemini.py`
Expected: không lỗi.

- [ ] **Step 5: Chạy test gemini hiện có không vỡ**

Run: `python -m pytest agent_service/tests/test_gemini_tool_loop.py -q`
Expected: passed (fake transport không đụng Redis; `record_runtime_llm_cost_async` với `create_task` an toàn trong loop test).

- [ ] **Step 6: Commit**

```bash
git add agent_service/llm/cost.py agent_service/llm/gemini.py agent_service/tests/test_cost_async.py
git commit -m "move LLM cost Redis-write off the event loop"
```

---

## Task 3: Đưa field vào listing overview chunk (P2)

**Files:**
- Modify: `data_pipeline/chunk.py:32-64` (`build_listing_chunks`, `overview_parts`)
- Test: `data_pipeline` không có test dir riêng → thêm test dưới `backend/tests/` (nơi pipeline tests sống) `backend/tests/test_chunk_listing_fields.py` (new)

**Interfaces:**
- Consumes: `build_listing_chunks(listing: dict) -> list[dict]` với listing dict có thể chứa `frontage`, `road_width`, `direction`, `floors`.
- Produces: chunk `overview` text chứa các field trên khi có giá trị.

- [ ] **Step 1: Write the failing test**

Tạo `backend/tests/test_chunk_listing_fields.py`:

```python
from data_pipeline.chunk import build_listing_chunks


def test_overview_includes_frontage_and_direction():
    listing = {
        "title": "Nhà đẹp",
        "property_type": "Nhà riêng",
        "price_text": "5 tỷ",
        "area_text": "50 m²",
        "district": "Quận 1",
        "city": "TP.HCM",
        "frontage": "5m",
        "road_width": "8m",
        "direction": "Đông Nam",
        "floors": "3",
    }
    chunks = build_listing_chunks(listing)
    overview = next(c["text"] for c in chunks if c["chunk_type"] == "overview")
    assert "Mặt tiền: 5m" in overview
    assert "Đường vào: 8m" in overview
    assert "Hướng: Đông Nam" in overview
    assert "Số tầng: 3" in overview


def test_overview_omits_empty_fields():
    listing = {"title": "Nhà", "price_text": "2 tỷ"}  # no frontage/direction
    chunks = build_listing_chunks(listing)
    overview = next(c["text"] for c in chunks if c["chunk_type"] == "overview")
    assert "Mặt tiền" not in overview
    assert "Hướng" not in overview
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chunk_listing_fields.py -q`
Expected: FAIL — `test_overview_includes_frontage_and_direction` fails ("Mặt tiền: 5m" not in overview).

- [ ] **Step 3: Thêm field vào overview_parts**

`data_pipeline/chunk.py` — trong `build_listing_chunks`, thêm sau các dòng `compact_text` (sau `bathrooms = compact_text(...)` dòng 45):
```python
    frontage = compact_text(listing.get("frontage"))
    road_width = compact_text(listing.get("road_width"))
    direction = compact_text(listing.get("direction"))
    floors = compact_text(listing.get("floors"))
```

Và trong list `overview_parts` (dòng 50-61), thêm 4 dòng trước `f"Khu vực: {region}"`:
```python
        f"Mặt tiền: {frontage}" if frontage else "",
        f"Đường vào: {road_width}" if road_width else "",
        f"Hướng: {direction}" if direction else "",
        f"Số tầng: {floors}" if floors else "",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_chunk_listing_fields.py -q`
Expected: 2 passed.

- [ ] **Step 5: Verify ingestor forward field (đọc, không sửa nếu đã forward)**

Run: `grep -n "frontage\|road_width\|direction\|floors\|prepare_listing_chunks\|build_listing_chunks" data_pipeline/ingestors/listings_ingestor.py`
Expected: ingestor gọi `build_listing_chunks`/`prepare_listing_chunks` với listing dict từ `row_to_listing` (đã có frontage/road_width/direction/floors, clean.py:212-216). Nếu ingestor build dict con thiếu field → thêm field vào dict đó. Ghi lại phát hiện.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/chunk.py backend/tests/test_chunk_listing_fields.py
git commit -m "add frontage/road_width/direction/floors to listing overview chunk"
```

**Re-embed (chạy khi triển khai, KHÔNG trong test cycle):**
- Toàn bộ: `python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details_10k.csv --batch-size 50` (+ `rent_details_1k.csv`).
- Tập mẫu: giới hạn dòng để demo. Ingestor idempotent (xóa chunk cũ + insert mới).

---

## Task 4: Thêm `correction_round` vào GraphState (P3)

**Files:**
- Modify: `agent_service/graph/agentic_workflow.py:53-64` (GraphState), `:74-87` (`_initial_state`)

**Interfaces:**
- Produces: `GraphState["correction_round"]: int` (đơn node ghi, không cần reducer); khởi tạo 0.

- [ ] **Step 1: Thêm field vào GraphState**

`agent_service/graph/agentic_workflow.py` — trong `class GraphState` (sau `final_charts: list` dòng 64):
```python
    correction_round: int
```

- [ ] **Step 2: Khởi tạo trong _initial_state**

Trong `_initial_state` return dict (sau `"final_charts": []` dòng 86):
```python
        "correction_round": 0,
```

- [ ] **Step 3: Compile check**

Run: `python -m compileall agent_service/graph/agentic_workflow.py`
Expected: không lỗi.

- [ ] **Step 4: Commit**

```bash
git add agent_service/graph/agentic_workflow.py
git commit -m "add correction_round to agent graph state"
```

---

## Task 5: Node `grade` + `rewrite` + edge tự sửa (P3 core)

**Files:**
- Modify: `agent_service/graph/agentic_workflow.py` — thêm `_node_grade`, `_node_rewrite`, `_grade_decision`, `_relaxable_filters`, `_relax_filters`; đổi `_new_state_graph`; bỏ `print` trong `_node_synthesize`.
- Modify: `agent_service/config.py` — thêm `AGENT_GRADE_MIN_SCORE`, `AGENT_MAX_CORRECTION_ROUNDS`.
- Test: `agent_service/tests/test_grade_rewrite.py` (new)

**Interfaces:**
- Consumes: `GraphState` với `_agent_results` (dict agent_name→AgentResult.model_dump), `supervisor_plan` (dict có `selected_agents`, `rewritten_query`), `routing_filters` (dict), `correction_round` (int). Config `AGENT_GRADE_MIN_SCORE: float`, `AGENT_MAX_CORRECTION_ROUNDS: int`.
- Grade đọc mỗi AgentResult qua field: `status` ("no_evidence"/"completed"/...), `sources` (list, mỗi source có `rerank_score: float|None`).
- Produces:
  - `_grade_decision(state) -> "synthesize" | "rewrite"`.
  - `_relaxable_filters(filters: dict) -> bool` — True nếu có `bedrooms`/`price_max`/`max_price`/`district`/`area_max`/`max_area` để nới.
  - `_relax_filters(filters: dict) -> dict` — trả filter đã nới (drop bedrooms, +20% price_max, drop district phụ).

- [ ] **Step 1: Thêm config flags**

`agent_service/config.py` — sau `AGENT_MAX_CONCURRENT_LLM_CALLS` (đã có):
```python
    # Self-correction: ngưỡng rerank tối thiểu coi là "đủ tốt"; số vòng retry tối đa.
    AGENT_GRADE_MIN_SCORE: float = 0.2
    AGENT_MAX_CORRECTION_ROUNDS: int = 1
```

- [ ] **Step 2: Write the failing test**

Tạo `agent_service/tests/test_grade_rewrite.py`:

```python
from agent_service.graph.agentic_workflow import (
    _grade_decision, _relaxable_filters, _relax_filters,
)


def _state(results, filters, rnd=0):
    return {
        "_agent_results": results,
        "supervisor_plan": {"selected_agents": list(results.keys())},
        "routing_filters": filters,
        "correction_round": rnd,
    }


def test_zero_results_with_relaxable_filter_retries():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {"bedrooms": 5, "price_max": 2.0})
    assert _grade_decision(state) == "rewrite"


def test_zero_results_no_relaxable_filter_goes_synthesize():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {})  # nothing to relax → honest answer
    assert _grade_decision(state) == "synthesize"


def test_good_results_go_synthesize():
    results = {"property_search": {"status": "completed",
                                   "sources": [{"rerank_score": 0.8}]}}
    state = _state(results, {"bedrooms": 3})
    assert _grade_decision(state) == "synthesize"


def test_cap_stops_second_retry():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {"bedrooms": 5}, rnd=1)  # already retried once
    assert _grade_decision(state) == "synthesize"


def test_relax_drops_bedrooms_and_widens_price():
    relaxed = _relax_filters({"bedrooms": 5, "price_max": 2.0, "district": "Quận 1"})
    assert "bedrooms" not in relaxed
    assert relaxed["price_max"] == 2.4  # +20%
    assert "district" not in relaxed


def test_relaxable_true_false():
    assert _relaxable_filters({"bedrooms": 3}) is True
    assert _relaxable_filters({"listing_type": "sale"}) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest agent_service/tests/test_grade_rewrite.py -q`
Expected: FAIL — ImportError (`_grade_decision` not defined).

- [ ] **Step 4: Thêm helper + node vào agentic_workflow.py**

`agent_service/graph/agentic_workflow.py` — thêm trước `# ── Graph Builder ─` (trước `_new_state_graph`):

```python
# ── Self-correction (grade → rewrite) ─────────────────────────────

_RELAXABLE_KEYS = ("bedrooms", "price_max", "max_price", "district", "area_max", "max_area")


def _relaxable_filters(filters: dict[str, Any]) -> bool:
    """True nếu filter có ràng buộc có thể nới để cứu 0-kết-quả."""
    return any(filters.get(k) not in (None, "") for k in _RELAXABLE_KEYS)


def _relax_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Nới filter: bỏ bedrooms/district phụ, +20% price bound, +20% area bound."""
    relaxed = dict(filters)
    relaxed.pop("bedrooms", None)
    relaxed.pop("num_bedrooms", None)
    relaxed.pop("district", None)
    for pk in ("price_max", "max_price"):
        if isinstance(relaxed.get(pk), (int, float)):
            relaxed[pk] = round(relaxed[pk] * 1.2, 4)
    for ak in ("area_max", "max_area"):
        if isinstance(relaxed.get(ak), (int, float)):
            relaxed[ak] = round(relaxed[ak] * 1.2, 4)
    return relaxed


def _best_rerank_score(results: dict[str, Any]) -> float | None:
    """Điểm rerank cao nhất trên mọi source của mọi agent."""
    scores = [
        s["rerank_score"]
        for rd in results.values()
        for s in rd.get("sources", [])
        if isinstance(s, dict) and isinstance(s.get("rerank_score"), (int, float))
    ]
    return max(scores) if scores else None


def _grade_decision(state: dict[str, Any]) -> str:
    """Heuristic grade (0 LLM): 'rewrite' để tự sửa, 'synthesize' để trả lời."""
    settings = get_agent_settings()
    if state.get("correction_round", 0) >= settings.AGENT_MAX_CORRECTION_ROUNDS:
        return "synthesize"

    results = state.get("_agent_results", {})
    filters = state.get("routing_filters", {}) or {}

    has_evidence = any(
        rd.get("status") not in ("no_evidence", "failed") and rd.get("sources")
        for rd in results.values()
    )
    if not has_evidence:
        # 0 kết quả: chỉ retry nếu filter nới được, nếu không → trả lời trung thực
        return "rewrite" if _relaxable_filters(filters) else "synthesize"

    best = _best_rerank_score(results)
    if best is not None and best < settings.AGENT_GRADE_MIN_SCORE and _relaxable_filters(filters):
        return "rewrite"
    return "synthesize"


async def _node_grade(state: dict[str, Any]) -> dict[str, Any]:
    """No-op node: quyết định thực nằm ở conditional edge _grade_decision."""
    return {}


async def _node_rewrite(state: dict[str, Any]) -> dict[str, Any]:
    """Nới filter (deterministic) + paraphrase truy vấn (1 LLM call), tăng round."""
    filters = state.get("routing_filters", {}) or {}
    plan = dict(state.get("supervisor_plan") or {})

    new_filters = _relax_filters(filters)

    # LLM paraphrase (best-effort; giữ query cũ nếu lỗi/không có client)
    settings = get_agent_settings()
    llm_client = _make_llm_client(settings)
    original = plan.get("rewritten_query") or state["request"].message
    if llm_client is not None:
        try:
            data = await llm_client.generate_json(
                "Viết lại truy vấn bất động sản sau ngắn gọn, giữ nguyên ý, "
                "nới lỏng ràng buộc quá chặt. Trả JSON {\"query\": \"...\"}.\n"
                f"Truy vấn: {original}",
                timeout_seconds=settings.AGENT_LLM_QUERY_TIMEOUT_SECONDS,
            )
            if isinstance(data, dict) and data.get("query"):
                plan["rewritten_query"] = str(data["query"])
        except Exception as exc:  # paraphrase là best-effort
            logger.warning("rewrite paraphrase failed: %s", exc)

    # Reset kết quả cũ để specialist chạy lại sạch (merge reducer thay thế key).
    return {
        "routing_filters": new_filters,
        "supervisor_plan": plan,
        "correction_round": state.get("correction_round", 0) + 1,
        "_agent_results": {},
        "evidence_by_id": {},
    }
```

**LƯU Ý reducer:** `_agent_results`/`evidence_by_id` có reducer `_merge_dicts` → trả `{}` KHÔNG xóa được key cũ (merge giữ cũ). Cần đổi reducer để hỗ trợ reset, HOẶC dùng key riêng cho round mới. Cách lazy: đổi `_merge_dicts` để khi giá trị mới rỗng `{}` thì reset:
```python
def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer for parallel Send writes; empty new dict resets (for retry)."""
    if b == {}:
        return {}
    return {**(a or {}), **(b or {})}
```
(Cập nhật `_merge_dicts` dòng 48-50 theo bản trên.)

- [ ] **Step 5: Run unit test to verify it passes**

Run: `python -m pytest agent_service/tests/test_grade_rewrite.py -q`
Expected: 6 passed.

- [ ] **Step 6: Đổi graph edges + bỏ print**

`agent_service/graph/agentic_workflow.py` — trong `_new_state_graph`, thay khối add_node/edge:
```python
    graph.add_node("supervisor", _node_supervisor)
    graph.add_node("specialist", _node_specialist)
    graph.add_node("grade", _node_grade)
    graph.add_node("rewrite", _node_rewrite)
    graph.add_node("synthesize", _node_synthesize)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", _dispatch, ["specialist", "synthesize"])
    graph.add_edge("specialist", "grade")
    graph.add_conditional_edges("grade", _grade_decision, ["synthesize", "rewrite"])
    graph.add_edge("rewrite", "specialist")
    graph.add_edge("synthesize", END)
    return graph
```

Và bỏ `print(...)` debug trong `_node_synthesize` (dòng ~353-358), thay bằng:
```python
    logger.info(
        "synthesize used_llm=%s warnings=%s agents=%s allowed_evidence=%d final_len=%d",
        synth.used_llm, synth.warnings, agents_used,
        len(allowed_evidence_ids), len(synth.final_response or ""),
    )
```
(bỏ luôn `import sys` nếu không còn dùng — kiểm bằng grep.)

**LƯU Ý dispatch với round mới:** `_dispatch` emit `Send("specialist", {..., **state})`. Sau rewrite, edge `rewrite → specialist` đi thẳng vào specialist KHÔNG qua `_dispatch`, nên specialist chạy lại cho MỌI agent trong `selected_agents`? Không — `rewrite → specialist` là edge thường, chỉ chạy specialist 1 lần với state hiện tại (thiếu `agent_name`). **Phải cho rewrite quay lại supervisor-dispatch, hoặc rewrite tự emit Send.** Cách lazy: đổi `rewrite → specialist` thành đi qua một dispatch lại. Đổi edge thành:
```python
    graph.add_conditional_edges("rewrite", _dispatch, ["specialist", "synthesize"])
```
(bỏ `graph.add_edge("rewrite", "specialist")`). `_dispatch` đọc `supervisor_plan.selected_agents` (vẫn còn) → re-emit Send cho từng agent với state đã nới filter. Cập nhật list nhánh cho đúng.

- [ ] **Step 7: Run full graph e2e test**

Run: `python -m pytest agent_service/tests/test_agentic_endtoend.py agent_service/tests/test_supervisor_graph.py -q`
Expected: passed (vòng mới không phá luồng cũ; ca có evidence tốt đi thẳng synthesize như trước).

- [ ] **Step 8: Compile + full suite**

Run: `python -m compileall agent_service && python -m pytest agent_service/tests -q`
Expected: không lỗi compile; test suite pass (hoặc chỉ fail các test không liên quan đã fail từ trước — ghi lại).

- [ ] **Step 9: Commit**

```bash
git add agent_service/graph/agentic_workflow.py agent_service/config.py agent_service/tests/test_grade_rewrite.py
git commit -m "add grade/rewrite self-correction loop to agent graph"
```

---

## Task 6: Đo lường baseline (P4)

**Files:**
- Không code mới bắt buộc. Dùng `agent_service/evaluation/judge.py` qua endpoint `/internal/agent/evaluate` + query DB observability.

**Interfaces:** đọc-only. Bảng `agent_llm_calls` (latency), `agent_retrieval_events` (result_count), `eval_runs`/`eval_scores` (judge).

- [ ] **Step 1: Chuẩn bị tập câu hỏi cố định**

Tạo file `data/eval/questions.txt` (~10-15 câu tiếng Việt: có câu 0-kết-quả-do-filter, câu hỏi field mới, câu thị trường, câu pháp lý). Ghi vào plan/repo để tái lập.

- [ ] **Step 2: Đo BASELINE (trước khi bật self-correction / trước re-embed nếu muốn tách biến)**

Chạy agent service, gọi từng câu, ghi latency p50/p95 từ `agent_llm_calls`, answer-rate từ `agent_retrieval_events`, điểm judge từ `/internal/agent/evaluate`. Lưu bảng số.

- [ ] **Step 3: Đo SAU (P1-P3 đã bật + đã re-embed)**

Lặp lại Step 2. So sánh. Lưu bảng cho luận văn.

- [ ] **Step 4: Commit tài liệu số đo**

```bash
git add data/eval/questions.txt docs/eval-results.md
git commit -m "add before/after eval baseline for agentic RAG changes"
```

---

## Self-Review

**Spec coverage:**
- P1a semaphore → Task 1 ✓
- P1b async cost-write → Task 2 ✓
- P2 chunk fields + re-embed → Task 3 ✓
- P3 correction_round → Task 4 ✓; grade/rewrite/edge → Task 5 ✓
- P4 đo lường → Task 6 ✓
- "bỏ print debug" → Task 5 Step 6 ✓

**Rủi ro đã ghi rõ trong plan (không phải placeholder):**
1. Reducer `_merge_dicts` không reset khi retry → Task 5 Step 4 đã cho bản sửa reducer.
2. `rewrite → specialist` thiếu Send fan-out → Task 5 Step 6 đổi thành `add_conditional_edges("rewrite", _dispatch, ...)`.
3. Ingestor có thể không forward field mới → Task 3 Step 5 verify + hướng xử lý.

**Type consistency:** `_grade_decision`, `_relaxable_filters`, `_relax_filters`, `_best_rerank_score` dùng nhất quán giữa test (Task 5 Step 2) và impl (Step 4). AgentResult đọc qua `status` + `sources[].rerank_score` (khớp contracts.py:198-201, 40).

**Điểm cần người review chú ý:** Task 5 là task lớn nhất (2 rủi ro reducer/dispatch) — nên review kỹ sau khi chạy `test_agentic_endtoend`.
