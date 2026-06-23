from __future__ import annotations

import pytest

from app.services.rag.hybrid_search import reciprocal_rank_fusion


def _vec(cid: str, dist: float) -> dict:
    return {"id": cid, "text": f"chunk-{cid}", "distance": dist}


def _lex(cid: str) -> dict:
    return {"id": cid, "text": f"chunk-{cid}"}


def test_rrf_orders_by_fused_score():
    """Known RRF example (k=60):
    vector=[A,B,C], lexical=[B,D,A] -> fused order [B, A, D, C].
    B scores 1/62+1/61, A scores 1/61+1/63, D 1/62, C 1/63.
    """
    vector = [_vec("A", 0.1), _vec("B", 0.2), _vec("C", 0.3)]
    lexical = [_lex("B"), _lex("D"), _lex("A")]

    fused = reciprocal_rank_fusion(vector, lexical, k=60, top_n=10)
    assert [c["id"] for c in fused] == ["B", "A", "D", "C"]


def test_rrf_rewards_items_in_both_lists():
    """An item present in both rankers beats one present in a single ranker
    at the same rank."""
    vector = [_vec("X", 0.1), _vec("Y", 0.2)]
    lexical = [_lex("X"), _lex("Z")]
    fused = reciprocal_rank_fusion(vector, lexical, k=60, top_n=10)
    # X is in both at rank 1 -> highest.
    assert fused[0]["id"] == "X"


def test_rrf_caps_to_top_n():
    vector = [_vec("A", 0.1), _vec("B", 0.2), _vec("C", 0.3)]
    lexical = [_lex("D"), _lex("E")]
    fused = reciprocal_rank_fusion(vector, lexical, k=60, top_n=2)
    assert len(fused) == 2


def test_lexical_only_chunk_carries_none_distance():
    """A chunk that appears only in the lexical list must still expose a
    `distance` key (None) so downstream resolve_to_*_records never KeyErrors."""
    vector = [_vec("A", 0.1)]
    lexical = [_lex("B")]
    fused = reciprocal_rank_fusion(vector, lexical, k=60, top_n=10)
    by_id = {c["id"]: c for c in fused}
    assert "distance" in by_id["B"]
    assert by_id["B"]["distance"] is None
    # Vector chunk keeps its real distance.
    assert by_id["A"]["distance"] == 0.1


def test_empty_lexical_preserves_vector_order():
    """Degradation: with no lexical results, fusion returns vector order."""
    vector = [_vec("A", 0.1), _vec("B", 0.2), _vec("C", 0.3)]
    fused = reciprocal_rank_fusion(vector, [], k=60, top_n=10)
    assert [c["id"] for c in fused] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_hybrid_search_fuses_lexical_into_results(monkeypatch):
    """End-to-end wiring: hybrid_search() must run lexical_search alongside
    pgvector_knn and fuse both via RRF before rerank/resolve.

    vector=[A,B], lexical=[B,C] -> B (in both) ranks first, then A, then
    lexical-only C (which must carry distance=None). We stub rerank and resolve
    as identity so the assertion observes the fused ordering directly.
    """
    from app.services.rag import hybrid_search as hs

    async def fake_sql_filter(parent_type, filters, limit=500):
        return [1, 2, 3]

    async def fake_get_query_embedding(query, *, embedder, cache=None):
        return [0.0] * 4

    async def fake_redis():
        raise RuntimeError("no redis in test")

    async def fake_pgvector_knn(query_embedding, parent_type, parent_ids, k):
        return [
            {"id": "A", "parent_id": 1, "chunk_type": "x", "text": "a", "distance": 0.1},
            {"id": "B", "parent_id": 2, "chunk_type": "x", "text": "b", "distance": 0.2},
        ]

    async def fake_lexical_search(query, *, parent_type, parent_ids, k):
        return [
            {"id": "B", "parent_id": 2, "chunk_type": "x", "text": "b"},
            {"id": "C", "parent_id": 3, "chunk_type": "x", "text": "c"},
        ]

    captured: dict[str, list] = {}

    async def fake_rerank(query, chunks, top_n):
        captured["reranked_in"] = chunks
        return chunks[:top_n]

    async def fake_resolve(chunks):
        return chunks

    monkeypatch.setattr(hs, "sql_filter", fake_sql_filter)
    monkeypatch.setattr(hs, "_get_query_embedder", lambda: object())
    monkeypatch.setattr(hs, "get_query_embedding", fake_get_query_embedding)
    monkeypatch.setattr(hs, "get_redis_client", fake_redis)
    monkeypatch.setattr(hs, "pgvector_knn", fake_pgvector_knn)
    monkeypatch.setattr(hs, "lexical_search", fake_lexical_search)
    monkeypatch.setattr(hs, "cohere_rerank", fake_rerank)
    monkeypatch.setattr(hs, "resolve_to_listing_records", fake_resolve)

    result = await hs.hybrid_search("nha quan 7", parent_type="listing", top_k=10, rerank_to=10)

    # B is in both rankers -> first; A vector-only -> second; C lexical-only -> last.
    assert [c["id"] for c in result] == ["B", "A", "C"]
    # The lexical-only chunk must expose distance=None for downstream resolve.
    by_id = {c["id"]: c for c in result}
    assert by_id["C"]["distance"] is None
    # Fusion happened before rerank: rerank saw the fused list, not raw vector.
    assert [c["id"] for c in captured["reranked_in"]] == ["B", "A", "C"]


@pytest.mark.asyncio
async def test_hybrid_search_skips_lexical_when_disabled(monkeypatch):
    """With HYBRID_LEXICAL_ENABLED=False, lexical_search must not run and the
    result is pure vector order."""
    from app.services.rag import hybrid_search as hs

    settings = hs.get_settings()
    monkeypatch.setattr(settings, "HYBRID_LEXICAL_ENABLED", False, raising=False)

    async def fake_sql_filter(parent_type, filters, limit=500):
        return [1, 2]

    async def fake_get_query_embedding(query, *, embedder, cache=None):
        return [0.0] * 4

    async def fake_redis():
        raise RuntimeError("no redis in test")

    async def fake_pgvector_knn(query_embedding, parent_type, parent_ids, k):
        return [
            {"id": "A", "parent_id": 1, "chunk_type": "x", "text": "a", "distance": 0.1},
            {"id": "B", "parent_id": 2, "chunk_type": "x", "text": "b", "distance": 0.2},
        ]

    lexical_called = {"hit": False}

    async def fake_lexical_search(query, *, parent_type, parent_ids, k):
        lexical_called["hit"] = True
        return [{"id": "Z", "parent_id": 9, "chunk_type": "x", "text": "z"}]

    async def identity_rerank(query, chunks, top_n):
        return chunks[:top_n]

    async def fake_resolve(chunks):
        return chunks

    monkeypatch.setattr(hs, "sql_filter", fake_sql_filter)
    monkeypatch.setattr(hs, "_get_query_embedder", lambda: object())
    monkeypatch.setattr(hs, "get_query_embedding", fake_get_query_embedding)
    monkeypatch.setattr(hs, "get_redis_client", fake_redis)
    monkeypatch.setattr(hs, "pgvector_knn", fake_pgvector_knn)
    monkeypatch.setattr(hs, "lexical_search", fake_lexical_search)
    monkeypatch.setattr(hs, "cohere_rerank", identity_rerank)
    monkeypatch.setattr(hs, "resolve_to_listing_records", fake_resolve)

    result = await hs.hybrid_search("nha quan 7", parent_type="listing", top_k=10, rerank_to=10)

    assert lexical_called["hit"] is False
    assert [c["id"] for c in result] == ["A", "B"]
