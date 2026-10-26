def text_or_empty(element) -> str:
    if element is None:
        return ""
    try:
        return " ".join(element.inner_text().split())
    except Exception:
        return ""
