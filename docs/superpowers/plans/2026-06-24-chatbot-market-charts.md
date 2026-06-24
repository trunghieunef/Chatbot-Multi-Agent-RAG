# Chatbot Market Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a price-trend line chart and a district-comparison bar chart inside chatbot answers when the market-analysis agent has the data.

**Architecture:** Pure chart-builder functions turn the market data the agent already fetched (`timeseries`, `metrics`) into a `ChartSpec` dict; `market_analysis_agent.build_result` attaches them to `AgentResult.charts`; the synthesize node carries them to `AgentChatResponse.charts` (the public-API/frontend `charts` field already exists end-to-end); a new `ChatChart` recharts component renders them in the bubble. Charts are deterministic post-processing (Plan A), not a tool the LLM calls.

**Tech Stack:** Python (agent_service, pure functions + Pydantic), Next.js + React + TypeScript + recharts (already a dependency, used in `/thi-truong`).

## Global Constraints

- Chart unit label: `triệu VNĐ/m²`.
- `line_band` = solid avg line + dashed min and max lines (matches the reference image); `bar` = one `avg` bar per district, sorted descending.
- Thresholds: price-trend needs **≥ 2** months with a numeric `avg`; district-comparison needs **≥ 2** distinct districts — otherwise the builder returns `None` (no chart).
- Charts are built deterministically in `build_result` (NOT a registered tool).
- Backend: Python type hints; pure builders do no I/O. Frontend: TypeScript strict, recharts only, Tailwind v4, lucide-react only.
- No frontend unit-test framework exists; frontend tasks gate on `cd frontend && npm run lint`.
- The `charts` field already exists in `agent_service/contracts.py` (AgentResult + AgentChatResponse), `backend/app/schemas/chat.py:42`, `backend/app/routers/chat.py:775`, and `frontend/lib/types.ts:171` — do NOT re-add it.

---

### Task 1: Pure chart-builder functions

**Files:**
- Create: `agent_service/graph/charts.py`
- Test: `agent_service/tests/test_charts.py`

**Interfaces:**
- Produces:
  - `build_price_trend_chart(timeseries: list[dict], *, title: str, unit: str = "triệu VNĐ/m²") -> dict | None`
  - `build_district_comparison_chart(metrics: list[dict], *, title: str, unit: str = "triệu VNĐ/m²") -> dict | None`
  - line_band ChartSpec: `{"type":"line_band","title","unit","x_key":"month","data":[{"month","avg","min","max"}]}`
  - bar ChartSpec: `{"type":"bar","title","unit","x_key":"district","data":[{"district","avg"}]}`

- [ ] **Step 1: Write the failing tests**

Create `agent_service/tests/test_charts.py`:
```python
from agent_service.graph.charts import (
    build_district_comparison_chart,
    build_price_trend_chart,
)


def test_price_trend_builds_sorted_line_band():
    rows = [
        {"snapshot_month": "2024-Q4", "avg_price_per_m2": 78, "min_price_per_m2": 60, "max_price_per_m2": 95},
        {"snapshot_month": "2024-Q2", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 88},
    ]
    chart = build_price_trend_chart(rows, title="T")
    assert chart["type"] == "line_band"
    assert chart["x_key"] == "month"
    assert [d["month"] for d in chart["data"]] == ["2024-Q2", "2024-Q4"]
    assert chart["data"][0] == {"month": "2024-Q2", "avg": 70.0, "min": 55.0, "max": 88.0}


def test_price_trend_none_under_two_points():
    assert build_price_trend_chart([{"snapshot_month": "a", "avg_price_per_m2": 78}], title="T") is None
    assert build_price_trend_chart([], title="T") is None


def test_price_trend_skips_rows_without_numeric_avg():
    rows = [
        {"snapshot_month": "a", "avg_price_per_m2": None},
        {"snapshot_month": "b", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 90},
        {"snapshot_month": "c", "avg_price_per_m2": 80, "min_price_per_m2": 60, "max_price_per_m2": 100},
    ]
    chart = build_price_trend_chart(rows, title="T")
    assert [d["month"] for d in chart["data"]] == ["b", "c"]


def test_district_comparison_sorted_desc():
    metrics = [
        {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
        {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
    ]
    chart = build_district_comparison_chart(metrics, title="T")
    assert chart["type"] == "bar"
    assert chart["x_key"] == "district"
    assert [d["district"] for d in chart["data"]] == ["Đống Đa", "Cầu Giấy"]
    assert chart["data"][0] == {"district": "Đống Đa", "avg": 120.0}


def test_district_comparison_none_under_two_and_dedups():
    one = [{"metric": "avg_price_per_m2", "value": 120, "location": {"district": "A"}}]
    assert build_district_comparison_chart(one, title="T") is None
    dup = [
        {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
        {"metric": "avg_price_per_m2", "value": 118, "location": {"district": "Đống Đa"}},
        {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
    ]
    chart = build_district_comparison_chart(dup, title="T")
    assert len(chart["data"]) == 2
    assert chart["data"][0] == {"district": "Đống Đa", "avg": 120.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest agent_service/tests/test_charts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_service.graph.charts'`.

