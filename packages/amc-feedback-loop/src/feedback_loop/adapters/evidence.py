"""
Evidence adapter  read-only access to AMC's interaction_evidence table
and in-session follow-up query activity.

The abstract base defines the contract.  The InMemoryEvidenceAdapter is the
test stub.  Production implementations call AMC's internal API or DB directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from feedback_loop.domain_models import EvidenceChunk, EvidenceSnapshot, FollowUpQuery


class AbstractEvidenceAdapter(ABC):
    """
    Read-only contract over AMC's interaction_evidence table and
    in-session query log.

    The module never writes to these sources  it only reads via this
    interface to stay decoupled from AMC's schema.
    """

    @abstractmethod
    def get_evidence_snapshot(self, response_id: str) -> EvidenceSnapshot:
        """
        Fetch the frozen D0â€“D3 context for a given response_id.
        Raises KeyError if the response is not found in interaction_evidence.
        """
        ...

    @abstractmethod
    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[FollowUpQuery]:
        """
        Return follow-up queries made in the same session within
        *window_minutes* after the given response was delivered.

        Returns an empty list when the user made no follow-up (silence).
        The caller (Step 2 / dissatisfaction detection) interprets an empty
        list as automatic  nothing to infer.
        """
        ...

    @abstractmethod
    def validate_response_exists(self, response_id: str) -> bool:
        """
        Fast existence check against ResponseMetadataCache (24h TTL).
        Returns True when the response_id is known; False / raises when not.
        This mirrors AMC's ~1ms cache lookup described in Section 2.3.
        """
        ...


#  In-memory stub (tests / local dev) 

class InMemoryEvidenceAdapter(AbstractEvidenceAdapter):
    """
    Thread-safe in-memory adapter.  Pre-seed with snapshots and follow-ups
    for test scenarios.  Not for production use.
    """

    def __init__(self) -> None:
        # response_id â†’ EvidenceSnapshot
        self._snapshots: dict[str, EvidenceSnapshot] = {}
        # session_id â†’ list[FollowUpQuery] (ordered by created_at)
        self._followups: dict[str, list[FollowUpQuery]] = {}
        # response_id set that passes the cache check
        self._known_responses: set[str] = set()

    #  Seeding helpers 

    def seed_snapshot(self, snapshot: EvidenceSnapshot) -> None:
        self._snapshots[snapshot.response_id] = snapshot
        self._known_responses.add(snapshot.response_id)

    def seed_followups(self, session_id: str, queries: list[FollowUpQuery]) -> None:
        self._followups[session_id] = sorted(queries, key=lambda q: q.created_at)

    def seed_known_response(self, response_id: str) -> None:
        self._known_responses.add(response_id)

    #  AbstractEvidenceAdapter implementation 

    def get_evidence_snapshot(self, response_id: str) -> EvidenceSnapshot:
        try:
            return self._snapshots[response_id]
        except KeyError:
            raise KeyError(
                f"No interaction_evidence snapshot found for response_id={response_id}"
            )

    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[FollowUpQuery]:
        """
        Returns all follow-ups for the session.
        In-memory stub ignores the time window  tests control the list directly.
        A production implementation filters by created_at within the window.
        """
        return list(self._followups.get(session_id, []))

    def validate_response_exists(self, response_id: str) -> bool:
        return response_id in self._known_responses

