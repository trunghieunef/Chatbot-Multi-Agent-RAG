from app.services.rag.hybrid_search import group_listing_images


def test_groups_and_caps_at_three_preserving_order():
    rows = [
        (1, "a1"), (1, "a2"), (1, "a3"), (1, "a4"),  # 4th must be dropped
        (2, "b1"),
    ]
    assert group_listing_images(rows) == {1: ["a1", "a2", "a3"], 2: ["b1"]}


def test_skips_empty_urls():
    rows = [(1, ""), (1, None), (1, "a1")]  # type: ignore[list-item]
    assert group_listing_images(rows) == {1: ["a1"]}


def test_empty_rows_returns_empty_dict():
    assert group_listing_images([]) == {}


def test_custom_limit():
    rows = [(1, "a1"), (1, "a2"), (1, "a3")]
    assert group_listing_images(rows, limit=2) == {1: ["a1", "a2"]}
