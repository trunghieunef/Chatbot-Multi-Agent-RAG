# Article and Project Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist crawler image URLs for articles/projects and render them through public APIs and frontend pages.

**Architecture:** Add separate image tables and SQLAlchemy models mirroring `listing_images`, then wire ingestors to replace image rows during parent upserts. API response helpers batch-load ordered images and expose `primary_image_url` plus `image_urls`; frontend list/detail pages use those fields with stable placeholders when absent.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest, Next.js App Router, React client components, TypeScript, Tailwind CSS.

---

## File Structure

- Create `backend/app/models/article_image.py`: image model for article media.
- Create `backend/app/models/project_image.py`: image model for project media.
- Modify `backend/app/models/__init__.py`: export new models.
- Create `backend/alembic/versions/20260801_0010_article_project_images.py`: migration for both image tables.
- Modify `backend/app/schemas/article.py`: add image fields.
- Modify `backend/app/schemas/project.py`: add image fields.
- Modify `backend/app/routers/articles.py`: response helper and batch image map.
- Modify `backend/app/routers/projects.py`: response helper and batch image map.
- Modify `data_pipeline/ingestors/news_ingestor.py`: parse and persist article images.
- Modify `data_pipeline/ingestors/projects_ingestor.py`: parse and persist project images.
- Modify `backend/tests/test_articles_api.py`: response helper image assertions.
- Modify `backend/tests/test_projects_api.py`: response helper image assertions.
- Modify `backend/tests/test_news_ingestor.py`: parser and article image row tests.
- Modify `backend/tests/test_projects_ingestor.py`: parser and project image row tests.
- Modify `frontend/lib/types.ts`: image fields on `ArticleCard` and `ProjectCard`.
- Modify `frontend/app/tin-tuc/page.tsx`: card/featured media uses images.
- Modify `frontend/app/tin-tuc/[id]/page.tsx`: article hero/gallery uses images.
- Modify `frontend/app/du-an/page.tsx`: project cards use images.
- Modify `frontend/app/du-an/[id]/page.tsx`: project hero/gallery uses images.
- Modify `frontend/tests/content-detail-pages.test.mjs`: static image field usage checks.

---

### Task 1: Backend Image Models and Migration

**Files:**
- Create: `backend/app/models/article_image.py`
- Create: `backend/app/models/project_image.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260801_0010_article_project_images.py`

- [ ] **Step 1: Add model import test expectations**

Add these imports to `backend/tests/test_article_metadata.py`:

```python
from app.models import ArticleImage, ProjectImage


def test_article_project_image_models_are_exported():
    assert ArticleImage.__tablename__ == "article_images"
    assert ProjectImage.__tablename__ == "project_images"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest backend\tests\test_article_metadata.py -q
```

Expected: fail because `ArticleImage` and `ProjectImage` are not exported yet.

- [ ] **Step 3: Create `ArticleImage` model**

Create `backend/app/models/article_image.py`:

```python
"""SQLAlchemy ORM model for article image URLs."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Text, String, func

from app.database import Base


class ArticleImage(Base):
    """An image URL associated with an article."""

    __tablename__ = "article_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    article_url = Column(Text, nullable=True, index=True)
    image_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(80), nullable=False, default="batdongsan")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_article_images_article_order", "article_id", "sort_order"),
        Index("ix_article_images_url_order", "article_url", "sort_order"),
    )
```

- [ ] **Step 4: Create `ProjectImage` model**

Create `backend/app/models/project_image.py`:

```python
"""SQLAlchemy ORM model for project image URLs."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from app.database import Base


class ProjectImage(Base):
    """An image URL associated with a project."""

    __tablename__ = "project_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_slug = Column(String(255), nullable=True, index=True)
    image_url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)
    source = Column(String(80), nullable=False, default="batdongsan")
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_project_images_project_order", "project_id", "sort_order"),
        Index("ix_project_images_slug_order", "project_slug", "sort_order"),
    )
```

- [ ] **Step 5: Export models**

Modify `backend/app/models/__init__.py`:

