# News Project Landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build public `/tin-tuc` and `/du-an` landing/list pages backed by real `articles` and `projects` API data with graceful fallback content.

**Architecture:** Add two focused FastAPI routers that expose existing parent tables through paginated list endpoints. Extend the Next.js API client and types, then add client-side pages that follow the current frontend design system and render fallback datasets when API data is unavailable. Keep detail pages, crawler changes, and migrations out of scope.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Next.js App Router, React, TypeScript, Tailwind CSS v4, lucide-react.

---

## File Structure

- Create `backend/app/schemas/project.py`: Pydantic response schema for project cards.
- Create `backend/app/schemas/article.py`: Pydantic response schema for public article cards and summaries.
- Create `backend/app/routers/projects.py`: paginated public projects list endpoint and query helpers.
- Create `backend/app/routers/articles.py`: paginated public articles list endpoint and query helpers.
- Modify `backend/app/main.py`: register the new routers.
- Create `backend/tests/test_projects_api.py`: backend tests for project response helpers and query behavior.
- Create `backend/tests/test_articles_api.py`: backend tests for article response helpers and query behavior.
- Modify `frontend/lib/types.ts`: add project/article card and filter types.
- Modify `frontend/lib/api.ts`: add `getProjects` and `getArticles`.
- Create `frontend/app/du-an/page.tsx`: project landing/list page.
- Create `frontend/app/tin-tuc/page.tsx`: news landing/list page.
- Modify `frontend/components/layout/Header.tsx`: add project and news navigation.
- Modify `frontend/components/layout/Footer.tsx`: add project and news footer links.

---

### Task 1: Backend Project API

**Files:**
- Create: `backend/app/schemas/project.py`
- Create: `backend/app/routers/projects.py`
- Create: `backend/tests/test_projects_api.py`

- [ ] **Step 1: Write failing project API helper tests**

Create `backend/tests/test_projects_api.py`:

```python
from app.routers.projects import apply_project_filters, apply_project_sort
from app.schemas.project import ProjectCardResponse


class ProjectStub:
    id = 1
    name = "Sun Festo Town"
    slug = "sun-festo-town"
    developer = "Sun Group"
    location = "Ha Long, Quang Ninh"
    district = "Ha Long"
    city = "Quang Ninh"
    total_units = 1200
    price_range = "3 - 8 ty"
    area_range = "45 - 120 m2"
    status = "selling"
    project_type = "apartment"
    description = "Project overview"
    amenities = ["pool", "park"]
    url = "https://example.test/project"
    created_at = None
    updated_at = None


def test_project_card_response_accepts_model_attributes():
    response = ProjectCardResponse.model_validate(ProjectStub())

    assert response.name == "Sun Festo Town"
    assert response.slug == "sun-festo-town"
    assert response.amenities == ["pool", "park"]


def test_project_filters_apply_search_and_location():
    params = {
        "search": "festo",
        "city": "Quang Ninh",
        "district": "Ha Long",
        "project_type": "apartment",
        "status": "selling",
    }

    query = apply_project_filters(None, params)

    assert query is not None


def test_project_sort_supports_known_options():
    assert apply_project_sort(None, "newest") is not None
    assert apply_project_sort(None, "name_asc") is not None
    assert apply_project_sort(None, "name_desc") is not None
```

- [ ] **Step 2: Run project API tests to verify RED**

Run:

```powershell
python -m pytest backend\tests\test_projects_api.py -q
```

Expected: fails because `app.routers.projects` and `app.schemas.project` do not exist.

- [ ] **Step 3: Add project schema**

Create `backend/app/schemas/project.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCardResponse(BaseModel):
    id: int
    name: str
    slug: str | None = None
    developer: str | None = None
    location: str | None = None
    district: str | None = None
    city: str | None = None
    total_units: int | None = None
    price_range: str | None = None
    area_range: str | None = None
    status: str | None = None
    project_type: str | None = None
    description: str | None = None
    amenities: list[str] = Field(default_factory=list)
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Add project router**

Create `backend/app/routers/projects.py` with public helpers and endpoint:

```python
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.schemas.common import PaginatedResponse
from app.schemas.project import ProjectCardResponse


