from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, select, text


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Article, Chunk
from data_pipeline.clean import slugify
from data_pipeline.embed import BGEEmbedder
from data_pipeline.ingestors.legal_kb_ingestor import prepare_chunk_rows
from data_pipeline.legal.chunker import build_legal_chunks
from data_pipeline.legal.html_parser import parse_html
from data_pipeline.legal.structure import split_into_articles


DATASET_NAME = "th1nhng0/vietnamese-legal-documents"
SOURCE_NAME = f"huggingface:{DATASET_NAME}"
DATASET_SERVER_ROWS_URL = "https://datasets-server.huggingface.co/rows"
REAL_ESTATE_LEGAL_KEYWORDS = (
    "bat dong san",
    "dat dai",
    "nha o",
    "quyen su dung dat",
    "giay chung nhan",
    "so do",
    "so hong",
    "quy hoach",
    "xay dung",
    "chung cu",
    "kinh doanh bat dong san",
    "chuyen nhuong dat",
    "dau gia dat",
    "boi thuong giai phong mat bang",
    "tai dinh cu",
    "thue su dung dat",
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    stripped = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if text_value.lower() in {"nan", "none", "null"}:
        return ""
    return text_value


def _keyword_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in row.items():
        if key == "content_html":
            continue
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
    if not parts and row.get("content_html"):
        parts.append(normalize_hf_legal_body(row))
    return _strip_accents(" ".join(parts))


def is_real_estate_legal_document(row: dict[str, Any]) -> bool:
    searchable = _keyword_text(row)
    return any(keyword in searchable for keyword in REAL_ESTATE_LEGAL_KEYWORDS)


def extract_dataset_server_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("rows") or []:
        row = item.get("row") if isinstance(item, dict) else None
        if isinstance(row, dict):
            rows.append(row)
    return rows


async def fetch_dataset_server_rows(*, scan_limit: int | None, page_size: int = 1) -> list[dict[str, Any]]:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("Missing dependency httpx for Hugging Face datasets-server ingestion.") from exc

    rows: list[dict[str, Any]] = []
    offset = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        while scan_limit is None or len(rows) < scan_limit:
            length = page_size if scan_limit is None else min(page_size, scan_limit - len(rows))
            if length <= 0:
                break
            response = await client.get(
                DATASET_SERVER_ROWS_URL,
                params={
                    "dataset": DATASET_NAME,
                    "config": "content",
                    "split": "data",
                    "offset": offset,
                    "length": length,
                },
            )
            response.raise_for_status()
            page_rows = extract_dataset_server_rows(response.json())
            if not page_rows:
                break
            rows.extend(page_rows)
            offset += len(page_rows)
    return rows


def normalize_hf_legal_body(row: dict[str, Any]) -> str:
    html = _clean_text(row.get("content_html") or row.get("html") or row.get("content"))
    if not html:
        return ""
    return parse_html(html)


def _derive_title(row: dict[str, Any], body: str) -> str:
    for key in ("title", "doc_title", "name", "subject"):
        value = _clean_text(row.get(key))
        if value:
            return value
    for line in body.splitlines():
        candidate = line.strip()
        if 5 <= len(candidate) <= 200:
            return candidate
    return f"Văn bản pháp luật {row.get('id') or row.get('doc_id') or 'unknown'}"


def _fallback_chunks(body: str, *, chunk_size: int = 1500, overlap: int = 200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(body), step):
        text_value = body[start : start + chunk_size].strip()
        if text_value:
            chunks.append({"chunk_type": "body", "text": text_value})
        if start + chunk_size >= len(body):
            break
    return chunks


def build_hf_legal_article_payload(
    *,
    doc_id: str,
    title: str,
    body: str,
    chunks_count: int,
) -> dict[str, Any]:
    slug = slugify(title) or f"hf-legal-{doc_id}"
    return {
        "title": title,
        "body": body,
        "category": "legal",
        "source": SOURCE_NAME,
        "post_date": None,
        "url": f"legal-hf://{doc_id}",
        "metadata_json": {
            "slug": slug,
            "hf_dataset": DATASET_NAME,
            "hf_doc_id": doc_id,
            "chunks_count": chunks_count,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        },
    }


async def _ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def ingest_hf_legal_documents(
    *,
    limit: int | None = 100,
    scan_limit: int | None = 5_000,
    dataset_rows: Iterable[dict[str, Any]] | None = None,
    embedder: Any | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    if dataset_rows is None:
        dataset_rows = await fetch_dataset_server_rows(scan_limit=scan_limit)

    if not dry_run:
        await _ensure_schema()

    scanned = 0
    matched = 0
    documents = 0
    total_chunks = 0

    for row in dataset_rows:
        if scan_limit is not None and scanned >= scan_limit:
            break
        completed = matched if dry_run else documents
        if limit is not None and completed >= limit:
            break

        row_dict = dict(row)
        scanned += 1
        body = normalize_hf_legal_body(row_dict)
        if not body:
            continue
        if not is_real_estate_legal_document({**row_dict, "body": body}):
            continue

        matched += 1
        doc_id = _clean_text(row_dict.get("id") or row_dict.get("doc_id") or str(scanned))
        title = _derive_title(row_dict, body)
        slug = slugify(title) or f"hf-legal-{doc_id}"
        articles_struct = split_into_articles(body)
        chunks = build_legal_chunks(articles_struct, doc_slug=slug)
        if not chunks:
            chunks = _fallback_chunks(body)
        if not chunks:
            continue

        if dry_run:
            total_chunks += len(chunks)
            continue

        if embedder is None:
            settings = get_settings()
            embedder = BGEEmbedder(
                model_name=settings.HF_EMBEDDING_MODEL,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                embedding_dim=settings.EMBEDDING_DIM,
                device=settings.HF_EMBEDDING_DEVICE or None,
            )
        vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])
        payload = build_hf_legal_article_payload(
            doc_id=doc_id,
            title=title,
            body=body,
            chunks_count=len(chunks),
        )

        async with async_session() as session:
            existing = await session.execute(select(Article).where(Article.url == payload["url"]))
            article = existing.scalar_one_or_none()
            if article is None:
                article = Article(**payload)
                session.add(article)
                await session.flush()
            else:
                for key, value in payload.items():
                    setattr(article, key, value)
                await session.flush()

            await session.execute(
                delete(Chunk).where(
                    Chunk.parent_type == "article",
                    Chunk.parent_id == article.id,
                )
            )
            session.add_all(
                [
                    Chunk(**row)
                    for row in prepare_chunk_rows(
                        article_id=article.id,
                        chunks=chunks,
                        vectors=vectors,
                    )
                ]
            )
            await session.commit()

        documents += 1
        total_chunks += len(chunks)

    return {
        "scanned": scanned,
        "matched": matched,
        "documents": documents,
        "chunks": total_chunks,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Ingest real-estate legal docs from {DATASET_NAME}.")
    parser.add_argument("--limit", type=int, default=20, help="Documents to ingest. Use 0 for no document limit.")
    parser.add_argument("--scan-limit", type=int, default=5_000, help="Rows to scan. Use 0 for no scan limit.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and filter rows without embedding or writing DB.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    limit = None if args.limit == 0 else args.limit
    scan_limit = None if args.scan_limit == 0 else args.scan_limit
    result = asyncio.run(
        ingest_hf_legal_documents(
            limit=limit,
            scan_limit=scan_limit,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
