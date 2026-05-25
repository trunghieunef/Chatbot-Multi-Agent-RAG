import asyncio

from data_pipeline.ingestors.listings_ingestor import load_csv_to_db, main


__all__ = ["load_csv_to_db"]


if __name__ == "__main__":
    asyncio.run(main())
