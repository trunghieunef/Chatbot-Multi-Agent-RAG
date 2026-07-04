from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent


def test_accented_legal_query_is_in_domain():
    # Real users type accented Vietnamese; the guard must strip accents to
    # match its accent-stripped keyword list (it used to always miss).
    agent = LegalAdvisorAgent()
    assert agent._is_in_domain("Thủ tục sang tên sổ đỏ cần giấy tờ gì?")
    assert agent._is_in_domain("phí trước bạ khi mua chung cư")


def test_non_legal_query_is_out_of_domain():
    agent = LegalAdvisorAgent()
    assert not agent._is_in_domain("hôm nay ăn gì cho ngon")
