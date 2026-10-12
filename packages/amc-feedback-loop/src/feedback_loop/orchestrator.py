"""
RecordBuilder  orchestrates the 4-step unified record build.

Execution model (per design Section 3):
    Steps 1 + 2  run concurrently  (ThreadPoolExecutor, max_workers=2)
    Steps 3 + 4  run sequentially  after both 1 and 2 finish
    One single DB write at the end

Returns:
    UnifiedEvaluationRecord    successfully built record
    None                        row was a duplicate; discard silently
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional

import structlog

from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    ClassificationResult,
    EnrichmentResult,
    FeedbackRecord,
    LifecycleStatus,
    UnifiedEvaluationRecord,
)
from feedback_loop.services.adjudication import AdjudicationService
from feedback_loop.services.classification import ClassificationService
from feedback_loop.services.enrichment import EvidenceEnrichmentService
from feedback_loop.services.router import AdaptiveRouterService

logger = structlog.get_logger(__name__)


class RecordBuilder:
    """
    Wires the four services together and enforces the concurrency model
    defined in the technical design.

    A single RecordBuilder instance is safe to share across threads 
    all mutable state lives in local variables within build().
    """

    def __init__(
        self,
        config: FeedbackLoopConfig,
        db: AbstractDatabaseAdapter,
        evidence_adapter: AbstractEvidenceAdapter,
    ) -> None:
        self._config = config
        self._db = db
        self._classification_svc = ClassificationService()
        self._enrichment_svc = EvidenceEnrichmentService(config, evidence_adapter, db)
        self._router_svc = AdaptiveRouterService(config)
        self._adjudication_svc = AdjudicationService()

    def build(self, row: FeedbackRecord) -> Optional[UnifiedEvaluationRecord]:
        """
        Execute the 4-step build for one feedback_records row.

        Returns None when the row is a duplicate and should be discarded.
        The caller (IngestService) is responsible for the single DB write
        so that write errors don't get swallowed here.
        """
        log = logger.bind(
            feedback_id=row.feedback_id,
            response_id=row.response_id,
            source=row.source,
        )

        #  Guard: skip if a unified record already exists for this response 
        if self._db.unified_record_exists(row.response_id):
            log.info("unified_record_already_exists_skipping")
            return None

        #  Steps 1 + 2  concurrent 
        classification: Optional[ClassificationResult] = None
        enrichment: Optional[EnrichmentResult] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            # Step 1 is only scheduled when there is text to classify
            step1_future: Optional[concurrent.futures.Future] = None
            if self._classification_svc.should_run(row):
                step1_future = pool.submit(self._classification_svc.run, row, row.session_id, row.feedback_id)

            # Step 2 always runs
            step2_future = pool.submit(self._enrichment_svc.run, row, row.session_id, row.feedback_id)

            # Collect results  step 1 result is optional
            if step1_future is not None:
                try:
                    classification = step1_future.result()
                except Exception as exc:
                    # Step 1 failure is non-fatal; log and continue without it
                    log.warning("step1_classification_failed", error=str(exc))
                    classification = None

            try:
                enrichment = step2_future.result()
                log.info("step2_enrichment_complete", snapshot=enrichment.evidence_snapshot)
            except Exception as exc:
                # Step 2 failure is fatal  we cannot build a record without evidence
                log.error("step2_enrichment_failed", error=str(exc))
                raise

        #  Duplicate short-circuit 
        if enrichment.is_duplicate:
            log.info("duplicate_short_circuit", cluster_id=enrichment.cluster_id)
            return None

        #  Step 3  Adaptive Router (needs step 2 evidence) 
        router_result = self._router_svc.run(
            row=row,
            snapshot=enrichment.evidence_snapshot,
            session_id=row.session_id,
            feedback_id=row.feedback_id,
        )

        #  Step 4  Adjudication (needs step 3 output) 
        adjudication_result = self._adjudication_svc.run(
            row=row,
            snapshot=enrichment.evidence_snapshot,
            router_result=router_result,
            classification=classification,
            session_id=row.session_id,
            feedback_id=row.feedback_id,
        )

        #  Assemble the unified record 
        record = UnifiedEvaluationRecord(
            session_id=row.session_id,
            response_id=row.response_id,
            entry_route=enrichment.entry_route,
            feedback_ref=row.feedback_id if enrichment.entry_route == "hitl" else None,
            evidence_snapshot_ref=enrichment.evidence_snapshot_ref,
            root_cause=adjudication_result.root_cause,
            severity=router_result.severity,
            lifecycle_status=LifecycleStatus.OPEN,
            # Auditability: store dissatisfaction evidence when present
            dissatisfaction_evidence=(
                enrichment.dissatisfaction_signal.model_dump()
                if enrichment.dissatisfaction_signal
                else None
            ),
        )

        log.info(
            "record_built",
            entry_route=record.entry_route,
            root_cause=record.root_cause,
            severity=record.severity,
        )
        return record

