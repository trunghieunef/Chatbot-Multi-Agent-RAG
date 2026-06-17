from app.models import Article, ArticleImage, ProjectImage


def test_article_model_exposes_metadata_json():
    columns = {col.name for col in Article.__table__.columns}
    assert "metadata_json" in columns


def test_article_project_image_models_are_exported():
    assert ArticleImage.__tablename__ == "article_images"
    assert ProjectImage.__tablename__ == "project_images"
