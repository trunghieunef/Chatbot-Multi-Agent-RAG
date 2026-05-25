import pytest

from data_pipeline.enrich import GeminiIntentExtractor


class FakeResp:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents))
        return FakeResp(self.payload)


class FakeClient:
    def __init__(self, payload):
        self.models = FakeModels(payload)


@pytest.mark.asyncio
async def test_gemini_intent_extractor_parses_json_array():
    client = FakeClient('{"tags": ["gần trường", "view sông"]}')
    extractor = GeminiIntentExtractor(api_key="k", client=client, model="gemini-2.0-flash")

    tags = await extractor.extract("Căn hộ gần trường, view sông đẹp.")

    assert tags == ["gần trường", "view sông"]


@pytest.mark.asyncio
async def test_gemini_intent_extractor_returns_empty_on_invalid_json():
    extractor = GeminiIntentExtractor(api_key="k", client=FakeClient("not json"))

    assert await extractor.extract("nội dung") == []


@pytest.mark.asyncio
async def test_gemini_intent_extractor_returns_empty_for_blank_input():
    extractor = GeminiIntentExtractor(api_key="k", client=FakeClient('{"tags": []}'))

    assert await extractor.extract("") == []
