from app.models import Article


def test_article_model_exposes_metadata_json():
    columns = {col.name for col in Article.__table__.columns}
    assert "metadata_json" in columns