```python
from app.models.article_image import ArticleImage
from app.models.project_image import ProjectImage
```

Add `"ArticleImage"` and `"ProjectImage"` to `__all__`.

- [ ] **Step 6: Add Alembic migration**

Create `backend/alembic/versions/20260801_0010_article_project_images.py`:

```python
"""add article and project image urls tables

Revision ID: 20260801_0010
Revises: 20260801_0009
Create Date: 2026-08-01 00:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0010"
down_revision: Union[str, None] = "20260801_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("article_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_images_article_id"), "article_images", ["article_id"], unique=False)
    op.create_index(op.f("ix_article_images_article_url"), "article_images", ["article_url"], unique=False)
    op.create_index("ix_article_images_article_order", "article_images", ["article_id", "sort_order"], unique=False)
    op.create_index("ix_article_images_url_order", "article_images", ["article_url", "sort_order"], unique=False)

    op.create_table(
        "project_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_slug", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_images_project_id"), "project_images", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_images_project_slug"), "project_images", ["project_slug"], unique=False)
    op.create_index("ix_project_images_project_order", "project_images", ["project_id", "sort_order"], unique=False)
    op.create_index("ix_project_images_slug_order", "project_images", ["project_slug", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_images_slug_order", table_name="project_images")
    op.drop_index("ix_project_images_project_order", table_name="project_images")
    op.drop_index(op.f("ix_project_images_project_slug"), table_name="project_images")
    op.drop_index(op.f("ix_project_images_project_id"), table_name="project_images")
    op.drop_table("project_images")
    op.drop_index("ix_article_images_url_order", table_name="article_images")
    op.drop_index("ix_article_images_article_order", table_name="article_images")
    op.drop_index(op.f("ix_article_images_article_url"), table_name="article_images")
    op.drop_index(op.f("ix_article_images_article_id"), table_name="article_images")
    op.drop_table("article_images")
```

- [ ] **Step 7: Run model test**

Run:

```powershell
pytest backend\tests\test_article_metadata.py -q
```

Expected: pass.

---

### Task 2: Ingest Article and Project Images

**Files:**
- Modify: `data_pipeline/ingestors/news_ingestor.py`
- Modify: `data_pipeline/ingestors/projects_ingestor.py`
- Modify: `backend/tests/test_news_ingestor.py`
- Modify: `backend/tests/test_projects_ingestor.py`

- [ ] **Step 1: Add parser tests**

Add to `backend/tests/test_news_ingestor.py`:

```python
from data_pipeline.ingestors.news_ingestor import (
    article_image_urls_from_row,
    prepare_article_image_rows,
)


class ArticleImageStub:
    id = 11
    url = "https://example.test/article"


def test_article_image_urls_from_row_accepts_json_and_dedupes():
    row = {
        "image_urls": '["https://cdn.example.test/a.jpg", "https://cdn.example.test/a.jpg", "ftp://bad.test/a.jpg", "https://cdn.example.test/b.jpg"]'
    }

    assert article_image_urls_from_row(row) == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.jpg",
    ]


def test_prepare_article_image_rows_marks_first_image_primary():
    rows = prepare_article_image_rows(
        ArticleImageStub(),
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert rows[0]["article_id"] == 11
    assert rows[0]["article_url"] == "https://example.test/article"
    assert rows[0]["sort_order"] == 0
    assert rows[0]["is_primary"] is True
    assert rows[1]["is_primary"] is False
```

Add to `backend/tests/test_projects_ingestor.py`:

