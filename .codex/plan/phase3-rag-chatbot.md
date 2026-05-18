# Phase 3 — RAG Chatbot MVP

> **Prerequisite:** Phase 1 complete (stable backend APIs). Phase 2 is helpful but not blocking.
> **Goal:** Replace placeholder chat responses with real RAG pipeline using listings data + legal knowledge.
> **Timeline:** Week 4-6

---

## Section 1: Rename RAG Package

**Why:** Folder is `RAG/` (uppercase) but all Python imports use `from rag.*` (lowercase). This works on Windows but **fails on Linux/Docker** (case-sensitive filesystem).

### Tasks

- [ ] Rename folder: `git mv RAG rag` (this preserves git history).
- [ ] Verify all internal imports still use `from rag.xxx` — they should work unchanged.
- [ ] Update these files that reference `RAG/`:
  - `AGENTS.md` (root) — change `RAG/` references to `rag/`.
  - `.codex/AGENTS.md` — change `RAG/` references to `rag/`.
  - Any `compileall` commands — change `RAG` to `rag`.
- [ ] Verify import works:

```powershell
python -c "from rag.graph import run_chat_pipeline; print('import OK')"
```

### Verify

```powershell
Test-Path rag\graph.py         # True
Test-Path RAG\graph.py         # False (old folder gone)
python -c "from rag.graph import run_chat_pipeline; print('OK')"
```

---

## Section 2: Embedding Pipeline

**Why:** RAG needs vector embeddings to perform semantic search over listings.

### Tasks

- [ ] Create `data_pipeline/embed.py`.
- [ ] Add function `generate_embeddings(batch_size: int = 50)`:
  - Connect to PostgreSQL using `app.database.async_session`.
  - Query listings where `embedding IS NULL`.
  - For each listing, build text: `f"{title}. {description}. {property_type}, {district}, {city}. {price_text}, {area_text}"`.
  - Call Gemini `text-embedding-004` API to get 768-dim vector.
  - Batch requests (50 at a time) with retry on rate limit (429) — wait 60s and retry.
  - Store vector in `listings.embedding` column.
  - Print progress: `"Embedded 50/1234 listings"`.
- [ ] Add CLI: `python -m data_pipeline.embed` runs `generate_embeddings()`.
- [ ] Skip listings that already have non-null embeddings (idempotent re-run).
- [ ] Requires `GEMINI_API_KEY` in `.env`.

### Verify

```powershell
python -m data_pipeline.embed
# Should print progress and embed listings
python -c "
from app.database import async_session
from app.models.listing import Listing
from sqlalchemy import select, func
import asyncio
async def check():
    async with async_session() as s:
        total = (await s.execute(select(func.count()).select_from(Listing))).scalar()
        embedded = (await s.execute(select(func.count()).select_from(Listing).where(Listing.embedding.isnot(None)))).scalar()
        print(f'{embedded}/{total} listings have embeddings')
asyncio.run(check())
"
```

---

## Section 3: Property Search Agent

**File:** `rag/agents/property_search.py`

**Why:** Replace placeholder with real search combining SQL filters + pgvector similarity.

### Tasks

- [ ] Extract structured filters from user query using Gemini:
  - Input: `"Tìm căn hộ 2 phòng ngủ Quận 7 giá dưới 5 tỷ"`
  - Output: `{"property_type": "Căn hộ chung cư", "bedrooms": 2, "district": "Quận 7", "max_price": 5}`
- [ ] Build SQL query with extracted filters (reuse `_apply_filters` pattern from listings router).
- [ ] If embeddings exist, also do pgvector similarity search:
  ```python
  query_embedding = await embed_text(user_query)
  results = session.execute(
      select(Listing).order_by(Listing.embedding.cosine_distance(query_embedding)).limit(10)
  )
  ```
- [ ] Combine SQL results and vector results, deduplicate by `product_id`.
- [ ] Use Gemini to generate a natural language summary of results.
- [ ] Return listing cards: `id`, `title`, `price_text`, `area_text`, `district`, `url`.
- [ ] If no listings match, return: `"Không tìm thấy bất động sản phù hợp với tiêu chí của bạn."`.

### Verify

Send to chat: `"Tìm căn hộ 2 phòng ngủ Quận 7 giá dưới 5 tỷ"` — should return real listings if data matches.

---

## Section 4: Market Analysis Agent

