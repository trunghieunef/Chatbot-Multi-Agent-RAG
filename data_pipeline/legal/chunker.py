from __future__ import annotations

import re
from typing import Any


KHOAN_RE = re.compile(r"(?:^|\n)\s*(\d+)\.\s+", re.MULTILINE)


def _format_dieu_header(article: dict[str, Any]) -> str:
    return f"Điều {article['dieu_number']}. {article['dieu_title']}"


def _split_long_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(text), step):
        piece = text[start : start + chunk_size]
        if piece.strip():
            pieces.append(piece)
        if start + chunk_size >= len(text):
            break
    return pieces


def _split_by_khoan(text: str) -> list[tuple[int, str]]:
    """Split a long Điều body into (khoan_number, text) pieces.

    Returns an empty list when no Khoản numbering is found, so callers can
    fall back to fixed-size splitting.
    """
    matches = list(KHOAN_RE.finditer(text))
    if len(matches) < 2:
        return []

    pieces: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        khoan_number = int(match.group(1))
        body = text[start:end].strip()
        if body:
            pieces.append((khoan_number, body))
    return pieces


def _citation(*, doc_slug: str, article: dict[str, Any], khoan_number: int | None) -> dict[str, Any]:
    return {
        "doc_slug": doc_slug,
        "chuong": article.get("chuong") or "",
        "dieu_number": article["dieu_number"],
        "dieu_title": article.get("dieu_title") or "",
        "khoan_number": khoan_number,
    }


def build_legal_chunks(
    articles: list[dict[str, Any]],
    *,
    doc_slug: str,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for article in articles:
        header = _format_dieu_header(article)
        full_text = f"{header}\n{article['text']}".strip()

        if len(full_text) <= chunk_size:
            chunks.append(
                {
                    "chunk_type": "dieu",
                    "text": full_text,
                    "citation": _citation(doc_slug=doc_slug, article=article, khoan_number=None),
                }
            )
            continue

        khoan_pieces = _split_by_khoan(article["text"])
        if khoan_pieces:
            for khoan_number, khoan_text in khoan_pieces:
                full_khoan = f"{header}\n{khoan_text}".strip()
                for piece in _split_long_text(full_khoan, chunk_size=chunk_size, overlap=overlap):
                    chunks.append(
                        {
                            "chunk_type": "khoan",
                            "text": piece,
                            "citation": _citation(doc_slug=doc_slug, article=article, khoan_number=khoan_number),
                        }
                    )
            continue

        for piece in _split_long_text(full_text, chunk_size=chunk_size, overlap=overlap):
            chunks.append(
                {
                    "chunk_type": "dieu",
                    "text": piece,
                    "citation": _citation(doc_slug=doc_slug, article=article, khoan_number=None),
                }
            )
    return chunks
