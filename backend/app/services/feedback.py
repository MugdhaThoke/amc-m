# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback.py
===========
Service layer connecting AMC feedback submissions to the human-feedback-loop module.
"""

from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session

from feedback_loop import FeedbackLoopConfig, start_feedback_loop
from app.adapters.feedback_adapters import AMCDatabaseAdapter, AMCEvidenceAdapter
from app.core.database import SessionLocal
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.services.repair_service import process_unified_record_for_repair_sync

logger = logging.getLogger("app.services.feedback")

_config = FeedbackLoopConfig()
_db_adapter = AMCDatabaseAdapter(session_factory=SessionLocal)
_evidence_adapter = AMCEvidenceAdapter(session_factory=SessionLocal)


def trigger_feedback_loop(
    feedback_id: str,
    session_id: str,
    response_id: str,
    source: str = "active",
    db: Optional[Session] = None,
    process_repair: bool = True,
) -> Optional[UnifiedEvaluationRecord]:
    """
    Executes the human-feedback-loop pipeline (Steps 1–4) for a feedback record.

    Uses AMC's AMCDatabaseAdapter and AMCEvidenceAdapter to read from
    response_feedback and query_evidence, and write the adjudicated
    result to unified_evaluation_records.
    
    Args:
        feedback_id: Primary key of the feedback record
        session_id: User session ID
        response_id: Response being evaluated
        source: 'active' or 'passive' feedback source
        db: Optional database session
        process_repair: Whether to automatically process repairs (default: True)
    
    Returns:
        UnifiedEvaluationRecord if created, else None
    """
    logger.info(
        "FEEDBACK LOOP START: feedback_id=%s, response_id=%s, session_id=%s, source=%s",
        feedback_id,
        response_id,
        session_id,
        source,
    )

    try:
        # Verify QueryEvidence exists before starting feedback loop
        check_db = db or SessionLocal()
        try:
            from app.schemas.query_evidence_table import QueryEvidence
            has_evidence = (
                check_db.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            if not has_evidence:
                logger.info("QueryEvidence not present for response_id=%s, skipping deep loop", response_id)
                return None
        finally:
            if db is None:
                check_db.close()

        logger.info("Running feedback loop pipeline (Steps 1-4)...")
        success = start_feedback_loop(
            feedback_id=feedback_id,
            session_id=session_id,
            response_id=response_id,
            source=source,
            config=_config,
            db=_db_adapter,
            evidence_adapter=_evidence_adapter,
        )
        logger.info("Feedback loop pipeline completed: success=%s", success)

        # Retrieve the generated UnifiedEvaluationRecord
        local_db = db or SessionLocal()
        try:
            record = (
                local_db.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == response_id)
                .first()
            )
            
            if not record:
                logger.warning("⚠️  No UnifiedEvaluationRecord created for response_id=%s", response_id)
                return None
            
            logger.info(
                "Unified record created: entry_route=%s, root_cause=%s, severity=%s, repair=%s",
                record.entry_route, record.root_cause, record.severity, record.repair
            )
            
            # NEW: If repair is flagged, trigger repair engine microservice
            if process_repair and record.repair:
                logger.info(
                    "REPAIR FLAGGED: response_id=%s, root_cause=%s, repair_target=%s",
                    response_id, record.root_cause, record.repair_target
                )
                try:
                    # Import here to avoid circular imports
                    import asyncio
                    from app.services.repair_integration import trigger_repair_on_feedback
                    
                    # Run async repair trigger synchronously
                    repair_result = asyncio.run(trigger_repair_on_feedback(record, db=local_db))
                    
                    logger.info(
                        "Repair engine integration result: success=%s, patches=%d",
                        repair_result.get("success"),
                        len(repair_result.get("patches_created", []))
                    )
                    
                    if repair_result.get("patches_created"):
                        logger.info(
                            "Patches created via repair engine: %s",
                            repair_result["patches_created"]
                        )
                
                except Exception as repair_exc:
                    logger.error(
                        "Repair engine integration error: %s",
                        repair_exc, exc_info=True
                    )
            
            return record
        finally:
            if db is None:
                local_db.close()

    except Exception as exc:
        logger.error(
            "trigger_feedback_loop FAILED: feedback_id=%s, error: %s",
            feedback_id,
            exc,
            exc_info=True,
        )
        raise