from app.routers.projects import apply_project_filters, apply_project_sort
from app.schemas.project import ProjectCardResponse


class ProjectStub:
    id = 1
    name = "Sun Festo Town"
    slug = "sun-festo-town"
    developer = "Sun Group"
    location = "Ha Long, Quang Ninh"
    district = "Ha Long"
    city = "Quang Ninh"
    total_units = 1200
    price_range = "3 - 8 ty"
    area_range = "45 - 120 m2"
    status = "selling"
    project_type = "apartment"
    description = "Project overview"
    amenities = ["pool", "park"]
    url = "https://example.test/project"
    created_at = None
    updated_at = None


def test_project_card_response_accepts_model_attributes():
    response = ProjectCardResponse.model_validate(ProjectStub())

    assert response.name == "Sun Festo Town"
    assert response.slug == "sun-festo-town"
    assert response.amenities == ["pool", "park"]


def test_project_filters_apply_search_and_location():
    params = {
        "search": "festo",
        "city": "Quang Ninh",
        "district": "Ha Long",
        "project_type": "apartment",
        "status": "selling",
    }

    query = apply_project_filters(None, params)

    assert query is not None


def test_project_sort_supports_known_options():
    assert apply_project_sort(None, "newest") is not None
    assert apply_project_sort(None, "name_asc") is not None
    assert apply_project_sort(None, "name_desc") is not None
