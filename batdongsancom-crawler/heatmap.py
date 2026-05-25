#!/usr/bin/env python3
"""Generate a choropleth heatmap of median apartment price/m² on Vietnam's new 34-province map."""

import json
import math
import sqlite3
import geopandas as gpd
import folium
import pandas as pd
import numpy as np

# --- Old GeoJSON province name -> New 34-province name (2025 reform) ---
GEOJSON_TO_NEW = {
    "An Giang": "An Giang",
    "Bà Rịa -Vũng Tàu": "Hồ Chí Minh",
    "Bình Dương": "Hồ Chí Minh",
    "Bình Phước": "Đồng Nai",
    "Bình Thuận": "Lâm Đồng",
    "Bình Định": "Gia Lai",
    "Bạc Liêu": "Cà Mau",
    "Bắc Giang": "Bắc Ninh",
    "Bắc Kạn": "Thái Nguyên",
    "Bắc Ninh": "Bắc Ninh",
    "Bến Tre": "Vĩnh Long",
    "Cao Bằng": "Cao Bằng",
    "Cà Mau": "Cà Mau",
    "Cần Thơn": "Cần Thơ",  # typo in GeoJSON
    "Gia Lai": "Gia Lai",
    "Hà Giang": "Tuyên Quang",
    "Hà Nam": "Ninh Bình",
    "Hà Nội": "Hà Nội",
    "Hà Tĩnh": "Hà Tĩnh",
    "Hòa Bình": "Phú Thọ",
    "Hưng Yên": "Hưng Yên",
    "Hải Dương": "Hải Phòng",
    "Hải Phòng": "Hải Phòng",
    "Hậu Giang": "Cần Thơ",
    "Khánh Hòa": "Khánh Hòa",
    "Kien Giang": "An Giang",  # typo in GeoJSON
    "Kon Tum": "Quảng Ngãi",
    "Lai Châu": "Lai Châu",
    "Long An": "Tây Ninh",
    "Lào Cai": "Lào Cai",
    "Lâm Đồng": "Lâm Đồng",
    "Lạng Sơn": "Lạng Sơn",
    "Nam Định": "Ninh Bình",
    "Nghệ An": "Nghệ An",
    "Ninh Bình": "Ninh Bình",
    "Ninh Thuận": "Khánh Hòa",
    "Phú Thọ": "Phú Thọ",
    "Phú Yên": "Đắk Lắk",
    "Quản Bình": "Quảng Trị",  # typo in GeoJSON
    "Quảng Nam": "Đà Nẵng",
    "Quảng Ngãi": "Quảng Ngãi",
    "Quảng Ninh": "Quảng Ninh",
    "Quảng Trị": "Quảng Trị",
    "Sóc Trăng": "Cần Thơ",
    "Sơn La": "Sơn La",
    "TP. Hồ Chí Minh": "Hồ Chí Minh",
    "Thanh Hóa": "Thanh Hóa",
    "Thái Bình": "Hưng Yên",
    "Thái Nguyên": "Thái Nguyên",
    "Thừa Thiên Huế": "Thừa Thiên Huế",
    "Tiền Giang": "Đồng Tháp",
    "Trà Vinh": "Vĩnh Long",
    "Tuyên Quang": "Tuyên Quang",
    "Tây Ninh": "Tây Ninh",
    "Vĩnh Long": "Vĩnh Long",
    "Vĩnh Phúc": "Phú Thọ",
    "Yên Bái": "Lào Cai",
    "Điện Biên": "Điện Biên",
    "Đà Nẵng": "Đà Nẵng",
    "Đăk Lăk": "Đắk Lắk",
    "Đăk Nông": "Lâm Đồng",
    "Đồng Nai": "Đồng Nai",
    "Đồng Tháp": "Đồng Tháp",
}

