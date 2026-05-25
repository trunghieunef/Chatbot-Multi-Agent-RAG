from data_pipeline.legal.structure import split_into_articles


SAMPLE = """
Chương I. NHỮNG QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Luật này quy định về quản lý đất đai.
2. Áp dụng với mọi tổ chức, cá nhân.

Điều 2. Đối tượng áp dụng
Đối tượng áp dụng gồm:
a) Cơ quan nhà nước;
b) Tổ chức trong nước.

Chương II. QUYỀN VÀ NGHĨA VỤ

Điều 3. Quyền của người sử dụng đất
Người sử dụng đất có các quyền sau:
1. Quyền chuyển nhượng.
"""


def test_split_into_articles_preserves_chuong_and_dieu():
    articles = split_into_articles(SAMPLE)

    assert len(articles) == 3
    assert articles[0]["chuong"] == "Chương I"
    assert articles[0]["chuong_title"] == "NHỮNG QUY ĐỊNH CHUNG"
    assert articles[0]["dieu_number"] == 1
    assert articles[0]["dieu_title"] == "Phạm vi điều chỉnh"
    assert "Luật này quy định" in articles[0]["text"]

    assert articles[1]["dieu_number"] == 2
    assert articles[2]["chuong"] == "Chương II"
    assert articles[2]["dieu_number"] == 3


def test_split_into_articles_returns_empty_for_blank_text():
    assert split_into_articles("") == []
