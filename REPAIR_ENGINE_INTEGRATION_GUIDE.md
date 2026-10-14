# Repair Engine Integration Guide

## How It Works

The repair engine integrates with the feedback loop to automatically create, manage, and promote correction patches:

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERACTION                      │
│                                                           │
│  User submits feedback: "Fund category is wrong"        │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│            BACKEND (Port 8000)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Feedback API (/api/feedback/submit)             │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │                                    │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │ Feedback Loop                                    │   │
│  │ (packages/amc-feedback-loop)                    │   │
│  │                                                  │   │
│  │ • Classification Service                        │   │
│  │ • Evidence Enrichment Service                   │   │
│  │ • Adaptive Router                               │   │
│  │ • Adjudication Service                          │   │
│  │                                                  │   │
│  │ Creates: UnifiedEvaluationRecord                │   │
│  │ With: dissatisfaction_evidence_json             │   │
│  │       containing correction_claims              │   │
│  └──────────────────┬──────────────────────────────┘   │
│                     │                                    │
│  ┌──────────────────▼──────────────────────────────┐   │
│  │ Trigger Repair Engine                           │   │
│  │ (if corrections detected)                       │   │
│  │                                                  │   │
│  │ HTTP POST to REPAIR_SERVICE_URL                 │   │
│  └──────────────────┬──────────────────────────────┘   │
└─────────────────────┼──────────────────────────────────┘
                      │
        ┌─────────────▼──────────────┐
        │                            │
        ▼                            │
┌──────────────────────────────┐    │
│  Embedded Repair Engine      │    │ or (more common in production)
│  (app.state.repair_engine)   │    │
└──────────────────────────────┘    │
                                     │
                                     ▼
                            ┌──────────────────────────────┐
                            │ REPAIR ENGINE MICROSERVICE   │
                            │ (packages/amc-repair-engine) │
                            │ Port 8002                    │
                            │                              │
                            │ • Create Patch               │
                            │ • Manage Corrections         │
                            │ • Governance Batch           │
                            │ • Graph Integration          │
                            └────────────┬─────────────────┘
                                         │
                                         ▼
                            ┌──────────────────────────────┐
                            │ Neo4j Graph Database         │
                            │                              │
                            │ • Apply approved patches     │
                            │ • Update entity properties   │
                            └──────────────────────────────┘
```

---

## Step-by-Step Integration

### Step 1: Start the Repair Engine Microservice

```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --host 0.0.0.0 --port 8002 --reload
```

### Step 2: Configure Backend

Update `backend/.env`:
```
REPAIR_SERVICE_URL=http://localhost:8002
SERVICE_TIMEOUT=30.0
```

### Step 3: Verify Connection

```bash
# From backend code or terminal
curl http://localhost:8002/api/health
```

### Step 4: Submit Feedback Through Backend

```bash
# User submits feedback
curl -X POST http://localhost:8000/api/feedback/submit \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": "resp_user_123",
    "session_id": "sess_user_456",
    "feedback_type": "correction",
    "feedback_text": "The fund category is Mid Cap, not Large Cap"
  }'
```

### Step 5: Verify Patch Creation

```bash
# Check if patch was created in repair engine
curl http://localhost:8002/api/patches/pending | jq '.total'
```

---

## Integration Points

### 1. Feedback Submission → Unified Record

**File:** `backend/app/api/routes/feedback.py` (or equivalent)

```python
from feedback_loop.api import submit_feedback

async def submit_feedback_endpoint(request: FeedbackRequest):
    """Handle feedback submission and create unified evaluation record."""
    
    # Trigger feedback loop
    unified_record = submit_feedback(
        feedback_id=generate_id(),
        session_id=request.session_id,
        response_id=request.response_id,
        source="active",  # or "passive"
        feedback_text=request.feedback_text,
        # ... other fields
    )
    
    return {
        "status": "received",
        "feedback_id": unified_record.feedback_id,
        "has_corrections": unified_record.dissatisfaction_evidence is not None
    }
```

### 2. Unified Record → Trigger Repair Engine

**File:** `backend/app/services/feedback.py` (or trigger handler)

```python
import httpx
from app.config import get_settings

