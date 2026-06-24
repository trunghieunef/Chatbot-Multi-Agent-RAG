# Chatbot Listing Comparison Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "So sánh N căn" toggle button under property-search results that reveals a side-by-side comparison table of the returned listings.

**Architecture:** property_search builds a `comparison_table` block (deterministic, from the listings it already has + the area average it already fetched) and appends it to `AgentResult.charts`; the existing `_collect_charts` → response → `msg.charts` plumbing carries it to the frontend; the chat dispatches `msg.charts` by `type` — `comparison_table` renders a toggle button + table, other types still go to `ChatChart`.

**Tech Stack:** Python (agent_service pure functions + Pydantic), Next.js + React + TypeScript (no recharts — plain HTML table).

## Global Constraints

- Reuse the existing `charts` field (a list of display blocks); do NOT add a new response field/plumbing.
- `price_per_m2 = round(price * 1000 / area, 1)` (price is in tỷ → triệu/m²); `null` if price/area missing.
- `pct_vs_area_avg = round((price_per_m2 - avg) / avg * 100, 1)`; `null` if no ppm or no avg.
- Within-set tags (deterministic): "Rẻ nhất" (min price), "Rộng nhất" (max area), "Giá/m² tốt nhất" (min price_per_m2).
- Table columns: Tin (title+link), Giá, Diện tích, Giá/m², PN/WC, Pháp lý, Vị trí, Nội thất, Đánh giá.
- Comparison block only when ≥2 listings; builder returns `None` otherwise.
- The block carries `"auto_open"`: when the user's query expresses comparison intent (lowercased query contains any of "so sanh", "so sánh", "compare", "doi chieu", "đối chiếu"), the table renders expanded by default; otherwise it stays collapsed behind the button.
- Backend type hints; frontend TS strict, lucide-react only; detail links open new tab (`target="_blank" rel="noopener noreferrer"`); frontend gated on `cd frontend && npm run lint`.
- No frontend unit-test framework exists.

---

### Task 1: Backend — fetch legal_status + furniture in resolve

**Files:**
- Modify: `backend/app/services/rag/hybrid_search.py` (the SELECT in `resolve_to_listing_records`)

**Interfaces:**
- Produces: resolved listing records gain `legal_status` and `furniture` keys (in addition to existing `price`, `area`, `bedrooms`, `bathrooms`).

- [ ] **Step 1: Add the two columns to the SELECT**

Find (in `resolve_to_listing_records`):
```python
    query = text(
        "SELECT id, product_id, title, price, price_text, area, area_text, bedrooms, "
        "bathrooms, district, city, address, url "
        "FROM listings WHERE id = ANY(:ids)"
    )
```
Replace with:
```python
    query = text(
        "SELECT id, product_id, title, price, price_text, area, area_text, bedrooms, "
        "bathrooms, district, city, address, url, legal_status, furniture "
        "FROM listings WHERE id = ANY(:ids)"
    )
```

- [ ] **Step 2: Verify compile + existing hybrid tests still pass**

Run: `cd backend && python -m compileall app/services/rag/hybrid_search.py -q && python -m pytest tests/test_hybrid_search.py tests/test_rrf_fusion.py tests/test_listing_images.py -q`
Expected: COMPILE OK and all green (the columns `legal_status`, `furniture` exist on `listings` — model lines 49-50).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/rag/hybrid_search.py
git commit -m "feat: resolve listing legal_status and furniture for comparison"
```

---

### Task 2: Backend — pure `build_comparison_table`

**Files:**
- Modify: `agent_service/graph/charts.py` (add function + tagging helpers)
- Test: `agent_service/tests/test_charts.py` (append)

**Interfaces:**
- Produces: `build_comparison_table(listings: list[dict], *, area_avg_price_per_m2: float | None, unit: str = "triệu VNĐ/m²") -> dict | None`
- comparison_table block: `{"type":"comparison_table","title","unit","area_avg_price_per_m2","rows":[{title,url,price_text,area_text,price_per_m2,bedrooms,bathrooms,legal_status,furniture,location,tags,pct_vs_area_avg}]}`

- [ ] **Step 1: Write the failing tests (append to `agent_service/tests/test_charts.py`)**

```python
from agent_service.graph.charts import build_comparison_table


