from __future__ import annotations

import sys
from typing import Any

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session
from app.services.rag.cache import JsonCache, get_redis_client, hash_pair, hash_text
from app.services.rag.embeddings import BGEEmbedder

_QUERY_EMBEDDER: BGEEmbedder | None = None


def _get_query_embedder() -> BGEEmbedder:
    global _QUERY_EMBEDDER
    if _QUERY_EMBEDDER is None:
        settings = get_settings()
        _QUERY_EMBEDDER = BGEEmbedder(
            model_name=settings.HF_EMBEDDING_MODEL,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            embedding_dim=settings.EMBEDDING_DIM,
            device=settings.HF_EMBEDDING_DEVICE or None,
        )
    return _QUERY_EMBEDDER


def embedding_cache_namespace(embedder: Any) -> str:
    provider = getattr(embedder, "provider", "embedding")
    model_name = getattr(embedder, "model_name", getattr(embedder, "model", "unknown"))
    dimension = getattr(embedder, "embedding_dim", "unknown")
    return f"{provider}:{model_name}:{dimension}"


def _format_pgvector(values: list[float]) -> str:
    return "[" + ",".join(format(float(value), ".8f") for value in values) + "]"


def build_listing_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses = ["is_active = true"]
    params: dict[str, Any] = {}

    price_min = filters.get("price_min", filters.get("min_price"))
    price_max = filters.get("price_max", filters.get("max_price"))
    area_min = filters.get("area_min", filters.get("min_area"))
    area_max = filters.get("area_max", filters.get("max_area"))

    if price_min is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = price_min
    if price_max is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = price_max
    if area_min is not None:
        clauses.append("area >= :area_min")
        params["area_min"] = area_min
    if area_max is not None:
        clauses.append("area <= :area_max")
        params["area_max"] = area_max
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
    cache_key = hash_text(query, namespace=embedding_cache_namespace(embedder))
    if cache is not None:
        cached = await cache.get(cache_key)
        if cached is not None:
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

    try:
        rerank_cache: JsonCache | None = JsonCache(
            client=await get_redis_client(),
            namespace="rerank",
            ttl_seconds=60 * 60,
        )
    except Exception as exc:
        print(f"[hybrid_search] rerank cache disabled: {exc}", file=sys.stderr)
        rerank_cache = None

    set_signature = "|".join(f"{chunk.get('id', index)}:{chunk['text']}" for index, chunk in enumerate(chunks))
    cache_key = hash_pair(
        f"{query}|n={top_n}",
        set_signature,
        namespace=settings.RERANK_MODEL,
    )

    if rerank_cache is not None:
        cached = await rerank_cache.get(cache_key)
        if isinstance(cached, list) and cached:
            scored: list[dict[str, Any]] = []
            for entry in cached:
                idx = entry.get("index")
                if not isinstance(idx, int) or not 0 <= idx < len(chunks):
                    scored = []
                    break
                copy = dict(chunks[idx])
                copy["rerank_score"] = entry.get("score")
                scored.append(copy)
            if scored:
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
        print(f"[hybrid_search] cohere rerank failed, falling back to vector order: {exc}", file=sys.stderr)
        return chunks[:top_n]

    results = data.get("results")
    if not results:
        return chunks[:top_n]

    reranked: list[dict[str, Any]] = []
    cache_payload: list[dict[str, Any]] = []
    for item in results:
        if "index" not in item:
            return chunks[:top_n]
        chunk = dict(chunks[item["index"]])
        chunk["rerank_score"] = item.get("relevance_score")
        reranked.append(chunk)
        cache_payload.append({"index": item["index"], "score": chunk["rerank_score"]})

    if rerank_cache is not None and cache_payload:
        try:
            await rerank_cache.set(cache_key, cache_payload)
        except Exception as exc:
            print(f"[hybrid_search] rerank cache write failed: {exc}", file=sys.stderr)
    return reranked


async def resolve_to_listing_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_ids: list[int] = []
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
        parent_id = chunk["parent_id"]
        if parent_id not in parent_ids:
            parent_ids.append(parent_id)

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
        parent_id = chunk["parent_id"]
        if parent_id not in parent_ids:
            parent_ids.append(parent_id)

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
        article["matched_chunk"] = {
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "distance": float(chunk["distance"]),
            "rerank_score": chunk.get("rerank_score"),
        }
        chunk_meta = chunk.get("metadata_json") or {}
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
    try:
        embedding_cache: JsonCache | None = JsonCache(
            client=await get_redis_client(),
            namespace="embed:q",
            ttl_seconds=60 * 60 * 24 * 7,
        )
    except Exception as exc:
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
