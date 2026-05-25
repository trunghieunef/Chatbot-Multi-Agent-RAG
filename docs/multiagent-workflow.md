# Multi-Agent Chatbot Workflow

Tài liệu này mô tả workflow hiện tại của production multi-agent chatbot trong backend.

## Entry Point

Frontend gọi API hiện có:

```http
POST /api/v1/chat
```

Request body giữ nguyên contract:

```json
{
  "message": "Mua căn hộ Quận 7 để đầu tư dưới 5 tỷ",
  "session_id": null
}
```

Backend entry point nằm ở:

```text
backend/app/routers/chat.py
```

Luồng chính trong `send_message()`:

1. Nhận message từ user.
2. Lấy hoặc tạo `ChatSession`.
3. Lưu user message vào `chat_messages`.
4. Gọi `_run_chatbot_pipeline()`.
5. Lưu assistant response cùng metadata.
6. Trả `ChatMessageResponse` cho frontend.

## High-Level Flow

```text
User message
  |
  v
/api/v1/chat
  |
  v
_run_chatbot_pipeline()
  |
  v
run_chat_pipeline()
  |
  v
route_query()
  |
  v
Selected agents
  |
  v
_combine_results()
  |
  v
ChatMessageResponse
```

Nếu multi-agent pipeline lỗi:

```text
run_chat_pipeline() fails
  |
  v
run_simple_rag() fallback
  |
  v
safe error response if fallback also fails
```

## Production Modules

Production multi-agent code nằm trong:

```text
backend/app/services/chatbot/
```

Các module chính:

```text
backend/app/services/chatbot/contracts.py
backend/app/services/chatbot/router.py
backend/app/services/chatbot/orchestrator.py
backend/app/services/chatbot/agents/property.py
backend/app/services/chatbot/agents/market.py
backend/app/services/chatbot/agents/legal.py
backend/app/services/chatbot/agents/investment.py
```

Root-level `chatbot/` hiện chỉ nên xem là sandbox/scaffold thử nghiệm. Endpoint production không phụ thuộc vào package đó.

## Routing Workflow

Router nằm ở:

```text
backend/app/services/chatbot/router.py
```

Function chính:

```python
route_query(query: str) -> RoutingDecision
```

Router xử lý theo thứ tự:

1. Đọc `GEMINI_API_KEY` từ settings.
2. Nếu có API key, thử dùng Gemini để classify intent JSON.
3. Nếu thiếu API key hoặc Gemini lỗi, fallback sang keyword router.
4. Extract filter cơ bản bằng `extract_search_filters()` từ `simple_rag`.
5. Bổ sung filter thủ công như `district` và `max_price`.
6. Trả `RoutingDecision`.

Output của router:

```python
RoutingDecision(
    intent="mixed",
    target_agents=["investment_advisor", "property_search"],
    search_filters={
        "listing_type": "sale",
        "district": "Quan 7",
        "max_price": 5,
    },
)
```

Keyword routing hiện nhận diện các nhóm intent:

| Intent | Agent | Ví dụ tín hiệu |
| --- | --- | --- |
| Tìm bất động sản | `property_search` | `tìm`, `căn hộ`, `chung cư`, `quận`, `dưới`, `phòng` |
| Thị trường | `market_analysis` | `thị trường`, `xu hướng`, `biến động`, `thống kê`, `giá trung bình` |
| Pháp lý | `legal_advisor` | `pháp lý`, `luật`, `thủ tục`, `công chứng`, `sổ đỏ`, `sang tên` |
| Đầu tư | `investment_advisor` | `đầu tư`, `ROI`, `lợi nhuận`, `sinh lời`, `rental yield` |

Một query có thể route nhiều agent. Ví dụ:

```text
Mua căn hộ Quận 7 để đầu tư dưới 5 tỷ
```

Target agents:

```text
investment_advisor, property_search
```

## Orchestrator Workflow

Orchestrator nằm ở:

```text
backend/app/services/chatbot/orchestrator.py
```

Function chính:

```python
run_chat_pipeline(query: str, db: AsyncSession, session_id: str | None = None) -> dict
```

Luồng xử lý:

1. Gọi `route_query(query)`.
2. Map `target_agents` sang runner tương ứng trong `AGENT_RUNNERS`.
3. Nếu không có agent hợp lệ, fallback nội bộ sang `property_search`.
4. Chạy các agent được chọn bằng `asyncio.gather()`.
5. Gom kết quả bằng `_combine_results()`.
6. Trả dict cùng shape với `simple_rag`.

Output contract:

```python
{
    "final_response": "...",
    "agent_used": "investment_advisor, property_search",
    "sources": [...],
    "suggested_actions": [...],
}
```

`_combine_results()` hiện:

1. Sort kết quả theo `agent_name`.
2. Nối nội dung từng agent bằng blank line.
3. Gộp toàn bộ `sources`.
4. Dedupe `suggested_actions`, tối đa 5 action.
5. Ghi `agent_used` bằng danh sách agent phân tách bởi `, `.

## Agent Workflows

### Property Search Agent

File:

```text
backend/app/services/chatbot/agents/property.py
```

Function:

```python
run_property_search(query, db, routing) -> AgentResult
```

Workflow:

1. Khởi tạo `GeminiClient` từ settings.
2. Embed user query bằng Gemini embedding.
3. Gọi `_retrieve_listings()` từ `simple_rag`.
4. Áp dụng filters từ `routing.search_filters`.
5. Nếu có listing:
   - gọi Gemini để generate answer;
   - nếu Gemini generate lỗi, dùng `build_fallback_answer()`;
   - format sources bằng `format_listing_source()`.
6. Nếu không có listing hoặc thiếu config embedding:
   - trả response an toàn, yêu cầu user nới điều kiện.

