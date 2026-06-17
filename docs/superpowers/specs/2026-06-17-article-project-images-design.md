# Article and Project Images Design

## Goal

Persist and display real image URLs for articles and projects using separate image tables, matching the existing `listing_images` architecture. The crawler already extracts `image_urls`; this work makes those images survive ingestion, appear in public APIs, and render on list/detail pages.

## Scope

- Add `article_images` and `project_images` tables.
- Add SQLAlchemy models for article and project images.
- Ingest `image_urls` from crawler CSV rows into the new tables.
- Return `primary_image_url` and `image_urls` from article and project list/detail APIs.
- Render real images on news/project landing pages and detail pages.
- Preserve current placeholders when no image exists.
- Keep existing chatbot layout untouched.

## Database Design

Create `article_images`:

- `id`: integer primary key.
- `article_id`: required foreign key to `articles.id` with `ON DELETE CASCADE`.
- `article_url`: text copy of the source article URL for operational lookup.
- `image_url`: required text URL.
- `sort_order`: integer, zero-based crawler order.
- `is_primary`: boolean, true only for the first image.
- `source`: short source label, default `batdongsan`.
- `created_at`: timestamp.

Create indexes:

- `article_id`
- `article_url`
- `(article_id, sort_order)`
- `(article_url, sort_order)`

Create `project_images`:

- `id`: integer primary key.
- `project_id`: required foreign key to `projects.id` with `ON DELETE CASCADE`.
- `project_slug`: string copy of the project slug for operational lookup.
- `image_url`: required text URL.
- `sort_order`: integer, zero-based crawler order.
- `is_primary`: boolean, true only for the first image.
- `source`: short source label, default `batdongsan`.
- `created_at`: timestamp.

Create indexes:

- `project_id`
- `project_slug`
- `(project_id, sort_order)`
- `(project_slug, sort_order)`

## Backend Models

Add models:

- `backend/app/models/article_image.py`
- `backend/app/models/project_image.py`

Register both models in `backend/app/models/__init__.py` so migrations, imports, and tests can resolve them consistently.

The model fields should mirror `ListingImage` where possible so future maintenance remains predictable.

## Ingestion Design

Use the same ingestion pattern as `listings_ingestor.py`:

1. Parse `image_urls` from a CSV row.
2. Accept JSON arrays, Python lists, or comma/newline-separated strings.
3. Keep only `http://` and `https://` URLs.
4. Deduplicate while preserving order.
5. Attach parsed URLs to prepared article/project data under an internal key.
6. Upsert the parent article/project.
7. Delete existing images for that parent.
8. Insert the replacement image rows.

For articles, the parent key is article `id` plus source `url`.

For projects, the parent key is project `id` plus `slug`.

If a row has no image URLs, the ingestor deletes existing images for that parent so the DB reflects the latest crawl.

## API Design

Extend both public response schemas:

- `primary_image_url: str | None = None`
- `image_urls: list[str] = []`

Article APIs:

- `GET /api/v1/articles`
- `GET /api/v1/articles/{article_id}`

Project APIs:

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`

Both list and detail endpoints should query image tables in batches for list responses, and once for detail responses. Images must be ordered by parent id, `sort_order`, then image id.

The first URL becomes `primary_image_url`. The full ordered list becomes `image_urls`.

## Frontend Design

Update TypeScript types:

- `ArticleCard`
- `ProjectCard`

Add:

- `primary_image_url`
- `image_urls`

News landing page:

- Article cards show the primary image when present.
- Featured article uses primary image as the media panel when present.
- Empty image state keeps the current visual structure.

Article detail page:

- Show a large hero image when `primary_image_url` exists.
- If there are multiple images, render a compact gallery strip.
- If no image exists, keep a branded placeholder.

Project landing page:

- Project cards show the primary image when present.
- If no image exists, keep the current icon placeholder.

Project detail page:

- Replace the current placeholder hero with real image gallery when `image_urls` exists.
- Show image count and allow selecting thumbnails if practical within existing client component state.
- If no image exists, keep the current placeholder hero.

## Error Handling

- Invalid image URL values are ignored during ingestion.
- Duplicate URLs are ignored after the first occurrence.
- Missing image rows never break API responses; they return `primary_image_url = None` and `image_urls = []`.
- Frontend hides gallery controls when there are no images or only one image.
- Broken remote images should not collapse surrounding layout; cards and hero areas keep stable dimensions.

## Testing

Backend:

- Test image URL parser accepts JSON arrays and dedupes values.
- Test article image row preparation marks the first image as primary.
- Test project image row preparation marks the first image as primary.
- Test article response helper returns `primary_image_url` and `image_urls`.
- Test project response helper returns `primary_image_url` and `image_urls`.
- Test public content APIs still register list/detail routes.

Frontend:

- Static test verifies article/project types include image fields.
- Static test verifies landing and detail pages reference `primary_image_url` or `image_urls`.
- Run `npm.cmd run lint`.
- Run `npm.cmd run build`.

## Out of Scope

- Downloading, proxying, resizing, or storing image binaries.
- Building a media admin UI.
- Adding captions, alt text from crawler, width, height, or image hashes.
- Reworking listing images.
- Changing chatbot layout.
