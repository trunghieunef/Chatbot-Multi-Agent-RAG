from data_pipeline.clean import row_to_project


def test_row_to_project_normalizes_string_fields_and_amenities():
    row = {
        "slug": "vinhomes-grand-park",
        "name": "Vinhomes Grand Park",
        "developer": "Vinhomes",
        "location": "Quận 9, Hồ Chí Minh",
        "district": "Quận 9",
        "city": "Hồ Chí Minh",
        "total_units": "10000",
        "price_range": "2,5 - 4,8 tỷ",
        "area_range": "55 - 120 m²",
        "status": "selling",
        "project_type": "apartment",
        "description": "Khu đô thị lớn",
        "amenities": '["Hồ bơi", "Gym", "Công viên"]',
        "url": "https://batdongsan.com.vn/du-an/vinhomes-grand-park",
    }

    project = row_to_project(row)

    assert project["slug"] == "vinhomes-grand-park"
    assert project["total_units"] == 10000
    assert project["amenities"] == ["Hồ bơi", "Gym", "Công viên"]


def test_row_to_project_handles_missing_amenities_and_units():
    row = {"slug": "x", "name": "X", "url": "u"}

    project = row_to_project(row)

    assert project["total_units"] is None
    assert project["amenities"] == []
