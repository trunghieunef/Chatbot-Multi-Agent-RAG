import importlib


def test_repo_root_packages_are_importable():
    importlib.import_module("etl.data_pipeline")
    importlib.import_module("chatbot")
