# Hiển thị ảnh listing trong kết quả chatbot (gallery + lightbox)

**Ngày:** 2026-06-24
**Trạng thái:** Đã duyệt thiết kế, chờ review spec

## Mục tiêu

Khi chatbot trả về các tin bất động sản (listing), mỗi card nguồn hiển thị một
hàng **tối đa 3 ảnh thumbnail**. Bấm vào ảnh mở **lightbox** phóng to xem ngay
trong chat (không rời trang); dòng "Xem chi tiết" sẵn có vẫn giữ nguyên để đi
tới trang listing đầy đủ.

Phi mục tiêu (YAGNI): không tải/host ảnh về server (chỉ dùng `image_url` gốc);
không resize ảnh; không thêm ảnh cho nguồn không phải listing (market/pháp lý).

## Kiến trúc & luồng dữ liệu

```
listing_images (DB)
  └─► resolve_to_listing_records()  → record["images"] = [url, ...]   (BACKEND)
        └─► property_search_agent  → AgentSource.metadata["images"]    (đã có sẵn)
              └─► public API sources[].metadata.images
                    └─► <ListingImageGallery images=...>               (FRONTEND)
                          ├─ hàng thumbnail (lazy)
                          └─ <ImageLightbox> khi bấm ảnh
```

Agent đã sẵn `metadata={"images": listing.get("images", [])}` → **không sửa
agent**. Chỉ cần backend đổ ảnh vào record, và frontend render.

## Thành phần

### 1. Backend — `resolve_to_listing_records` (`backend/app/services/rag/hybrid_search.py`)

- Sau khi nạp listings theo `ids`, query bảng `listing_images` cho các
  `listing_id` đó:
  ```sql
  SELECT listing_id, image_url
  FROM listing_images
  WHERE listing_id = ANY(:ids)
  ORDER BY listing_id, is_primary DESC, sort_order ASC
  ```
- Gom theo `listing_id`, **cắt tối đa 3 ảnh/listing**, gắn `record["images"]`.
- Dùng index sẵn có `ix_listing_images_listing_order (listing_id, sort_order)`.
- Tin không có ảnh → `images = []`.

### 2. Frontend — component dùng chung `ListingImageGallery.tsx`

Một component đóng gói cả hàng thumbnail lẫn lightbox, để **ChatPanel.tsx** và
**ChatWidget.tsx** chỉ cần gọi `<ListingImageGallery images={...} />` (tránh lặp
logic ở hai chỗ render card).

- Props: `images: string[]`.
- Render tối đa 3 `<img>`: kích thước cố định (~64×64), `object-cover`, bo góc,
  `loading="lazy"`; `onError` → ẩn ảnh hỏng.
- State nội bộ: `openIndex: number | null`. Bấm thumbnail thứ `i` → `openIndex=i`.
- Render `<ImageLightbox>` khi `openIndex !== null`.
- `images` rỗng → render `null` (card như cũ).

### 3. Frontend — `ImageLightbox.tsx`

- Props: `images: string[]`, `index: number`, `onClose: () => void`,
  `onIndexChange: (i) => void`.
- Overlay cố định phủ toàn màn (z cao), nền tối mờ; ảnh phóng to ở giữa.
- Icon `lucide-react`: `X` (đóng), `ChevronLeft`/`ChevronRight` (prev/next).
- Đóng khi: bấm ✕, bấm nền tối, nhấn `Esc`. Chỉ tiến/lùi khi `images.length > 1`.

### 4. Link "Xem chi tiết" trong card (mở tab mới)

**Hiện trạng:** nội dung trả lời được render plain text
(`<p className="whitespace-pre-wrap">{msg.content}</p>`), KHÔNG phải markdown —
nên `[Xem chi tiết](url)` và `![Ảnh](url)` agent tạo ra chỉ là chữ thô, không
bấm được; card nguồn là `<div>` không có link. Vì vậy cần thêm link thật.

- Trong card nguồn loại listing, thêm link "Xem chi tiết" trỏ tới
  `source.url` (link gốc) hoặc fallback `/nha-dat-ban/{id}`:
  ```jsx
  <a href={detailHref} target="_blank" rel="noopener noreferrer">Xem chi tiết</a>
  ```
- **`target="_blank"`** → mở **tab mới**, không điều hướng trong khung chat
  (giữ nguyên cuộc trò chuyện). `rel="noopener noreferrer"` cho an toàn.
- Phân biệt hành vi: bấm **thumbnail** = mở lightbox tại chỗ (không điều hướng);
  bấm **"Xem chi tiết"** = mở tab mới sang trang chi tiết.
- Không có `detailHref` → ẩn link.

## Types

- `frontend/lib/types.ts`: đảm bảo kiểu source có `metadata?: { images?: string[]; ... }`
  để truy cập `source.metadata.images` an toàn (mở rộng nếu chưa có).

## Edge cases

- Tin không có ảnh → không hiện hàng ảnh.
- Ảnh 404/hỏng → `onError` ẩn ảnh đó; khung cố định nên layout không vỡ.
- Nguồn không phải listing → `metadata.images` không có → không render gallery.
- `images.length === 1` → lightbox không hiện mũi tên prev/next.

## Testing

- **Backend:** test `resolve_to_listing_records` gắn đúng `images` cho từng record,
  ưu tiên `is_primary` rồi `sort_order`, **cắt tối đa 3** (theo cách mock DB như
  các test resolve hiện có trong `tests/test_hybrid_search*.py`).
- **Frontend:** `npm run lint`; kiểm tra thủ công lightbox (mở/đóng/prev/next/Esc)
  và fallback ảnh hỏng.

## Phạm vi thay đổi

- `backend/app/services/rag/hybrid_search.py` (resolve images)
- `backend/tests/test_hybrid_search*.py` (test)
- `frontend/components/chatbot/ListingImageGallery.tsx` (mới)
- `frontend/components/chatbot/ImageLightbox.tsx` (mới)
- `frontend/components/chatbot/ChatPanel.tsx` (gọi gallery)
- `frontend/components/chatbot/ChatWidget.tsx` (gọi gallery)
- `frontend/lib/types.ts` (kiểu metadata.images nếu cần)
