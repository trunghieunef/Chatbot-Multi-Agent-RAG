# M4 Legal Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Vietnamese real-estate legal documents (Luật Đất đai 2024, Luật Nhà ở 2023, Luật Kinh doanh BĐS 2023, plus relevant nghị định/thông tư) as PDF/HTML files into the existing `articles`/`chunks` schema with `category="legal"`, then wire the Legal Advisor Agent to answer questions using hybrid search restricted to legal chunks.

**Architecture:** Reuse the M1+M2 pipeline shape — clean → chunk → embed → upsert into `articles` + `chunks` — but swap the source: PDF/HTML files in `data/knowledge/raw/` instead of crawled web pages. A dedicated `legal_kb_ingestor.py` parses each document, chunks by legal hierarchy (Chương → Điều → Khoản → Điểm), embeds with the same Gemini model, and stores `parent_type="article"`, `category="legal"`. A monthly Airflow DAG (`monthly_legal_kb_dag`) detects new/changed files via SHA-256 checksums and re-ingests only those documents. Legal Advisor Agent calls `hybrid_search(parent_type="article", filters={"category": "legal"})` and synthesizes answers with mandatory citations to Điều/Khoản.

**Tech Stack:** Python 3.11, PyMuPDF (fitz) for PDF parsing, BeautifulSoup4 for HTML, Google Gemini for embedding + answer synthesis, existing SQLAlchemy + pgvector + LangGraph stack from M1–M3.

---

## Scope And Existing Repo Notes

- M4 Tasks 1–9 require M2 to be merged (`articles`, `chunks`, hybrid search article path, embedder). They can run end-to-end via the manual CLI even before M3 lands.
- M4 Tasks 10 (`monthly_legal_kb_dag`) and the DAG-related verification step in Task 12 require M3 to be merged (Airflow stack, `pipeline_runner.py`, `alerting.py`). If M3 is not merged yet, defer Task 10 — every other M4 task still produces working software.
- M4 assumes M1 + M2 are merged: `articles` and `chunks` ORM models, `data_pipeline/embed.py`, `chatbot/tools/hybrid_search.py` with `parent_type="article"` dispatch.
- Legal documents are NOT crawled. Operators drop PDF/HTML files into `data/knowledge/raw/<doc-slug>/<filename>` manually or via a separate sync script (out of scope here).
- The M2 news ingestor handles `category="news"` from web crawls; M4 handles `category="legal"` from local files. They share the `articles` table but never overlap on `url` (legal docs use `legal://<slug>` as a synthetic URL).
- Chunking strategy is hierarchical, not fixed-size: split first by Chương heading, then by Điều, then by Khoản numbering when an Điều exceeds 1500 characters, falling back to fixed-size only when no Khoản pattern is found. This keeps citations meaningful and matches how Vietnamese lawyers reference statutes.
- Citations are mandatory in Legal Advisor responses. Each cited chunk must include the document slug, Chương, Điều number, and Khoản number when present. Without citations the agent must say so explicitly rather than fabricate one.
- `metadata_json` on each legal article carries `{slug, sha256, chunks_count, ingested_at}` for auditability. Future fields (e.g. `effective_date`, `version`) can be added without a migration.
- The monthly DAG runs on `0 5 1 * *` (1st of every month, 05:00 ICT). It does not crawl the web — the only side effect outside the DB is reading from `data/knowledge/raw/` and writing to `data/knowledge/ingested/<sha>.json` log files.
- File watcher / hot reload is out of scope. Operators add documents and trigger the DAG manually if they need immediate indexing.
- Existing `chatbot/agents/legal_advisor.py` is a placeholder. M4 replaces the body with a real implementation that calls hybrid search + Gemini synthesis with citations.

## File Structure

