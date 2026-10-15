# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_integration.py
=====================
Integrates repair engine microservice with feedback loop and query context.

End-to-end flow:
  1. User submits feedback with corrections
  2. Feedback loop processes and creates UnifiedEvaluationRecord
  3. If repair=true, extract corrections and call repair engine
  4. Repair engine creates patches (persisted in layer)
  5. Next query: patches injected into context
  6. LLM synthesis uses corrected values
  7. User receives corrected response
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from app.config import get_settings
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from sqlalchemy.orm import Session

logger = logging.getLogger("app.services.repair_integration")


class RepairEngineIntegration:
    """
    Bridge between feedback loop and repair engine microservice.
    
    Handles:
    - Extraction of corrections from unified evaluation records
    - HTTP communication with repair engine
    - Patch injection into query context
    - Governance batch triggering
    """
    
    def __init__(self, repair_service_url: Optional[str] = None):
        """Initialize with repair engine URL."""
        self.repair_service_url = repair_service_url or get_settings().repair_service_url
        self.timeout = float(get_settings().service_timeout or 30.0)
    
    async def trigger_repair_engine(
        self,
        record: UnifiedEvaluationRecord,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Trigger repair engine to create patches from unified evaluation record.
        
        Args:
            record: UnifiedEvaluationRecord with corrections
            db: Database session (optional)
        
        Returns:
            Dict with created patch IDs and status
        """
        if not self.repair_service_url:
            logger.debug("Repair service URL not configured, skipping repair engine trigger")
            return {"success": False, "reason": "repair_service_url_not_configured"}
        
        if not record.dissatisfaction_evidence_json:
            logger.debug("No dissatisfaction evidence for %s, skipping repair trigger", record.response_id)
            return {"success": False, "reason": "no_dissatisfaction_evidence"}
        
        evidence = record.dissatisfaction_evidence_json
        correction_claims = evidence.get("correction_claims", [])
        
        if not correction_claims:
            logger.debug("No correction claims in evidence for %s, skipping", record.response_id)
            return {"success": False, "reason": "no_correction_claims"}
        
        logger.info(
            "🚀 REPAIR ENGINE TRIGGER: Processing %d correction(s) for response_id=%s",
            len(correction_claims),
            record.response_id
        )
        
        result = {
            "success": True,
            "response_id": record.response_id,
            "patches_created": [],
            "patches_failed": [],
            "errors": []
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for idx, claim in enumerate(correction_claims, 1):
                try:
                    patch_response = await self._create_patch_via_api(
                        client=client,
                        claim=claim,
                        response_id=record.response_id
                    )
                    
                    if patch_response:
                        patch_id = patch_response.get("patch_id")
                        result["patches_created"].append(patch_id)
                        logger.info(
                            "✅ Patch %d/%d created: %s (entity=%s, attr=%s)",
                            idx,
                            len(correction_claims),
                            patch_id,
                            claim.get("entity_id", "?"),
                            claim.get("attribute", "?")
                        )
                    else:
                        result["patches_failed"].append(claim)
                        logger.warning(
                            "Patch %d/%d failed to create for %s.%s",
                            idx,
                            len(correction_claims),
                            claim.get("entity_id", "?"),
                            claim.get("attribute", "?")
                        )
                
                except Exception as exc:
                    error_msg = f"Exception creating patch: {exc}"
                    result["patches_failed"].append(claim)
                    result["errors"].append(error_msg)
                    logger.error(
                        "Patch %d/%d exception: %s",
                        idx,
                        len(correction_claims),
                        exc
                    )
        
        logger.info(
            "REPAIR ENGINE RESULT: response_id=%s, created=%d, failed=%d",
            record.response_id,
            len(result["patches_created"]),
            len(result["patches_failed"])
        )
        
        return result
    
    async def _create_patch_via_api(
        self,
        client: httpx.AsyncClient,
        claim: Dict[str, Any],
        response_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a single patch via HTTP API.
        
        Args:
            client: httpx AsyncClient
            claim: Correction claim from evidence
            response_id: Source response ID
        
        Returns:
            API response dict or None on failure
        """
        url = f"{self.repair_service_url}/api/patches"
        
        payload = {
            "entity_id": claim.get("entity_id"),
            "attribute": claim.get("attribute"),
            "canonical_value": claim.get("rejected_value"),
            "corrected_value": claim.get("asserted_value"),
            "confidence": float(claim.get("confidence", 0.75)),
            "provenance": {
                "source": "unified_feedback_loop",
                "response_id": response_id,
                "entity_name": claim.get("entity_name"),
                "extraction_method": claim.get("source", "unknown")
            },
            "approved": False
        }
        
        try:
            logger.debug(
                "📡 HTTP POST to repair engine: %s with entity_id=%s, attr=%s",
                url,
                payload["entity_id"],
                payload["attribute"]
            )
            
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                logger.debug("Repair engine response: %s", data)
                return data
            else:
                logger.warning(
                    "Repair engine HTTP %d: %s",
                    response.status_code,
                    response.text[:200]
                )
                return None
        
        except httpx.TimeoutError:
            logger.warning("Repair engine timeout (%.1f seconds)", self.timeout)
            return None
        except Exception as exc:
            logger.error("Repair engine communication error: %s", exc)
            return None
    
    async def get_patches_for_entities(
        self,
        entity_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetch applicable patches for entities (used during query retrieval).
        
        Args:
            entity_ids: List of entity IDs to get patches for
        
        Returns:
            List of patch dicts
        """
        if not self.repair_service_url or not entity_ids:
            return []
        
        try:
            entity_ids_str = ",".join(entity_ids)
            url = f"{self.repair_service_url}/api/patches/for-entities"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params={"entity_ids": entity_ids_str})
                
                if response.status_code == 200:
                    data = response.json()
                    patches = data.get("patches", [])
                    if patches:
                        logger.debug("🔧 Retrieved %d patches for %d entities", len(patches), len(entity_ids))
                    return patches
                else:
                    logger.warning("Failed to fetch patches: HTTP %d", response.status_code)
                    return []
        
        except Exception as exc:
            logger.warning("Could not fetch patches: %s", exc)
            return []
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: float = 0.95
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger governance batch in repair engine.
        
        Args:
            auto_approve_threshold: Confidence threshold for auto-approval
        
        Returns:
            Governance batch result or None
        """
        if not self.repair_service_url:
            logger.debug("Repair service URL not configured, skipping governance batch")
            return None
        
        try:
            url = f"{self.repair_service_url}/api/governance/run-batch"
            payload = {"auto_approve_threshold": auto_approve_threshold}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info("Starting governance batch with threshold=%.2f", auto_approve_threshold)
                
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        "Governance batch completed: evaluated=%d, approved=%d, deployed=%d",
                        result.get("total_evaluated", 0),
                        result.get("approved", 0),
                        result.get("deployed", 0)
                    )
                    return result
                else:
                    logger.warning("Governance batch failed: HTTP %d", response.status_code)
                    return None
        
        except Exception as exc:
            logger.error("Governance batch error: %s", exc)
            return None


# Singleton instance
_repair_integration: Optional[RepairEngineIntegration] = None


def get_repair_integration() -> RepairEngineIntegration:
    """Get or create repair integration singleton."""
    global _repair_integration
    if _repair_integration is None:
        _repair_integration = RepairEngineIntegration()
    return _repair_integration


async def trigger_repair_on_feedback(
    record: UnifiedEvaluationRecord,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Public API to trigger repair engine when feedback creates a unified record.
    
    Called from feedback.py after UnifiedEvaluationRecord is created.
    """
    logger.info(
        "Repair integration called: response_id=%s, repair=%s, root_cause=%s",
        record.response_id,
        record.repair,
        record.root_cause
    )
    
    if not record.repair:
        logger.debug("Record doesn't require repair, skipping")
        return {"success": False, "reason": "repair_not_flagged"}
    
    integration = get_repair_integration()
    result = await integration.trigger_repair_engine(record, db)
    
    return result
