from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
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

# ── Real‑estate keyword groups for metadata‑based filtering ──────────────
# Each group covers a distinct domain; a document matches when its title,
# nganh, or linh_vuc contains any keyword from any group.
RE_GROUPS: dict[str, list[str]] = {
    "dat_dai": [
        "đất đai", "quyền sử dụng đất", "sổ đỏ", "sổ hồng",
        "giấy chứng nhận quyền sử dụng đất", "địa chính",
        "giao đất", "cho thuê đất", "chuyển mục đích sử dụng đất",
        "thu hồi đất", "bồi thường", "giải phóng mặt bằng", "tái định cư",
        "đấu giá đất", "chuyển nhượng quyền sử dụng đất",
        "cấp giấy chứng nhận", "đo đạc", "bản đồ", "địa giới",
    ],
    "nha_o": [
        "nhà ở", "chung cư", "căn hộ", "nhà ở xã hội",
        "nhà ở thương mại", "sở hữu nhà", "quản lý nhà",
        "phát triển nhà", "cải tạo nhà", "xây dựng nhà",
        "condotel", "officetel", "công trình nhà",
    ],
    "kinh_doanh_bds": [
        "kinh doanh bất động sản", "bất động sản",
        "dự án bất động sản", "đầu tư bất động sản",
        "môi giới bất động sản", "sàn giao dịch bất động sản",
        "định giá bất động sản", "thế chấp bất động sản",
        "giao dịch bất động sản", "chuyển nhượng bất động sản",
        "cho thuê bất động sản", "mua bán bất động sản",
    ],
    "hop_dong_dan_su": [
        "hợp đồng", "dân sự", "công chứng", "chứng thực",
        "thừa kế", "tặng cho", "ủy quyền", "thế chấp",
        "bảo lãnh", "giao dịch dân sự", "nghĩa vụ dân sự",
        "quyền sở hữu", "quyền tài sản", "đăng ký giao dịch",
        "văn phòng công chứng", "luật công chứng",
    ],
    "thue_phi_sang_ten": [
        "thuế", "phí", "lệ phí", "sang tên",
        "thuế thu nhập cá nhân", "thuế giá trị gia tăng",
        "thuế sử dụng đất", "tiền sử dụng đất",
        "lệ phí trước bạ", "miễn thuế", "giảm thuế",
        "khai thuế", "quyết toán thuế", "hoàn thuế",
        "đăng ký biến động", "đăng ký quyền sở hữu",
        "thuế chuyển nhượng", "thuế bất động sản",
    ],
    "quy_hoach_xay_dung": [
        "quy hoạch", "xây dựng", "đô thị", "kiến trúc",
        "cấp phép xây dựng", "giấy phép xây dựng",
        "quy hoạch sử dụng đất", "quy hoạch đô thị",
        "hạ tầng kỹ thuật", "phát triển đô thị",
        "chỉ giới", "mật độ xây dựng", "hệ số sử dụng đất",
    ],
}

# Flattened set of all keywords for quick lookup
_ALL_RE_KEYWORDS: set[str] = set()
for _kw_list in RE_GROUPS.values():
    _ALL_RE_KEYWORDS.update(kw.lower() for kw in _kw_list)
