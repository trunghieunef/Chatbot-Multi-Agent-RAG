from data_pipeline.legal.html_parser import parse_html


def test_parse_html_strips_tags_and_keeps_text():
    html = """
    <html><body>
      <h1>Luật Đất đai 2024</h1>
      <p>Điều 1. <em>Phạm vi điều chỉnh</em></p>
      <script>alert('x')</script>
      <style>body{color:red}</style>
    </body></html>
    """

    text = parse_html(html)

    assert "Luật Đất đai 2024" in text
    assert "Điều 1" in text
    assert "Phạm vi điều chỉnh" in text
    assert "alert" not in text
    assert "color:red" not in text