- [ ] **Step 3: Write the implementation**

Create `agent_service/graph/charts.py`:
```python
"""Pure builders that turn already-fetched market data into chart specs.

No I/O — deterministic shaping of data the market tools already returned, so the
chatbot can render a price-trend line and a district-comparison bar in the bubble.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_UNIT = "triệu VNĐ/m²"


def _to_float(value: Any) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def build_price_trend_chart(
    timeseries: list[dict], *, title: str, unit: str = _DEFAULT_UNIT
) -> dict | None:
    """line_band spec from market timeseries rows (snapshot_month + avg/min/max).

    Returns None if fewer than 2 months have a numeric avg.
    """
    points: list[dict[str, Any]] = []
    for row in timeseries:
        month = row.get("snapshot_month")
        avg = _to_float(row.get("avg_price_per_m2"))
        if not month or avg is None:
            continue
        points.append(
            {
                "month": month,
                "avg": avg,
                "min": _to_float(row.get("min_price_per_m2")),
                "max": _to_float(row.get("max_price_per_m2")),
            }
        )
    if len(points) < 2:
        return None
    points.sort(key=lambda p: p["month"])
    return {"type": "line_band", "title": title, "unit": unit, "x_key": "month", "data": points}


def build_district_comparison_chart(
    metrics: list[dict], *, title: str, unit: str = _DEFAULT_UNIT
) -> dict | None:
    """bar spec comparing avg price/m² across districts (first value per district).

    Returns None if fewer than 2 distinct districts have a numeric value.
    """
    by_district: dict[str, float] = {}
    for item in metrics:
        location = item.get("location")
        district = location.get("district") if isinstance(location, dict) else None
        district = district or item.get("district")
        avg = _to_float(item.get("value"))
        if not district or avg is None or district in by_district:
            continue
        by_district[district] = avg
    if len(by_district) < 2:
        return None
    data = sorted(
        ({"district": d, "avg": a} for d, a in by_district.items()),
        key=lambda x: x["avg"],
        reverse=True,
    )
    return {"type": "bar", "title": title, "unit": unit, "x_key": "district", "data": data}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest agent_service/tests/test_charts.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add agent_service/graph/charts.py agent_service/tests/test_charts.py
git commit -m "feat: pure builders for price-trend and district-comparison charts"
```

---

### Task 2: market_analysis_agent emits charts

**Files:**
- Modify: `agent_service/agents/market_analysis_agent.py` (function `build_result`, the "completed" return around lines 142-171)
- Test: `agent_service/tests/test_charts.py` (append)

**Interfaces:**
- Consumes: `build_price_trend_chart`, `build_district_comparison_chart` (Task 1)
- Produces: `MarketAnalysisAgent().build_result(...)` returns `AgentResult` with `.charts` populated when timeseries/metrics are present.