# --- Our data location names -> New 34-province name ---
DATA_TO_NEW = {
    "Bà Rịa - Vũng Tàu": "Hồ Chí Minh",
    "Bình Dương": "Hồ Chí Minh",
    "Bình Thuận": "Lâm Đồng",
    "Bình Định": "Gia Lai",
    "Bắc Giang": "Bắc Ninh",
    "Bắc Ninh": "Bắc Ninh",
    "Cần Thơ": "Cần Thơ",
    "Hà Nam": "Ninh Bình",
    "Hà Nội": "Hà Nội",
    "Hưng Yên": "Hưng Yên",
    "Hải Dương": "Hải Phòng",
    "Hải Phòng": "Hải Phòng",
    "Hồ Chí Minh": "Hồ Chí Minh",
    "Khánh Hòa": "Khánh Hòa",
    "Kiên Giang": "An Giang",
    "Long An": "Tây Ninh",
    "Lào Cai": "Lào Cai",
    "Lâm Đồng": "Lâm Đồng",
    "Nghệ An": "Nghệ An",
    "Ninh Thuận": "Khánh Hòa",
    "Phú Thọ": "Phú Thọ",
    "Phú Yên": "Đắk Lắk",
    "Quảng Bình": "Quảng Trị",
    "Quảng Ninh": "Quảng Ninh",
    "Thanh Hóa": "Thanh Hóa",
    "Thái Bình": "Hưng Yên",
    "Thái Nguyên": "Thái Nguyên",
    "Thừa Thiên Huế": "Thừa Thiên Huế",
    "Tiền Giang": "Đồng Tháp",
    "Tây Ninh": "Tây Ninh",
    "Vĩnh Phúc": "Phú Thọ",
    "Đà Nẵng": "Đà Nẵng",
    "Đắk Lắk": "Đắk Lắk",
    "Đồng Nai": "Đồng Nai",
}


def build_new_geojson():
    """Merge old 63-province GeoJSON into new 34-province boundaries."""
    gdf = gpd.read_file("vn_old.json")
    gdf["new_province"] = gdf["ten_tinh"].map(GEOJSON_TO_NEW)
    merged = gdf.dissolve(by="new_province").reset_index()
    return merged


def get_median_prices():
    """Get median price_per_m2 by new province, aggregating ALL listings across merged provinces."""
    con = sqlite3.connect("apartments.db")
    df = pd.read_sql(
        "SELECT location, price_per_m2_million FROM apartments WHERE price_per_m2_million IS NOT NULL",
        con,
    )
    con.close()
    # Map old location to new province BEFORE computing median
    df["new_province"] = df["location"].map(DATA_TO_NEW)
    stats = df.groupby("new_province")["price_per_m2_million"].agg(["median", "count"]).reset_index()
    stats.columns = ["new_province", "median_price_per_m2", "listing_count"]
    print(stats.to_string(index=False))
    return stats


def main():
    print("Building merged 34-province GeoJSON...")
    gdf = build_new_geojson()

    print("Calculating median prices...")
    prices = get_median_prices()

    gdf = gdf.merge(prices, on="new_province", how="left")

    print(f"Provinces with data: {gdf['median_price_per_m2'].notna().sum()}/34")

    # Build folium map
    m = folium.Map(location=[16.0, 106.0], zoom_start=6, tiles="cartodbpositron")

    folium.Choropleth(
        geo_data=gdf.to_json(),
        data=gdf,
        columns=["new_province", "median_price_per_m2"],
        key_on="feature.properties.new_province",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.3,
        nan_fill_color="#e0e0e0",
        legend_name="Median price (triệu VND/m²)",
    ).add_to(m)

    # Add bubbles sized by listing count
    max_count = gdf["listing_count"].max()
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid
        price = row["median_price_per_m2"]
        count = row.get("listing_count", 0)
        if pd.isna(count) or count == 0:
            continue

        # Scale radius: sqrt to make area proportional to count, capped for readability
        radius = max(4, math.sqrt(count / max_count) * 40)

        label = f"<b>{row['new_province']}</b><br>Median: {price:.1f} tr/m²<br>Listings: {int(count):,}"
        folium.CircleMarker(
            location=[centroid.y, centroid.x],
            radius=radius,
            color="#333",
            weight=1,
            fill=True,
            fill_color="#e74c3c",
            fill_opacity=0.5,
            tooltip=folium.Tooltip(label),
        ).add_to(m)

    m.save("heatmap.html")
    print("Saved to heatmap.html — open in browser")


if __name__ == "__main__":
    main()