```python
from data_pipeline.ingestors.projects_ingestor import (
    prepare_project_image_rows,
    project_image_urls_from_row,
)


class ProjectImageStub:
    id = 22
    slug = "sun-festo-town"


def test_project_image_urls_from_row_accepts_json_and_dedupes():
    row = {
        "image_urls": '["https://cdn.example.test/p1.jpg", "https://cdn.example.test/p1.jpg", "data:image/png;base64,abc", "https://cdn.example.test/p2.jpg"]'
    }

    assert project_image_urls_from_row(row) == [
        "https://cdn.example.test/p1.jpg",
        "https://cdn.example.test/p2.jpg",
    ]


def test_prepare_project_image_rows_marks_first_image_primary():
    rows = prepare_project_image_rows(
        ProjectImageStub(),
        ["https://cdn.example.test/p1.jpg", "https://cdn.example.test/p2.jpg"],
    )

    assert rows[0]["project_id"] == 22
    assert rows[0]["project_slug"] == "sun-festo-town"
    assert rows[0]["sort_order"] == 0
    assert rows[0]["is_primary"] is True
    assert rows[1]["is_primary"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
pytest backend\tests\test_news_ingestor.py backend\tests\test_projects_ingestor.py -q
```

Expected: fail because parser/preparation functions do not exist.

- [ ] **Step 3: Implement article image ingestion helpers**

In `data_pipeline/ingestors/news_ingestor.py`:

```python
import json
```

Import `ArticleImage`:

```python
from app.models import Article, ArticleImage, Chunk
```

Add:

```python
ARTICLE_IMAGE_META_KEY = "_image_urls"


def article_image_urls_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("image_urls") or ""
    if not raw:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            values = [part.strip() for part in text.replace("\n", ",").split(",")]

    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = str(value).strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def prepare_article_image_rows(article: Article, image_urls: list[str], *, source: str = "batdongsan") -> list[dict[str, Any]]:
    return [
        {
            "article_id": article.id,
            "article_url": article.url,
            "image_url": image_url,
            "sort_order": index,
            "is_primary": index == 0,
            "source": source,
        }
        for index, image_url in enumerate(image_urls)
    ]


async def replace_article_images(session, article: Article, image_urls: list[str]) -> None:
    await session.execute(delete(ArticleImage).where(ArticleImage.article_id == article.id))
    if image_urls:
        session.add_all(
            ArticleImage(**image_row)
            for image_row in prepare_article_image_rows(article, image_urls)
        )
```

Update `publish_article_batch`:

```python
for article_data in articles_data:
    image_urls = list(article_data.get(ARTICLE_IMAGE_META_KEY) or [])
    article = await upsert_article(session, article_data)
    await replace_article_images(session, article, image_urls)
    persisted.append(article)
```

Update prepared rows:

```python
article_data[ARTICLE_IMAGE_META_KEY] = article_image_urls_from_row(row)
```

- [ ] **Step 4: Implement project image ingestion helpers**

In `data_pipeline/ingestors/projects_ingestor.py`:

```python
import json
```

Import `ProjectImage`:

```python
from app.models import Chunk, Project, ProjectImage
```

Add `PROJECT_IMAGE_META_KEY`, `project_image_urls_from_row`, `prepare_project_image_rows`, and `replace_project_images` mirroring article helpers but using `project_id` and `project_slug`.

Update `publish_project_batch` to pop image URLs before public model data:

```python
for project_data in projects_data:
    image_urls = list(project_data.get(PROJECT_IMAGE_META_KEY) or [])
    project = await upsert_project(session, public_project_data(project_data))
    await replace_project_images(session, project, image_urls)
    persisted.append(project)
```

Update prepared rows:

```python
project_data[PROJECT_IMAGE_META_KEY] = project_image_urls_from_row(row)
```

- [ ] **Step 5: Run ingestor tests**

Run:

```powershell
pytest backend\tests\test_news_ingestor.py backend\tests\test_projects_ingestor.py -q
```

Expected: pass.

---

### Task 3: API Schemas and Image Response Helpers

**Files:**
- Modify: `backend/app/schemas/article.py`
- Modify: `backend/app/schemas/project.py`
- Modify: `backend/app/routers/articles.py`
- Modify: `backend/app/routers/projects.py`
- Modify: `backend/tests/test_articles_api.py`
- Modify: `backend/tests/test_projects_api.py`

- [ ] **Step 1: Add response helper tests**

Update `backend/tests/test_articles_api.py`:

```python
def test_article_card_response_includes_primary_image_url():
    response = article_card_response(
        ArticleStub(),
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert response.primary_image_url == "https://cdn.example.test/a.jpg"
    assert response.image_urls == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.jpg",
    ]
```

