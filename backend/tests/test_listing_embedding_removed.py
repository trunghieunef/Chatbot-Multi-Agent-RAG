from app.models import Listing


def test_listing_model_no_longer_has_embedding_column():
    columns = {col.name for col in Listing.__table__.columns}
    assert "embedding" not in columns


def test_production_chatbot_no_longer_references_listing_embedding():
    import inspect

    import app.services.chatbot.agents.property as property_agent
    import app.services.chatbot.agents.legal as legal_agent
    import app.services.rag.simple_rag as simple_rag

    checked_sources = [
        inspect.getsource(property_agent),
        inspect.getsource(legal_agent),
        inspect.getsource(simple_rag),
    ]

    assert all("Listing.embedding" not in source for source in checked_sources)


def test_production_chatbot_uses_backend_hybrid_search_not_root_scaffold():
    import inspect

    import app.services.chatbot.agents.property as property_agent
    import app.services.chatbot.agents.legal as legal_agent
    import app.services.rag.simple_rag as simple_rag

    checked_sources = [
        inspect.getsource(property_agent),
        inspect.getsource(legal_agent),
        inspect.getsource(simple_rag),
    ]

    assert all("chatbot.tools.hybrid_search" not in source for source in checked_sources)