async def trigger_repair_from_unified_record(record):
    """
    Called when UnifiedEvaluationRecord is created.
    If it contains corrections, submit them to repair engine.
    """
    settings = get_settings()
    
    if not settings.repair_service_url:
        logger.debug("Repair service URL not configured, skipping")
        return
    
    if not record.dissatisfaction_evidence:
        logger.debug("No dissatisfaction evidence, skipping repair trigger")
        return
    
    evidence = record.dissatisfaction_evidence
    correction_claims = evidence.get("correction_claims", [])
    
    if not correction_claims:
        logger.debug("No correction claims, skipping repair trigger")
        return
    
    logger.info(f"📋 Triggering repair engine for {len(correction_claims)} corrections")
    
    async with httpx.AsyncClient(timeout=settings.service_timeout) as client:
        for claim in correction_claims:
            try:
                response = await client.post(
                    f"{settings.repair_service_url}/api/patches",
                    json={
                        "entity_id": claim.get("entity_id"),
                        "attribute": claim.get("attribute"),
                        "canonical_value": claim.get("rejected_value"),
                        "corrected_value": claim.get("asserted_value"),
                        "confidence": float(claim.get("confidence", 0.75)),
                        "provenance": {
                            "source": "unified_feedback_loop",
                            "response_id": record.response_id,
                            "session_id": record.session_id,
                            "feedback_ref": record.feedback_ref
                        }
                    },
                    follow_redirects=True
                )
                
                if response.status_code == 200:
                    patch_data = response.json()
                    logger.info(f"✅ Patch created: {patch_data.get('patch_id')}")
                else:
                    logger.warning(f"⚠️  Repair service error: {response.status_code} {response.text}")
            
            except httpx.TimeoutError:
                logger.warning("⏱️  Repair service timeout")
            except Exception as exc:
                logger.error(f"❌ Error triggering repair: {exc}")
```

### 3. Patch Injection into Query Context

**File:** `backend/app/retrieval/context_assembly.py` (or equivalent)

```python
import httpx

async def get_patches_for_entities(entity_ids: list, repair_service_url: str) -> dict:
    """Fetch applicable patches from repair engine for given entities."""
    
    if not repair_service_url or not entity_ids:
        return {}
    
    entity_ids_str = ",".join(entity_ids)
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{repair_service_url}/api/patches/for-entities",
                params={"entity_ids": entity_ids_str}
            )
            
            if response.status_code == 200:
                return response.json().get("patches", [])
    except Exception as exc:
        logger.warning(f"Could not fetch patches: {exc}")
    
    return {}


async def assemble_context(query: str, entity_ids: list, repair_service_url: str):
    """
    Assemble query context with patch injection.
    """
    
    # 1. Get base context from graph
    context = await graph_retrieval.retrieve(query)
    
    # 2. Fetch applicable patches
    patches = await get_patches_for_entities(entity_ids, repair_service_url)
    
    # 3. Apply patches to context
    if patches:
        logger.info(f"🛠️  Injecting {len(patches)} patches into context")
        
        for patch in patches:
            entity_id = patch["entity_id"]
            attribute = patch["attribute"]
            corrected_value = patch["corrected_value"]
            
            # Find and update entity in context
            for entity in context.get("entities", []):
                if entity.get("id") == entity_id or entity.get("isin") == entity_id:
                    logger.debug(f"   • Patching {entity_id}.{attribute} → {corrected_value}")
                    entity[attribute] = corrected_value
                    entity["_patch_applied"] = True
    
    return context
