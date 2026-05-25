from app.config import Settings


def test_m2_settings_defaults(monkeypatch):
    for var in (
        "GEOCODER_PROVIDER",
        "GEOCODER_USER_AGENT",
        "GEOCODER_RATE_LIMIT_SECONDS",
        "GOONG_API_KEY",
        "INTENT_EXTRACTOR",
        "GEMINI_INTENT_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.GEOCODER_PROVIDER == "nominatim"
    assert settings.GEOCODER_USER_AGENT.startswith("realestate-chatbot")
    assert settings.GEOCODER_RATE_LIMIT_SECONDS == 1.0
    assert settings.GOONG_API_KEY == ""
    assert settings.INTENT_EXTRACTOR == "rule"
    assert settings.GEMINI_INTENT_MODEL == "gemini-2.0-flash"