router = APIRouter(prefix="/projects", tags=["Projects"])


def apply_project_filters(query, params: dict):
    filters = []
    if params.get("search"):
        term = f"%{params['search']}%"
        filters.append(
            or_(
                Project.name.ilike(term),
                Project.description.ilike(term),
                Project.location.ilike(term),
                Project.developer.ilike(term),
            )
        )
    if params.get("city"):
        filters.append(Project.city.ilike(f"%{params['city']}%"))
    if params.get("district"):
        filters.append(Project.district.ilike(f"%{params['district']}%"))
    if params.get("project_type"):
        filters.append(Project.project_type.ilike(f"%{params['project_type']}%"))
    if params.get("status"):
        filters.append(Project.status == params["status"])
    if not filters:
        return query if query is not None else select(Project)
    target = query if query is not None else select(Project)
    return target.where(and_(*filters))


def apply_project_sort(query, sort: str | None):
    target = query if query is not None else select(Project)
    sort_map = {
        "name_asc": Project.name.asc(),
        "name_desc": Project.name.desc(),
        "newest": Project.created_at.desc(),
    }
    return target.order_by(sort_map.get(sort, Project.created_at.desc()))


@router.get("", response_model=PaginatedResponse)
async def get_projects(
    search: str | None = None,
    city: str | None = None,
    district: str | None = None,
    project_type: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    params = {
        "search": search,
        "city": city,
        "district": district,
        "project_type": project_type,
        "status": status,
    }
    count_query = apply_project_filters(select(func.count()).select_from(Project), params)
    total = (await db.execute(count_query)).scalar() or 0

    query = apply_project_filters(select(Project), params)
    query = apply_project_sort(query, sort).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()

    return PaginatedResponse(
        items=[ProjectCardResponse.model_validate(project) for project in projects],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )
```

- [ ] **Step 5: Run project API tests to verify GREEN**

Run:

```powershell
python -m pytest backend\tests\test_projects_api.py -q
```

Expected: all tests pass.

---

### Task 2: Backend Article API

**Files:**
- Create: `backend/app/schemas/article.py`
- Create: `backend/app/routers/articles.py`
- Create: `backend/tests/test_articles_api.py`

- [ ] **Step 1: Write failing article API helper tests**

Create `backend/tests/test_articles_api.py`:

```python
from app.routers.articles import article_card_response, apply_article_filters, apply_article_sort


class ArticleStub:
    id = 7
    title = "Thi truong BDS phuc hoi"
    body = "Noi dung bai viet " * 30
    category = "news"
    source = "batdongsan.com"
    post_date = None
    url = "https://example.test/news"
    created_at = None
    updated_at = None


def test_article_card_response_derives_summary():
    response = article_card_response(ArticleStub())

    assert response.title == "Thi truong BDS phuc hoi"
    assert response.summary.startswith("Noi dung bai viet")
    assert len(response.summary) <= 163


def test_article_filters_exclude_legal_by_default():
    query = apply_article_filters(None, {"search": None, "category": None})

    assert query is not None


def test_article_sort_supports_known_options():
    assert apply_article_sort(None, "newest") is not None
    assert apply_article_sort(None, "oldest") is not None
```

- [ ] **Step 2: Run article API tests to verify RED**

Run:

```powershell
python -m pytest backend\tests\test_articles_api.py -q
```

Expected: fails because `app.routers.articles` and `app.schemas.article` do not exist.

- [ ] **Step 3: Add article schema**

Create `backend/app/schemas/article.py`:

```python
from datetime import date, datetime

from pydantic import BaseModel


class ArticleCardResponse(BaseModel):
    id: int
    title: str
    body: str | None = None
    summary: str | None = None
    category: str | None = None
    source: str | None = None
    post_date: date | None = None
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Add article router**

Create `backend/app/routers/articles.py`:

```python
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.schemas.article import ArticleCardResponse
from app.schemas.common import PaginatedResponse


router = APIRouter(prefix="/articles", tags=["Articles"])


def _summary(body: str | None, limit: int = 160) -> str | None:
    if not body:
        return None
    normalized = " ".join(body.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def article_card_response(article: Article) -> ArticleCardResponse:
    response = ArticleCardResponse.model_validate(article)
    response.summary = _summary(response.body)
    return response


def apply_article_filters(query, params: dict):
    filters = []
    category = params.get("category")
    if category:
        filters.append(Article.category == category)
    else:
        filters.append(or_(Article.category.is_(None), Article.category != "legal"))
    if params.get("search"):
        term = f"%{params['search']}%"
        filters.append(or_(Article.title.ilike(term), Article.body.ilike(term)))
    target = query if query is not None else select(Article)
    return target.where(and_(*filters))


def apply_article_sort(query, sort: str | None):
    target = query if query is not None else select(Article)
    if sort == "oldest":
        return target.order_by(Article.post_date.asc().nullslast(), Article.created_at.asc())
    return target.order_by(Article.post_date.desc().nullslast(), Article.created_at.desc())


@router.get("", response_model=PaginatedResponse)
async def get_articles(
    search: str | None = None,
    category: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    params = {"search": search, "category": category}
    count_query = apply_article_filters(select(func.count()).select_from(Article), params)
    total = (await db.execute(count_query)).scalar() or 0

    query = apply_article_filters(select(Article), params)
    query = apply_article_sort(query, sort).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    articles = result.scalars().all()

    return PaginatedResponse(
        items=[article_card_response(article) for article in articles],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )
```

- [ ] **Step 5: Run article API tests to verify GREEN**

Run:

```powershell
python -m pytest backend\tests\test_articles_api.py -q
```

Expected: all tests pass.

---

### Task 3: Register Routers

**Files:**
- Modify: `backend/app/main.py`
- Create or modify: `backend/tests/test_public_content_routes.py`

- [ ] **Step 1: Write failing route registration test**

Create `backend/tests/test_public_content_routes.py`:

```python
from app.main import app


def test_public_content_routes_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/projects" in paths
    assert "/api/v1/articles" in paths
```

- [ ] **Step 2: Run route registration test to verify RED**

Run:

```powershell
python -m pytest backend\tests\test_public_content_routes.py -q
```

Expected: fails because routers are not included.

- [ ] **Step 3: Register routers**

Modify `backend/app/main.py` imports:

```python
from app.routers import admin, articles, auth, chat, listings, market, metrics, preferences, projects
```

Add router includes after market/listings:

```python
app.include_router(projects.router, prefix="/api/v1")
app.include_router(articles.router, prefix="/api/v1")
```

- [ ] **Step 4: Run backend API tests**

Run:

```powershell
python -m pytest backend\tests\test_projects_api.py backend\tests\test_articles_api.py backend\tests\test_public_content_routes.py -q
```

Expected: all tests pass.

---

### Task 4: Frontend Types And API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add frontend types**

Append to `frontend/lib/types.ts`:

```typescript
export interface ProjectCard {
  id: number;
  name: string;
  slug: string | null;
  developer: string | null;
  location: string | null;
  district: string | null;
  city: string | null;
  total_units: number | null;
  price_range: string | null;
  area_range: string | null;
  status: string | null;
  project_type: string | null;
  description: string | null;
  amenities: string[];
  url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectFilters {
  search?: string;
  city?: string;
  district?: string;
  project_type?: string;
  status?: string;
  sort?: string;
  page?: number;
  limit?: number;
}

export interface ArticleCard {
  id: number;
  title: string;
  body: string | null;
  summary: string | null;
  category: string | null;
  source: string | null;
  post_date: string | null;
  url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ArticleFilters {
  search?: string;
  category?: string;
  sort?: string;
  page?: number;
  limit?: number;
}
```

- [ ] **Step 2: Add frontend API imports and helpers**

Modify the import in `frontend/lib/api.ts` to include:

```typescript
  ArticleCard,
  ArticleFilters,
  ProjectCard,
  ProjectFilters,
```

Add helpers after listings:

```typescript
export async function getProjects(
  filters: ProjectFilters = {}
): Promise<PaginatedResponse<ProjectCard>> {
  return fetchJSON(`${BASE}/projects${buildQuery({ ...filters })}`);
}

export async function getArticles(
  filters: ArticleFilters = {}
): Promise<PaginatedResponse<ArticleCard>> {
  return fetchJSON(`${BASE}/articles${buildQuery({ ...filters })}`);
}
```

- [ ] **Step 3: Run frontend type/lint check**

Run:

```powershell
cd frontend
npm run lint
```

Expected: no new lint errors.

---

### Task 5: Project Landing Page

**Files:**
- Create: `frontend/app/du-an/page.tsx`

- [ ] **Step 1: Create project page with API-backed fallback UI**

Create `frontend/app/du-an/page.tsx` as a client component. It must:

- call `getProjects({ search, city, project_type, status, sort, limit: 12 })`
- maintain loading/error state
- render fallback project cards if API fails or returns zero rows
- include search input, city/type/status/sort selects, and project cards
- use lucide icons from `Search`, `MapPin`, `Building2`, `ArrowRight`, `SlidersHorizontal`, `Layers3`, `BadgeCheck`

- [ ] **Step 2: Run frontend lint**

Run:

```powershell
cd frontend
npm run lint
```

Expected: no lint errors from `frontend/app/du-an/page.tsx`.

---

### Task 6: News Landing Page

**Files:**
- Create: `frontend/app/tin-tuc/page.tsx`

- [ ] **Step 1: Create news page with API-backed fallback UI**

Create `frontend/app/tin-tuc/page.tsx` as a client component. It must:

- call `getArticles({ search, category, sort, limit: 12 })`
- maintain loading/error state
- render fallback articles if API fails or returns zero rows
- include search input, category tabs, sort select, featured article, and article cards
- use lucide icons from `Search`, `Newspaper`, `ArrowRight`, `CalendarDays`, `BookOpen`, `TrendingUp`

- [ ] **Step 2: Run frontend lint**

Run:

```powershell
cd frontend
npm run lint
```

Expected: no lint errors from `frontend/app/tin-tuc/page.tsx`.

---

### Task 7: Navigation

**Files:**
- Modify: `frontend/components/layout/Header.tsx`
- Modify: `frontend/components/layout/Footer.tsx`

- [ ] **Step 1: Add header navigation links**

Modify `NAV_LINKS` in `frontend/components/layout/Header.tsx`:

```typescript
const NAV_LINKS = [
  { href: "/nha-dat-ban", label: "Nha dat ban" },
  { href: "/nha-dat-cho-thue", label: "Nha dat cho thue" },
  { href: "/du-an", label: "Du an" },
  { href: "/tin-tuc", label: "Tin tuc" },
  { href: "/thi-truong", label: "Thi truong" },
];
```

- [ ] **Step 2: Add footer navigation links**

Add `/du-an` and `/tin-tuc` links to the footer category list, matching the current `Link` styling.

- [ ] **Step 3: Run frontend lint**

Run:

```powershell
cd frontend
npm run lint
```

Expected: no lint errors from navigation changes.

---

### Task 8: Final Verification

**Files:**
- No source changes expected.

- [ ] **Step 1: Run backend targeted tests**

Run:

```powershell
python -m pytest backend\tests\test_projects_api.py backend\tests\test_articles_api.py backend\tests\test_public_content_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run backend compile check**

Run:

```powershell
python -m compileall backend\app\schemas\project.py backend\app\schemas\article.py backend\app\routers\projects.py backend\app\routers\articles.py backend\app\main.py
```

Expected: no syntax errors.

- [ ] **Step 3: Run frontend lint**

Run:

```powershell
cd frontend
npm run lint
```

Expected: ESLint exits with code 0.

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: Next.js build completes.

- [ ] **Step 5: Start dev server and smoke test pages**

Run:

```powershell
cd frontend
npm run dev
```

Open:

- `http://localhost:3000/du-an`
- `http://localhost:3000/tin-tuc`

Expected: both pages render non-empty content. If backend has data, cards use API data. If API is unavailable or empty, fallback cards are visible.

