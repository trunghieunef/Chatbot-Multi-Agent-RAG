from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Article, Chunk
from data_pipeline.clean import slugify
from data_pipeline.embed import GeminiEmbedder
from data_pipeline.legal.chunker import build_legal_chunks
from data_pipeline.legal.html_parser import parse_html
from data_pipeline.legal.manifest import compute_sha256, has_been_ingested, mark_ingested
from data_pipeline.legal.pdf_parser import parse_pdf
from data_pipeline.legal.structure import split_into_articles


KNOWLEDGE_RAW = ROOT / "data" / "knowledge" / "raw"
KNOWLEDGE_LOG = ROOT / "data" / "knowledge" / "ingested"


def build_article_payload(
    *,
    title: str,
    slug: str,
    body: str,
    source_filename: str,
    digest: str,
    chunks_count: int,
) -> dict[str, Any]:
    """Compose Article kwargs for a legal document, including audit metadata."""
    return {
        "title": title,
        "body": body,
        "category": "legal",
        "source": source_filename,
        "post_date": None,
        "url": f"legal://{slug}",
        "metadata_json": {
            "slug": slug,
            "sha256": digest,
            "chunks_count": chunks_count,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def prepare_chunk_rows(
    *, article_id: int, chunks: list[dict], vectors: list[list[float]]
) -> list[dict]:
    """Pair chunk dicts with their vectors into Chunk row kwargs."""
    if len(chunks) != len(vectors):
        raise ValueError("chunk/vector count mismatch")
    rows: list[dict] = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        rows.append(
            {
                "parent_type": "article",
                "parent_id": article_id,
                "chunk_type": chunk["chunk_type"],
                "text": chunk["text"],
                "embedding": vector,
            }
        )
    return rows


def _read_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(str(path))
    if suffix in {".html", ".htm"}:
        for encoding in ("utf-8", "utf-8-sig", "cp1258", "latin-1"):
            try:
                return parse_html(path.read_text(encoding=encoding))
            except UnicodeDecodeError:
                continue
        return parse_html(path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"Unsupported legal document type: {path.suffix}")


def _derive_title(path: Path, body: str) -> str:
    """Prefer the first non-empty line of the parsed text as the title.

    Vietnamese statutes start with the official title on the first content
    line (e.g. "LUẬT ĐẤT ĐAI"). Falling back to the filename loses diacritics
    and ends up with a degraded title in the database, so we only use the
    filename when text extraction failed entirely.
    """
    for line in body.splitlines():
        candidate = line.strip()
        if 5 <= len(candidate) <= 200:
            return candidate
    return path.stem.replace("-", " ").replace("_", " ").strip()


async def ingest_legal_documents(
    raw_dir: Path = KNOWLEDGE_RAW, log_dir: Path = KNOWLEDGE_LOG
) -> dict[str, int]:
    """Ingest every supported legal file under raw_dir, skipping unchanged files."""
    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_EMBEDDING_MODEL
    )

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    total_docs = 0
    skipped = 0
    total_chunks = 0

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".html", ".htm"}:
            continue

        digest = compute_sha256(str(path))
        if has_been_ingested(digest, str(log_dir)):
            skipped += 1
            continue

        body = _read_document_text(path)
        title = _derive_title(path, body)
        slug = slugify(title)
        articles_struct = split_into_articles(body)
        chunks = build_legal_chunks(articles_struct, doc_slug=slug)

        if not chunks:
            skipped += 1
            mark_ingested(digest, str(log_dir), info={"file": path.name, "skipped": "no chunks"})
            continue

        vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])

        async with async_session() as session:
            payload = build_article_payload(
                title=title,
                slug=slug,
                body=body,
                source_filename=path.name,
                digest=digest,
                chunks_count=len(chunks),
            )
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
                    Chunk.parent_type == "article", Chunk.parent_id == article.id
                )
            )
            chunk_rows = prepare_chunk_rows(
                article_id=article.id, chunks=chunks, vectors=vectors
            )
            session.add_all([Chunk(**row) for row in chunk_rows])
            await session.commit()

        total_docs += 1
        total_chunks += len(chunks)
        mark_ingested(
            digest,
            str(log_dir),
            info={"file": path.name, "slug": slug, "chunks": len(chunks)},
        )

    return {"documents": total_docs, "chunks": total_chunks, "skipped": skipped}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(KNOWLEDGE_RAW))
    parser.add_argument("--log-dir", default=str(KNOWLEDGE_LOG))
    args = parser.parse_args()
    result = await ingest_legal_documents(Path(args.raw_dir), Path(args.log_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
