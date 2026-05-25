import pytest

from data_pipeline import enrich


@pytest.mark.asyncio
async def test_build_geocoder_warns_for_unsupported_provider(caplog):
    caplog.set_level("WARNING", logger="data_pipeline.enrich")

    geocoder = enrich.build_geocoder(provider="goong", user_agent="test/0.1", goong_api_key="")

    coord = await geocoder.geocode("Quận 7, Hồ Chí Minh")

    assert coord is None
    assert any("goong" in record.message.lower() for record in caplog.records)


@pytest.mark.asyncio
async def test_build_geocoder_returns_nominatim_for_default_provider():
    geocoder = enrich.build_geocoder(provider="nominatim", user_agent="test/0.1", goong_api_key="")
    assert isinstance(geocoder, enrich.NominatimGeocoder)


@pytest.mark.asyncio
async def test_build_geocoder_warns_for_unknown_provider(caplog):
    caplog.set_level("WARNING", logger="data_pipeline.enrich")

    geocoder = enrich.build_geocoder(provider="bogus", user_agent="test/0.1", goong_api_key="")

    assert await geocoder.geocode("X") is None
    assert any("bogus" in record.message.lower() for record in caplog.records)
