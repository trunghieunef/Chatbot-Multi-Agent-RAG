---
paths:
  - RAG/**/*
  - backend/app/routers/chat.py
  - backend/app/services/chatbot/**/*
---
# RAG Multi-Agent System

## Architecture

- Framework: LangGraph (StateGraph).
- LLM: Google Gemini via `google-generativeai` SDK.
- Vector store: ChromaDB (dev) / pgvector (backup).
- Embeddings: `text-embedding-004`, dimension 1536.

## Workflow

```
START -> router -> [conditional routing] -> agent(s) -> synthesizer -> END
```

## State

- `ChatState` extends `MessagesState` from LangGraph.
- Key fields: user_query, intent, target_agents, search_filters, agent_results, final_response, sources.

## Agents

- **Router**: classifies intent, extracts filters, routes to 1+ agents. Uses Gemini with JSON output. Falls back to keyword routing when API key unavailable.
- **Property Search**: vector + SQL hybrid search on listings.
- **Market Analysis**: SQL aggregates for price trends, supply/demand stats.
- **Legal Advisor**: RAG on legal knowledge base documents.
- **Investment Advisor**: ROI calculation, price comparison, risk assessment.

## Conventions

- Config lives in `RAG/config.py`.
- All agents return results via `agent_results` dict in state.
- Responses must be in Vietnamese.
- Always include sources/citations when available.
