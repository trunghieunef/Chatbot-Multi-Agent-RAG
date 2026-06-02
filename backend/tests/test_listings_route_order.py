from app.main import app


def test_static_listing_routes_are_registered_before_listing_id_route():
    paths = [
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/listings")
    ]

    detail_index = paths.index("/api/v1/listings/{listing_id}")

    assert paths.index("/api/v1/listings/by-product-id/{product_id}") < detail_index
    assert paths.index("/api/v1/listings/similar/{listing_id}") < detail_index