Nguồn dữ liệu:

```text
PostgreSQL listings table
pgvector embedding column
Gemini embedding/generation
```

### Market Analysis Agent

File:

```text
backend/app/services/chatbot/agents/market.py
```

Function:

```python
run_market_analysis(query, db, routing) -> AgentResult
```

Workflow:

1. Đọc filters từ routing.
2. Query SQL aggregate trên bảng `listings`.
3. Tính:
   - số lượng listing;
   - giá trung bình;
   - diện tích trung bình;
   - giá/m2 trung bình.
4. Trả summary dạng văn bản và source type `market_aggregate`.

Agent này không gọi Gemini trong MVP.

### Legal Advisor Agent

File:

```text
backend/app/services/chatbot/agents/legal.py
```

Function:

```python
run_legal_advisor(query, db, routing) -> AgentResult
```

Workflow:

1. Trả checklist pháp lý bảo thủ.
2. Nhắc các điểm cần kiểm tra:
   - chủ sở hữu;
   - quy hoạch/tranh chấp;
   - đặt cọc;
   - thuế phí;
   - công chứng/sang tên.
3. Luôn có disclaimer: chỉ mang tính tham khảo.
4. Trả source type `legal_checklist`.

Agent này chưa dùng knowledge base pháp lý đầy đủ. Đây là MVP an toàn để tránh bịa luật.

### Investment Advisor Agent

File:

```text
backend/app/services/chatbot/agents/investment.py
```

Function:

```python
run_investment_advisor(query, db, routing) -> AgentResult
```

Workflow:

1. Đọc filters từ routing.
2. Query aggregate từ bảng `listings`.
3. Tính:
   - số listing có giá;
   - giá trung bình;
   - giá/m2 trung bình.
4. Trả phân tích đầu tư mức tham khảo:
   - thanh khoản;
   - khả năng cho thuê;
   - pháp lý;
   - biên an toàn dòng tiền.
5. Luôn nhắc đây không phải lời khuyên tài chính chính thức.

## Fallback Workflow

Fallback nằm trong:

```text
backend/app/routers/chat.py
```

Function:

```python
_run_chatbot_pipeline(message, db, session_id)
```

Luồng fallback:

```text
try run_chat_pipeline()
except:
    try run_simple_rag()
    except:
        raise RuntimeError
```

Sau đó `send_message()` bắt `RuntimeError` và trả response an toàn:

```text
Chatbot RAG chưa sẵn sàng do cấu hình backend còn thiếu...
```

Điều này giúp endpoint không crash nếu:

1. Multi-agent pipeline lỗi.
2. Gemini/vector retrieval lỗi.
3. `simple_rag` fallback cũng lỗi.

## Data Written To Database

Mỗi request chat ghi:

1. `ChatSession` nếu chưa có session.
2. User `ChatMessage`.
3. Assistant `ChatMessage`.

Assistant message lưu:

```python
agent_used = "investment_advisor, property_search"
metadata_json = {
    "sources": [...],
    "suggested_actions": [...]
}
```

Frontend đọc lại các field này qua `ChatMessageResponse`.

## Response Contract

Frontend không cần đổi contract.

Response vẫn có shape:

```json
{
  "session_id": "uuid",
  "role": "assistant",
  "content": "final answer",
  "agent_used": "investment_advisor, property_search",
  "sources": [],
  "suggested_actions": [],
  "created_at": "datetime"
}
```

Các giá trị `agent_used` có thể gặp:

```text
property_search
market_analysis
legal_advisor
investment_advisor
investment_advisor, property_search
market_analysis, property_search
simple_rag
```

## Test Coverage

Các test liên quan:

```text
backend/tests/test_production_chatbot.py
backend/tests/test_chat_router_pipeline.py
backend/tests/test_simple_rag.py
backend/tests/test_chatbot_scaffold.py
```

Các scenario đã có test:

1. Router chọn nhiều agent và extract filters.
2. Router chọn legal agent cho câu pháp lý.
3. Legal agent trả disclaimer và sources.
4. Orchestrator combine nhiều agent.
5. `/api/v1/chat` dùng multi-agent mặc định.
6. `/api/v1/chat` fallback sang `simple_rag` khi multi-agent lỗi.
7. `/api/v1/chat` trả response an toàn khi cả multi-agent và `simple_rag` cùng lỗi.
8. `simple_rag` contract vẫn giữ nguyên.
9. Root `chatbot/` sandbox vẫn import được.

Lệnh kiểm thử:

```powershell
pytest backend\tests -q
python -m compileall backend\app chatbot data_pipeline
```

## Current Limitations

1. `property_search` phụ thuộc `GEMINI_API_KEY` và embeddings trong DB để tìm listing bằng vector.
2. `market_analysis` và `investment_advisor` đang dùng SQL aggregate cơ bản, chưa có time-series trend thật.
3. `legal_advisor` mới là checklist tĩnh, chưa có legal knowledge base/citation theo điều luật.
4. Orchestrator đang chạy agent bằng `asyncio.gather()`, chưa có tracing chi tiết hoặc streaming.
5. Frontend chưa hiển thị nhiều agent như một trace riêng; hiện chỉ hiển thị `agent_used` dạng label.

## Suggested Next Improvements

1. Thêm legal knowledge base và ingestion cho `legal_advisor`.
2. Tách market analytics thành service dùng lại giữa `/market/*` và chatbot.
3. Thêm observability: log `routing`, `agent_used`, latency từng agent.
4. Thêm feature flag `CHATBOT_PIPELINE=multi|simple` nếu cần rollback khi deploy.
5. Thêm streaming/WebSocket sau khi REST flow ổn định.

## Operations

- Grafana: import `infra/grafana/realestate-pipeline.json` and point it at the FastAPI Prometheus scrape job.