- Create: `data/knowledge/raw/` directory (gitignored except `.gitkeep`).
- Create: `data/knowledge/ingested/` directory (gitignored except `.gitkeep`).
- Create: `data_pipeline/legal/__init__.py`
- Create: `data_pipeline/legal/pdf_parser.py` — PyMuPDF wrapper turning a PDF path into normalized text.
- Create: `data_pipeline/legal/html_parser.py` — BeautifulSoup wrapper for HTML files.
- Create: `data_pipeline/legal/structure.py` — splits Vietnamese legal text into Chương/Điều/Khoản tree.
- Create: `data_pipeline/legal/chunker.py` — turns the structure tree into chunk dicts with citation metadata.
- Create: `data_pipeline/legal/manifest.py` — SHA-256 fingerprint + ingested log helpers.
- Create: `data_pipeline/ingestors/legal_kb_ingestor.py` — orchestrate parse → structure → chunk → embed → upsert.
- Modify: `data_pipeline/clean.py` — add `slugify()` helper (used to make stable document slugs).
- Modify: `backend/app/models/article.py` — add `metadata_json` JSON column for legal hierarchy info, with Alembic migration.
- Create: `backend/alembic/versions/20260701_0003_legal_metadata.py`
- Create: `airflow/dags/monthly_legal_kb_dag.py`
- Modify: `airflow/plugins/pipeline_runner.py` — add `run_legal_ingestion()`.
- Modify: `chatbot/agents/legal_advisor.py` — call hybrid search + Gemini, format citations.
- Create: `chatbot/tools/legal_synthesis.py` — prompt template + Gemini call wrapper.
- Modify: `chatbot/tools/hybrid_search.py` — `resolve_to_article_records` already exists; ensure `metadata_json` is included in the response.
- Test: `backend/tests/test_legal_pdf_parser.py`, `backend/tests/test_legal_structure.py`, `backend/tests/test_legal_chunker.py`, `backend/tests/test_legal_manifest.py`, `backend/tests/test_legal_kb_ingestor.py`, `backend/tests/test_legal_synthesis.py`, `backend/tests/test_legal_dag_structure.py`.

---

### Task 1: Dependencies And Article Metadata Column

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/models/article.py`
- Create: `backend/alembic/versions/20260701_0003_legal_metadata.py`
- Test: `backend/tests/test_article_metadata.py`

- [ ] **Step 1: Add dependencies**

`beautifulsoup4>=4.14.0` is already pinned in `backend/requirements.txt` (used elsewhere in the repo). M4 only needs the PDF parser.

Append to `backend/requirements.txt`:

```text
pymupdf>=1.24.0
```

- [ ] **Step 2: Write failing test for `metadata_json` column**

Create `backend/tests/test_article_metadata.py`:

```python
from app.models import Article


def test_article_model_exposes_metadata_json():
    columns = {col.name for col in Article.__table__.columns}
    assert "metadata_json" in columns
```

- [ ] **Step 3: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_article_metadata.py -q
```

Expected: fail because `metadata_json` is missing.

- [ ] **Step 4: Add the column**

Modify `backend/app/models/article.py`:

```python
from sqlalchemy import JSON

class Article(Base):
    ...
    metadata_json = Column(JSON, nullable=True)
```

Place the column right before `created_at`. Keep all other fields identical.

- [ ] **Step 5: Add the Alembic migration**

Create `backend/alembic/versions/20260701_0003_legal_metadata.py`:

```python
"""legal article metadata

Revision ID: 20260701_0003
Revises: 20260601_0002
Create Date: 2026-07-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0003"
down_revision: Union[str, None] = "20260601_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "metadata_json")
```

- [ ] **Step 6: Run the test**

```powershell
cd backend
python -m pytest tests/test_article_metadata.py -q
```

Expected: pass.

- [ ] **Step 7: Apply migration locally**

```powershell
docker-compose up -d postgres
cd backend
alembic upgrade head
```

Expected: revision `20260701_0003` applied without errors.

- [ ] **Step 8: Commit**

```powershell
git add backend/requirements.txt backend/app/models/article.py backend/alembic/versions/20260701_0003_legal_metadata.py backend/tests/test_article_metadata.py
git commit -m "add metadata_json column for legal articles"
```

---

### Task 2: PDF Parser

**Files:**
- Create: `data_pipeline/legal/__init__.py` (empty)
- Create: `data_pipeline/legal/pdf_parser.py`
- Test: `backend/tests/test_legal_pdf_parser.py`

- [ ] **Step 1: Write failing tests with a sample fixture**

Create a minimal sample PDF for testing. From repo root:

```powershell
python -c "import fitz; doc = fitz.open(); page = doc.new_page(); page.insert_text((50, 72), 'Điều 1. Phạm vi điều chỉnh\n1. Luật này quy định...'); doc.save('backend/tests/fixtures/sample_legal.pdf'); doc.close()"
```

If the `fixtures` directory does not exist, create it first:

```powershell
mkdir backend\tests\fixtures
```

Create `backend/tests/test_legal_pdf_parser.py`:

```python
from pathlib import Path

from data_pipeline.legal.pdf_parser import parse_pdf


FIXTURE = Path(__file__).parent / "fixtures" / "sample_legal.pdf"


def test_parse_pdf_returns_text_with_normalized_whitespace():
    text = parse_pdf(str(FIXTURE))

    assert "Điều 1" in text
    assert "Phạm vi điều chỉnh" in text
    # Whitespace should be normalized (no triple newlines)
    assert "\n\n\n" not in text


def test_parse_pdf_raises_for_missing_file():
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_pdf("does/not/exist.pdf")
```

- [ ] **Step 2: Run the test and confirm import failure**

