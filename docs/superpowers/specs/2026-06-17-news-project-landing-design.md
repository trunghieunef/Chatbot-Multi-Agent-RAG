# News And Project Landing Pages Design

## Goal

Add public landing/listing pages for real estate news and projects, inspired by the browsing structure of Batdongsan.com, backed by real database data when available.

The feature should expose `articles` and `projects` through public backend APIs and render frontend pages at `/tin-tuc` and `/du-an`. Pages must remain useful when the API is unavailable or the database has no rows by showing curated fallback content.

## Scope

In scope:

- Public API list endpoints for `projects` and `articles`.
- Pagination, search, filtering, and sorting for those endpoints.
- Frontend API client types and fetch helpers.
- `/du-an` project landing/list page.
- `/tin-tuc` news landing/list page.
- Header and footer navigation links.
- Focused backend and frontend verification.

Out of scope:

- Project detail pages such as `/du-an/[slug]`.
- Article detail pages such as `/tin-tuc/[id]`.
- Crawler, ingestion, or database migration changes.
- Pixel-copying Batdongsan.com branding or layout.

## Backend Design

Create `backend/app/schemas/project.py` with `ProjectCardResponse`. It should include:

- `id`, `name`, `slug`, `developer`
- `location`, `district`, `city`
- `total_units`, `price_range`, `area_range`
- `status`, `project_type`, `description`, `amenities`, `url`
- `created_at`, `updated_at`

Create `backend/app/schemas/article.py` with `ArticleCardResponse`. It should include:

- `id`, `title`, `body`, `category`, `source`
- `post_date`, `url`, `created_at`, `updated_at`
- `summary`, derived from `body` for card display

Create `backend/app/routers/projects.py`:

- `GET /projects`
- Query params: `search`, `city`, `district`, `project_type`, `status`, `sort`, `page`, `limit`
- Sort options: `newest`, `name_asc`, `name_desc`
- Response shape: existing `PaginatedResponse`

Create `backend/app/routers/articles.py`:

- `GET /articles`
- Query params: `search`, `category`, `sort`, `page`, `limit`
- Sort options: `newest`, `oldest`
- Default behavior excludes legal knowledge base rows by using `category != "legal"` unless `category` is explicitly set.
- Response shape: existing `PaginatedResponse`

Register both routers in `backend/app/main.py` under `/api/v1`.

## Frontend Design

Update `frontend/lib/types.ts` with `ProjectCard`, `ArticleCard`, and filter types. Update `frontend/lib/api.ts` with:

- `getProjects(filters)`
- `getArticles(filters)`

Create `/du-an` as a client page with:

- Breadcrumb.
- Search-forward hero with quick filter controls.
- Compact filter bar for city, project type, status, and sort.
- Project card grid/list with project name, location, developer, status, price range, area range, type, and amenities.
- Sidebar-like desktop column for highlighted areas and project browsing prompts.
- Empty/error state that falls back to curated sample projects.

Create `/tin-tuc` as a client page with:

- Breadcrumb.
- Search-forward hero.
- Featured article slot from the first real article or fallback article.
- Category tabs for market, guide, planning, and general news.
- Article grid/list with title, source, category, post date, summary, and outbound URL when available.
- Empty/error state that falls back to curated sample articles.

Update `frontend/components/layout/Header.tsx` and `Footer.tsx` to include `Du an` and `Tin tuc` links using the current navigation style.

## UX Notes

The UI should borrow information architecture from Batdongsan.com:

- News: prominent search, featured content, category browsing, article cards.
- Projects: search and filter surface, project status/type/location filtering, dense browsable cards.

The implementation should fit the existing app visual language: restrained red primary color, neutral backgrounds, cards for repeated items, lucide icons in controls, responsive grids, and no decorative gradient-orb backgrounds.

## Error Handling

Backend endpoints return empty paginated responses when no rows match. Missing optional project/article fields are returned as `null` or empty arrays where appropriate.

Frontend catches API failures and renders fallback datasets so the landing pages never look broken during local development or before ingestion has populated `projects` and `articles`.

## Testing

Backend:

- Unit tests for response helpers where useful.
- Router tests or helper tests covering search/filter/sort behavior for projects and articles.
- Route registration smoke coverage through import/compile.

Frontend:

- TypeScript and ESLint verification.
- Build verification if feasible.
- Browser smoke test for `/du-an` and `/tin-tuc` after dev server starts.

## Assumptions

- The existing `projects` and `articles` tables are already created by current models/Alembic history.
- News rows are stored in `articles`; legal knowledge base rows also use `articles` but should not dominate the public news page by default.
- The first implementation can link cards to the original `url` when available instead of creating internal detail pages.
