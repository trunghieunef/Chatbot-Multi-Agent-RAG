# Chatbot Listing Image Gallery + Lightbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show up to 3 listing image thumbnails per source card in the chatbot, with a click-to-zoom lightbox and a "Xem chi tiết" link that opens the listing detail page in a new tab.

**Architecture:** Backend `resolve_to_listing_records` fetches image URLs from `listing_images` and attaches `record["images"]`; the agent already forwards `metadata.images`, which passes through the public API (`sources: list[dict]`) unchanged to the frontend. The frontend renders a shared `ListingImageGallery` (thumbnails + `ImageLightbox`) plus a real detail link inside the listing source card, in both `ChatPanel` and `ChatWidget`.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js App Router + React + TypeScript + Tailwind v4 + lucide-react (frontend).

## Global Constraints

- Images use the original `listing_images.image_url` (external CDN); never download/host them.
- Max 3 images per listing, ordered `is_primary DESC, sort_order ASC`.
- Frontend: TypeScript strict, functional components, lucide-react icons only, Tailwind v4 (no config file). API calls in `lib/api.ts`, types in `lib/types.ts`.
- Backend: SQLAlchemy 2.0 async, type hints required, English code/comments.
- No frontend unit-test framework exists; frontend tasks gate on `cd frontend && npm run lint`.

---

### Task 1: Backend pure helper `group_listing_images`

**Files:**
- Modify: `backend/app/services/rag/hybrid_search.py`
- Test: `backend/tests/test_listing_images.py`

**Interfaces:**
- Produces: `group_listing_images(rows: list[tuple[int, str]], *, limit: int = 3) -> dict[int, list[str]]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_listing_images.py`:
```python
from app.services.rag.hybrid_search import group_listing_images


def test_groups_and_caps_at_three_preserving_order():
    rows = [
        (1, "a1"), (1, "a2"), (1, "a3"), (1, "a4"),  # 4th must be dropped
        (2, "b1"),
    ]
    assert group_listing_images(rows) == {1: ["a1", "a2", "a3"], 2: ["b1"]}


def test_skips_empty_urls():
    rows = [(1, ""), (1, None), (1, "a1")]  # type: ignore[list-item]
    assert group_listing_images(rows) == {1: ["a1"]}


def test_empty_rows_returns_empty_dict():
    assert group_listing_images([]) == {}


def test_custom_limit():
    rows = [(1, "a1"), (1, "a2"), (1, "a3")]
    assert group_listing_images(rows, limit=2) == {1: ["a1", "a2"]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_listing_images.py -q`
Expected: FAIL with `ImportError: cannot import name 'group_listing_images'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/rag/hybrid_search.py`, add above `async def resolve_to_listing_records`:
```python
def group_listing_images(
    rows: list[tuple[int, str]], *, limit: int = 3
) -> dict[int, list[str]]:
    """Group ordered ``(listing_id, image_url)`` rows into ``{listing_id: [url]}``.

    Rows must already be ordered (is_primary DESC, sort_order ASC). Keeps at most
    ``limit`` non-empty urls per listing, preserving the input order.
    """
    grouped: dict[int, list[str]] = {}
    for listing_id, image_url in rows:
        if not image_url:
            continue
        bucket = grouped.setdefault(listing_id, [])
        if len(bucket) < limit:
            bucket.append(image_url)
    return grouped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_listing_images.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rag/hybrid_search.py backend/tests/test_listing_images.py
git commit -m "feat: add group_listing_images helper for listing thumbnails"
```

---

### Task 2: Backend wire images into `resolve_to_listing_records`

**Files:**
- Modify: `backend/app/services/rag/hybrid_search.py` (function `resolve_to_listing_records`)

**Interfaces:**
- Consumes: `group_listing_images` (Task 1)
- Produces: each returned listing record gains `record["images"]: list[str]`

- [ ] **Step 1: Add the image query + attach in `resolve_to_listing_records`**

Find the session block:
```python
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        listings = {row._mapping["id"]: dict(row._mapping) for row in result.all()}
```
Replace it with:
```python
    image_query = text(
        "SELECT listing_id, image_url FROM listing_images "
        "WHERE listing_id = ANY(:ids) "
        "ORDER BY listing_id, is_primary DESC, sort_order ASC"
    )
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        listings = {row._mapping["id"]: dict(row._mapping) for row in result.all()}
        img_result = await session.execute(image_query, {"ids": parent_ids})
        images_by_listing = group_listing_images(
            [
                (row._mapping["listing_id"], row._mapping["image_url"])
                for row in img_result.all()
            ]
        )
```

