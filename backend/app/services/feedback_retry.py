# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_retry.py
==================
Resilient retry mechanism for pending/failed feedback loop executions with
exponential backoff, in-flight evidence grace periods, and orphan prevention.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence

logger = logging.getLogger("app.services.feedback_retry")


class FeedbackRetryService:
    """Retry failed/pending feedback loop triggers with evidence awareness and attempt capping."""

    def __init__(
        self,
        retry_intervals: Optional[List[int]] = None,
        max_attempts: int = 3,
        evidence_grace_period_seconds: float = 120.0,
    ):
        self.retry_intervals = retry_intervals or [60, 300, 900]  # 1min, 5min, 15min
        self.max_attempts = max_attempts
        self.evidence_grace_period_seconds = evidence_grace_period_seconds
        self._retry_attempts: Dict[str, int] = {}
        self._last_retry_time: Dict[str, float] = {}
        self._exceeded_logged: Set[str] = set()
        self._orphaned_logged: Set[str] = set()

    def _prune_tracking_cache(self, active_feedback_ids: Set[str]) -> None:
        """Prune stale tracking IDs if tracking cache exceeds memory limits."""
        if len(self._retry_attempts) > 1000:
            stale = set(self._retry_attempts.keys()) - active_feedback_ids
            for fid in stale:
                self._retry_attempts.pop(fid, None)
                self._last_retry_time.pop(fid, None)
                self._exceeded_logged.discard(fid)
                self._orphaned_logged.discard(fid)

    async def process_retries(self) -> int:
        """Find pending feedback records and retry trigger with evidence validation."""
        db = SessionLocal()
        retried_count = 0
        try:
            # Find records between 1 minute and 35 minutes old with no unified_record_ref
            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()
            cutoff_max = now - timedelta(seconds=2100)  # 35 min cutoff
            cutoff_min = now - timedelta(seconds=60)    # 1 min cutoff

            pending = (
                db.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.unified_record_ref.is_(None),
                    ResponseFeedback.created_at >= cutoff_max.isoformat(),
                    ResponseFeedback.created_at <= cutoff_min.isoformat(),
                )
                .limit(50)
                .all()
            )

            active_ids = {r.feedback_id for r in pending}
            self._prune_tracking_cache(active_ids)

            for record in pending:
                try:
                    record_dt = datetime.fromisoformat(record.created_at)
                    if record_dt.tzinfo is None:
                        record_dt = record_dt.replace(tzinfo=timezone.utc)
                    age_seconds = (now - record_dt).total_seconds()
                except Exception:
                    continue

                # 1. Enforce max attempts cap
                attempts = self._retry_attempts.get(record.feedback_id, 0)
                if attempts >= self.max_attempts:
                    if record.feedback_id not in self._exceeded_logged:
                        self._exceeded_logged.add(record.feedback_id)
                        logger.warning(
                            "Feedback %s reached max retry attempts (%d); stopping further retries",
                            record.feedback_id,
                            self.max_attempts,
                        )
                    continue

                # 2. Defensive check: verify QueryEvidence existence before attempting deep loop
                has_evidence = (
                    db.query(QueryEvidence.response_id)
                    .filter(QueryEvidence.response_id == record.response_id)
                    .first()
                ) is not None

                if not has_evidence:
                    # In-flight grace period: evidence may still be committing asynchronously
                    if age_seconds < self.evidence_grace_period_seconds:
                        logger.debug(
                            "QueryEvidence not yet available for response_id=%s, deferring retry (age=%.1fs)",
                            record.response_id,
                            age_seconds,
                        )
                        continue

                    # Grace period expired: this feedback is orphaned or refers to a missing response
                    if record.feedback_id not in self._orphaned_logged:
                        self._orphaned_logged.add(record.feedback_id)
                        logger.warning(
                            "Skipping feedback loop retry for feedback %s: no QueryEvidence found for response_id=%s after %.0fs (orphaned record)",
                            record.feedback_id,
                            record.response_id,
                            age_seconds,
                        )
                    continue

                # 3. Minimum cooldown between retry attempts for the same feedback record
                last_retry_ts = self._last_retry_time.get(record.feedback_id)
                if last_retry_ts is not None and (now_ts - last_retry_ts) < 45.0:
                    continue

                # 4. Schedule check
                should_retry = any(
                    abs(age_seconds - interval) < 45  # 45s tolerance
                    for interval in self.retry_intervals
                ) or (age_seconds < 120 and age_seconds >= 60 and attempts == 0)

                if should_retry:
                    self._retry_attempts[record.feedback_id] = attempts + 1
                    self._last_retry_time[record.feedback_id] = now_ts
                    current_attempt = self._retry_attempts[record.feedback_id]
                    try:
                        from app.services.feedback import trigger_feedback_loop
                        result = await asyncio.to_thread(
                            trigger_feedback_loop,
                            feedback_id=record.feedback_id,
                            session_id=record.session_id,
                            response_id=record.response_id,
                            source="active" if record.feedback_text else "passive",
                        )
                        if result is not None:
                            retried_count += 1
                            logger.info(
                                "Retry trigger successfully executed for feedback %s (attempt %d/%d)",
                                record.feedback_id,
                                current_attempt,
                                self.max_attempts,
                            )
                        else:
                            logger.warning(
                                "Retry trigger executed for feedback %s but feedback loop did not yield a unified record (attempt %d/%d)",
                                record.feedback_id,
                                current_attempt,
                                self.max_attempts,
                            )
                    except Exception as exc:
                        logger.error(
                            "Retry failed for feedback %s (attempt %d/%d): %s",
                            record.feedback_id,
                            current_attempt,
                            self.max_attempts,
                            exc,
                        )

                # 5. Long-term window expiration notice (logged once at 30 minutes)
                if age_seconds > 1800 and record.feedback_id not in self._exceeded_logged:
                    self._exceeded_logged.add(record.feedback_id)
                    logger.warning("Feedback %s exceeded total retry window (30m)", record.feedback_id)

            return retried_count
        finally:
            db.close()


_running: bool = False
_retry_task: Optional[asyncio.Task] = None


async def start_retry_service(interval_seconds: int = 60) -> None:
    """Background task running feedback retry sweeps."""
    global _running, _retry_task
    if _running:
        return
    _running = True
    service = FeedbackRetryService()
    logger.info("FeedbackRetryService started (interval=%ds)", interval_seconds)
    while _running:
        try:
            await asyncio.sleep(interval_seconds)
            await service.process_retries()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Retry service error: %s", exc)


def stop_retry_service() -> None:
    """Stop the background retry service."""
    global _running, _retry_task
    _running = False
    if _retry_task and not _retry_task.done():
        _retry_task.cancel()
