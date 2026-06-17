# Article and Project Detail Pages Design

## Goal

Build public detail pages for articles and projects with an information architecture inspired by Vietnamese real-estate portals, while keeping this app's own brand identity. The implementation must not copy Batdongsan.com logos, names, visual assets, proprietary styling, or exact page composition.

## Scope

- Add backend detail APIs for articles and projects.
- Add frontend routes for article and project detail pages.
- Reuse real database data when available.
- Keep Vietnamese UI copy accented.
- Preserve the existing chatbot placement and behavior.
- Keep the existing news and project landing pages intact except for links to detail pages.

## Backend Design

Add two public detail endpoints:

- `GET /api/v1/articles/{article_id}`
- `GET /api/v1/projects/{project_id}`

Each endpoint returns one record from the existing `articles` or `projects` table. If the record does not exist, return `404` with a clear message. The response schemas should match the current card/list schemas where practical and include extra detail fields already available on the database models, such as body/content, summary, status, address, location, description, amenities, and timestamps.

No new tables are required.

## Frontend Routes

Add two Next.js routes:

- `/tin-tuc/[id]`
- `/du-an/[id]`

The pages fetch detail data from the backend through the existing frontend API helper pattern. If the API returns `404`, show a polished not-found state or use Next.js `notFound()` if it fits the current app style. If optional fields are missing, the layout should remain stable and hide empty sections instead of showing blank labels.

## Project Detail UX

The project detail page should use the app's own visual identity with a real-estate portal structure:

- Breadcrumb: home, projects, project title.
- Header: project title, address/location, status badge if available.
- Media area: image/gallery-style area if images exist later; for now use a clean branded placeholder when no project image field exists.
- Quick facts: project type, location, status, area, price, or other available fields.
- Main sections: `Tổng quan`, `Thông tin chi tiết`, `Tiện ích`, `Vị trí`, and `Dự án liên quan`.
- CTA area: contact or consultation call-to-action that does not interfere with the chatbot.

Vietnamese display text must use accents, for example `Tổng quan`, `Thông tin chi tiết`, `Tiện ích`, `Vị trí`, and `Dự án liên quan`.

## Article Detail UX

The article detail page should feel like a real-estate editorial page:

- Breadcrumb: home, news, article title.
- Header: category/status if available, article title, publication date, author if available.
- Main content: summary lead, body/content from DB, readable typography.
- Sidebar or lower section: related articles and featured projects when data is available from existing list APIs.
- Empty states: if content is short or missing, show summary/body fallback without breaking spacing.

Vietnamese display text must use accents, for example `Tin tức`, `Bài viết liên quan`, `Dự án nổi bật`, and `Ngày đăng`.

## Data Flow

1. User opens a detail URL.
2. Next.js route calls the backend detail endpoint through `frontend/lib/api.ts`.
3. Backend reads the matching SQLAlchemy model row.
4. Frontend renders page sections based on available fields.
5. Landing page cards link to the new detail routes.

## Error Handling

- Backend returns `404` for missing records.
- Frontend handles missing records with a not-found page/state.
- Frontend hides optional empty sections.
- API failures should show a calm, user-facing error state rather than a broken page.

## Testing

- Backend tests for successful article detail, successful project detail, and `404` responses.
- Frontend checks for route files and Vietnamese accented labels.
- Run existing lint/build verification after implementation.

## Out of Scope

- Copying Batdongsan.com brand, logo, text, images, CSS, or exact visual assets.
- Adding authentication requirements to public detail pages.
- Adding new database migrations unless existing models lack required fields.
- Building a full image management system.
- Changing chatbot layout beyond preserving the current fixed placement.
