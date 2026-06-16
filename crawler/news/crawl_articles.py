"""
Compatibility wrapper for the news crawler.

The news pipeline now follows the same two-stage contract as listings and
projects:

    crawl_urls -> crawl_details -> ingest

This module preserves the older ``python -m crawler.news.crawl_articles`` CLI
by running both stages in sequence.
"""

from __future__ import annotations

import argparse

from crawler.news import crawl_details, crawl_urls

FIELDS = crawl_details.FIELDS
extract_article_urls = crawl_urls.extract_article_urls
parse_article_listing = crawl_urls.parse_article_listing
parse_article = crawl_details.parse_article
parse_article_page = crawl_details.parse_article_page


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl news URLs, then crawl article details from batdongsan.com.vn/tin-tuc"
    )
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 50],
        metavar=("START", "END"), help="page range (default: 1 50)",
    )
    parser.add_argument(
        "--urls-output", default="data/raw/news_urls.csv",
        help="intermediate URL CSV file (default: data/raw/news_urls.csv)",
    )
    parser.add_argument(
        "--output", default="data/raw/news_articles.csv",
        help="article detail CSV file (default: data/raw/news_articles.csv)",
    )
    parser.add_argument("--workers", type=int, default=4, help="parallel workers (default: 4)")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max detail URLs to crawl after URL discovery (0 = all). Useful for testing.",
    )
    args = parser.parse_args()

    crawl_urls.run(
        pages=(args.pages[0], args.pages[1]),
        output=args.urls_output,
        workers=args.workers,
    )
    crawl_details.run(
        input_file=args.urls_output,
        output=args.output,
        workers=args.workers,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