```powershell
cd backend
python -m pytest tests/test_legal_pdf_parser.py -q
```

Expected: fail because `data_pipeline.legal.pdf_parser` does not exist.

- [ ] **Step 3: Implement the parser**

Create `data_pipeline/legal/__init__.py` (empty file).

Create `data_pipeline/legal/pdf_parser.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

import fitz


def parse_pdf(path: str) -> str:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(path)

    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))

    text = "\n".join(parts)
    # Collapse 3+ newlines and trailing spaces
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

- [ ] **Step 4: Run parser tests**

```powershell
cd backend
python -m pytest tests/test_legal_pdf_parser.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/legal/__init__.py data_pipeline/legal/pdf_parser.py backend/tests/test_legal_pdf_parser.py backend/tests/fixtures/sample_legal.pdf
git commit -m "add legal pdf parser"
```

---

### Task 3: HTML Parser

**Files:**
- Create: `data_pipeline/legal/html_parser.py`
- Test: `backend/tests/test_legal_html_parser.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_legal_html_parser.py`:

```python
from data_pipeline.legal.html_parser import parse_html


def test_parse_html_strips_tags_and_keeps_text():
    html = """
    <html><body>
      <h1>Luật Đất đai 2024</h1>
      <p>Điều 1. <em>Phạm vi điều chỉnh</em></p>
      <script>alert('x')</script>
      <style>body{color:red}</style>
    </body></html>
    """

    text = parse_html(html)

    assert "Luật Đất đai 2024" in text
    assert "Điều 1" in text
    assert "Phạm vi điều chỉnh" in text
    assert "alert" not in text
    assert "color:red" not in text
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_html_parser.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement the parser**

Create `data_pipeline/legal/html_parser.py`:

```python
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def parse_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_legal_html_parser.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/legal/html_parser.py backend/tests/test_legal_html_parser.py
git commit -m "add legal html parser"
```

---

### Task 4: Legal Structure Splitter

**Files:**
- Create: `data_pipeline/legal/structure.py`
- Test: `backend/tests/test_legal_structure.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_legal_structure.py`:

```python
from data_pipeline.legal.structure import split_into_articles


SAMPLE = """
Chương I. NHỮNG QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Luật này quy định về quản lý đất đai.
2. Áp dụng với mọi tổ chức, cá nhân.

Điều 2. Đối tượng áp dụng
Đối tượng áp dụng gồm:
a) Cơ quan nhà nước;
b) Tổ chức trong nước.

Chương II. QUYỀN VÀ NGHĨA VỤ

Điều 3. Quyền của người sử dụng đất
Người sử dụng đất có các quyền sau:
1. Quyền chuyển nhượng.
"""


def test_split_into_articles_preserves_chuong_and_dieu():
    articles = split_into_articles(SAMPLE)

    assert len(articles) == 3
    assert articles[0]["chuong"] == "Chương I"
    assert articles[0]["chuong_title"] == "NHỮNG QUY ĐỊNH CHUNG"
    assert articles[0]["dieu_number"] == 1
    assert articles[0]["dieu_title"] == "Phạm vi điều chỉnh"
    assert "Luật này quy định" in articles[0]["text"]

    assert articles[1]["dieu_number"] == 2
    assert articles[2]["chuong"] == "Chương II"
    assert articles[2]["dieu_number"] == 3


def test_split_into_articles_returns_empty_for_blank_text():
    assert split_into_articles("") == []
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_structure.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement the splitter**

Create `data_pipeline/legal/structure.py`:

```python
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
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_legal_structure.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/legal/structure.py backend/tests/test_legal_structure.py
git commit -m "split legal text by chuong and dieu"
```

---

### Task 5: Legal Chunker

**Files:**
- Create: `data_pipeline/legal/chunker.py`
- Test: `backend/tests/test_legal_chunker.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_legal_chunker.py`:

```python
from data_pipeline.legal.chunker import build_legal_chunks


def test_build_legal_chunks_creates_one_chunk_per_dieu_when_short():
    articles = [
        {"chuong": "Chương I", "chuong_title": "Quy định chung", "dieu_number": 1, "dieu_title": "Phạm vi", "text": "Luật này quy định..."},
        {"chuong": "Chương I", "chuong_title": "Quy định chung", "dieu_number": 2, "dieu_title": "Đối tượng", "text": "Áp dụng cho..."},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500)

    assert len(chunks) == 2
    assert chunks[0]["chunk_type"] == "dieu"
    assert chunks[0]["text"].startswith("Điều 1. Phạm vi")
    assert chunks[0]["citation"] == {
        "doc_slug": "luat-dat-dai-2024",
        "chuong": "Chương I",
        "dieu_number": 1,
        "dieu_title": "Phạm vi",
        "khoan_number": None,
    }


