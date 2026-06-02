---
paths:
  - Crawl/**/*
  - batdongsancom-crawler/**/*
---
# Crawler Conventions

- Tool: Playwright + playwright-stealth for anti-bot bypass.
- Parallelism: 8 workers for URL crawling, 4 workers for detail crawling.
- Output: CSV files in `data/`.
- Anti-detection: stealth mode, random delays (1-3s), user-agent rotation, browser restart every 15-20 pages.
- Resume support: skips already-crawled product_ids from output + tmp files.
- Crash-safe: each worker writes to its own `.tmp` file, merged at end.
- Deduplication: by `product_id` during merge step.
- Detail fields: 20+ fields including title, price, area, bedrooms, bathrooms, direction, legal status, address, description.
