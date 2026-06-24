# Bảng so sánh các tin trong chatbot (sau nút "So sánh")

**Ngày:** 2026-06-24
**Trạng thái:** Đã duyệt thiết kế, chờ review spec
**Phạm vi:** Sub-project 2 của 2 (sub-project 1 = market charts, đã xong).

## Mục tiêu

Khi property_search trả ≥2 tin, kèm một **nút "So sánh N căn"** dưới các card; bấm vào
hiện một **bảng so sánh** các tin cạnh nhau. Cột: Tên (link), Giá, Diện tích, Giá/m²,
PN/WC, Pháp lý, Vị trí, Nội thất, và **Đánh giá nhanh** (tag suy ra từ dữ liệu + % so giá
TB khu vực).

Phi mục tiêu (YAGNI): không gọi LLM để sinh đánh giá; không thêm field response mới
(tái dùng `charts`); không so sánh tin ngoài tập vừa trả về.

## Kiến trúc

Tái dùng cơ chế `charts` đã có (sub-project 1): `charts` là danh sách "display block"
chảy end-to-end (`AgentResult.charts` → `_collect_charts` gom từ MỌI agent gồm
property_search → `AgentChatResponse.charts` → backend schema/router → frontend
`msg.charts`). Thêm một loại block `comparison_table`. Frontend dispatch theo `type`:
`line_band`/`bar` → `ChatChart` (đã có); `comparison_table` → **nút toggle + bảng**.

→ KHÔNG thêm field/plumbing mới (tránh đúng cái bẫy `useChat.ts` ở sub-project 1).

```
property_search_agent.build_result (đã thu all_listings + market_data avg)
  └─ build_comparison_table(all_listings, area_avg_price_per_m2=avg) → block
       → AgentResult.charts.append(block)
         → _collect_charts (đã có) → AgentChatResponse.charts → frontend msg.charts
             → ChatPanel/ChatWidget: type=comparison_table → "So sánh N căn" (toggle) → <ComparisonTable>
```

## Payload `comparison_table`

```jsonc
{
  "type": "comparison_table",
  "title": "So sánh 4 căn",
  "unit": "triệu VNĐ/m²",
  "area_avg_price_per_m2": 152.31,        // null nếu không có dữ liệu market
  "rows": [
    {
      "title": "Căn hộ ...", "url": "/nha-dat-ban/123",
      "price_text": "6,6 tỷ", "area_text": "79,1 m²",
      "price_per_m2": 83.4,                // tính = price(tỷ)*1000/area(m²); null nếu thiếu
      "bedrooms": 3, "bathrooms": 2,
      "legal_status": "Sổ đỏ", "furniture": "Đầy đủ",
      "location": "Nam Từ Liêm, Hà Nội",
      "tags": ["Rẻ nhất"],                 // tag suy ra trong nhóm
      "pct_vs_area_avg": -45.2             // % so giá TB khu vực; null nếu không có avg
    }
  ]
}
```

## Thành phần

### 1. Backend — `resolve_to_listing_records` SELECT (`backend/app/services/rag/hybrid_search.py`)

Thêm `legal_status`, `furniture` vào câu SELECT (đã có `price`, `area`, `bedrooms`,
`bathrooms`). Hai cột này có thật: `listings.legal_status` (Pháp lý), `listings.furniture`
(Nội thất). Map vào record dict như các cột khác.

### 2. Backend — hàm thuần `build_comparison_table` (`agent_service/graph/charts.py`)

`build_comparison_table(listings: list[dict], *, area_avg_price_per_m2: float | None, unit: str = "triệu VNĐ/m²") -> dict | None`

- Trả `None` nếu `len(listings) < 2`.
- Mỗi row lấy: title, url (hoặc `/nha-dat-ban/{id}`), price_text, area_text, bedrooms,
  bathrooms, legal_status, furniture, location (`"{district}, {city}"`).
- `price_per_m2 = round(price * 1000 / area, 1)` nếu `price` và `area` đều là số > 0,
  ngược lại `None`. (`price` đơn vị tỷ → ×1000 ra triệu/m².)
- `pct_vs_area_avg = round((price_per_m2 - avg) / avg * 100, 1)` nếu cả hai có số,
  ngược lại `None`.
