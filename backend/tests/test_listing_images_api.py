from app.routers.listings import listing_card_response, listing_detail_response


class ListingStub:
    id = 42
    product_id = "p42"
    listing_type = "sale"
    property_type = "apartment"
    title = "Can ho co anh"
    description = "Mo ta"
    price = None
    price_unit = None
    price_text = "5 ty"
    price_per_m2 = None
    price_per_m2_text = None
    area = None
    area_text = "70 m2"
    bedrooms = None
    bathrooms = None
    floors = None
    direction = None
    balcony_direction = None
    frontage = None
    road_width = None
    legal_status = None
    furniture = None
    address = None
    ward = None
    district = None
    city = None
    latitude = None
    longitude = None
    contact_name = None
    contact_phone = None
    post_date = None
    expiry_date = None
    url = None
    badge = None
    created_at = None


def test_listing_card_response_includes_primary_image_url():
    response = listing_card_response(
        ListingStub(),
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert response.primary_image_url == "https://cdn.example.test/a.jpg"
    assert response.image_urls == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.jpg",
    ]


def test_listing_detail_response_includes_all_image_urls():
    response = listing_detail_response(
        ListingStub(),
        ["https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"],
    )

    assert response.primary_image_url == "https://cdn.example.test/a.jpg"
    assert response.image_urls == [
        "https://cdn.example.test/a.jpg",
        "https://cdn.example.test/b.jpg",
    ]
