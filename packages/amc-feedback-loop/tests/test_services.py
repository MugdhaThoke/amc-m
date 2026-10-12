"""
Unit tests for feedback_loop individual services:
- ClassificationService (Step 1)
- EvidenceEnrichmentService (Step 2)
- AdaptiveRouterService (Step 3)
- AdjudicationService (Step 4)
"""
from datetime import datetime, timezone
import pytest

from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    ClassificationResult,
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    FollowUpQuery,
    RatingType,
    RootCause,
    RuleFinding,
    RouterResult,
    Severity,
    EntryRoute,
)
from feedback_loop.adapters import InMemoryDatabaseAdapter, InMemoryEvidenceAdapter
from feedback_loop.services.classification import ClassificationService, _classify_intent
from feedback_loop.services.enrichment import EvidenceEnrichmentService, _cosine_similarity, _matches_correction_pattern
from feedback_loop.services.router import AdaptiveRouterService
from feedback_loop.services.adjudication import AdjudicationService


def test_classification_intent_and_should_run():
    svc = ClassificationService()

    # Passive rows should not run classification
    passive_row = FeedbackRecord(
        feedback_id="p1",
        session_id="s1",
        response_id="r1",
        rating=RatingType.UNRATED,
        feedback_type=FeedbackType.SILENT_ACCEPT,
        source=FeedbackSource.PASSIVE,
        received_at=datetime.now(timezone.utc),
        notes=None,
    )
    assert svc.should_run(passive_row) is False

    # Active row with notes should run
    active_row = FeedbackRecord(
        feedback_id="a1",
        session_id="s1",
        response_id="r1",
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        notes="Actually it's wrong, the NAV is 145.0",
    )
    assert svc.should_run(active_row) is True

    # Rule-based intent helper
    assert _classify_intent("Actually it's wrong, please check") == "correction"
    assert _classify_intent("This is terrible and useless") == "complaint"
    assert _classify_intent("Could you clarify the exit load?") == "query"
    assert _classify_intent("Here is the requested data.") == "neutral"


def test_enrichment_similarity_and_patterns():
    # Cosine similarity helper
    text1 = "What is the expense ratio of Axis Bluechip?"
    text2 = "What is the expense ratio for Axis Bluechip Fund?"
    sim = _cosine_similarity(text1, text2)
    assert sim > 0.70

    # Pattern matching helper
    patterns = [r"\bshould\s+be\b", r"\bactually\b"]
    assert _matches_correction_pattern("The return should be 15%", patterns) is True
    assert _matches_correction_pattern("Everything looks good", patterns) is False


def test_router_service_rules():
    config = FeedbackLoopConfig()
    router = AdaptiveRouterService(config)

    row = FeedbackRecord(
        feedback_id="r1",
        session_id="s1",
        response_id="resp1",
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
        entity_name="Axis Bluechip Fund",
        notes="SEBI regulation statutory violation",
    )

    snapshot = EvidenceSnapshot(
        response_id="resp1",
        original_query="What is TER?",
        response_text="TER is 0.50%",
        entity_name="Axis Bluechip Fund",
        evidence_selected=[
            EvidenceChunk(chunk_id="c1", value="0.90%", content="Axis Bluechip TER is 0.90%")
        ],
    )

    result = router.run(row=row, snapshot=snapshot)
    assert isinstance(result, RouterResult)
    # Compliance keyword detected -> Severity CRITICAL
    assert result.severity == Severity.CRITICAL
    rule_names = [f.rule for f in result.rules_fired]
    assert "C05_compliance_jurisdiction" in rule_names


def test_adjudication_service_priority():
    adj = AdjudicationService()

    row = FeedbackRecord(
        feedback_id="adj1",
        session_id="s1",
        response_id="r1",
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.INACCURATE,
        source=FeedbackSource.ACTIVE,
        received_at=datetime.now(timezone.utc),
    )

    snapshot = EvidenceSnapshot(
        response_id="r1",
        original_query="What is the NAV?",
        response_text="The NAV is 100",
        evidence_selected=[EvidenceChunk(chunk_id="c1", value="150")],
    )

    # 1. Numeric discrepancy -> MODEL
    router_numeric = RouterResult(
        rules_fired=[RuleFinding(rule="C03_numeric_accuracy", result="mismatch")],
        severity=Severity.HIGH,
    )
    res_model = adj.run(row=row, snapshot=snapshot, router_result=router_numeric)
    assert res_model.root_cause == RootCause.MODEL

    # 2. Compliance fired -> COMPLIANCE (highest priority)
    router_comp = RouterResult(
        rules_fired=[
            RuleFinding(rule="C05_compliance", result="violation"),
            RuleFinding(rule="C03_numeric_accuracy", result="mismatch"),
        ],
        severity=Severity.CRITICAL,
    )
    res_comp = adj.run(row=row, snapshot=snapshot, router_result=router_comp)
    assert res_comp.root_cause == RootCause.COMPLIANCE

    # 3. Entity missing from evidence -> RETRIEVAL
    router_retrieval = RouterResult(
        rules_fired=[RuleFinding(rule="C01_referential_integrity", result="missing")],
        severity=Severity.HIGH,
    )
    snapshot_empty = EvidenceSnapshot(response_id="r1", original_query="q", response_text="ans")
    res_retrieval = adj.run(row=row, snapshot=snapshot_empty, router_result=router_retrieval)
    assert res_retrieval.root_cause == RootCause.RETRIEVAL
