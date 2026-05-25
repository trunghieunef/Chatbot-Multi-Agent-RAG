import pytest

from data_pipeline.ingestors.listings_ingestor import enrich_listing_data


class StubGeocoder:
    def __init__(self, coord):
        self.coord = coord
        self.calls = []

    async def geocode(self, address):
        self.calls.append(address)
        return self.coord


class StubIntent:
    def __init__(self, tags):
        self.tags = tags
        self.calls = []

    async def extract(self, content):
        self.calls.append(content)
        return list(self.tags)


@pytest.mark.asyncio
async def test_enrich_listing_data_fills_lat_lon_and_tags():
    listing = {
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Gần trường học, view sông",
    }
    geocoder = StubGeocoder((10.73, 106.72))
    intent = StubIntent(["gần trường", "view sông"])

    enriched = await enrich_listing_data(listing, geocoder=geocoder, intent_extractor=intent)

    assert enriched["latitude"] == 10.73
    assert enriched["longitude"] == 106.72
    assert enriched["intent_tags"] == ["gần trường", "view sông"]


@pytest.mark.asyncio
async def test_enrich_listing_data_skips_geocode_for_blank_address():
    listing = {"address": "", "description": "..."}
    geocoder = StubGeocoder(None)
    intent = StubIntent([])

    enriched = await enrich_listing_data(listing, geocoder=geocoder, intent_extractor=intent)

    assert enriched["latitude"] is None
    assert enriched["longitude"] is None
    assert geocoder.calls == []
