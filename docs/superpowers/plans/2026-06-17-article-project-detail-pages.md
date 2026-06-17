# Article and Project Detail Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add public detail API endpoints and Batdongsan-inspired, app-branded detail pages for articles and projects.

**Architecture:** Backend detail endpoints return one `Article` or `Project` row through existing SQLAlchemy and Pydantic patterns. Frontend adds typed API helpers, updates landing cards to link to internal detail routes, and renders two client-side dynamic pages that fetch real DB data and hide empty optional sections.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Next.js App Router, React client components, TypeScript, Tailwind CSS, lucide-react.

---

## File Structure

- Modify `backend/app/routers/articles.py`: add `GET /articles/{article_id}` and reusable detail response helper.
- Modify `backend/app/routers/projects.py`: add `GET /projects/{project_id}`.
- Modify `backend/tests/test_articles_api.py`: add lightweight tests for response helper behavior.
- Modify `backend/tests/test_projects_api.py`: add lightweight tests for detail response schema behavior.
- Modify `backend/tests/test_public_content_routes.py`: assert detail routes are registered.
- Modify `frontend/lib/types.ts`: add `ArticleDetail` and `ProjectDetail` aliases/interfaces.
- Modify `frontend/lib/api.ts`: add `getArticleDetail(id)` and `getProjectDetail(id)`.
- Modify `frontend/app/tin-tuc/page.tsx`: link article cards and featured article to `/tin-tuc/{id}` for DB/fallback rows.
- Modify `frontend/app/du-an/page.tsx`: link project cards to `/du-an/{id}` for DB/fallback rows.
- Create `frontend/app/tin-tuc/[id]/page.tsx`: article detail page.
- Create `frontend/app/du-an/[id]/page.tsx`: project detail page.
- Create `frontend/tests/content-detail-pages.test.mjs`: static checks for routes, API helpers, and Vietnamese accented labels.

---

### Task 1: Backend Detail Endpoints

**Files:**
- Modify: `backend/app/routers/articles.py`
- Modify: `backend/app/routers/projects.py`
- Modify: `backend/tests/test_articles_api.py`
- Modify: `backend/tests/test_projects_api.py`
- Modify: `backend/tests/test_public_content_routes.py`

- [ ] **Step 1: Add route registration tests**

Add these assertions to `backend/tests/test_public_content_routes.py`:

```python
def test_public_content_detail_routes_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/projects/{project_id}" in paths
    assert "/api/v1/articles/{article_id}" in paths
```

- [ ] **Step 2: Add schema/helper tests**

Add this test to `backend/tests/test_articles_api.py`:

```python
def test_article_card_response_keeps_body_for_detail_pages():
    response = article_card_response(ArticleStub())

    assert response.body.startswith("Noi dung bai viet")
    assert response.summary
```

Add this test to `backend/tests/test_projects_api.py`:

```python
def test_project_card_response_has_detail_page_fields():
    response = ProjectCardResponse.model_validate(ProjectStub())

    assert response.description == "Project overview"
    assert response.price_range == "3 - 8 ty"
    assert response.area_range == "45 - 120 m2"
```

- [ ] **Step 3: Run backend tests and confirm route test fails first**

Run:

```powershell
pytest backend\tests\test_public_content_routes.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py -q
```

Expected before implementation: the new detail route registration test fails because the paths are not registered.

- [ ] **Step 4: Implement article detail endpoint**

In `backend/app/routers/articles.py`, update imports and add the route after `get_articles`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

```python
@router.get("/{article_id}", response_model=ArticleCardResponse)
async def get_article_detail(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article_card_response(article)
```

- [ ] **Step 5: Implement project detail endpoint**

In `backend/app/routers/projects.py`, update imports and add the route after `get_projects`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

```python
@router.get("/{project_id}", response_model=ProjectCardResponse)
async def get_project_detail(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectCardResponse.model_validate(project)
```

- [ ] **Step 6: Run backend focused tests**

Run:

```powershell
pytest backend\tests\test_public_content_routes.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit backend changes**

Run:

```powershell
git add backend\app\routers\articles.py backend\app\routers\projects.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py backend\tests\test_public_content_routes.py
git commit -m "add article and project detail APIs"
```

---

### Task 2: Frontend Data Helpers and Landing Links

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/tin-tuc/page.tsx`
- Modify: `frontend/app/du-an/page.tsx`
- Create: `frontend/tests/content-detail-pages.test.mjs`

- [ ] **Step 1: Add frontend static test**

Create `frontend/tests/content-detail-pages.test.mjs`:

```javascript
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();
const read = (path) => readFileSync(join(root, path), "utf8");

test("content detail routes and helpers exist", () => {
  assert.equal(existsSync(join(root, "app/tin-tuc/[id]/page.tsx")), true);
  assert.equal(existsSync(join(root, "app/du-an/[id]/page.tsx")), true);

  const api = read("lib/api.ts");
  assert.match(api, /getArticleDetail/);
  assert.match(api, /getProjectDetail/);
});

test("landing pages link to internal detail routes", () => {
  assert.match(read("app/tin-tuc/page.tsx"), /`\/tin-tuc\/\$\{article\.id\}`/);
  assert.match(read("app/du-an/page.tsx"), /`\/du-an\/\$\{project\.id\}`/);
});

test("detail pages keep Vietnamese accented labels", () => {
  const article = read("app/tin-tuc/[id]/page.tsx");
  const project = read("app/du-an/[id]/page.tsx");

  assert.match(article, /Tin tức/);
  assert.match(article, /Bài viết liên quan/);
  assert.match(project, /Tổng quan/);
  assert.match(project, /Thông tin chi tiết/);
});
```

