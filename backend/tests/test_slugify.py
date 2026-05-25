from data_pipeline.clean import slugify


def test_slugify_strips_diacritics_and_lowers():
    assert slugify("Luật Đất đai 2024") == "luat-dat-dai-2024"
    assert slugify("Nghị định 99/2024/NĐ-CP") == "nghi-dinh-99-2024-nd-cp"
    assert slugify("") == ""
