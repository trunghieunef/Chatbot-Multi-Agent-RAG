from __future__ import annotations

import re
from typing import Iterator

CHUONG_RE = re.compile(r"^\s*(Chương\s+[IVXLCDM]+)\.?\s*(.*)$", re.IGNORECASE | re.MULTILINE)
DIEU_RE = re.compile(r"^\s*Điều\s+(\d+)\.\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _iter_chuongs(text: str) -> Iterator[tuple[str, str, int, int]]:
    matches = list(CHUONG_RE.finditer(text))
    if not matches:
        yield "", "", 0, len(text)
        return

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(1).strip(), match.group(2).strip(), match.end(), end


def split_into_articles(text: str) -> list[dict]:
    if not text or not text.strip():
        return []

    articles: list[dict] = []
    for chuong, chuong_title, ch_start, ch_end in _iter_chuongs(text):
        section = text[ch_start:ch_end]
        dieu_matches = list(DIEU_RE.finditer(section))
        for index, match in enumerate(dieu_matches):
            body_start = match.end()
            body_end = dieu_matches[index + 1].start() if index + 1 < len(dieu_matches) else len(section)
            body = section[body_start:body_end].strip()
            articles.append(
                {
                    "chuong": chuong,
                    "chuong_title": chuong_title,
                    "dieu_number": int(match.group(1)),
                    "dieu_title": match.group(2).strip().rstrip("."),
                    "text": body,
                }
            )
    return articles