def test_comparison_table_tags_ppm_and_pct():
    listings = [
        {"id": 1, "title": "A", "url": "/a", "price": 6.6, "area": 79,
         "price_text": "6,6 tỷ", "area_text": "79 m²", "bedrooms": 3, "bathrooms": 2,
         "legal_status": "Sổ đỏ", "furniture": "Đầy đủ", "district": "Nam Từ Liêm", "city": "Hà Nội"},
        {"id": 2, "title": "B", "url": "/b", "price": 3.9, "area": 55,
         "price_text": "3,9 tỷ", "area_text": "55 m²", "bedrooms": 2, "bathrooms": 1,
         "district": "Nam Từ Liêm", "city": "Hà Nội"},
    ]
    table = build_comparison_table(listings, area_avg_price_per_m2=100.0)
    assert table["type"] == "comparison_table"
    assert table["title"] == "So sánh 2 căn"
    rows = table["rows"]
    assert rows[0]["price_per_m2"] == 83.5   # 6.6*1000/79
    assert rows[1]["price_per_m2"] == 70.9   # 3.9*1000/55
    assert rows[0]["location"] == "Nam Từ Liêm, Hà Nội"
    assert "Rộng nhất" in rows[0]["tags"]
    assert "Rẻ nhất" in rows[1]["tags"]
    assert "Giá/m² tốt nhất" in rows[1]["tags"]
    assert rows[0]["pct_vs_area_avg"] == -16.5
    assert rows[1]["pct_vs_area_avg"] == -29.1


def test_comparison_table_none_under_two():
    assert build_comparison_table([{"id": 1, "price": 5, "area": 50}], area_avg_price_per_m2=100.0) is None
    assert build_comparison_table([], area_avg_price_per_m2=None) is None


def test_comparison_table_missing_price_area_and_no_avg():
    listings = [
        {"id": 1, "title": "A", "price": None, "area": None, "price_text": "Liên hệ", "area_text": "N/A"},
        {"id": 2, "title": "B", "price": 4.0, "area": 50, "price_text": "4 tỷ", "area_text": "50 m²"},
    ]
    table = build_comparison_table(listings, area_avg_price_per_m2=None)
    assert table["rows"][0]["price_per_m2"] is None
    assert table["rows"][0]["pct_vs_area_avg"] is None
    assert table["rows"][1]["pct_vs_area_avg"] is None   # no avg
    assert table["rows"][0]["url"] == "/nha-dat-ban/1"   # url fallback from id
    assert "Rẻ nhất" in table["rows"][1]["tags"]         # only B has a numeric price