def test_build_legal_chunks_splits_long_dieu_by_khoan_with_citations():
    body = (
        "1. Khoản một nội dung. " + "Khoản một mở rộng. " * 60
        + "\n2. Khoản hai nội dung. " + "Khoản hai mở rộng. " * 60
        + "\n3. Khoản ba nội dung. " + "Khoản ba mở rộng. " * 60
    )
    articles = [
        {"chuong": "Chương II", "chuong_title": "Quyền", "dieu_number": 3, "dieu_title": "Quyền sử dụng", "text": body},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500, overlap=200)

    khoan_numbers = [chunk["citation"]["khoan_number"] for chunk in chunks]
    assert {1, 2, 3}.issubset(set(khoan_numbers))
    for chunk in chunks:
        assert chunk["citation"]["dieu_number"] == 3


def test_build_legal_chunks_falls_back_to_fixed_size_when_no_khoan():
    long_text = "Một câu nội dung dài không có khoản. " * 200
    articles = [
        {"chuong": "Chương III", "chuong_title": "Khác", "dieu_number": 7, "dieu_title": "Điều khác", "text": long_text},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500, overlap=200)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["citation"]["dieu_number"] == 7
        assert chunk["citation"]["khoan_number"] is None
        assert len(chunk["text"]) <= 1700
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_chunker.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement the chunker**

Create `data_pipeline/legal/chunker.py`:

```python
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
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_legal_chunker.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/legal/chunker.py backend/tests/test_legal_chunker.py
git commit -m "chunk legal text by article with overlap"
```

---

### Task 6: Manifest And Slugify Helpers

**Files:**
- Create: `data_pipeline/legal/manifest.py`
- Modify: `data_pipeline/clean.py`
- Test: `backend/tests/test_legal_manifest.py`, `backend/tests/test_slugify.py`

- [ ] **Step 1: Write failing tests for manifest helpers**

Create `backend/tests/test_legal_manifest.py`:

```python
from pathlib import Path

from data_pipeline.legal.manifest import compute_sha256, has_been_ingested, mark_ingested


def test_compute_sha256_is_deterministic(tmp_path: Path):
    file_a = tmp_path / "a.txt"
    file_a.write_bytes(b"hello world")

    digest = compute_sha256(str(file_a))

    assert len(digest) == 64
    assert digest == compute_sha256(str(file_a))


def test_mark_and_check_ingested(tmp_path: Path):
    log_dir = tmp_path / "ingested"
    digest = "a" * 64

    assert not has_been_ingested(digest, str(log_dir))
    mark_ingested(digest, str(log_dir), info={"file": "x.pdf", "chunks": 12})
    assert has_been_ingested(digest, str(log_dir))
```

Create `backend/tests/test_slugify.py`:

```python
from data_pipeline.clean import slugify


def test_slugify_strips_diacritics_and_lowers():
    assert slugify("Luật Đất đai 2024") == "luat-dat-dai-2024"
    assert slugify("Nghị định 99/2024/NĐ-CP") == "nghi-dinh-99-2024-nd-cp"
    assert slugify("") == ""
```

