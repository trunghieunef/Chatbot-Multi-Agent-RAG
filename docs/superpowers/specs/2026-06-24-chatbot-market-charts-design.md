# Biểu đồ thị trường trong chatbot — biến động giá (line) + so sánh quận (bar)

**Ngày:** 2026-06-24
**Trạng thái:** Đã duyệt thiết kế (Plan A — deterministic), chờ review spec
**Phạm vi:** Sub-project 1 của 2. Sub-project 2 (bảng so sánh các tin vừa tìm) làm sau, spec riêng.

## Mục tiêu

Khi chatbot trả lời câu hỏi thị trường, kèm **biểu đồ ngay trong bong bóng chat**:
- **A. Biến động giá:** line chart giá trung bình/m² theo tháng + **dải min–max**.
- **B. So sánh quận:** bar chart giá trung bình/m² giữa các quận trong một thành phố.

Cách tiếp cận (Plan A): chart là **view của dữ liệu mà các tool market đã lấy**, được
dựng **deterministic trong `build_result`** (giống cách `sources` được dựng) — KHÔNG
phải tool agent tự gọi. Quyết định "có lấy dữ liệu thị trường/xu hướng" vốn đã agentic
ở `lookup_market_metrics` / `lookup_market_timeseries`.

Phi mục tiêu (YAGNI): không thêm tool mới; không vẽ chart cho intent ngoài market;
không làm bảng so sánh listing (đó là sub-project 2).

## Hiện trạng đường ống (đã thông sẵn phần lớn)

`charts` đã tồn tại end-to-end — chỉ thiếu producer + render:
- `agent_service/contracts.py:139` `AgentResult.charts`; `:203` response `charts`.
- `backend/app/schemas/chat.py:42` `charts: list[dict] | None`; `backend/app/routers/chat.py:775` forward `charts=agent_response.charts`.
- `frontend/lib/types.ts:171` `charts?: Record<string, unknown>[] | null`.
- **Thiếu:** (1) agent ĐIỀN `charts`; (2) `_node_synthesize` CHUYỂN charts từ agent ra response; (3) frontend RENDER charts.

`market_analysis_agent.build_result` **đã thu sẵn** `metrics` và `timeseries`
(từ tool `lookup_market_metrics` + `lookup_market_timeseries`) — chỉ chưa đóng gói
thành chart.

## ChartSpec (payload agent phát → frontend render)

```jsonc
// A. line_band
{
  "type": "line_band",
  "title": "Biến động giá — Đống Đa (Căn hộ chung cư)",
  "unit": "triệu VNĐ/m²",
  "x_key": "month",
  "data": [ {"month": "2024-Q4", "avg": 78.0, "min": 60.0, "max": 95.0}, ... ]
}
// B. bar
{
  "type": "bar",
  "title": "So sánh giá theo quận — Hà Nội",
  "unit": "triệu VNĐ/m²",
  "x_key": "district",
  "data": [ {"district": "Đống Đa", "avg": 120.0}, {"district": "Cầu Giấy", "avg": 105.0}, ... ]
}
```

## Luồng dữ liệu

```
market_analysis_agent (đã gọi lookup_market_metrics + lookup_market_timeseries)
  └─ build_result: timeseries → build_price_trend_chart()
                   metrics    → build_district_comparison_chart()
                   → AgentResult.charts = [spec for spec if spec is not None]
       └─ _node_synthesize: gom charts từ agent_results → AgentChatResponse.charts
            └─ backend public API (đã forward) → frontend ChatMessageResponse.charts
                 └─ <ChatChart> (recharts) render trong bong bóng
```

## Thành phần

### 1. Hàm thuần dựng chart — `agent_service/graph/charts.py` (mới)

Hàm thuần, không I/O → TDD dễ.

- `build_price_trend_chart(timeseries: list[dict], *, title: str, unit: str = "triệu VNĐ/m²") -> dict | None`
  - Input: rows có `snapshot_month`, `avg_price_per_m2`, `min_price_per_m2`, `max_price_per_m2`.
  - Sắp xếp theo `snapshot_month`; map → `{"month","avg","min","max"}`.
  - Trả `None` nếu **< 2 tháng** có `avg` (không đủ để thấy "biến động").