Update `backend/tests/test_projects_api.py`:

```python
from app.routers.projects import project_card_response
```

```python
def test_project_card_response_includes_primary_image_url():
    response = project_card_response(
        ProjectStub(),
        ["https://cdn.example.test/p1.jpg", "https://cdn.example.test/p2.jpg"],
    )

    assert response.primary_image_url == "https://cdn.example.test/p1.jpg"
    assert response.image_urls == [
        "https://cdn.example.test/p1.jpg",
        "https://cdn.example.test/p2.jpg",
    ]
```

- [ ] **Step 2: Run API tests and confirm failure**

Run:

```powershell
pytest backend\tests\test_articles_api.py backend\tests\test_projects_api.py -q
```

Expected: fail because schema fields/helper signatures are not implemented.

- [ ] **Step 3: Add schema fields**

In both `backend/app/schemas/article.py` and `backend/app/schemas/project.py`, import `Field` and add:

```python
primary_image_url: str | None = None
image_urls: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add article image map**

In `backend/app/routers/articles.py`, import `ArticleImage` and update helper:

```python
def article_card_response(article: Article, image_urls: list[str] | None = None) -> ArticleCardResponse:
    response = ArticleCardResponse.model_validate(article)
    urls = image_urls or []
    response.summary = _summary(response.body)
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response
```

Add:

```python
async def _article_image_map(db: AsyncSession, article_ids: list[int]) -> dict[int, list[str]]:
    if not article_ids:
        return {}
    result = await db.execute(
        select(ArticleImage)
        .where(ArticleImage.article_id.in_(article_ids))
        .order_by(ArticleImage.article_id, ArticleImage.sort_order, ArticleImage.id)
    )
    images_by_article: dict[int, list[str]] = {article_id: [] for article_id in article_ids}
    for image in result.scalars().all():
        images_by_article.setdefault(image.article_id, []).append(image.image_url)
    return images_by_article
```

Use it in list/detail responses.

- [ ] **Step 5: Add project image map**

In `backend/app/routers/projects.py`, import `ProjectImage`, add:

```python
def project_card_response(project: Project, image_urls: list[str] | None = None) -> ProjectCardResponse:
    response = ProjectCardResponse.model_validate(project)
    urls = image_urls or []
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response
```

Add `_project_image_map` mirroring `_article_image_map`. Use it in list/detail responses.

- [ ] **Step 6: Run focused backend tests**

Run:

```powershell
pytest backend\tests\test_article_metadata.py backend\tests\test_news_ingestor.py backend\tests\test_projects_ingestor.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py backend\tests\test_public_content_routes.py -q
```

Expected: pass.

- [ ] **Step 7: Commit backend changes**

Run:

```powershell
git add backend\app\models backend\app\schemas backend\app\routers backend\alembic\versions\20260801_0010_article_project_images.py backend\tests\test_article_metadata.py backend\tests\test_news_ingestor.py backend\tests\test_projects_ingestor.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py data_pipeline\ingestors\news_ingestor.py data_pipeline\ingestors\projects_ingestor.py
git commit -m "add article and project image APIs"
```

---

### Task 4: Frontend Image Rendering

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/tin-tuc/page.tsx`
- Modify: `frontend/app/tin-tuc/[id]/page.tsx`
- Modify: `frontend/app/du-an/page.tsx`
- Modify: `frontend/app/du-an/[id]/page.tsx`
- Modify: `frontend/tests/content-detail-pages.test.mjs`

- [ ] **Step 1: Add static test expectations**

Append to `frontend/tests/content-detail-pages.test.mjs`:

```javascript
test("content pages render article and project images when present", () => {
  const types = read("lib/types.ts");
  const news = read("app/tin-tuc/page.tsx");
  const article = read("app/tin-tuc/[id]/page.tsx");
  const projects = read("app/du-an/page.tsx");
  const project = read("app/du-an/[id]/page.tsx");

  assert.match(types, /primary_image_url/);
  assert.match(types, /image_urls/);
  assert.match(news, /primary_image_url/);
  assert.match(article, /image_urls/);
  assert.match(projects, /primary_image_url/);
  assert.match(project, /image_urls/);
});
```

