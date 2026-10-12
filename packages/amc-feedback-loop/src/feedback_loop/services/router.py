"""
Step 3  AdaptiveRouterService

Deterministic rule check against the evidence snapshot and any structured
corrections.  Maps fired rules to a preliminary severity.

Rules implemented:
  C01   referential integrity (entity present in evidence)
  C02   temporal freshness  (source_version staleness indicator)
  C03   numeric accuracy    (response value vs. evidence value)
  C04   structured correction present (user-supplied explicit correction)
  C05   compliance / jurisdiction keyword detection

Severity mapping (design Â§ 3):
  - Compliance / jurisdiction violation  â†’ critical
  - Numeric delta â‰¥ thresholds           â†’ critical / high / medium
  - Entity not in evidence               â†’ high
  - Structured correction present        â†’ high
  - Presentation-only / minor            â†’ low
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

from feedback_loop.logging_config import get_pipeline_logger
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    EvidenceSnapshot,
    FeedbackRecord,
    RouterResult,
    RuleFinding,
    Severity,
)

logger = structlog.get_logger(__name__)

# Compliance / jurisdiction keywords that auto-triage to critical
_COMPLIANCE_KEYWORDS = re.compile(
    r"\b(sebi|amfi|irda|nsdl|cdsl|rbi|compliance|regulation|regulatory|"
    r"jurisdiction|statutory|mandatory|breach|penalty|violation)\b",
    re.IGNORECASE,
)


def _extract_numeric(text: str) -> Optional[float]:
    """Pull first numeric value (int or decimal, optionally followed by %) from text."""
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*%?", text)
    if match:
        return float(match.group(1))
    return None


def _delta_pct(response_val: float, evidence_val: float) -> float:
    """Absolute percentage deviation of response vs. evidence."""
    if evidence_val == 0:
        return 0.0
    return abs(response_val - evidence_val) / abs(evidence_val) * 100.0


class AdaptiveRouterService:
    """
    Step 3  deterministic rule check + severity assignment.

    Runs for BOTH active and passive rows.
    Does NOT escalate to NLI or LLM  that tier only exists in the
    external Evaluation Layer.
    """

    def __init__(self, config: FeedbackLoopConfig) -> None:
        self._config = config

    #  Individual rule checks 

    def _check_c01_referential(
        self, row: FeedbackRecord, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C01  entity named in feedback should appear in evidence chunks."""
        entity = row.entity_name
        if not entity:
            return None
        # Check response text and evidence chunks
        in_response = entity.lower() in snapshot.response_text.lower()
        in_chunks = any(
            entity.lower() in (c.content or "").lower()
            or entity.lower() in (c.value or "").lower()
            for c in snapshot.evidence_selected
        )
        if not in_response and not in_chunks:
            return RuleFinding(
                rule="C01_referential_integrity",
                result="FAIL",
                detail=f"Entity '{entity}' not found in response or evidence chunks.",
            )
        return None

    def _check_c02_temporal(
        self, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C02  flag when any evidence chunk has no source_version (staleness indicator)."""
        stale = [c.chunk_id for c in snapshot.evidence_selected if not c.source_version]
        if stale:
            return RuleFinding(
                rule="C02_temporal_freshness",
                result="WARN",
                detail=f"Chunks missing source_version (possible stale data): {stale}",
            )
        return None

    def _check_c03_numeric(
        self, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """
        C03  numeric accuracy.
        Compares the first numeric value in response_text against the first
        numeric value in any evidence chunk.
        """
        response_val = _extract_numeric(snapshot.response_text)
        if response_val is None:
            return None

        for chunk in snapshot.evidence_selected:
            evidence_text = chunk.value or chunk.content or ""
            evidence_val = _extract_numeric(evidence_text)
            if evidence_val is None:
                continue
            delta = _delta_pct(response_val, evidence_val)
            if delta > 0:
                return RuleFinding(
                    rule="C03_numeric_accuracy",
                    result="FAIL",
                    response_value=response_val,
                    evidence_value=evidence_val,
                    delta_pct=round(delta, 2),
                )
        return None

    def _check_c04_structured_correction(
        self, row: FeedbackRecord
    ) -> Optional[RuleFinding]:
        """C04  user supplied an explicit structured correction."""
        if row.corrections:
            return RuleFinding(
                rule="C04_structured_correction",
                result="FAIL",
                detail=f"User-supplied correction: {row.corrections}",
            )
        return None

    def _check_c05_compliance(
        self, row: FeedbackRecord, snapshot: EvidenceSnapshot
    ) -> Optional[RuleFinding]:
        """C05  compliance/jurisdiction keyword in notes or response."""
        text_to_scan = " ".join(filter(None, [
            row.notes or "",
            snapshot.response_text,
        ]))
        matches = _COMPLIANCE_KEYWORDS.findall(text_to_scan)
        if matches:
            return RuleFinding(
                rule="C05_compliance_jurisdiction",
                result="FAIL",
                detail=f"Compliance keywords detected: {list(set(m.lower() for m in matches))}",
            )
        return None

    #  Severity mapping 

    def _severity_from_rules(self, findings: list[RuleFinding]) -> Optional[Severity]:
        if not findings:
            return None

        rule_names = {f.rule for f in findings}

        # Compliance â†’ always critical
        if "C05_compliance_jurisdiction" in rule_names:
            return Severity.CRITICAL

        # Numeric severity tiers
        for f in findings:
            if f.rule == "C03_numeric_accuracy" and f.delta_pct is not None:
                if f.delta_pct >= self._config.numeric_critical_delta_pct:
                    return Severity.CRITICAL
                if f.delta_pct >= self._config.numeric_high_delta_pct:
                    return Severity.HIGH
                if f.delta_pct >= self._config.numeric_medium_delta_pct:
                    return Severity.MEDIUM
                return Severity.LOW

        # Entity / correction mismatch â†’ high
        if rule_names & {"C01_referential_integrity", "C04_structured_correction"}:
            return Severity.HIGH

        # Temporal warning â†’ low
        if "C02_temporal_freshness" in rule_names:
            return Severity.LOW

        return Severity.MEDIUM  # fallback

    #  Public API 

    def run(self, row: FeedbackRecord, snapshot: EvidenceSnapshot, session_id: str = None, feedback_id: str = None) -> RouterResult:
        """
        """
        findings: list[RuleFinding] = []

        for checker in (
            lambda: self._check_c01_referential(row, snapshot),
            lambda: self._check_c02_temporal(snapshot),
            lambda: self._check_c03_numeric(snapshot),
            lambda: self._check_c04_structured_correction(row),
            lambda: self._check_c05_compliance(row, snapshot),
        ):
            result = checker()
            if result is not None:
                findings.append(result)

        severity = self._severity_from_rules(findings)

        step_logger = None
        if session_id and feedback_id:
            step_logger = get_pipeline_logger("router", session_id, feedback_id)
            if step_logger:

                step_logger.info("Router complete")
        logger.info(
            "router_complete",
            feedback_id=row.feedback_id,
            rules_fired=[f.rule for f in findings],
            severity=severity,
        )

        return RouterResult(rules_fired=findings, severity=severity)