def test_comparison_table_auto_open_flag():
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79},
        {"id": 2, "title": "B", "price": 3.9, "area": 55},
    ]
    assert build_comparison_table(listings, area_avg_price_per_m2=None)["auto_open"] is False
    assert build_comparison_table(listings, area_avg_price_per_m2=None, auto_open=True)["auto_open"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_charts.py::test_comparison_table_tags_ppm_and_pct -q`
Expected: FAIL with `ImportError: cannot import name 'build_comparison_table'`.

- [ ] **Step 3: Implement (append to `agent_service/graph/charts.py`)**

```python
def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tag_extreme(rows: list[dict], values: list[float | None], tag: str, *, want_min: bool) -> None:
    idxs = [i for i, v in enumerate(values) if isinstance(v, (int, float))]
    if not idxs:
        return
    best = (min if want_min else max)(idxs, key=lambda i: values[i])
    rows[best]["tags"].append(tag)


def build_comparison_table(
    listings: list[dict],
    *,
    area_avg_price_per_m2: float | None,
    unit: str = _DEFAULT_UNIT,
    auto_open: bool = False,
) -> dict | None:
    """Side-by-side comparison block for >=2 listings.

    Computes price_per_m2 (price in tỷ -> triệu/m²), within-set tags
    (cheapest / largest / best price-per-m²), and % vs the area average.
    ``auto_open`` tells the frontend to show the table expanded by default
    (set when the user explicitly asked to compare). Returns None for fewer
    than 2 listings.
    """
    if len(listings) < 2:
        return None

    prices: list[float | None] = []
    areas: list[float | None] = []
    ppms: list[float | None] = []
    rows: list[dict[str, Any]] = []

    for listing in listings:
        price = _num(listing.get("price"))
        area = _num(listing.get("area"))
        ppm = round(price * 1000 / area, 1) if price and area else None
        pct = (
            round((ppm - area_avg_price_per_m2) / area_avg_price_per_m2 * 100, 1)
            if ppm is not None and area_avg_price_per_m2
            else None
        )
        district = listing.get("district") or ""
        city = listing.get("city") or ""
        location = f"{district}, {city}" if district else city
        listing_id = listing.get("id")
        url = listing.get("url") or (f"/nha-dat-ban/{listing_id}" if listing_id else None)

        prices.append(price)
        areas.append(area)
        ppms.append(ppm)
        rows.append(
            {
                "title": listing.get("title"),
                "url": url,
                "price_text": listing.get("price_text"),
                "area_text": listing.get("area_text"),
                "price_per_m2": ppm,
                "bedrooms": listing.get("bedrooms"),
                "bathrooms": listing.get("bathrooms"),
                "legal_status": listing.get("legal_status"),
                "furniture": listing.get("furniture"),
                "location": location,
                "tags": [],
                "pct_vs_area_avg": pct,
            }
        )

    _tag_extreme(rows, prices, "Rẻ nhất", want_min=True)
    _tag_extreme(rows, areas, "Rộng nhất", want_min=False)
    _tag_extreme(rows, ppms, "Giá/m² tốt nhất", want_min=True)

    return {
        "type": "comparison_table",
        "title": f"So sánh {len(rows)} căn",
        "unit": unit,
        "area_avg_price_per_m2": area_avg_price_per_m2,
        "auto_open": auto_open,
        "rows": rows,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest agent_service/tests/test_charts.py -q`
Expected: PASS (all chart tests, including the 3 new comparison ones).

- [ ] **Step 5: Commit**

```bash
git add agent_service/graph/charts.py agent_service/tests/test_charts.py
git commit -m "feat: build_comparison_table with tags and area-average comparison"
```

---

### Task 3: Backend — property_search emits the comparison table

**Files:**
- Modify: `agent_service/agents/property_search_agent.py` (`build_result`: import, area_avg refactor, emit + `charts=`)
- Test: `agent_service/tests/test_charts.py` (append)

**Interfaces:**
- Consumes: `build_comparison_table` (Task 2)
- Produces: `PropertySearchAgent().build_result(...)` returns `AgentResult` with `.charts` containing one `comparison_table` block when ≥2 listings.

- [ ] **Step 1: Write the failing test (append to `agent_service/tests/test_charts.py`)**

```python
from agent_service.agents.property_search_agent import PropertySearchAgent


def _ps_action(results):
    return AgentAction(iteration=1, action_type="call_tool", status="success",
                       tool_result={"results": results})


def test_property_search_emits_comparison_table():
    ctx = AgentContext(agent_name="property_search", query="tìm căn hộ")
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"},
        {"id": 2, "title": "B", "price": 3.9, "area": 55, "price_text": "3,9 tỷ", "area_text": "55 m²"},
    ]
    result = PropertySearchAgent().build_result(ctx, thoughts=[], actions=[_ps_action(listings)])
    tables = [c for c in result.charts if c.get("type") == "comparison_table"]
    assert len(tables) == 1
    assert len(tables[0]["rows"]) == 2


def test_property_search_no_table_for_single_listing():
    ctx = AgentContext(agent_name="property_search", query="tìm căn hộ")
    listings = [{"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"}]
    result = PropertySearchAgent().build_result(ctx, thoughts=[], actions=[_ps_action(listings)])
    assert result.charts == []


def test_property_search_auto_opens_table_on_compare_intent():
    listings = [
        {"id": 1, "title": "A", "price": 6.6, "area": 79, "price_text": "6,6 tỷ", "area_text": "79 m²"},
        {"id": 2, "title": "B", "price": 3.9, "area": 55, "price_text": "3,9 tỷ", "area_text": "55 m²"},
    ]
    # Plain search -> button collapsed
    plain = PropertySearchAgent().build_result(
        AgentContext(agent_name="property_search", query="tìm căn hộ Nam Từ Liêm"),
        thoughts=[], actions=[_ps_action(listings)],
    )
    assert plain.charts[0]["auto_open"] is False
    # Explicit compare request -> table auto-opens
    compare = PropertySearchAgent().build_result(
        AgentContext(agent_name="property_search", query="so sánh các căn này"),
        thoughts=[], actions=[_ps_action(listings)],
    )
    assert compare.charts[0]["auto_open"] is True
```

(`AgentAction`, `AgentContext` are already imported in this test file from the Task-2/charts tests of the market-charts feature.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest agent_service/tests/test_charts.py::test_property_search_emits_comparison_table -q`
Expected: FAIL (`result.charts` is `[]`).

- [ ] **Step 3a: Add the import**

In `agent_service/agents/property_search_agent.py`, add near the top imports:
```python
from agent_service.graph.charts import build_comparison_table
```

- [ ] **Step 3b: Refactor the market-context block to expose `area_avg`**

Find:
```python
        # ── Market context if available ──────────────────────────
        if market_data:
            avg_prices = [
                float(m.get("value", 0))
                for m in market_data
                if m.get("metric") == "avg_price_per_m2" and m.get("value")
            ]
            if avg_prices:
                avg = sum(avg_prices) / len(avg_prices)
                lines.append(f"\n📊 **Giá trung bình khu vực:** {avg:.1f} tr/m²")
                lines.append(
                    "> ℹ️ Giá/m² tính từ diện tích và giá listing. "
                    "Giá thực tế có thể thay đổi khi thương lượng."
                )
```
Replace with:
```python
        # ── Market context (area average price/m²) ───────────────
        area_avg: float | None = None
        avg_prices = [
            float(m.get("value", 0))
            for m in market_data
            if m.get("metric") == "avg_price_per_m2" and m.get("value")
        ]
        if avg_prices:
            area_avg = sum(avg_prices) / len(avg_prices)
            lines.append(f"\n📊 **Giá trung bình khu vực:** {area_avg:.1f} tr/m²")
            lines.append(
                "> ℹ️ Giá/m² tính từ diện tích và giá listing. "
                "Giá thực tế có thể thay đổi khi thương lượng."
            )
```

- [ ] **Step 3c: Build the comparison block and attach `charts`**

Find the final completed return:
```python
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="high" if all_listings else "low",
            iterations=len(thoughts),
        )
```
Replace with:
```python
        query_text = f"{context.normalized_query or ''} {context.query or ''}".lower()
        wants_comparison = any(
            keyword in query_text
            for keyword in ("so sanh", "so sánh", "compare", "doi chieu", "đối chiếu")
        )
        comparison = build_comparison_table(
            all_listings, area_avg_price_per_m2=area_avg, auto_open=wants_comparison
        )

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="high" if all_listings else "low",
            iterations=len(thoughts),
            charts=[comparison] if comparison else [],
        )
```

- [ ] **Step 4: Run tests + compile + suite**

Run: `python -m pytest agent_service/tests/test_charts.py -q && python -m compileall agent_service/agents/property_search_agent.py -q && python -m pytest agent_service/tests -q`
Expected: test_charts pass; COMPILE OK; full agent_service suite green.

- [ ] **Step 5: Commit**

```bash
git add agent_service/agents/property_search_agent.py agent_service/tests/test_charts.py
git commit -m "feat: property_search emits a listing comparison table"
```

---

### Task 4: Frontend — `ComparisonTable` + `ComparisonToggle`

**Files:**
- Create: `frontend/components/chatbot/ComparisonTable.tsx`
- Create: `frontend/components/chatbot/ComparisonToggle.tsx`

**Interfaces:**
- Produces:
  - `ComparisonTable` default export, prop `{ table: Record<string, unknown> }` — renders the table.
  - `ComparisonToggle` default export, prop `{ table: Record<string, unknown> }` — renders a "So sánh N căn" button toggling the table.

- [ ] **Step 1: Create `ComparisonTable.tsx`**

```tsx
"use client";

interface ComparisonRow {
  title?: string;
  url?: string | null;
  price_text?: string;
  area_text?: string;
  price_per_m2?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  legal_status?: string | null;
  furniture?: string | null;
  location?: string;
  tags?: string[];
  pct_vs_area_avg?: number | null;
}

interface ComparisonTableSpec {
  title?: string;
  unit?: string;
  rows: ComparisonRow[];
}

const dash = (v: unknown) =>
  v === null || v === undefined || v === "" ? "—" : String(v);

export default function ComparisonTable({ table }: { table: Record<string, unknown> }) {
  const spec = table as unknown as ComparisonTableSpec;
  if (!spec || !Array.isArray(spec.rows) || spec.rows.length === 0) return null;

  const assess = (r: ComparisonRow) => {
    const parts = [...(r.tags ?? [])];
    if (typeof r.pct_vs_area_avg === "number") {
      const sign = r.pct_vs_area_avg > 0 ? "+" : "";
      parts.push(`${sign}${r.pct_vs_area_avg}% so TB khu vực`);
    }
    return parts.length ? parts.join(" · ") : "—";
  };

  const headers = ["Tin", "Giá", "Diện tích", "Giá/m²", "PN/WC", "Pháp lý", "Vị trí", "Nội thất", "Đánh giá"];

  return (
    <div className="mt-2 overflow-x-auto rounded-md border border-border/70">
      <table className="w-full text-[11px]">
        <thead className="bg-card/70 text-muted-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} className="whitespace-nowrap px-2 py-1 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50 align-top">
              <td className="max-w-[160px] px-2 py-1">
                {r.url ? (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="line-clamp-2 text-primary hover:underline"
                  >
                    {dash(r.title)}
                  </a>
                ) : (
                  <span className="line-clamp-2">{dash(r.title)}</span>
                )}
              </td>
              <td className="whitespace-nowrap px-2 py-1">{dash(r.price_text)}</td>
              <td className="whitespace-nowrap px-2 py-1">{dash(r.area_text)}</td>
              <td className="whitespace-nowrap px-2 py-1">
                {typeof r.price_per_m2 === "number"
                  ? `${r.price_per_m2} ${spec.unit ?? ""}`.trim()
                  : "—"}
              </td>
              <td className="whitespace-nowrap px-2 py-1">
                {dash(r.bedrooms)}/{dash(r.bathrooms)}
              </td>
              <td className="px-2 py-1">{dash(r.legal_status)}</td>
              <td className="px-2 py-1">{dash(r.location)}</td>
              <td className="px-2 py-1">{dash(r.furniture)}</td>
              <td className="px-2 py-1">{assess(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Create `ComparisonToggle.tsx`**

```tsx
"use client";

import { useState } from "react";
import ComparisonTable from "./ComparisonTable";

export default function ComparisonToggle({ table }: { table: Record<string, unknown> }) {
  const spec = table as { rows?: unknown[]; auto_open?: boolean };
  const [open, setOpen] = useState(spec.auto_open === true);
  const count = Array.isArray(spec.rows) ? spec.rows.length : 0;
  if (count < 2) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground transition-colors hover:border-primary hover:bg-primary hover:text-primary-foreground"
      >
        {open ? "Ẩn so sánh" : `So sánh ${count} căn`}
      </button>
      {open && <ComparisonTable table={table} />}
    </div>
  );
}
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors from the two new files.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chatbot/ComparisonTable.tsx frontend/components/chatbot/ComparisonToggle.tsx
git commit -m "feat: ComparisonTable + ComparisonToggle components"
```

---

### Task 5: Frontend — dispatch comparison_table in ChatPanel + ChatWidget

**Files:**
- Modify: `frontend/components/chatbot/ChatPanel.tsx` (the `msg.charts.map` block)
- Modify: `frontend/components/chatbot/ChatWidget.tsx` (the `msg.charts.map` block)

**Interfaces:**
- Consumes: `ComparisonToggle` (Task 4), existing `ChatChart`.

- [ ] **Step 1: ChatPanel — import + dispatch**

Add the import near the other chatbot-component imports:
```tsx
import ComparisonToggle from "./ComparisonToggle";
```
Find:
```tsx
                  {msg.charts && msg.charts.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {msg.charts.map((chart, chartIndex) => (
                        <ChatChart key={chartIndex} chart={chart} />
                      ))}
                    </div>
                  )}