- [ ] **Step 2: Run static test and confirm failure**

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
```

Expected: fail because frontend pages/types do not reference image fields yet.

- [ ] **Step 3: Add TypeScript image fields**

Add to `ArticleCard` and `ProjectCard` in `frontend/lib/types.ts`:

```ts
primary_image_url: string | null;
image_urls: string[];
```

- [ ] **Step 4: Render news landing images**

In `frontend/app/tin-tuc/page.tsx`, update fallback articles with:

```ts
primary_image_url: null,
image_urls: [],
```

In `ArticleCardItem`, render a fixed-height media area before text:

```tsx
<div className="mb-3 flex h-36 items-center justify-center overflow-hidden rounded-md bg-muted">
  {article.primary_image_url ? (
    <img src={article.primary_image_url} alt={article.title} className="h-full w-full object-cover" />
  ) : (
    <Newspaper size={32} className="text-primary/50" />
  )}
</div>
```

In the featured article media panel, use `featured.primary_image_url` when present.

- [ ] **Step 5: Render article detail gallery**

In `frontend/app/tin-tuc/[id]/page.tsx`, derive:

```ts
const imageUrls = article?.image_urls || [];
```

Render a hero media block above the summary:

```tsx
<div className="mb-6 flex h-72 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
  {article.primary_image_url ? (
    <img src={article.primary_image_url} alt={article.title} className="h-full w-full object-cover" />
  ) : (
    <Newspaper size={48} className="text-primary/50" />
  )}
</div>
```

If `imageUrls.length > 1`, render thumbnails below.

- [ ] **Step 6: Render project landing images**

In `frontend/app/du-an/page.tsx`, update fallback projects with image fields and render a fixed-height media area in `ProjectCardItem` using `project.primary_image_url`.

- [ ] **Step 7: Render project detail gallery**

In `frontend/app/du-an/[id]/page.tsx`, add selected image state:

```ts
const [selectedImageIndex, setSelectedImageIndex] = useState(0);
const imageUrls = project?.image_urls || [];
const selectedImageUrl = imageUrls[selectedImageIndex] || project?.primary_image_url;
```

Reset selected image after project changes:

```ts
setSelectedImageIndex(0);
```

Use `selectedImageUrl` in the hero. Render thumbnail buttons when `imageUrls.length > 1`.

- [ ] **Step 8: Run frontend verification**

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
npm.cmd run lint
npm.cmd run build
```

Expected: static test passes, lint exits 0 with only any pre-existing `<img>` warnings, build exits 0.

- [ ] **Step 9: Commit frontend changes**

Run:

```powershell
git add frontend\lib\types.ts frontend\app\tin-tuc\page.tsx frontend\app\tin-tuc\[id]\page.tsx frontend\app\du-an\page.tsx frontend\app\du-an\[id]\page.tsx frontend\tests\content-detail-pages.test.mjs
git commit -m "render article and project images"
```

---

### Task 5: Final Verification

**Files:**
- No code edits expected.

- [ ] **Step 1: Check git status**

Run:

```powershell
git status --short
```

Expected: only unrelated `report/main.log` and `report/main.pdf` remain modified, unless the user changed other files during implementation.

- [ ] **Step 2: Re-run backend verification**

Run:

```powershell
pytest backend\tests\test_article_metadata.py backend\tests\test_news_ingestor.py backend\tests\test_projects_ingestor.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py backend\tests\test_public_content_routes.py -q
```

Expected: pass.

- [ ] **Step 3: Re-run frontend verification**

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
npm.cmd run lint
npm.cmd run build
```

Expected: pass, with any unrelated pre-existing lint warnings reported clearly.

- [ ] **Step 4: Summarize Docker note**

Tell the user that because this includes a new migration and backend/frontend code, they should rebuild:

```powershell
docker compose up -d --build backend frontend
```

If their DB container already exists, apply migrations before running ingestion:

```powershell
docker compose exec backend alembic upgrade head
```
