from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import async_session
from chatbot.tools.cache import JsonCache, get_redis_client, hash_pair, hash_text
from data_pipeline.embed import GeminiEmbedder

_QUERY_EMBEDDER: GeminiEmbedder | None = None


def _get_query_embedder() -> GeminiEmbedder:
    global _QUERY_EMBEDDER
    if _QUERY_EMBEDDER is None:
        settings = get_settings()
        _QUERY_EMBEDDER = GeminiEmbedder(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_EMBEDDING_MODEL,
            batch_size=1,
        )
    return _QUERY_EMBEDDER


def _format_pgvector(values: list[float]) -> str:
    """Format a Python list as a pgvector text literal (e.g. '[0.1,0.2,...]')."""
    return "[" + ",".join(format(float(v), ".8f") for v in values) + "]"


def build_listing_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses = ["is_active = true"]
    params: dict[str, Any] = {}

    if filters.get("price_min") is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = filters["price_min"]
    if filters.get("price_max") is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = filters["price_max"]
    if filters.get("district"):
        clauses.append("district ILIKE :district")
        params["district"] = f"%{filters['district']}%"
    if filters.get("city"):
        clauses.append("city ILIKE :city")
        params["city"] = f"%{filters['city']}%"
    if filters.get("bedrooms") is not None:
        clauses.append("bedrooms = :bedrooms")
        params["bedrooms"] = filters["bedrooms"]
    if filters.get("listing_type"):
        clauses.append("listing_type = :listing_type")
        params["listing_type"] = filters["listing_type"]
    if filters.get("property_type"):
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{filters['property_type']}%"

    return clauses, params


def build_project_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.get("status"):
        clauses.append("status = :status")
        params["status"] = filters["status"]
    if filters.get("city"):
        clauses.append("city ILIKE :city")
        params["city"] = f"%{filters['city']}%"
    if filters.get("district"):
        clauses.append("district ILIKE :district")
        params["district"] = f"%{filters['district']}%"
    if filters.get("project_type"):
        clauses.append("project_type ILIKE :project_type")
        params["project_type"] = f"%{filters['project_type']}%"
    return clauses or ["1=1"], params


def build_article_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.get("category"):
        clauses.append("category = :category")
        params["category"] = filters["category"]
    return clauses or ["1=1"], params


async def sql_filter(parent_type: str, filters: dict[str, Any], limit: int = 500) -> list[int]:
    if parent_type == "listing":
        clauses, params = build_listing_filter_clauses(filters)
        table = "listings"
        order_by = "ORDER BY updated_at DESC NULLS LAST, id DESC"
    elif parent_type == "project":
        clauses, params = build_project_filter_clauses(filters)
        table = "projects"
        order_by = "ORDER BY updated_at DESC NULLS LAST, id DESC"
    elif parent_type == "article":
        clauses, params = build_article_filter_clauses(filters)
        table = "articles"
        order_by = "ORDER BY post_date DESC NULLS LAST, id DESC"
    else:
        return []

    params["limit"] = limit
    query = text(
        f"SELECT id FROM {table} WHERE {' AND '.join(clauses)} {order_by} LIMIT :limit"
    )
    async with async_session() as session:
        result = await session.execute(query, params)
        return [row[0] for row in result.all()]


async def get_query_embedding(
    query: str,
    *,
    embedder: Any,
    cache: JsonCache | None = None,
) -> list[float]:
    """Return the query embedding, consulting the cache before calling the embedder.

    Cache key is namespaced by the embedder model so a model upgrade never
    returns stale vectors.
    """
    cache_key = hash_text(query, namespace=getattr(embedder, "model", ""))
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached:
            return cached
    vectors = await embedder.embed_texts([query])
    embedding = vectors[0]
    if cache is not None:
        await cache.set(cache_key, embedding)
    return embedding


async def pgvector_knn(
    query_embedding: list[float],
    parent_type: str,
    parent_ids: list[int],
    k: int,
) -> list[dict[str, Any]]:
    if not parent_ids:
        return []

    query = text(
        "SELECT id, parent_type, parent_id, chunk_type, text, metadata_json, "
        "embedding <=> CAST(:query_embedding AS vector) AS distance "
        "FROM chunks "
        "WHERE parent_type = :parent_type AND parent_id = ANY(:parent_ids) "
        "ORDER BY embedding <=> CAST(:query_embedding AS vector) "
        "LIMIT :k"
    )
    params = {
        "query_embedding": _format_pgvector(query_embedding),
        "parent_type": parent_type,
        "parent_ids": parent_ids,
        "k": k,
    }
    async with async_session() as session:
        result = await session.execute(query, params)
        return [dict(row._mapping) for row in result.all()]