```

### 4. Governance Batch Processing

**File:** `backend/app/tasks/governance.py` (background task)

```python
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def run_governance_batch(repair_service_url: str):
    """Run governance batch to promote approved patches to graph."""
    
    if not repair_service_url:
        logger.debug("Repair service URL not configured, skipping governance")
        return
    
    logger.info("🔄 Running governance batch...")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{repair_service_url}/api/governance/run-batch",
                json={
                    "auto_approve_threshold": 0.95
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Governance batch completed:")
                logger.info(f"   • Total evaluated: {result['total_evaluated']}")
                logger.info(f"   • Approved: {result['approved']}")
                logger.info(f"   • Rejected: {result['rejected']}")
                logger.info(f"   • Deployed: {result['deployed']}")
            else:
                logger.error(f"Governance batch failed: {response.status_code}")
    
    except Exception as exc:
        logger.error(f"Error running governance batch: {exc}")


def schedule_governance_batch(app):
    """Schedule governance batch to run weekly (Friday 9 AM)."""
    
    scheduler = AsyncIOScheduler()
    
    # Friday 9 AM
    scheduler.add_job(
        run_governance_batch,
        'cron',
        day_of_week='fri',
        hour=9,
        minute=0,
        args=[get_settings().repair_service_url]
    )
    
    scheduler.start()
    logger.info("Governance batch scheduled: Friday 9 AM")
```

---

## Error Handling

### Circuit Breaker Pattern

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def call_repair_service(url: str, method: str, **kwargs):
    """Call repair service with automatic retry."""
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        if method == "POST":
            return await client.post(url, **kwargs)
        elif method == "GET":
            return await client.get(url, **kwargs)
```

### Graceful Degradation

```python
async def assemble_context_with_patches(query: str, entity_ids: list):
    """Get context with patches, but degrade gracefully if repair service fails."""
    
    # Get base context (always works)
    context = await get_base_context(query)
    
    # Try to inject patches (optional enhancement)
    try:
        patches = await get_patches_for_entities(entity_ids)
        context = apply_patches(context, patches)
    except Exception as exc:
        logger.warning(f"Patch injection failed, continuing without: {exc}")
        # Continue with base context
    
    return context
```

---

## Monitoring & Observability

### Health Metrics

```python
async def get_repair_engine_status():
    """Get repair engine health and metrics."""
    
    status = {
        "service": "repair-engine",
        "healthy": False,
        "pending_patches": 0,
        "approved_patches": 0,
        "approved_for_deployment": 0
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Health check
            health = await client.get(f"{repair_url}/api/health")
            status["healthy"] = health.status_code == 200
            
            # Pending patches count
            pending = await client.get(f"{repair_url}/api/patches/pending")
            status["pending_patches"] = pending.json()["total"]
    
    except Exception as exc:
        logger.warning(f"Could not fetch repair engine status: {exc}")
    
    return status
```

### Logging Integration

```python
import structlog

logger = structlog.get_logger("repair_integration")

# Structured logging
logger.info(
    "patch_created",
    patch_id="patch_001",
    entity_id="ISIN_123",
    attribute="fund_category",
    confidence=0.95,
    source="unified_feedback_loop"
)

logger.warning(
    "patch_approval_delayed",
    patch_id="patch_001",
    reason="confidence_below_threshold",
    confidence=0.72,
    threshold=0.80
)

logger.error(
    "governance_batch_failed",
    error="Neo4j connection timeout",
    retry_attempt=3
)
```

---

## Configuration Checklist

- [ ] Repair engine running on port 8002
- [ ] `REPAIR_SERVICE_URL` set in `backend/.env`
- [ ] Neo4j accessible from both backend and repair engine
- [ ] Feedback loop configured and tested
- [ ] Patch creation tested via API
- [ ] Patch injection in query context verified
- [ ] Governance batch scheduled
- [ ] Monitoring/alerting configured
- [ ] Error handling and retries tested
- [ ] Circuit breaker enabled
- [ ] Logging configured and tested

---

## Testing End-to-End

### Integration Test Script

```bash
#!/bin/bash

echo "🧪 Testing Repair Engine Integration"
echo

# 1. Health check
echo "1️⃣ Health Check"
curl -s http://localhost:8002/api/health | jq '.status'
echo

# 2. Create patch
echo "2️⃣ Creating patch"
PATCH_ID=$(curl -s -X POST http://localhost:8002/api/patches \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "TEST_001",
    "attribute": "test_attribute",
    "canonical_value": "old",
    "corrected_value": "new",
    "confidence": 0.85
  }' | jq -r '.patch_id')
echo "   Created: $PATCH_ID"
echo

# 3. Check pending
echo "3️⃣ Checking pending patches"
curl -s http://localhost:8002/api/patches/pending | jq '.total'
echo

# 4. Approve
echo "4️⃣ Approving patch"
curl -s -X POST http://localhost:8002/api/patches/$PATCH_ID/approve | jq '.status'
echo

# 5. Run governance
echo "5️⃣ Running governance batch"
curl -s -X POST http://localhost:8002/api/governance/run-batch | jq '.deployed'
echo

echo "✅ Integration test complete!"
```

---

## Summary

The repair engine microservice integrates seamlessly into the feedback loop:

1. **Feedback submission** → Feedback loop processes
2. **Unified record created** → With correction claims
3. **Repair engine triggered** → Creates patches
4. **Patches stored** → In correction patch layer
5. **Governance batch** → Approves and deploys patches
6. **Graph updated** → Neo4j reflects corrections
7. **Next query** → Uses corrected values

**Result:** Self-improving knowledge graph through feedback-driven corrections.

