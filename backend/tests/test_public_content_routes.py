from app.main import app


def test_public_content_routes_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/projects" in paths
    assert "/api/v1/articles" in paths