async def cohere_rerank(query: str, chunks: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    settings = get_settings()
    if not chunks or not settings.COHERE_API_KEY:
        return chunks[:top_n]

    rerank_cache: JsonCache | None
    try:
        rerank_cache = JsonCache(
            client=await get_redis_client(),
            namespace="rerank",
            ttl_seconds=60 * 60,
        )
    except Exception as exc:  # Redis unavailable — degrade gracefully.
        print(f"[hybrid_search] rerank cache disabled: {exc}", file=sys.stderr)
        rerank_cache = None

    rerank_namespace = settings.RERANK_MODEL

    if rerank_cache is not None:
        cached_scores: list[float | None] = []
        for chunk in chunks:
            key = hash_pair(query, chunk["text"], namespace=rerank_namespace)
            cached_scores.append(await rerank_cache.get(key))
        if all(score is not None for score in cached_scores):
            scored = []
            for chunk, score in zip(chunks, cached_scores, strict=True):
                copy = dict(chunk)
                copy["rerank_score"] = score
                scored.append(copy)
            scored.sort(key=lambda c: c["rerank_score"] or 0.0, reverse=True)
            return scored[:top_n]

    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": [chunk["text"] for chunk in chunks],
        "top_n": top_n,
    }
    headers = {
        "Authorization": f"Bearer {settings.COHERE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.cohere.com/v2/rerank", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Graceful fallback: degrade to vector-distance order on transient
        # API failure (5xx, timeout, 429) or malformed response.
        print(f"[hybrid_search] cohere rerank failed, falling back to vector order: {exc}", file=sys.stderr)
        return chunks[:top_n]

    results = data.get("results")
    if not results:
        return chunks[:top_n]

    reranked = []
    for item in results:
        if "index" not in item:
            return chunks[:top_n]
        chunk = dict(chunks[item["index"]])
        chunk["rerank_score"] = item.get("relevance_score")
        reranked.append(chunk)
        if rerank_cache is not None and chunk["rerank_score"] is not None:
            key = hash_pair(query, chunk["text"], namespace=rerank_namespace)
            await rerank_cache.set(key, chunk["rerank_score"])
    return reranked


async def resolve_to_listing_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_ids = []
    for chunk in chunks:
        parent_id = chunk["parent_id"]
        if parent_id not in parent_ids:
            parent_ids.append(parent_id)

    if not parent_ids:
        return []

    query = text(
        "SELECT id, product_id, title, price, price_text, area, area_text, bedrooms, "
        "bathrooms, district, city, address, url "
        "FROM listings WHERE id = ANY(:ids)"
    )
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        listings = {row._mapping["id"]: dict(row._mapping) for row in result.all()}

    records: list[dict[str, Any]] = []
    for chunk in chunks:
        listing = listings.get(chunk["parent_id"])
        if not listing:
            continue
        if any(record["id"] == listing["id"] for record in records):
            continue
        listing["matched_chunk"] = {
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "distance": float(chunk["distance"]),
            "rerank_score": chunk.get("rerank_score"),
        }
        records.append(listing)
    return records


async def resolve_to_project_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_ids: list[int] = []
    for chunk in chunks:
        pid = chunk["parent_id"]
        if pid not in parent_ids:
            parent_ids.append(pid)

    if not parent_ids:
        return []

    query = text(
        "SELECT id, slug, name, developer, district, city, status, "
        "price_range, area_range, project_type, url "
        "FROM projects WHERE id = ANY(:ids)"
    )
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        projects = {row._mapping["id"]: dict(row._mapping) for row in result.all()}

    records: list[dict[str, Any]] = []
    for chunk in chunks:
        project = projects.get(chunk["parent_id"])
        if not project:
            continue
        if any(record["id"] == project["id"] for record in records):
            continue
        project["matched_chunk"] = {
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "distance": float(chunk["distance"]),
            "rerank_score": chunk.get("rerank_score"),
        }
        records.append(project)
    return records


async def resolve_to_article_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_ids: list[int] = []
    for chunk in chunks:
        pid = chunk["parent_id"]
        if pid not in parent_ids:
            parent_ids.append(pid)

    if not parent_ids:
        return []

    query = text(
        "SELECT id, title, category, source, post_date, url, metadata_json "
        "FROM articles WHERE id = ANY(:ids)"
    )
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        articles = {row._mapping["id"]: dict(row._mapping) for row in result.all()}

    records: list[dict[str, Any]] = []
    for chunk in chunks:
        article = articles.get(chunk["parent_id"])
        if not article:
            continue
        if any(record["id"] == article["id"] for record in records):
            continue
        chunk_meta = chunk.get("metadata_json") or {}
        article["matched_chunk"] = {
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "distance": float(chunk["distance"]),
            "rerank_score": chunk.get("rerank_score"),
        }
        # Surface the per-chunk citation alongside the article-level
        # metadata so legal_synthesis.format_citations can render
        # Chương/Điều/Khoản references.
        if isinstance(chunk_meta, dict) and chunk_meta.get("citation"):
            article["citation"] = chunk_meta["citation"]
        records.append(article)
    return records


async def hybrid_search(
    query: str,
    filters: dict[str, Any] | None = None,
    parent_type: str = "listing",
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    filters = filters or {}
    candidate_ids = await sql_filter(parent_type, filters)
    if not candidate_ids:
        return []

    embedder = _get_query_embedder()
    embedding_cache: JsonCache | None
    try:
        embedding_cache = JsonCache(
            client=await get_redis_client(),
            namespace="embed:q",
            ttl_seconds=60 * 60 * 24 * 7,
        )
    except Exception as exc:  # Redis unavailable — degrade gracefully.
        print(f"[hybrid_search] embedding cache disabled: {exc}", file=sys.stderr)
        embedding_cache = None

    query_embedding = await get_query_embedding(query, embedder=embedder, cache=embedding_cache)
    chunks = await pgvector_knn(query_embedding, parent_type=parent_type, parent_ids=candidate_ids, k=top_k)
    reranked = await cohere_rerank(query, chunks, top_n=rerank_to)

    if parent_type == "listing":
        return await resolve_to_listing_records(reranked)
    if parent_type == "project":
        return await resolve_to_project_records(reranked)
    if parent_type == "article":
        return await resolve_to_article_records(reranked)
    return []


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(hybrid_search(args.query)), ensure_ascii=False, indent=2, default=str))