- [ ] **Step 1: Write the failing test (append to `agent_service/tests/test_charts.py`)**

```python
import pytest

from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.contracts import AgentAction, AgentContext


@pytest.mark.asyncio
async def test_market_agent_build_result_emits_charts():
    ctx = AgentContext(
        agent_name="market_analysis",
        query="giá Đống Đa đang tăng hay giảm",
        routing_filters={"district": "Đống Đa", "city": "Hà Nội", "property_type": "Căn hộ chung cư"},
    )
    action = AgentAction(
        iteration=1,
        action_type="call_tool",
        status="success",
        tool_result={
            "results": [
                {"snapshot_month": "2024-Q2", "avg_price_per_m2": 70, "min_price_per_m2": 55, "max_price_per_m2": 88},
                {"snapshot_month": "2024-Q4", "avg_price_per_m2": 78, "min_price_per_m2": 60, "max_price_per_m2": 95},
                {"metric": "avg_price_per_m2", "value": 120, "location": {"district": "Đống Đa"}},
                {"metric": "avg_price_per_m2", "value": 105, "location": {"district": "Cầu Giấy"}},
            ]
        },
    )
    result = MarketAnalysisAgent().build_result(ctx, thoughts=[], actions=[action])
    types = {c["type"] for c in result.charts}
    assert types == {"line_band", "bar"}
    trend = next(c for c in result.charts if c["type"] == "line_band")
    assert "Đống Đa" in trend["title"]


def test_market_agent_no_charts_without_data():
    ctx = AgentContext(agent_name="market_analysis", query="x")
    action = AgentAction(iteration=1, action_type="call_tool", status="success", tool_result={"results": []})
    result = MarketAnalysisAgent().build_result(ctx, thoughts=[], actions=[action])
    assert result.charts == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_charts.py::test_market_agent_build_result_emits_charts -q`
Expected: FAIL (`result.charts` is `[]`, so `types == set()` ≠ `{"line_band","bar"}`).

- [ ] **Step 3: Implement — set `charts` on the completed `AgentResult`**

In `agent_service/agents/market_analysis_agent.py`, add the import near the top with the other imports:
```python
from agent_service.graph.charts import (
    build_district_comparison_chart,
    build_price_trend_chart,
)
```
Then replace the final completed return (currently):
```python
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
        )
```
with:
```python
        filters = context.routing_filters or {}
        area = filters.get("district") or filters.get("city") or "khu vực"
        ptype = filters.get("property_type")
        trend_title = f"Biến động giá — {area}" + (f" ({ptype})" if ptype else "")
        comparison_title = f"So sánh giá theo quận — {filters.get('city') or 'khu vực'}"
        charts = [
            chart
            for chart in (
                build_price_trend_chart(timeseries, title=trend_title),
                build_district_comparison_chart(metrics, title=comparison_title),
            )
            if chart is not None
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
            charts=charts,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_charts.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add agent_service/agents/market_analysis_agent.py agent_service/tests/test_charts.py
git commit -m "feat: market_analysis agent attaches price-trend and comparison charts"
```

---

### Task 3: Carry charts through synthesize + state + responses

**Files:**
- Modify: `agent_service/graph/agentic_workflow.py` (GraphState ~52-62; `_initial_state` ~72-84; `_node_synthesize` return ~338-340; non-stream response ~444-457; stream response ~500-509)
- Test: `agent_service/tests/test_charts.py` (append)

**Interfaces:**
- Produces: `_collect_charts(raw_results: dict[str, Any], agents_used: list[str]) -> list[dict]`; `AgentChatResponse.charts` populated from agent results in both non-stream and stream paths.

- [ ] **Step 1: Write the failing test (append to `agent_service/tests/test_charts.py`)**