- [ ] **Step 2: Attach images to each record**

In the same function, find the record-building loop and the line that appends a listing. Just before `records.append(listing)`, add:
```python
        listing["images"] = images_by_listing.get(listing["id"], [])
```

- [ ] **Step 3: Verify compile + existing hybrid tests still pass**

Run: `cd backend && python -m compileall app/services/rag/hybrid_search.py -q && python -m pytest tests/test_hybrid_search.py tests/test_rrf_fusion.py tests/test_listing_images.py -q`
Expected: COMPILE OK and all green.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/rag/hybrid_search.py
git commit -m "feat: attach listing image urls to resolved listing records"
```

---

### Task 3: Frontend source helpers `getSourceImages` + `getListingDetailHref`

**Files:**
- Modify: `frontend/lib/chatSourceDisplay.ts`

**Interfaces:**
- Produces:
  - `getSourceImages(source: ChatSource): string[]`
  - `getListingDetailHref(source: ChatSource): string | undefined`

- [ ] **Step 1: Add the helpers**

Append to `frontend/lib/chatSourceDisplay.ts` (the file already imports `ChatSource`):
```ts
export function getSourceImages(source: ChatSource): string[] {
  const imgs = (source.metadata as { images?: unknown } | undefined)?.images;
  return Array.isArray(imgs)
    ? imgs.filter((u): u is string => typeof u === "string").slice(0, 3)
    : [];
}

export function getListingDetailHref(source: ChatSource): string | undefined {
  if (source.url) return source.url;
  if (source.id !== undefined && source.id !== null) {
    return `/nha-dat-ban/${source.id}`;
  }
  return undefined;
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors from `chatSourceDisplay.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/chatSourceDisplay.ts
git commit -m "feat: add getSourceImages and getListingDetailHref helpers"
```

---

### Task 4: Frontend `ImageLightbox` component

**Files:**
- Create: `frontend/components/chatbot/ImageLightbox.tsx`

**Interfaces:**
- Produces: default export `ImageLightbox` with props
  `{ images: string[]; index: number; onClose: () => void; onIndexChange: (index: number) => void }`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useEffect } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";

interface ImageLightboxProps {
  images: string[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}

export default function ImageLightbox({
  images,
  index,
  onClose,
  onIndexChange,
}: ImageLightboxProps) {
  const hasMany = images.length > 1;
  const prev = () => onIndexChange((index - 1 + images.length) % images.length);
  const next = () => onIndexChange((index + 1) % images.length);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && hasMany) prev();
      else if (e.key === "ArrowRight" && hasMany) next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, images.length, hasMany]);

  const current = images[index];
  if (!current) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <button
        onClick={onClose}
        aria-label="Đóng"
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
      >
        <X size={20} />
      </button>
      {hasMany && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            prev();
          }}
          aria-label="Ảnh trước"
          className="absolute left-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        >
          <ChevronLeft size={24} />
        </button>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={current}
        alt={`Ảnh ${index + 1}/${images.length}`}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain"
      />
      {hasMany && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            next();
          }}
          aria-label="Ảnh sau"
          className="absolute bottom-4 right-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
        >
          <ChevronRight size={24} />
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ImageLightbox.tsx
git commit -m "feat: add ImageLightbox overlay component"
```

---

### Task 5: Frontend `ListingImageGallery` component

**Files:**
- Create: `frontend/components/chatbot/ListingImageGallery.tsx`

**Interfaces:**
- Consumes: `ImageLightbox` (Task 4)
- Produces: default export `ListingImageGallery` with props `{ images: string[] }`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useState } from "react";
import ImageLightbox from "./ImageLightbox";

interface ListingImageGalleryProps {
  images: string[];
}

export default function ListingImageGallery({ images }: ListingImageGalleryProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [broken, setBroken] = useState<Set<number>>(new Set());

  const shown = images.slice(0, 3);
  if (shown.length === 0 || shown.every((_, i) => broken.has(i))) return null;

  return (
    <>
      <div className="mt-1.5 flex gap-1.5">
        {shown.map((url, i) =>
          broken.has(i) ? null : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={url}
              alt={`Ảnh ${i + 1}`}
              loading="lazy"
              onClick={() => setOpenIndex(i)}
              onError={() =>
                setBroken((b) => {
                  const nextSet = new Set(b);
                  nextSet.add(i);
                  return nextSet;
                })
              }
              className="h-16 w-16 cursor-pointer rounded-md object-cover transition-opacity hover:opacity-90"
            />
          )
        )}
      </div>
      {openIndex !== null && (
        <ImageLightbox
          images={shown}
          index={openIndex}
          onClose={() => setOpenIndex(null)}
          onIndexChange={setOpenIndex}
        />
      )}
    </>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/chatbot/ListingImageGallery.tsx
git commit -m "feat: add ListingImageGallery thumbnails + lightbox wrapper"
```

