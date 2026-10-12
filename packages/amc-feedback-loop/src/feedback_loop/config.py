"""
Runtime configuration for the Human Feedback Loop module.
All thresholds and tunable values live here so they can be changed
without a redeploy (load from env-vars or pass overrides at startup).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeedbackLoopConfig:
    # ── Passive-capture window ───────────────────────────────────────────────
    passive_window_minutes: int = 3          # 2–4 min per design; default 3

    # ── Dissatisfaction signal thresholds ────────────────────────────────────
    requery_similarity_threshold: float = 0.75   # cosine sim ≥ this → signal fires
    min_signals_required: int = 2                # 2-of-3 required to convert

    # ── Deduplication ────────────────────────────────────────────────────────
    dedup_window_minutes: int = 5            # session-level dedup window

    # ── Numeric accuracy rule ────────────────────────────────────────────────
    numeric_critical_delta_pct: float = 50.0   # ≥ 50 % deviation → critical
    numeric_high_delta_pct: float = 20.0       # ≥ 20 % → high
    numeric_medium_delta_pct: float = 10.0     # ≥ 10 % → medium

    # ── Trigger / retry ──────────────────────────────────────────────────────
    webhook_timeout_seconds: float = 5.0
    retry_max_attempts: int = 3
    retry_wait_seconds: float = 2.0

    # ── Correction-language pattern list ─────────────────────────────────────
    correction_patterns: list[str] = field(default_factory=lambda: [
        r"\bno[,.]?\s+that'?s?\s+wrong\b",
        r"\bactually\s+it'?s?\b",
        r"\bthat'?s?\s+not\s+right\b",
        r"\bshould\s+be\b",
        r"\bincorrect\b",
        r"\bwrong\s+(?:value|number|figure|data)\b",
    ])
