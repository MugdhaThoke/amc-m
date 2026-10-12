from pydantic import BaseModel, Field, field_validator
from typing import Optional


VALID_CODES = {f"F{i:02d}" for i in range(1, 13)}


class FeedbackIn(BaseModel):
    response_id: str = Field(..., min_length=1, description="Ties feedback to exact ContextGraph answer")
    interaction_id: str = Field(..., min_length=1, description="Interaction or conversation ID")
    session_id: str = Field(..., min_length=1, description="Session ID")
    turn_number: int = Field(..., ge=1, description="1-indexed turn number in session")
    query_text: Optional[str] = Field(default=None, max_length=2000, description="Question asked by user")
    actor_id: Optional[str] = Field(default=None, max_length=200, description="Reviewer / user identifier")
    actor_role: Optional[str] = Field(default="Compliance & Regulatory Officer", max_length=200)
    selected_categories: list[str] = Field(default_factory=list, description="Array of failure taxonomy codes F01-F12")
    feedback_text: Optional[str] = Field(default=None, max_length=2000, description="Reviewer commentary")
    client_timestamp: Optional[str] = Field(default=None, description="ISO timestamp from client")

    @field_validator("selected_categories")
    @classmethod
    def validate_codes(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip().upper() for c in v if c and c.strip()]
        bad = set(cleaned) - VALID_CODES
        if bad:
            raise ValueError(f"Unknown failure category codes: {sorted(bad)}. Allowed: {sorted(VALID_CODES)}")
        return cleaned


class FeedbackOut(BaseModel):
    feedback_id: str
    response_id: str
    stored_at: str
    status: str = "recorded"
    priority_tier: Optional[str] = None
    signal_quality_score: Optional[float] = None


class PendingFeedbackNotice(BaseModel):
    has_pending_feedback: bool = True
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Semantic similarity score (0.0 - 1.0)")
    original_query_text: Optional[str] = Field(default=None, description="Original query text (admin only)")
    feedback_submitted_at: Optional[str] = Field(default=None, description="ISO timestamp when original feedback was submitted")
    feedback_categories: list[str] = Field(default_factory=list, description="Taxonomy categories reported")
    repair_lifecycle_status: str = Field(default="open", description="Lifecycle status: open, diagnosing")
    match_count: int = Field(default=1, ge=1, description="Number of matching feedback entries with pending repairs")
    suppressed_by_cache_clear: bool = Field(default=False, description="True if suppressed due to intent cache clear")