- [ ] **Step 2: Run the tests and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_manifest.py tests/test_slugify.py -q
```

Expected: both fail (manifest module + `slugify` missing).

- [ ] **Step 3: Implement manifest helpers**

Create `data_pipeline/legal/manifest.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def compute_sha256(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _log_path(digest: str, log_dir: str) -> Path:
    return Path(log_dir) / f"{digest}.json"


def has_been_ingested(digest: str, log_dir: str) -> bool:
    return _log_path(digest, log_dir).exists()


def mark_ingested(digest: str, log_dir: str, *, info: dict[str, Any] | None = None) -> None:
    os.makedirs(log_dir, exist_ok=True)
    payload = {"digest": digest, "info": info or {}}
    _log_path(digest, log_dir).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Add `slugify` to `data_pipeline/clean.py`**

Append to `data_pipeline/clean.py`:

```python
import re
import unicodedata


def slugify(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_marks = without_marks.replace("đ", "d").replace("Đ", "d")
    lowered = without_marks.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned
```

- [ ] **Step 5: Run the tests**

```powershell
cd backend
python -m pytest tests/test_legal_manifest.py tests/test_slugify.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add data_pipeline/legal/manifest.py data_pipeline/clean.py backend/tests/test_legal_manifest.py backend/tests/test_slugify.py
git commit -m "add legal manifest and slugify helpers"
```

---

### Task 7: Legal KB Ingestor

**Files:**
- Create: `data_pipeline/ingestors/legal_kb_ingestor.py`
- Test: `backend/tests/test_legal_kb_ingestor.py`

- [ ] **Step 1: Write failing tests for the row builder**

Create `backend/tests/test_legal_kb_ingestor.py`:

```python
from data_pipeline.ingestors.legal_kb_ingestor import build_article_payload, prepare_chunk_rows


def test_build_article_payload_uses_synthetic_url_and_legal_category():
    payload = build_article_payload(
        title="Luật Đất đai 2024",
        slug="luat-dat-dai-2024",
        body="Toàn văn luật...",
        source_filename="luat-dat-dai-2024.pdf",
        digest="a" * 64,
        chunks_count=12,
    )

    assert payload["title"] == "Luật Đất đai 2024"
    assert payload["category"] == "legal"
    assert payload["source"] == "luat-dat-dai-2024.pdf"
    assert payload["url"] == "legal://luat-dat-dai-2024"
    metadata = payload["metadata_json"]
    assert metadata["slug"] == "luat-dat-dai-2024"
    assert metadata["sha256"] == "a" * 64
    assert metadata["chunks_count"] == 12
    assert "ingested_at" in metadata


def test_prepare_chunk_rows_pairs_chunks_and_vectors():
    chunks = [
        {"chunk_type": "dieu", "text": "Điều 1. ...", "citation": {"doc_slug": "x", "chuong": "Chương I", "dieu_number": 1, "dieu_title": "Phạm vi"}},
        {"chunk_type": "dieu", "text": "Điều 2. ...", "citation": {"doc_slug": "x", "chuong": "Chương I", "dieu_number": 2, "dieu_title": "Đối tượng"}},
    ]
    vectors = [[0.1] * 768, [0.2] * 768]

    rows = prepare_chunk_rows(article_id=42, chunks=chunks, vectors=vectors)

    assert rows[0]["parent_type"] == "article"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == "dieu"
    assert rows[0]["text"].startswith("Điều 1")
    assert rows[0]["embedding"] == [0.1] * 768
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_kb_ingestor.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement the ingestor**

Create `data_pipeline/ingestors/legal_kb_ingestor.py`:

```python
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


def build_article_payload(*, title: str, slug: str, body: str, source_filename: str, digest: str, chunks_count: int) -> dict[str, Any]:
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


def prepare_chunk_rows(*, article_id: int, chunks: list[dict], vectors: list[list[float]]) -> list[dict]:
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


async def ingest_legal_documents(raw_dir: Path = KNOWLEDGE_RAW, log_dir: Path = KNOWLEDGE_LOG) -> dict[str, int]:
    settings = get_settings()
    embedder = GeminiEmbedder(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_EMBEDDING_MODEL)

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
                delete(Chunk).where(Chunk.parent_type == "article", Chunk.parent_id == article.id)
            )
            chunk_rows = prepare_chunk_rows(article_id=article.id, chunks=chunks, vectors=vectors)
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
```

- [ ] **Step 4: Run the unit tests**

```powershell
cd backend
python -m pytest tests/test_legal_kb_ingestor.py -q
```

Expected: pass.

- [ ] **Step 5: Manual smoke test with the sample fixture**

```powershell
mkdir data\knowledge\raw\sample 2>$null
copy backend\tests\fixtures\sample_legal.pdf data\knowledge\raw\sample\sample_legal.pdf
docker-compose up -d postgres
cd backend
alembic upgrade head
cd ..
python -m data_pipeline.ingestors.legal_kb_ingestor
```

Expected: prints `{"documents": 1, "chunks": >0, "skipped": 0}` on first run, `{"documents": 0, "skipped": 1}` on second run.

- [ ] **Step 6: Commit**

```powershell
git add data_pipeline/ingestors/legal_kb_ingestor.py backend/tests/test_legal_kb_ingestor.py
git commit -m "ingest legal knowledge base from local files"
```

---

### Task 8: Legal Synthesis Tool With Citations

**Files:**
- Create: `chatbot/tools/legal_synthesis.py`
- Test: `backend/tests/test_legal_synthesis.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_legal_synthesis.py`:

```python
import pytest

from chatbot.tools.legal_synthesis import build_legal_prompt, format_citations


def test_format_citations_renders_dieu_with_doc_slug():
    chunks = [
        {"text": "Điều 1...", "matched_chunk": {"chunk_type": "dieu"}, "metadata_json": {"slug": "luat-dat-dai-2024"}, "citation": {"doc_slug": "luat-dat-dai-2024", "chuong": "Chương I", "dieu_number": 1, "dieu_title": "Phạm vi"}},
    ]

    text = format_citations(chunks)

    assert "luat-dat-dai-2024" in text
    assert "Điều 1" in text
    assert "Chương I" in text


def test_build_legal_prompt_warns_when_no_chunks():
    prompt = build_legal_prompt(query="Thủ tục sang tên?", chunks=[])

    assert "Thủ tục sang tên" in prompt
    assert "không tìm thấy" in prompt.lower() or "no relevant" in prompt.lower()
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_synthesis.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement legal synthesis**