**File:** `rag/agents/market_analysis.py`

### Tasks

- [ ] Query PostgreSQL for aggregate data:
  - `AVG(price)`, `COUNT(*)`, `AVG(area)` grouped by district.
  - Property type distribution.
- [ ] Use Gemini to generate natural language interpretation of the data.
- [ ] Include exact numbers in the response (e.g., "Giá trung bình Quận 7: 4.2 tỷ, 156 tin đăng").
- [ ] Do NOT claim monthly trends — there is no historical data. If asked, respond: "Hiện chưa có dữ liệu lịch sử để phân tích xu hướng."

### Verify

Send to chat: `"Giá nhà Quận 7 hiện nay?"` — should return DB-backed statistics.

---

## Section 5: Legal Advisor Agent

**File:** `rag/agents/legal_advisor.py`

### Tasks

- [ ] Create `data/knowledge/` directory.
- [ ] Create markdown files with curated legal knowledge:
  - `data/knowledge/thu-tuc-mua-ban.md` — buy/sell procedures, notarization, title transfer.
  - `data/knowledge/thue-phi.md` — taxes and transfer fees.
  - `data/knowledge/phap-ly-can-ho.md` — apartment legal requirements.
- [ ] For MVP, use keyword-based retrieval (search markdown files for matching terms). Do not require embedding if not ready.
- [ ] Use Gemini to generate advice based on retrieved knowledge content.
- [ ] Include citations: `"Theo thủ tục mua bán nhà đất (nguồn: thu-tuc-mua-ban.md)"`.
- [ ] Add disclaimer: `"Lưu ý: Thông tin trên mang tính tham khảo, không thay thế tư vấn pháp lý chuyên nghiệp."`.
- [ ] If no relevant knowledge found, return fallback: `"Tôi chưa có thông tin về vấn đề này. Vui lòng tham khảo luật sư chuyên ngành."`.

### Verify

Send to chat: `"Thủ tục mua nhà lần đầu?"` — should return legal steps with citations.

---

## Section 6: Investment Advisor Agent

**File:** `rag/agents/investment_advisor.py`

### Tasks

- [ ] Compare listing price to district average from PostgreSQL.
- [ ] Calculate price per m² and compare to district average price per m².
- [ ] Return basic assessment: "above average", "below average", "at market level".
- [ ] Rental yield calculation: **skip for MVP** — there is no rent data yet. If asked, respond: `"Chưa có dữ liệu cho thuê để tính tỷ suất sinh lời."`.
- [ ] Add basic risk notes: "thiếu dữ liệu pháp lý", "giá cao hơn trung bình khu vực 30%", etc.
- [ ] Do NOT use ML forecasting. Do NOT claim price predictions.

### Verify

Send to chat: `"Nên đầu tư căn hộ Quận 7 không?"` — should return DB-backed comparison.

---

## Section 7: Backend Chat Integration

**File:** `backend/app/routers/chat.py`

**Why:** Replace the placeholder response (lines ~63-78) with the real RAG pipeline.

### Tasks

- [ ] Uncomment the import: `from rag.graph import run_chat_pipeline`
- [ ] Replace the placeholder response block with:
  ```python
  try:
      result = await run_chat_pipeline(body.message, str(session.id))
      response_text = result["final_response"]
      agent_used = result.get("agent_used", "unknown")
      sources = result.get("sources", [])
      suggested_actions = result.get("suggested_actions", [])
  except Exception as e:
      logger.error(f"RAG pipeline failed: {e}")
      response_text = "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau."
      agent_used = "fallback"
      sources = []
      suggested_actions = ["Tìm nhà theo nhu cầu", "Phân tích thị trường", "Tư vấn pháp lý"]
  ```
- [ ] Save `agent_used` and `sources` in the `ChatMessage.metadata_json`.
- [ ] Save `suggested_actions` in the response.
- [ ] Keep REST endpoint as primary MVP interface.

### Verify

```powershell
curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"message\": \"Tim can ho Quan 7\"}"
# Should return RAG response, not placeholder text
# Response should NOT contain "Phase 3" or "đang được phát triển"
```

---

## Out Of Scope (do NOT implement in Phase 3)

- ChromaDB as a second vector store (use pgvector only)
- WebSocket streaming
- Token-level streaming
- Long-term memory beyond stored sessions
- ML price forecasting
- Embedding legal documents into pgvector (use keyword search for MVP)
