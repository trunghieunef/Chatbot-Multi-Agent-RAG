from agent_service.contracts import (
    AgentSource,
    Evidence,
    MatchedChunk,
    RetrievalResult,
    RetrievalTask,
    SpecialistResult,
    StructuredWarning,
)


def test_agent_source_accepts_frontend_safe_fields():
    source = AgentSource(
        type="article",
        domain="legal",
        id="article:7",
        title="Luật Đất đai",
        url=None,
        snippet="Điều kiện chuyển nhượng quyền sử dụng đất.",
        location={"city": "Ho Chi Minh"},
        citation={"doc_slug": "luat-dat-dai", "dieu_number": "45"},
        score=0.91,
        metadata={"source_identity": "article:legal://luat-dat-dai"},
    )

    assert source.id == "article:7"
    assert source.domain == "legal"
    assert source.metadata["source_identity"] == "article:legal://luat-dat-dai"


def test_evidence_preserves_many_matched_chunks():
    warning = StructuredWarning(
        code="no_evidence",
        domain="property",
        message="No listing evidence was found.",
        retryable=False,
    )
    chunk_1 = MatchedChunk(
        id="chunk:1",
        chunk_type="overview",
        text="Căn hộ Quận 7 dưới 5 tỷ",
        vector_distance=0.18,
        rerank_score=0.91,
        final_score=0.91,
    )
    chunk_2 = MatchedChunk(
        id="chunk:2",
        chunk_type="description",
        text="Gần trường học và siêu thị",
        vector_distance=0.22,
        final_score=0.78,
    )

    evidence = Evidence(
        evidence_id="ev_1",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:100",
        record={"id": 100},
        facts={"title": "Căn hộ Quận 7", "legal_status_claimed": "Sổ hồng"},
        source=AgentSource(type="listing", domain="property", id="listing:100"),
        matched_chunks=[chunk_1, chunk_2],
        retrieved_for=["property_search"],
        assigned_to=["property_search", "investment_advisor"],
        warnings=[warning],
    )

    assert len(evidence.matched_chunks) == 2
    assert evidence.assigned_to == ["property_search", "investment_advisor"]


def test_retrieval_task_result_and_specialist_result_shapes():
    task = RetrievalTask(
        task_id="search_legal_1",
        domain="legal",
        tool="search_articles",
        query="pháp lý mua căn hộ",
        filters={"category": "legal"},
        retrieved_for=["legal_advisor"],
        depends_on=[],
        dependency_mode="none",
        top_k=20,
        rerank_top_k=5,
        timeout_ms=None,
    )
    warning = StructuredWarning(
        code="source_not_ready",
        domain="legal",
        message="Legal knowledge base is not ready.",
        retryable=False,
    )
    result = RetrievalResult(
        task_id=task.task_id,
        status="skipped",
        evidence_ids=[],
        duration_ms=0,
        warnings=[warning],
        skip_reason="source_not_ready",
        error=None,
    )
    specialist = SpecialistResult(
        agent_name="legal_advisor",
        status="no_evidence",
        content="Chưa có căn cứ pháp lý để kết luận.",
        evidence_ids_used=[],
        confidence="low",
        warnings=[warning],
        missing_evidence=["legal"],
        sources=[],
    )

    assert result.status == "skipped"
    assert result.warnings[0].code == "source_not_ready"
    assert specialist.status == "no_evidence"


def test_specialist_result_accepts_current_specialist_output_shape():
    specialist = SpecialistResult.model_validate(
        {
            "agent_name": "property_search",
            "content": "No listing evidence yet.",
            "warnings": ["no_listing_evidence"],
            "sources": [],
        }
    )

    assert specialist.status == "completed"
    assert specialist.evidence_ids_used == []
    assert specialist.warnings == ["no_listing_evidence"]