```
Replace with:
```tsx
                  {msg.charts && msg.charts.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {msg.charts.map((chart, chartIndex) =>
                        (chart as { type?: string }).type === "comparison_table" ? (
                          <ComparisonToggle key={chartIndex} table={chart} />
                        ) : (
                          <ChatChart key={chartIndex} chart={chart} />
                        )
                      )}
                    </div>
                  )}
```

- [ ] **Step 2: ChatWidget — import + dispatch**

Add the import near the other chatbot-component imports:
```tsx
import ComparisonToggle from "./ComparisonToggle";
```
Find the equivalent `msg.charts.map(...)` block in `ChatWidget.tsx`:
```tsx
                    {msg.charts && msg.charts.length > 0 && (
                      <div className="mt-2 space-y-2">
                        {msg.charts.map((chart, chartIndex) => (
                          <ChatChart key={chartIndex} chart={chart} />
                        ))}
                      </div>
                    )}
```
Replace with:
```tsx
                    {msg.charts && msg.charts.length > 0 && (
                      <div className="mt-2 space-y-2">
                        {msg.charts.map((chart, chartIndex) =>
                          (chart as { type?: string }).type === "comparison_table" ? (
                            <ComparisonToggle key={chartIndex} table={chart} />
                          ) : (
                            <ChatChart key={chartIndex} chart={chart} />
                          )
                        )}
                      </div>
                    )}