---

### Task 6: Wire gallery + detail link into `ChatPanel`

**Files:**
- Modify: `frontend/components/chatbot/ChatPanel.tsx`

**Interfaces:**
- Consumes: `ListingImageGallery` (Task 5), `getSourceImages`, `getListingDetailHref` (Task 3)

- [ ] **Step 1: Add imports**

Add to the existing import from `lucide-react`: `ExternalLink`.
Add to the existing import from `@/lib/chatSourceDisplay`: `getSourceImages`, `getListingDetailHref`.
Add a new import: `import ListingImageGallery from "./ListingImageGallery";`

- [ ] **Step 2: Render gallery + link in the listing branch**

Find (around line 252):
```jsx
                                <div className="mt-1 text-muted-foreground">
                                  {listingDetails.join(" · ")}
                                </div>
                              </>
```
Replace with:
```jsx
                                <div className="mt-1 text-muted-foreground">
                                  {listingDetails.join(" · ")}
                                </div>
                                <ListingImageGallery
                                  images={getSourceImages(source)}
                                />
                                {getListingDetailHref(source) && (
                                  <a
                                    href={getListingDetailHref(source)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="mt-1 inline-flex items-center gap-1 text-primary hover:underline"
                                  >
                                    <ExternalLink size={11} className="shrink-0" />
                                    Xem chi tiết
                                  </a>
                                )}
                              </>
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chatbot/ChatPanel.tsx
git commit -m "feat: show listing gallery + detail link in ChatPanel sources"
```

---

### Task 7: Wire gallery + detail link into `ChatWidget`

**Files:**
- Modify: `frontend/components/chatbot/ChatWidget.tsx`

**Interfaces:**
- Consumes: `ListingImageGallery` (Task 5), `getSourceImages`, `getListingDetailHref` (Task 3)

- [ ] **Step 1: Add imports**

Add to the existing import from `lucide-react`: `ExternalLink`.
Add to the existing import from `@/lib/chatSourceDisplay`: `getSourceImages`, `getListingDetailHref`.
Add a new import: `import ListingImageGallery from "./ListingImageGallery";`

- [ ] **Step 2: Render gallery + link in the listing branch**

Find (around line 274):
```jsx
                                  <div className="mt-1 text-muted-foreground">
                                    {listingDetails.join(" · ")}
                                  </div>
                                </>
```
Replace with:
```jsx
                                  <div className="mt-1 text-muted-foreground">
                                    {listingDetails.join(" · ")}
                                  </div>
                                  <ListingImageGallery
                                    images={getSourceImages(source)}
                                  />
                                  {getListingDetailHref(source) && (
                                    <a
                                      href={getListingDetailHref(source)}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="mt-1 inline-flex items-center gap-1 text-primary hover:underline"
                                    >
                                      <ExternalLink size={11} className="shrink-0" />
                                      Xem chi tiết
                                    </a>
                                  )}
                                </>
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chatbot/ChatWidget.tsx
git commit -m "feat: show listing gallery + detail link in ChatWidget sources"
```

---

## Manual verification (after all tasks)

1. Rebuild: `docker compose up -d --build agent-service backend frontend` (or run frontend dev).
2. Ask the chatbot: "tìm căn hộ 2 phòng ngủ ở Nam Từ Liêm dưới 7 tỷ".
3. Confirm: each listing source card shows up to 3 thumbnails; clicking a thumbnail opens the lightbox (✕ / Esc / arrows / backdrop close it); "Xem chi tiết" opens the listing page in a new tab; a listing with no images shows the card without an image row; a broken image URL is hidden without breaking layout.

## Self-Review

- **Spec coverage:** backend image fetch (Task 1–2), gallery (Task 5), lightbox (Task 4), detail link new-tab (Task 6–7), both render sites (Task 6 ChatPanel + Task 7 ChatWidget), edge cases (empty/broken handled in Task 5; single-image no-arrows in Task 4). Covered.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `ImageLightbox` props `{images,index,onClose,onIndexChange}` used identically by `ListingImageGallery`; `getSourceImages`/`getListingDetailHref` signatures match their call sites in Tasks 6–7.
