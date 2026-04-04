# batdongsan.com.vn Real Estate Data Pipeline

Crawl, clean, and analyze real estate listing data from [batdongsan.com.vn](https://batdongsan.com.vn/nha-dat-ban).

Uses headless Chrome via Playwright with stealth to bypass bot detection. Supports parallel workers for fast crawling.

## Pipeline (3 Steps)

### Step 1: Crawl listing URLs

```bash
python crawl_listing_url.py --pages 1 10223 --workers 8 --output ../listing_url.csv
```

Crawls the listing index pages and collects `product_id` + `url` for each listing. Output: `listing_url.csv`

### Step 2: Crawl listing details

```bash
python crawl_listing_details.py --workers 4
python crawl_listing_details.py --input ../listing_url.csv --output ../listing_details.csv --workers 4
python crawl_listing_details.py --limit 100    # test with first 100 URLs
```

Reads URLs from `listing_url.csv`, visits each detail page, and extracts all property information. Output: `listing_details.csv`

**Features:**
- **Resume support**: automatically skips already-crawled listings (safe to restart)
- **Parallel workers**: each runs its own Chromium browser instance
- **Crash-safe**: each worker writes to its own `.tmp` file
- **Auto-merge**: results are deduplicated and merged at the end

### Step 3: Merge (manual, if needed)

```bash
python merge.py                                # merge listing_details tmp files
python merge.py --output ../listing_url.csv    # merge listing_url tmp files
python merge.py --keep-tmp                     # keep tmp files after merge
```

Standalone tool to merge worker `.tmp` files if the crawl was interrupted before auto-merge.

## Extracted fields (detail page)

| Field | Example |
|-------|---------|
| `product_id` | `45179819` |
| `title` | `Căn hộ 2PN Vinhomes Grand Park` |
| `price_text` | `4,68 tỷ` |
| `area_text` | `71 m²` |
| `price_per_m2_text` | `65,92 triệu/m²` |
| `bedrooms` | `2 PN` |
| `bathrooms` | `2 phòng` |
| `direction` | `Đông - Bắc` |
| `balcony_direction` | `Tây - Nam` |
| `floors` | `4 tầng` |
| `frontage` | `5 m` |
| `road_width` | `8 m` |
| `legal` | `Sổ đỏ/ Sổ hồng` |
| `furniture` | `Cơ bản` |
| `property_type` | `Nhà ở` |
| `address` | `Bán, Hồ Chí Minh, Quận 7, Nhà riêng tại đường Lâm Văn Bền` |
| `description` | Full listing description text |
| `post_date` | `15/03/2026` |
| `expiry_date` | `22/03/2026` |
| `listing_type` | `Tin VIP Kim Cương` |
| `contact_name` | `Nguyễn Văn A` |
| `url` | Full listing URL |

## Setup

```bash
pip install playwright playwright-stealth
python -m playwright install chromium
```

## How it works

1. **Step 1** crawls index pages and saves `product_id` + `url` to `listing_url.csv`
2. **Step 2** reads those URLs, visits each detail page, and extracts all property data
3. Each worker launches its own headless Chrome and crawls its assigned URLs
4. A fresh browser context is created per page to avoid bot detection
5. Browser is restarted every 15 pages to prevent memory leaks
6. Each worker writes results to its own `.tmp` CSV file (crash-safe)
7. After all workers finish, `.tmp` files are merged, deduplicated into the final CSV
8. If the crawl is interrupted, re-run the same command — it resumes automatically

## Data cleaning

```bash
python clean.py
```

Produces `apartments_cleaned.csv` and `apartments.db` (SQLite) with:

- **Parsed numeric columns**: `price_billion` (tỷ), `area_m2`, `price_per_m2_million` (triệu/m²)
- **Missing value handling**: drops empty titles, converts bedrooms/bathrooms to nullable ints
- **Standardized locations**: strips "(... mới)" suffixes

## Notes

- Each index page has ~20 listings. The site currently has ~45,000+ total listings.
- Price values are in Vietnamese format (`4,68 tỷ` = 4.68 billion VND).
- Workers: 4 is recommended for detail crawling (~8s per listing). Higher counts risk getting blocked.
- Memory: ~150MB per worker (Chromium instance).
- With 4 workers, full crawl of ~45k listings takes approximately 25-30 hours.
- If the crawl is interrupted, `.tmp` files preserve all progress. Just re-run — resume is automatic.