```python
from agent_service.graph.agentic_workflow import _collect_charts


def test_collect_charts_gathers_only_used_agents():
    raw = {
        "market_analysis": {"charts": [{"type": "bar"}, {"type": "line_band"}]},
        "property_search": {"charts": [{"type": "ignored"}]},
    }
    assert _collect_charts(raw, ["market_analysis"]) == [{"type": "bar"}, {"type": "line_band"}]


def test_collect_charts_handles_missing_and_nonlist():
    assert _collect_charts({}, ["market_analysis"]) == []
    assert _collect_charts({"market_analysis": {}}, ["market_analysis"]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_charts.py::test_collect_charts_gathers_only_used_agents -q`
Expected: FAIL with `ImportError: cannot import name '_collect_charts'`.

- [ ] **Step 3a: Add the helper + state key**

In `agent_service/graph/agentic_workflow.py`, add `final_charts: list` to the `GraphState` TypedDict (after `suggested_actions: list`):
```python
    final_response: str
    final_sources: list
    suggested_actions: list
    final_charts: list
```
Add `"final_charts": []` to the dict returned by `_initial_state` (after `"suggested_actions": []`):
```python
        "suggested_actions": [],
        "final_charts": [],
```
Add the module-level helper (place it just above `async def _node_synthesize`):
```python
def _collect_charts(raw_results: dict[str, Any], agents_used: list[str]) -> list[dict]:
    """Gather chart specs emitted by the agents that actually ran."""
    charts: list[dict] = []
    for name in agents_used:
        for chart in (raw_results.get(name) or {}).get("charts", []):
            if isinstance(chart, dict):
                charts.append(chart)
    return charts
```

- [ ] **Step 3b: Carry charts in `_node_synthesize` and both responses**

In `_node_synthesize`, change the final return (currently):
```python
    deduped = list({(s.type, s.id or s.url or s.title): s for s in all_sources}.values())
    return {"final_response": final, "final_sources": deduped,
            "suggested_actions": synth.suggested_actions[:5]}
```
to:
```python
    deduped = list({(s.type, s.id or s.url or s.title): s for s in all_sources}.values())
    return {"final_response": final, "final_sources": deduped,
            "suggested_actions": synth.suggested_actions[:5],
            "final_charts": _collect_charts(raw_results, agents_used)}
```
In the non-stream `AgentChatResponse(...)` (the one with `full_trace={... "mode": "supervisor_specialist_fc"}`), add after the `suggested_actions=` line:
```python
        suggested_actions=final_state.get("suggested_actions", []),
        charts=final_state.get("final_charts", []),
```
In the streaming `AgentChatResponse(...)` (the one with `full_trace={... "streaming": True}`), add after its `suggested_actions=` line:
```python
            suggested_actions=vs.get("suggested_actions", []),
            charts=vs.get("final_charts", []),
```

- [ ] **Step 4: Run tests + compile + suite**

Run: `python -m pytest agent_service/tests/test_charts.py -q && python -m compileall agent_service/graph/agentic_workflow.py -q && python -m pytest agent_service/tests -q`
Expected: test_charts all pass; COMPILE OK; full agent_service suite green.

- [ ] **Step 5: Commit**

```bash
git add agent_service/graph/agentic_workflow.py agent_service/tests/test_charts.py
git commit -m "feat: carry agent charts through synthesize into the chat response"
```

---

### Task 4: Frontend `ChatChart` component

**Files:**
- Create: `frontend/components/chatbot/ChatChart.tsx`

**Interfaces:**
- Produces: default export `ChatChart` with prop `{ chart: Record<string, unknown> }`, rendering a recharts `line_band` (avg solid + min/max dashed) or `bar` chart.

- [ ] **Step 1: Create the component**