- `build_district_comparison_chart(metrics: list[dict], *, title: str, unit: str = "triệu VNĐ/m²") -> dict | None`
  - Input: rows có `location.district` (hoặc `district`) + `value` (avg_price_per_m2).
  - Gom theo district (lấy 1 giá trị/quận), sort giảm dần theo `avg`.
  - Trả `None` nếu **< 2 quận** có giá trị.

### 2. `market_analysis_agent.build_result`

- Dùng `timeseries` và `metrics` đã thu (lines ~119–129) gọi 2 hàm trên.
- Đặt `charts=[c for c in (trend, comparison) if c]` vào `AgentResult(...)`.
- Title lấy từ `context.routing_filters` (district/city/property_type) nếu có, fallback chung chung.

### 3. `agentic_workflow._node_synthesize` (+ nhánh stream)

- Gom `charts` từ tất cả `agent_results[*].charts` (giống cách gom `all_sources`).
- Truyền vào `AgentChatResponse(..., charts=all_charts)` ở cả nhánh non-stream (~449) và stream (~505).

### 4. Frontend — `frontend/components/chatbot/ChatChart.tsx` (mới)

- Props: `chart: ChartSpec` (1 chart). Component cha map `msg.charts`.
- `recharts` (đã có, dùng ở `/thi-truong`):
  - `line_band`: `LineChart` + `Area`/`Line` cho `min`/`max` (vùng mờ) + `Line` đậm cho `avg`; `XAxis dataKey="month"`, tooltip, đơn vị.
  - `bar`: `BarChart` + `Bar dataKey="avg"`; `XAxis dataKey="district"`.
- Kích thước gọn trong bong bóng (`ResponsiveContainer`, cao ~180px), title + unit.
- `data` rỗng → render `null`.

### 5. Render trong chat — `ChatPanel.tsx` + `ChatWidget.tsx`

- Sau khối nội dung (`{msg.content}`), nếu `msg.charts?.length`, map mỗi chart → `<ChatChart chart={...} />`.
- Đặt trên hoặc dưới phần sources (chốt: **ngay dưới nội dung, trên sources**).

## Trigger

- `market_analysis` chạy → `build_result` tự dựng chart nào có đủ data:
  - ≥ 2 tháng timeseries ⇒ line_band.
  - ≥ 2 quận metrics ⇒ bar.
- Không đủ data ⇒ hàm trả `None` ⇒ không có chart, câu trả lời text như cũ.

## Error handling

- Thiếu/không đủ data ⇒ `None` ⇒ bỏ chart (không vỡ).
- `value`/`avg` không phải số ⇒ bỏ điểm đó; nếu còn < ngưỡng ⇒ `None`.
- Frontend: `data` rỗng hoặc `type` lạ ⇒ `ChatChart` trả `null` (không vỡ layout).

## Testing

- **Backend (TDD):** `agent_service/tests/test_charts.py`:
  - `build_price_trend_chart`: nhiều tháng → line_band đúng `data`/thứ tự; 1 tháng → `None`; rỗng → `None`; bỏ điểm thiếu `avg`.
  - `build_district_comparison_chart`: ≥2 quận → bar sort giảm dần; 1 quận → `None`; rỗng → `None`.
- **Agent:** test `market_analysis_agent.build_result` set `charts` khi có timeseries/metrics (inject actions giả), và `charts=[]` khi không có.
- **Synthesize:** test `_node_synthesize` carry charts từ agent_results ra response (có thể gộp vào test agentic hiện có).
- **Frontend:** `npm run lint`; thử thủ công recharts (line_band + bar) trong bong bóng.

## Phạm vi thay đổi

- `agent_service/graph/charts.py` (mới) + `agent_service/tests/test_charts.py` (mới)
- `agent_service/agents/market_analysis_agent.py` (build_result emit charts)
- `agent_service/graph/agentic_workflow.py` (_node_synthesize + stream carry charts)
- `frontend/components/chatbot/ChatChart.tsx` (mới)
- `frontend/components/chatbot/ChatPanel.tsx`, `ChatWidget.tsx` (render charts)
- (Không cần đổi contract: `charts` đã có ở agent_service/contracts, backend schema/router, frontend types.)