# Pre-compile a single regex for matching any keyword (word-boundary aware)
_RE_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in sorted(_ALL_RE_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if text_value.lower() in {"nan", "none", "null"}:
        return ""
    return text_value


# ── Metadata‑first filtering ─────────────────────────────────────────────

def _metadata_searchable(row: dict[str, Any]) -> str:
    """Concatenate title + nganh + linh_vuc for keyword matching."""
    parts: list[str] = []
    for key in ("title", "nganh", "linh_vuc"):
        value = _clean_text(row.get(key))
        if value:
            parts.append(value)
    return " ".join(parts)


def is_real_estate_by_metadata(row: dict[str, Any]) -> bool:
    """Check if metadata (title / nganh / linh_vuc) matches any BĐS keyword."""
    searchable = _metadata_searchable(row)
    return bool(_RE_PATTERN.search(searchable))


def fetch_real_estate_doc_ids(*, scan_limit: int | None) -> tuple[set[str], dict[str, dict[str, str]]]:
    """Load metadata, filter by BĐS keywords, return matching doc IDs and their metadata.

    Returns
    -------
    ids : set of doc_id strings that matched.
    meta_by_id : dict mapping doc_id → {title, nganh, linh_vuc, loai_van_ban, ngay_ban_hanh}.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Missing dependency datasets for Hugging Face ingestion.") from exc

    ds = load_dataset(DATASET_NAME, "metadata", split="data", streaming=True)
    matched_ids: set[str] = set()
    meta_by_id: dict[str, dict[str, str]] = {}
    scanned = 0

    for row in ds:
        if scan_limit is not None and scanned >= scan_limit:
            break
        scanned += 1
        row_dict = dict(row)
        if not is_real_estate_by_metadata(row_dict):
            continue
        doc_id = str(_clean_text(row_dict.get("id") or ""))
        if not doc_id:
            continue
        matched_ids.add(doc_id)
        meta_by_id[doc_id] = {
            "title": _clean_text(row_dict.get("title") or ""),
            "nganh": _clean_text(row_dict.get("nganh") or ""),
            "linh_vuc": _clean_text(row_dict.get("linh_vuc") or ""),
            "loai_van_ban": _clean_text(row_dict.get("loai_van_ban") or ""),
            "ngay_ban_hanh": _clean_text(row_dict.get("ngay_ban_hanh") or ""),
        }

    return matched_ids, meta_by_id


def fetch_content_for_ids(
    doc_ids: set[str],
    *,
    scan_limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load content config, keep only rows whose id is in *doc_ids*."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Missing dependency datasets for Hugging Face ingestion.") from exc

    ds = load_dataset(DATASET_NAME, "content", split="data", streaming=True)
    rows: list[dict[str, Any]] = []
    scanned = 0
    for row in ds:
        if scan_limit is not None and scanned >= scan_limit:
            break
        scanned += 1
        row_dict = dict(row)
        row_id = str(_clean_text(row_dict.get("id") or ""))
        if row_id in doc_ids:
            rows.append(row_dict)
    return rows


# ── Content processing ────────────────────────────────────────────────────

def normalize_hf_legal_body(row: dict[str, Any]) -> str:
    html = _clean_text(row.get("content_html") or row.get("html") or row.get("content"))
    if not html:
        return ""
    return parse_html(html)


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
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    slug = slugify(title) or f"hf-legal-{doc_id}"
    meta_payload: dict[str, Any] = {
        "slug": slug,
        "hf_dataset": DATASET_NAME,
        "hf_doc_id": doc_id,
        "chunks_count": chunks_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        meta_payload["hf_nganh"] = metadata.get("nganh", "")
        meta_payload["hf_linh_vuc"] = metadata.get("linh_vuc", "")
        meta_payload["hf_loai_van_ban"] = metadata.get("loai_van_ban", "")
        meta_payload["hf_ngay_ban_hanh"] = metadata.get("ngay_ban_hanh", "")
    return {
        "title": title,
        "body": body,
        "category": "legal",
        "source": SOURCE_NAME,
        "post_date": None,
        "url": f"legal-hf://{doc_id}",
        "metadata_json": meta_payload,
    }


# ── Database helpers ──────────────────────────────────────────────────────

async def _ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


# ── Main ingestion ────────────────────────────────────────────────────────

async def ingest_hf_legal_documents(
    *,
    limit: int | None = 100,
    scan_limit: int | None = 5_000,
    embedder: Any | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Metadata‑first: filter by title/nganh/linh_vuc, then ingest matching content."""

    # 1. Load metadata, find BĐS doc IDs
    doc_ids, meta_by_id = fetch_real_estate_doc_ids(scan_limit=scan_limit)
    total_matched = len(doc_ids)
    if total_matched == 0:
        return {"metadata_scanned": scan_limit or 0, "matched": 0, "documents": 0, "chunks": 0}

    # 2. Load content rows only for matched IDs
    content_rows = fetch_content_for_ids(doc_ids)
    if not content_rows:
        return {"metadata_scanned": scan_limit or 0, "matched": total_matched, "documents": 0, "chunks": 0}

    if not dry_run:
        await _ensure_schema()

    documents = 0
    total_chunks = 0

    for row_dict in content_rows:
        if limit is not None and documents >= limit:
            break

        doc_id = str(_clean_text(row_dict.get("id") or ""))
        meta = meta_by_id.get(doc_id, {})
        body = normalize_hf_legal_body(row_dict)
        if not body:
            continue

        title = meta.get("title") or ""
        if not title:
            for line in body.splitlines():
                candidate = line.strip()
                if 5 <= len(candidate) <= 200:
                    title = candidate
                    break
        if not title:
            title = f"Văn bản pháp luật {doc_id}"

        slug = slugify(title) or f"hf-legal-{doc_id}"
        articles_struct = split_into_articles(body)
        chunks = build_legal_chunks(articles_struct, doc_slug=slug)
        if not chunks:
            chunks = _fallback_chunks(body)
        if not chunks:
            continue

        if dry_run:
            total_chunks += len(chunks)
            documents += 1
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
            metadata=meta,
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
        "metadata_scanned": scan_limit or len(meta_by_id),
        "matched": total_matched,
        "documents": documents,
        "chunks": total_chunks,
    }


# ── CLI ───────────────────────────────────────────────────────────────────

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Ingest real-estate legal docs from {DATASET_NAME} (metadata-first).")
    parser.add_argument("--limit", type=int, default=20, help="Documents to ingest. Use 0 for no document limit.")
    parser.add_argument("--scan-limit", type=int, default=0, help="Metadata rows to scan. 0 = all 153K rows.")
    parser.add_argument("--dry-run", action="store_true", help="Match metadata + fetch content without writing DB.")
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