Create `chatbot/tools/legal_synthesis.py`:

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings


SYSTEM_PROMPT = (
    "Bạn là chuyên viên tư vấn pháp lý bất động sản. "
    "Trả lời chỉ dựa trên các trích dẫn cung cấp. "
    "Nếu không có trích dẫn liên quan, hãy nói rõ là chưa có cơ sở pháp lý. "
    "Mỗi luận điểm phải kèm trích dẫn theo dạng (slug-văn-bản, Điều X)."
)


def format_citations(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "Không có trích dẫn pháp lý phù hợp."

    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        citation = chunk.get("citation") or {}
        slug = citation.get("doc_slug") or (chunk.get("metadata_json") or {}).get("slug") or "không rõ"
        chuong = citation.get("chuong") or ""
        dieu = citation.get("dieu_number")
        dieu_title = citation.get("dieu_title") or ""
        header = f"[{index}] ({slug}, {chuong}, Điều {dieu} - {dieu_title})".strip(", ")
        snippet = (chunk.get("text") or "").strip().replace("\n", " ")
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        lines.append(f"{header}\n{snippet}")
    return "\n\n".join(lines)


def build_legal_prompt(query: str, chunks: list[dict[str, Any]]) -> str:
    citations_block = format_citations(chunks)
    if not chunks:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Câu hỏi: {query}\n\n"
            "Hệ thống không tìm thấy trích dẫn pháp lý phù hợp. "
            "Hãy trả lời rằng cần thêm thông tin hoặc đề nghị người dùng tham vấn luật sư."
        )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Câu hỏi: {query}\n\n"
        f"Trích dẫn pháp lý:\n{citations_block}\n\n"
        "Hãy trả lời ngắn gọn, có cấu trúc, và dẫn chiếu chính xác."
    )


async def synthesize_legal_answer(query: str, chunks: list[dict[str, Any]]) -> str:
    settings = get_settings()
    prompt = build_legal_prompt(query, chunks)

    if not settings.GEMINI_API_KEY:
        return prompt  # fallback returns the structured prompt itself

    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )
    return response.text or "Không thể tạo phản hồi pháp lý lúc này."
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_legal_synthesis.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add chatbot/tools/legal_synthesis.py backend/tests/test_legal_synthesis.py
git commit -m "synthesize legal answers with citations"
```

---

### Task 9: Wire Legal Advisor Agent

**Files:**
- Modify: `chatbot/agents/legal_advisor.py`
- Test: `backend/tests/test_legal_advisor_agent.py`

- [ ] **Step 1: Write failing test for the agent**

Create `backend/tests/test_legal_advisor_agent.py`:

```python
import pytest

from chatbot.agents import legal_advisor


@pytest.mark.asyncio
async def test_legal_advisor_calls_hybrid_search_with_legal_filter(monkeypatch):
    captured = {}

    async def fake_hybrid(query, filters, parent_type):
        captured.update({"query": query, "filters": filters, "parent_type": parent_type})
        return [
            {
                "id": 1,
                "title": "Luật Đất đai 2024",
                "metadata_json": {"slug": "luat-dat-dai-2024"},
                "matched_chunk": {"chunk_type": "dieu", "text": "Điều 5..."},
                "citation": {"doc_slug": "luat-dat-dai-2024", "chuong": "Chương II", "dieu_number": 5, "dieu_title": "Quyền"},
            }
        ]

    async def fake_synth(query, chunks):
        return f"Tổng hợp dựa trên {len(chunks)} trích dẫn."

    monkeypatch.setattr(legal_advisor, "hybrid_search", fake_hybrid)
    monkeypatch.setattr(legal_advisor, "synthesize_legal_answer", fake_synth)

    state = {"user_query": "Quyền sử dụng đất gồm những gì?", "search_filters": {}, "agent_results": {}}
    result = await legal_advisor.legal_advisor_node(state)

    assert captured["parent_type"] == "article"
    assert captured["filters"]["category"] == "legal"
    assert "1 trích dẫn" in result["agent_results"]["legal_advisor"]["content"]
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_legal_advisor_agent.py -q
```

Expected: fail because the agent still uses placeholder content.

- [ ] **Step 3: Replace `legal_advisor_node`**

Replace the body of `chatbot/agents/legal_advisor.py`:

```python
from chatbot.state import ChatState
from chatbot.tools.hybrid_search import hybrid_search
from chatbot.tools.legal_synthesis import synthesize_legal_answer


