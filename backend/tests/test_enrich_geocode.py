import pytest

from data_pipeline.enrich import NominatimGeocoder


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        return FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_nominatim_returns_first_result_lat_lon():
    client = FakeClient([{"lat": "10.7", "lon": "106.7"}])
    geocoder = NominatimGeocoder(user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: client)

    coord = await geocoder.geocode("Quận 7, Hồ Chí Minh")

    assert coord == (10.7, 106.7)
    assert client.calls[0][1]["q"] == "Quận 7, Hồ Chí Minh"
    assert client.calls[0][2]["User-Agent"] == "test/0.1"


@pytest.mark.asyncio
async def test_nominatim_returns_none_for_empty_response():
    geocoder = NominatimGeocoder(
        user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: FakeClient([])
    )

    assert await geocoder.geocode("không tồn tại") is None


@pytest.mark.asyncio
async def test_nominatim_returns_none_for_blank_address():
    geocoder = NominatimGeocoder(user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: FakeClient([]))

    assert await geocoder.geocode("") is None
