from data_pipeline.ingestors.projects_ingestor import build_project_chunks


def test_build_project_chunks_creates_overview_and_amenities_chunks():
    project = {
        "slug": "vinhomes-grand-park",
        "name": "Vinhomes Grand Park",
        "developer": "Vinhomes",
        "district": "Quận 9",
        "city": "Hồ Chí Minh",
        "price_range": "2,5 - 4,8 tỷ",
        "area_range": "55 - 120 m²",
        "status": "selling",
        "description": "Khu đô thị tích hợp.",
        "amenities": ["Hồ bơi", "Công viên"],
    }

    chunks = build_project_chunks(project)
    chunk_types = [chunk["chunk_type"] for chunk in chunks]

    assert "overview" in chunk_types
    assert "description" in chunk_types
    assert "amenities" in chunk_types