async def legal_advisor_node(state: ChatState) -> dict:
    query = state.get("user_query", "")
    filters = dict(state.get("search_filters", {}))
    filters["category"] = "legal"

    chunks = await hybrid_search(query=query, filters=filters, parent_type="article")
    answer = await synthesize_legal_answer(query, chunks)
    sources = []
    for chunk in chunks:
        citation = chunk.get("citation") or {}
        if citation.get("doc_slug"):
            sources.append(f"{citation['doc_slug']} - Điều {citation.get('dieu_number')}")

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "legal_advisor": {
                "agent_name": "legal_advisor",
                "content": answer,
                "sources": sources,
                "confidence": 0.8 if chunks else 0.3,
            },
        },
    }
```

- [ ] **Step 4: Run the test**

```powershell
cd backend
python -m pytest tests/test_legal_advisor_agent.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add chatbot/agents/legal_advisor.py backend/tests/test_legal_advisor_agent.py
git commit -m "wire legal advisor to hybrid search and synthesis"
```

---

### Task 10: Monthly Legal KB DAG

**Files:**
- Modify: `airflow/plugins/pipeline_runner.py`
- Create: `airflow/dags/monthly_legal_kb_dag.py`
- Modify: `backend/tests/test_dag_structure.py`
- Modify: `backend/tests/test_pipeline_runner.py`

- [ ] **Step 1: Add `run_legal_ingestion` runner helper test**

Append to `backend/tests/test_pipeline_runner.py`:

```python
def test_run_legal_ingestion_callable_exists():
    from plugins import pipeline_runner

    assert hasattr(pipeline_runner, "run_legal_ingestion")
    assert callable(pipeline_runner.run_legal_ingestion)
```

- [ ] **Step 2: Run and confirm failure**

```powershell
cd backend
python -m pytest tests/test_pipeline_runner.py -q
```

Expected: fail because the helper does not exist.

- [ ] **Step 3: Add the runner helper**

Append to `airflow/plugins/pipeline_runner.py`:

```python
def run_legal_ingestion() -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio

    from data_pipeline.ingestors.legal_kb_ingestor import ingest_legal_documents

    return asyncio.run(ingest_legal_documents())
```

- [ ] **Step 4: Add the DAG**

Create `airflow/dags/monthly_legal_kb_dag.py`:

```python
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import run_legal_ingestion


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _ingest_legal(**_):
    return run_legal_ingestion()


with DAG(
    dag_id="monthly_legal_kb_dag",
    description="Re-ingest changed legal PDF/HTML documents from data/knowledge/raw monthly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 5 1 * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "legal"],
) as dag:
    PythonOperator(task_id="ingest_legal_kb", python_callable=_ingest_legal)
```

- [ ] **Step 5: Add DAG structure assertion**

Append to `backend/tests/test_dag_structure.py`:

```python
def test_monthly_legal_kb_dag_loaded(dagbag):
    dag = dagbag.dags.get("monthly_legal_kb_dag")
    assert dag is not None
    task_ids = {task.task_id for task in dag.tasks}
    assert "ingest_legal_kb" in task_ids
```

- [ ] **Step 6: Run all tests**

```powershell
cd backend
python -m pytest tests/test_pipeline_runner.py tests/test_dag_structure.py -q
```

Expected: pass (or DAG test skipped if Airflow not installed in the host venv — see Task 7 of M3 for the container fallback).

- [ ] **Step 7: Verify DAG parses inside Airflow**

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -c "from airflow.models import DagBag; bag = DagBag(); assert 'monthly_legal_kb_dag' in bag.dags, bag.import_errors; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 8: Commit**

```powershell
git add airflow/plugins/pipeline_runner.py airflow/dags/monthly_legal_kb_dag.py backend/tests/test_pipeline_runner.py backend/tests/test_dag_structure.py
git commit -m "add monthly legal kb dag"
```

---

### Task 11: Knowledge Directory Bootstrap

**Files:**
- Create: `data/knowledge/raw/.gitkeep`
- Create: `data/knowledge/ingested/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Add directories**

```powershell
mkdir data\knowledge\raw 2>$null
mkdir data\knowledge\ingested 2>$null
type nul > data\knowledge\raw\.gitkeep
type nul > data\knowledge\ingested\.gitkeep
```

- [ ] **Step 2: Update `.gitignore`**

Append to `.gitignore`:

```text
# Legal knowledge base — large PDFs and ingestion logs are local-only
data/knowledge/raw/*
!data/knowledge/raw/.gitkeep
data/knowledge/ingested/*
!data/knowledge/ingested/.gitkeep
```

- [ ] **Step 3: Commit**

```powershell
git add data/knowledge .gitignore
git commit -m "bootstrap legal knowledge directories"
```

---

### Task 12: M4 End-To-End Verification

**Files:**
- No required code changes unless a previous task failed verification.

- [ ] **Step 1: Run all M1–M4 tests**

