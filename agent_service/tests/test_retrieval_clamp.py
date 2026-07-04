import pytest

from agent_service.tools import retrieval


@pytest.mark.asyncio
async def test_llm_args_are_clamped_before_hybrid_search(monkeypatch):
    # Gemini once passed rerank_to=0 → Cohere top_n=0 → 400 → empty results.
    captured = {}

    async def fake_hybrid_search(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(retrieval, "hybrid_search", fake_hybrid_search)
    trace = retrieval.RetrievalTrace(request_id="t")

    await retrieval.search_articles("q", None, trace, top_k=0, rerank_to=0)
    assert captured["top_k"] == 1
    assert captured["rerank_to"] == 1

    await retrieval.search_articles("q", None, trace, top_k=500, rerank_to="7")
    assert captured["top_k"] == 50          # upper bound
    assert captured["rerank_to"] == 7       # string coerced

    await retrieval.search_articles("q", None, trace, top_k="xx", rerank_to=99)
    assert captured["top_k"] == 20          # unparseable -> default
    assert captured["rerank_to"] == 20      # capped at top_k