```

- [ ] **Step 3: Lint + typecheck**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: no new lint errors from these two files; tsc reports no new errors about the charts dispatch (pre-existing unrelated errors, if any, may remain).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chatbot/ChatPanel.tsx frontend/components/chatbot/ChatWidget.tsx
git commit -m "feat: render listing comparison toggle in chatbot bubbles"
```

---

## Manual verification (after all tasks)

1. Rebuild: `docker compose up -d --build agent-service frontend`.
2. Ask: "Tìm căn hộ 2 phòng ngủ ở Nam Từ Liêm dưới 7 tỷ" → expect ≥2 listing cards plus a "So sánh N căn" button.
3. Click the button → a comparison table appears (Giá, Diện tích, Giá/m², PN/WC, Pháp lý, Vị trí, Nội thất, Đánh giá); the cheapest/largest/best-ppm rows carry tags; if market data exists, the Đánh giá column shows "% so TB khu vực". Click again → table hides.
4. A query returning a single listing → no comparison button.

## Self-Review

- **Spec coverage:** legal_status/furniture fetch (Task 1); comparison builder with ppm/tags/pct + None<2 (Task 2); property_search emit + area_avg (Task 3); table render with all 9 columns + new-tab link (Task 4); toggle button + dispatch in both chat UIs (Task 5). Error handling (missing price/area → null, no avg → null pct, <2 → no block/button) covered by Task 2 tests + Task 4/5 guards. Covered.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** the `comparison_table` block keys emitted by `build_comparison_table` (Task 2) — `type/title/unit/area_avg_price_per_m2/rows` with row keys `title/url/price_text/area_text/price_per_m2/bedrooms/bathrooms/legal_status/furniture/location/tags/pct_vs_area_avg` — match the `ComparisonRow`/`ComparisonTableSpec` interfaces (Task 4) and the dispatch `type === "comparison_table"` (Task 5). `build_comparison_table` signature matches its Task 3 call site.