- [ ] **Step 2: Run frontend static test and confirm it fails first**

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
```

Expected before implementation: fails because dynamic route files and helpers do not exist.

- [ ] **Step 3: Add detail types**

Append to `frontend/lib/types.ts` after `ArticleCard`:

```ts
export interface ProjectDetail extends ProjectCard {}

export interface ArticleDetail extends ArticleCard {}
```

- [ ] **Step 4: Add API helpers**

In `frontend/lib/api.ts`, import the detail types and add:

```ts
export async function getProjectDetail(id: number): Promise<ProjectDetail> {
  return fetchJSON(`${BASE}/projects/${id}`);
}

export async function getArticleDetail(id: number): Promise<ArticleDetail> {
  return fetchJSON(`${BASE}/articles/${id}`);
}
```

- [ ] **Step 5: Update landing links**

In `frontend/app/du-an/page.tsx`, change the card href to:

```ts
const href = `/du-an/${project.id}`;
```

Render it with `Link` instead of external `<a>`:

```tsx
<Link
  href={href}
  className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
>
  Xem dự án <ArrowRight size={14} />
</Link>
```

In `frontend/app/tin-tuc/page.tsx`, change article hrefs to:

```ts
const href = `/tin-tuc/${article.id}`;
```

Use `Link` for both card and featured article:

```tsx
<Link
  href={href}
  className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
>
  Đọc tiếp <ArrowRight size={14} />
</Link>
```

- [ ] **Step 6: Commit helper/link changes after route pages exist**

Do not commit until Task 3 route files exist and tests pass, because the static test requires all frontend pieces together.

---

### Task 3: Frontend Detail Pages

**Files:**
- Create: `frontend/app/tin-tuc/[id]/page.tsx`
- Create: `frontend/app/du-an/[id]/page.tsx`
- Modify: `frontend/tests/content-detail-pages.test.mjs`

- [ ] **Step 1: Create article detail page**

Create `frontend/app/tin-tuc/[id]/page.tsx` as a client component. It must:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CalendarDays, Newspaper, UserRound } from "lucide-react";
import { getArticleDetail, getArticles, getProjects } from "@/lib/api";
import type { ArticleDetail, ArticleCard, ProjectCard } from "@/lib/types";
```

Use state:

```tsx
const [article, setArticle] = useState<ArticleDetail | null>(null);
const [related, setRelated] = useState<ArticleCard[]>([]);
const [projects, setProjects] = useState<ProjectCard[]>([]);
const [loading, setLoading] = useState(true);
```

Render these labels exactly with accents: `Tin tức`, `Ngày đăng`, `Bài viết liên quan`, `Dự án nổi bật`.

- [ ] **Step 2: Create project detail page**

Create `frontend/app/du-an/[id]/page.tsx` as a client component. It must:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  BadgeCheck,
  Building2,
  CheckCircle2,
  Home,
  Layers3,
  MapPin,
  Phone,
  Ruler,
} from "lucide-react";
import { getProjectDetail, getProjects } from "@/lib/api";
import type { ProjectCard, ProjectDetail } from "@/lib/types";
```

Render these labels exactly with accents: `Tổng quan`, `Thông tin chi tiết`, `Tiện ích`, `Vị trí`, `Dự án liên quan`.

- [ ] **Step 3: Keep layout stable on missing data**

Both pages must use helper functions:

```ts
function fieldLabel(value: string | number | null | undefined, fallback = "Đang cập nhật") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}
```

For article content, split paragraphs safely:

```ts
const paragraphs = useMemo(() => {
  const content = article?.body || article?.summary || "";
  return content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
}, [article]);
```

- [ ] **Step 4: Run frontend static test**

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
```

Expected: pass.

- [ ] **Step 5: Run lint and build**

Run from `frontend`:

```powershell
npm.cmd run lint
npm.cmd run build
```

Expected: lint passes; build includes `/du-an/[id]` and `/tin-tuc/[id]`. Existing `<img>` lint warnings may remain if they are unrelated.

- [ ] **Step 6: Commit frontend changes**

Run:

```powershell
git add frontend\lib\api.ts frontend\lib\types.ts frontend\app\tin-tuc\page.tsx frontend\app\du-an\page.tsx frontend\app\tin-tuc\[id]\page.tsx frontend\app\du-an\[id]\page.tsx frontend\tests\content-detail-pages.test.mjs
git commit -m "add article and project detail pages"
```

---

### Task 4: Final Verification

**Files:**
- No code edits expected.

- [ ] **Step 1: Check git status**

Run:

```powershell
git status --short
```

Expected: only unrelated `report/main.log` and `report/main.pdf` remain modified, unless the user changed other files during implementation.

- [ ] **Step 2: Re-run focused verification**

Run:

```powershell
pytest backend\tests\test_public_content_routes.py backend\tests\test_articles_api.py backend\tests\test_projects_api.py -q
```

Expected: pass.

Run from `frontend`:

```powershell
node --test tests\content-detail-pages.test.mjs
npm.cmd run lint
npm.cmd run build
```

Expected: pass, with any pre-existing lint warnings reported clearly.

- [ ] **Step 3: Summarize result**

Report:

- Backend endpoints added: `/api/v1/articles/{article_id}` and `/api/v1/projects/{project_id}`.
- Frontend routes added: `/tin-tuc/[id]` and `/du-an/[id]`.
- Landing cards now open internal detail pages.
- Chatbot layout was not changed.
- Verification commands and results.