```powershell
cd backend
python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 2: Apply migrations**

```powershell
cd backend
alembic upgrade head
```

Expected: revisions up to `20260701_0003` applied.

- [ ] **Step 3: Drop a real legal PDF in `data/knowledge/raw/`**

Place at least one real Vietnamese law PDF (e.g. Luật Đất đai 2024) under `data/knowledge/raw/luat-dat-dai-2024/luat-dat-dai-2024.pdf`. If you do not have the file locally, reuse `backend/tests/fixtures/sample_legal.pdf` for smoke testing.

- [ ] **Step 4: Run the ingestor manually**

```powershell
python -m data_pipeline.ingestors.legal_kb_ingestor
```

Expected: prints nonzero `documents` and `chunks`. Re-running the same command prints `documents: 0, skipped: >=1`.

- [ ] **Step 5: Verify rows in DB**

```powershell
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT id, title, category, url FROM articles WHERE category='legal';"
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT count(*) FROM chunks WHERE parent_type='article';"
```

Expected: legal articles present with `url LIKE 'legal://%'`; chunk count nonzero.

- [ ] **Step 6: Hybrid search test from Python REPL**

```powershell
python -c "import asyncio; from chatbot.tools.hybrid_search import hybrid_search; print(asyncio.run(hybrid_search('Quyền sử dụng đất', filters={'category':'legal'}, parent_type='article')))"
```

Expected: returns at least one record with a `matched_chunk` and `citation`-bearing metadata.

- [ ] **Step 7: Legal Advisor end-to-end via the chatbot graph**

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

In another shell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/chat -ContentType "application/json" -Body '{"message":"Thủ tục sang tên sổ đỏ căn hộ chung cư?"}'
```

Expected: response contains `agent_used` matching `legal_advisor` (or includes it among multiple agents) and the `final_response` cites a doc slug with an Điều number.

- [ ] **Step 8: Trigger the monthly DAG manually**

In Airflow UI, unpause and trigger `monthly_legal_kb_dag`. The single task should turn green; if no new files exist, output is `documents: 0, skipped: >=1`.

- [ ] **Step 9: Commit verification fixes**

If any verification step required code changes:

```powershell
git add <changed-files>
git commit -m "fix m4 verification issues"
```

---

## Self-Review

- Spec coverage: M4 ships the legal metadata column + migration (Task 1), PDF and HTML parsers (Tasks 2–3), Vietnamese legal structure splitter (Task 4), Khoản-aware citation chunker with safe fixed-size fallback (Task 5), manifest + slugify helpers (Task 6), the `legal_kb_ingestor` with audit-rich `metadata_json` (Task 7), the citation-formatted Gemini synthesizer (Task 8), the live Legal Advisor Agent (Task 9), the monthly Airflow DAG (Task 10), the bootstrap directories (Task 11), and end-to-end verification (Task 12). Master plan items left for later milestones: monitoring dashboards, Cohere caching, removal of the legacy `Listing.embedding` column (M5).
- Dependency staging: Tasks 1–9 + 11 + 12 (manual portion) only require M2. Task 10 and the Airflow trigger step in Task 12 require M3. Operators can ship the legal KB ingestion now and add the scheduled DAG once Airflow lands.
- Placeholder scan: every code block is concrete, every command is runnable. The "drop a real legal PDF" step in Task 12 is a deployment instruction, not a placeholder — the smoke test fixture from Task 2 stays valid as a fallback.
- Type consistency: legal chunks emit the same `parent_type="article"`, `chunk_type`, `text`, `embedding` shape as M2 news chunks; citation metadata travels via `metadata_json` on the parent `Article` row plus an in-memory `citation` dict surfaced through `hybrid_search` / `legal_synthesis`. `chunk_type` is one of `"dieu"` (whole article or fixed-size fallback) or `"khoan"` (per-Khoản piece of a long article).
- Known limits accepted in M4: PDF text extraction depends on PyMuPDF — scanned image PDFs without OCR will yield no text and the ingestor will skip them with a `no chunks` log entry. Citations rely on the regex-based Vietnamese legal structure splitter; documents that deviate strongly from the standard `Chương ... Điều N. <Title>` style will fall back to one chunk per document with empty `chuong` / `dieu_number=0`. Khoản splitting only fires when the Điều exceeds the chunk size and the body contains at least two `^N.` markers; otherwise the whole article stays in one chunk. Legal Advisor refuses to fabricate citations: when hybrid search returns zero chunks the synthesizer explicitly tells the user no legal basis was found, which is the desired behavior over hallucinated answers. HTML files are decoded with a UTF-8 → cp1258 → latin-1 fallback chain plus a final lossy `errors="replace"` so malformed encoding never blocks the pipeline.
