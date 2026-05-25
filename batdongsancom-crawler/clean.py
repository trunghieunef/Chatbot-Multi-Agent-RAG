#!/usr/bin/env python3
"""Clean apartments.csv: parse numerics, handle missing values, standardize locations."""

import re
import sqlite3
import pandas as pd

INPUT = "data/apartments.csv"
OUTPUT_CSV = "data/apartments_cleaned.csv"
OUTPUT_DB = "data/apartments.db"


# --- 1. Parse numeric values ---

def parse_price(text: str) -> float | None:
    """Parse price_text to float in tỷ (billion VND). Returns None if unparseable."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if text in ("Giá thỏa thuận", ""):
        return None

    # Replace Vietnamese decimal comma with dot
    num_str = text.split()[0].replace(",", ".")

    try:
        value = float(num_str)
    except ValueError:
        return None

    if "tỷ" in text:
        return value  # already in tỷ
    elif "triệu" in text:
        return value / 1000  # convert triệu to tỷ
    elif "nghìn" in text:
        return value / 1_000_000  # convert nghìn to tỷ
    return None


def parse_area(text: str) -> float | None:
    """Parse area_text like '61,8 m²' to float m²."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    num_str = text.replace("m²", "").replace(",", ".").strip()
    try:
        return float(num_str)
    except ValueError:
        return None


def parse_price_per_m2(text: str) -> float | None:
    """Parse price_per_m2_text to float in triệu/m². Returns None if unparseable."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if text in ("Thỏa thuận", ""):
        return None

    num_str = text.split()[0].replace(",", ".")
    try:
        value = float(num_str)
    except ValueError:
        return None

    if "tr/m²" in text:
        return value  # already in triệu/m²
    elif "tỷ/m²" in text:
        return value * 1000  # convert tỷ to triệu
    elif "nghìn/m²" in text:
        return value / 1000  # convert nghìn to triệu
    elif "đồng/m²" in text:
        return value / 1_000_000  # convert đồng to triệu
    return None


# --- 2. & 4. Location standardization ---

# Map raw location to standardized province/city name (strip the "(... mới)" suffixes)
LOCATION_MAP = {
    "Bà Rịa Vũng Tàu (Hồ Chí Minh mới)": "Bà Rịa - Vũng Tàu",
    "Bình Dương (Hồ Chí Minh mới)": "Bình Dương",
    "Bình Thuận (Lâm Đồng mới)": "Bình Thuận",
    "Bình Định (Gia Lai mới)": "Bình Định",
    "Bắc Giang (Bắc Ninh mới)": "Bắc Giang",
    "Hà Nam (Ninh Bình mới)": "Hà Nam",
    "Hải Dương (Hải Phòng mới)": "Hải Dương",
    "Kiên Giang (An Giang mới)": "Kiên Giang",
    "Long An (Tây Ninh mới)": "Long An",
    "Ninh Thuận (Khánh Hòa mới)": "Ninh Thuận",
    "Phú Yên (Đắk Lắk mới)": "Phú Yên",
    "Quảng Bình (Quảng Trị mới)": "Quảng Bình",
    "Thái Bình (Hưng Yên mới)": "Thái Bình",
    "Thừa Thiên Huế (Huế mới)": "Thừa Thiên Huế",
    "Tiền Giang (Đồng Tháp mới)": "Tiền Giang",
    "Vĩnh Phúc (Phú Thọ mới)": "Vĩnh Phúc",
}


def main():
    df = pd.read_csv(INPUT, dtype=str)
    print(f"Loaded {len(df)} rows")

    # --- 1. Parse numeric columns ---
    df["price_billion"] = df["price_text"].apply(parse_price)
    df["area_m2"] = df["area_text"].apply(parse_area)
    df["price_per_m2_million"] = df["price_per_m2_text"].apply(parse_price_per_m2)

    # --- 2. Handle missing values ---
    # Convert bedrooms/bathrooms to numeric (NaN for missing)
    df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce").astype("Int64")
    df["bathrooms"] = pd.to_numeric(df["bathrooms"], errors="coerce").astype("Int64")

    # Drop rows with no title
    before = len(df)
    df = df.dropna(subset=["title"])
    df = df[df["title"].str.strip() != ""]
    print(f"Dropped {before - len(df)} rows with empty title")

    # Fill price_per_m2 from price/area where missing but both available
    mask = df["price_per_m2_million"].isna() & df["price_billion"].notna() & df["area_m2"].notna()
    df.loc[mask, "price_per_m2_million"] = (
        df.loc[mask, "price_billion"] * 1000 / df.loc[mask, "area_m2"]
    ).round(2)
    print(f"Filled {mask.sum()} missing price_per_m2 values from price/area")

    # --- 4. Standardize location ---
    df["location"] = df["location"].replace(LOCATION_MAP)

    # Report
    print(f"\n--- Summary ---")
    print(f"Rows: {len(df)}")
    print(f"price_billion: {df['price_billion'].notna().sum()} valid, {df['price_billion'].isna().sum()} missing")
    print(f"area_m2: {df['area_m2'].notna().sum()} valid, {df['area_m2'].isna().sum()} missing")
    print(f"price_per_m2_million: {df['price_per_m2_million'].notna().sum()} valid, {df['price_per_m2_million'].isna().sum()} missing")
    print(f"bedrooms: {df['bedrooms'].notna().sum()} valid, {df['bedrooms'].isna().sum()} missing")
    print(f"bathrooms: {df['bathrooms'].notna().sum()} valid, {df['bathrooms'].isna().sum()} missing")
    print(f"\nLocations ({df['location'].nunique()} unique):")
    print(df["location"].value_counts().to_string())

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved to {OUTPUT_CSV}")

    # --- Export to SQLite ---
    db_df = df[["product_id", "title", "price_billion", "area_m2", "price_per_m2_million",
                "bedrooms", "bathrooms", "location", "post_date", "contact_name", "url"]].copy()

    con = sqlite3.connect(OUTPUT_DB)
    db_df.to_sql("apartments", con, if_exists="replace", index=False)

    # Create indexes for common query patterns
    cur = con.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_location ON apartments(location)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bedrooms ON apartments(bedrooms)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price ON apartments(price_billion)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_per_m2 ON apartments(price_per_m2_million)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_area ON apartments(area_m2)")
    con.commit()
    con.close()
    print(f"Saved to {OUTPUT_DB} (table: apartments)")


if __name__ == "__main__":
    main()