```tsx
"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface ChartSpec {
  type: "line_band" | "bar";
  title?: string;
  unit?: string;
  x_key: string;
  data: Record<string, number | string>[];
}

export default function ChatChart({ chart }: { chart: Record<string, unknown> }) {
  const spec = chart as unknown as ChartSpec;
  if (!spec || !Array.isArray(spec.data) || spec.data.length === 0) return null;

  return (
    <div className="rounded-md border border-border/70 bg-card/60 p-2">
      {spec.title && (
        <div className="mb-1 text-[11px] font-medium text-foreground">
          {spec.title}
          {spec.unit ? ` (${spec.unit})` : ""}
        </div>
      )}
      <ResponsiveContainer width="100%" height={180}>
        {spec.type === "line_band" ? (
          <LineChart data={spec.data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={spec.x_key} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={32} />
            <Tooltip />
            <Line type="monotone" dataKey="max" stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="min" stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="avg" stroke="var(--primary)" strokeWidth={2} dot={false} />
          </LineChart>
        ) : (
          <BarChart data={spec.data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey={spec.x_key} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={32} />
            <Tooltip />
            <Bar dataKey="avg" fill="var(--primary)" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors from `ChatChart.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ChatChart.tsx
git commit -m "feat: add ChatChart recharts component (line_band + bar)"
```

---

### Task 5: Render charts in ChatPanel + ChatWidget

**Files:**
- Modify: `frontend/components/chatbot/ChatPanel.tsx` (after the `{msg.content}` paragraph, before the sources block)
- Modify: `frontend/components/chatbot/ChatWidget.tsx` (same location)

**Interfaces:**
- Consumes: `ChatChart` (Task 4); `msg.charts` (already typed `charts?: Record<string, unknown>[] | null` in `lib/types.ts`).

- [ ] **Step 1: ChatPanel — import + render**

Add the import near the other chatbot-component imports:
```tsx
import ChatChart from "./ChatChart";
```
Find the content paragraph:
```tsx
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {msg.content}
                  </p>
```
Insert directly AFTER it:
```tsx
                  {msg.charts && msg.charts.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {msg.charts.map((chart, chartIndex) => (
                        <ChatChart key={chartIndex} chart={chart} />
                      ))}
                    </div>
                  )}
```

- [ ] **Step 2: ChatWidget — import + render**

Add the import near the other chatbot-component imports:
```tsx
import ChatChart from "./ChatChart";
```
Find the content paragraph that renders `{msg.content}` (a `<p className="whitespace-pre-wrap ...">{msg.content}</p>`). Insert directly AFTER it:
```tsx
                    {msg.charts && msg.charts.length > 0 && (
                      <div className="mt-2 space-y-2">
                        {msg.charts.map((chart, chartIndex) => (
                          <ChatChart key={chartIndex} chart={chart} />
                        ))}
                      </div>
                    )}
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors from `ChatPanel.tsx` / `ChatWidget.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chatbot/ChatPanel.tsx frontend/components/chatbot/ChatWidget.tsx
git commit -m "feat: render market charts in chatbot bubbles (ChatPanel + ChatWidget)"
```

---

## Manual verification (after all tasks)

1. Rebuild: `docker compose up -d --build agent-service frontend` (charts need `market_price_snapshots` data for the queried city/district).
2. Ask: "Khu Đống Đa giá đang tăng hay giảm?" → expect a line chart (avg solid + min/max dashed) under the text.
3. Ask: "So sánh giá các quận ở Hà Nội" → expect a bar chart of districts.
4. Ask a market question for an area with no snapshot data → expect text only, no chart, no layout break.

## Self-Review

- **Spec coverage:** line_band builder + bar builder (Task 1); agent emits charts (Task 2); synthesize + state + both responses carry charts (Task 3); ChatChart render line_band/bar (Task 4); rendered under content in both chat UIs (Task 5). Triggers (≥2 points/districts) enforced in Task 1 builders; no-data → None → no chart (Task 1 + manual step 4). Covered.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** ChartSpec keys (`type`, `title`, `unit`, `x_key`, `data` with `month/avg/min/max` and `district/avg`) are identical across Task 1 (producer), Task 4 (`ChartSpec` interface), and Task 2 titles. `_collect_charts` signature matches its Task 3 call site and test.