- **tags** (so trong nhóm, deterministic): gắn `"Rẻ nhất"` cho row có `price` nhỏ nhất;
  `"Rộng nhất"` cho `area` lớn nhất; `"Giá/m² tốt nhất"` cho `price_per_m2` nhỏ nhất.
  Bỏ qua tag nếu trường tương ứng thiếu ở mọi row.

### 3. Backend — `property_search_agent.build_result`

- Tính `area_avg`: trung bình các `market_data[*].value` (metric=avg_price_per_m2),
  `None` nếu không có. (build_result đã thu `market_data` và tính avg cho phần text —
  trích `avg` ra biến để dùng lại.)
- Gọi `build_comparison_table(all_listings, area_avg_price_per_m2=area_avg)`; nếu khác
  `None`, thêm vào `charts` của `AgentResult` được trả về (AgentResult.charts đã tồn tại;
  hiện build_result chưa set `charts` → thêm `charts=[block] if block else []`).

### 4. Frontend — `ComparisonTable.tsx` (`frontend/components/chatbot/`)

- Props: `{ table: Record<string, unknown> }` (cast nội bộ sang interface).
- Render `<table>` cuộn ngang (`overflow-x-auto`): header các cột; mỗi row một tin.
  - Tên = link `<a target="_blank" rel="noopener noreferrer" href={row.url}>`.
  - Giá/m² hiển thị số + `unit`; ẩn nếu null.
  - Đánh giá nhanh = `tags.join(" · ")` + (nếu `pct_vs_area_avg` có) `"{±x}% so TB khu vực"`.
  - Cột thiếu dữ liệu → "—".
- `rows` rỗng → render `null`.

### 5. Frontend — toggle trong `ChatPanel.tsx` + `ChatWidget.tsx`

Sửa block render `msg.charts`: tách theo `type`.
- `chart.type === "comparison_table"` → render một `<button>` "So sánh N căn" (N = số rows);
  state toggle (mở/đóng) theo từng message; khi mở render `<ComparisonTable table={chart} />`.
- Các type khác (`line_band`/`bar`) → vẫn `<ChatChart chart={chart} />` như hiện tại.
- Toggle state: `useState<Record<number,boolean>>` keyed theo message index (hoặc một
  component con bọc cả nút + bảng để giữ state cục bộ — ưu tiên component con cho gọn).

## Trigger

property_search có ≥2 tin → emit `comparison_table` vào charts. Frontend luôn hiện **nút**
"So sánh N căn"; bảng ẩn cho tới khi bấm.

## Error handling

- < 2 tin → builder trả `None` → không có block → không có nút.
- Thiếu price/area một dòng → `price_per_m2`/`pct_vs_area_avg` = null, vẫn hiện dòng (cột "—").
- Không có market avg → `area_avg_price_per_m2` = null → bỏ phần "% so TB", vẫn có tags.
- Frontend: `rows` rỗng / type lạ → không render.

## Testing

- **Backend (TDD)** — `agent_service/tests/test_charts.py` (mở rộng):
  - `build_comparison_table`: 3 tin → tags đúng (rẻ nhất/rộng nhất/giá-m² tốt nhất),
    `price_per_m2` tính đúng, `pct_vs_area_avg` đúng dấu; 1 tin → `None`; thiếu
    price/area một dòng → dòng đó `price_per_m2`/`pct` null nhưng vẫn có; `area_avg=None`
    → mọi `pct_vs_area_avg` null.
  - `property_search_agent.build_result`: ≥2 tin → `charts` có 1 block `comparison_table`;
    1 tin → `charts == []`.
- **Frontend:** `npm run lint` + thử thủ công (bấm nút → bảng hiện, cuộn ngang mobile).

## Phạm vi thay đổi

- `backend/app/services/rag/hybrid_search.py` (resolve SELECT += legal_status, furniture)
- `agent_service/graph/charts.py` (build_comparison_table) + `agent_service/tests/test_charts.py`
- `agent_service/agents/property_search_agent.py` (build_result emit comparison_table)
- `frontend/components/chatbot/ComparisonTable.tsx` (mới)
- `frontend/components/chatbot/ChatPanel.tsx`, `ChatWidget.tsx` (dispatch type + nút toggle)
- (Không đổi contract: `charts` đã có end-to-end gồm `useChat.ts` Message sau sub-project 1.)
