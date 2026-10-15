"""
HTTP client for standalone Repair Engine service with circuit breaker fallback.
"""
import logging
from typing import Any, Dict, List, Optional
import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger("app.clients.repair_client")

class RepairServiceClient:
    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url.rstrip("/")
        self.breaker = CircuitBreaker()

    async def get_pending_patches(self) -> List[Dict[str, Any]]:
        if not self.breaker.allow_request():
            logger.warning("Repair service circuit breaker is OPEN")
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/patches/pending")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return res.json()
                else:
                    self.breaker.record_failure()
                    return []
        except Exception as exc:
            self.breaker.record_failure()
            logger.warning("Failed to call remote repair service (%s)", exc)
            raise

    async def approve_patch(self, patch_id: str) -> bool:
        if not self.breaker.allow_request():
            raise CircuitBreakerOpenException("Repair service circuit is OPEN")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(f"{self.base_url}/api/patches/{patch_id}/approve")
                if res.status_code == 200:
                    self.breaker.record_success()
                    return True
                else:
                    self.breaker.record_failure()
                    return False
        except Exception as exc:
            self.breaker.record_failure()
            raise

    async def create_repair_task(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a repair task in the standalone Repair Engine service.
        If the remote service is unavailable or circuit is open, creates a local repair task
        via CorrectionPatchLayer fallback.
        """
        if self.breaker.allow_request():
            try:
                entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
                payload = {
                    "entity_id": entity_id,
                    "attribute": "regulatory_fact",
                    "canonical_value": canonical_query,
                    "corrected_value": f"Pending repair for query: {canonical_query}",
                    "confidence": 0.9,
                    "provenance": provenance or {
                        "issue_id": issue_id,
                        "contributor_count": contributor_count,
                        "taxonomy_paths": taxonomy_paths or [],
                    },
                    "approved": False,
                }
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.post(f"{self.base_url}/api/patches", json=payload)
                    if res.status_code in (200, 201):
                        self.breaker.record_success()
                        data = res.json()
                        patch_id = data.get("patch_id") or data.get("task_id")
                        if patch_id:
                            return f"task_{patch_id}" if not patch_id.startswith("task_") else patch_id
                    else:
                        self.breaker.record_failure()
            except Exception as exc:
                self.breaker.record_failure()
                logger.info(
                    "Remote repair service at %s unavailable (%s). Falling back to local repair task generator.",
                    self.base_url,
                    exc,
                )

        return self._create_local_repair_task(
            issue_id=issue_id,
            canonical_query=canonical_query,
            primary_entities=primary_entities,
            taxonomy_paths=taxonomy_paths,
            contributor_count=contributor_count,
            provenance=provenance,
        )

    def _create_local_repair_task(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Local in-memory / shadow graph patch creation fallback."""
        try:
            from app.graph.correction_patch_layer import get_correction_patch_layer
            patch_layer = get_correction_patch_layer()
            entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
            patch_id = patch_layer.add_correction(
                entity_id=entity_id,
                attribute="regulatory_fact",
                canonical_value=canonical_query,
                corrected_value=f"Pending repair for query: {canonical_query}",
                confidence=0.9,
                provenance=provenance or {
                    "issue_id": issue_id,
                    "contributor_count": contributor_count,
                    "taxonomy_paths": taxonomy_paths or [],
                },
                approved=False,
            )
            return f"task_{patch_id}"
        except Exception as local_exc:
            logger.debug("Local patch layer fallback note: %s", local_exc)
            import uuid
            return f"task_rep_{uuid.uuid4().hex[:12]}"

    def create_repair_task_sync(
        self,
        issue_id: str,
        canonical_query: str,
        primary_entities: Optional[List[str]] = None,
        taxonomy_paths: Optional[List[str]] = None,
        contributor_count: int = 1,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Synchronous version for direct sync route/service invocation."""
        if self.breaker.allow_request():
            try:
                entity_id = (primary_entities[0] if primary_entities else f"issue_{issue_id}").strip()
                payload = {
                    "entity_id": entity_id,
                    "attribute": "regulatory_fact",
                    "canonical_value": canonical_query,
                    "corrected_value": f"Pending repair for query: {canonical_query}",
                    "confidence": 0.9,
                    "provenance": provenance or {
                        "issue_id": issue_id,
                        "contributor_count": contributor_count,
                        "taxonomy_paths": taxonomy_paths or [],
                    },
                    "approved": False,
                }
                with httpx.Client(timeout=2.0) as client:
                    res = client.post(f"{self.base_url}/api/patches", json=payload)
                    if res.status_code in (200, 201):
                        self.breaker.record_success()
                        data = res.json()
                        patch_id = data.get("patch_id") or data.get("task_id")
                        if patch_id:
                            return f"task_{patch_id}" if not patch_id.startswith("task_") else patch_id
                    else:
                        self.breaker.record_failure()
            except Exception as exc:
                self.breaker.record_failure()
                logger.info(
                    "Remote repair service at %s unavailable (%s). Using local task generator.",
                    self.base_url,
                    exc,
                )

        return self._create_local_repair_task(
            issue_id=issue_id,
            canonical_query=canonical_query,
            primary_entities=primary_entities,
            taxonomy_paths=taxonomy_paths,
            contributor_count=contributor_count,
            provenance=provenance,
        )


_repair_service_client: Optional[RepairServiceClient] = None


def get_repair_service_client() -> RepairServiceClient:
    global _repair_service_client
    if _repair_service_client is None:
        import os
        base_url = os.getenv("REPAIR_ENGINE_URL", "http://localhost:8002")
        _repair_service_client = RepairServiceClient(base_url=base_url)
    return _repair_service_client

