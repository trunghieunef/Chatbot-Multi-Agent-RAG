from app.models import Listing


def test_listing_model_no_longer_has_embedding_column():
    columns = {col.name for col in Listing.__table__.columns}
    assert "embedding" not in columns
