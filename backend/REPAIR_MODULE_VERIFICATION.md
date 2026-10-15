# 🔧 Repair Module Implementation & Verification Guide

## Overview

The repair module is now **fully integrated**. When a user submits feedback that triggers a correction need, the system now automatically:

1. ✅ Captures feedback (active or passive)
2. ✅ Builds unified evaluation records via feedback loop
3. ✅ **NEW:** Automatically extracts corrections from evidence
4. ✅ **NEW:** Creates patches in the shadow correction layer
5. ✅ Injects patches into retrieval context
6. ✅ Weekly governance batch promotes approved patches to Neo4j

---

## What Changed

### New Files

**`backend/app/services/repair_service.py`** (280 lines)
- `extract_corrections_from_evidence()` - Extracts correction claims from dissatisfaction evidence
- `resolve_entity_id()` - Maps fund names to entity IDs
- `create_patch_from_correction()` - Creates patches in shadow layer
- `process_unified_record_for_repair()` - Main orchestrator (async)
- `process_unified_record_for_repair_sync()` - Sync wrapper for FastAPI

**`backend/tests/test_repair_service.py`** (450 lines)
- Comprehensive test suite with fixtures
- 15+ test cases covering all code paths
- Integration tests for end-to-end flow

### Modified Files

**`backend/app/services/feedback.py`**
- Added import: `from app.services.repair_service import process_unified_record_for_repair_sync`
- Added parameter: `process_repair: bool = True` to `trigger_feedback_loop()`
- Added automatic repair processing after unified record creation
- Auto-calls repair service when `record.repair = true`

---

## How It Works Now

### Flow Diagram

```
User Submits Feedback
        ↓
POST /api/feedback/submit or /api/feedback/follow-up
        ↓
Feedback captured in response_feedback table
        ↓
trigger_feedback_loop() called
        ↓
feedback_loop package runs:
  - Step 1: Classification
  - Step 2: Evidence enrichment
  - Step 3: Adaptive routing
  - Step 4: Adjudication
        ↓
unified_evaluation_records created
        ↓
[NEW] repair_service.process_unified_record_for_repair_sync()
        ↓
Check if repair=true && dissatisfaction_evidence present
        ↓
extract_corrections_from_evidence()
        ↓
For each correction:
  - resolve_entity_id() → ISIN
  - create_patch_from_correction() → shadow layer
        ↓
Patches now active in correction_patch_layer
        ↓
[Next Query] apply_patches_to_context() injects corrections
        ↓
LLM sees: "⚠️ INSTRUCTION: Use corrected value X not Y"
        ↓
[Friday 9 AM UTC] governance_batch.py promotes approved patches
        ↓
Canonical Neo4j graph updated
        ↓
✅ Loop closes - system self-improves
```

---

## Step-by-Step Verification

### Step 1: Verify Repair Service Can Be Imported

```python
from app.services.repair_service import (
    extract_corrections_from_evidence,
    process_unified_record_for_repair_sync
)
print("✅ Repair service imported successfully")
```

### Step 2: Run the Test Suite

```bash
cd backend
pytest tests/test_repair_service.py -v

# Expected output:
# test_repair_service.py::TestExtractCorrectionsFromEvidence::test_extract_from_structured_claims PASSED
# test_repair_service.py::TestExtractCorrectionsFromEvidence::test_extract_from_feedback_text PASSED
# ... (15+ more tests)
# ============ 15 passed in 2.34s ============
```

### Step 3: Check Logs for Repair Processing

After submitting feedback, watch for these log lines:

**✅ SUCCESS INDICATORS:**

```
[INFO] app.services.feedback: trigger_feedback_loop started: feedback_id=fb_xyz, ...
[INFO] app.feedback_loop: record_built entry_route=hitl, root_cause=knowledge, ...
[INFO] app.services.repair: Processing repair for response_id=resp_abc, root_cause=knowledge, repair_target=vector
[INFO] app.services.repair: Extracted 1 correction(s) from unified record
[INFO] app.services.repair: Resolved entity 'Axis Liquid Fund' → INF846K01DP5 (confidence=0.95)
[INFO] app.services.repair: Created correction patch patch_xyz: INF846K01DP5.TER 0.75 → 0.82 (confidence=0.92)
[INFO] app.services.repair: Repair processing completed: 1 patches created for resp_abc
[INFO] app.services.feedback: Repair processing completed: 1 patches created for resp_abc
```

**❌ TROUBLESHOOTING INDICATORS:**

```
[INFO] app.services.repair: No corrections extracted from record  → No feedback text or structured claims
[WARNING] app.services.repair: Could not resolve entity ID  → Fund matcher not working
[WARNING] app.services.repair: Repair processing had errors  → Check error details
[ERROR] app.services.repair: Repair processing exception  → Exception in processing
```

### Step 4: Verify Patches Were Created

**Via API:**
```bash
curl http://localhost:8000/api/governance/pending-corrections \
  -H "Authorization: Bearer <token>"

# Expected response:
{
  "total": 1,
  "pending": [
    {
      "patch_id": "patch_abc123",
      "entity_id": "INF846K01DP5",
      "attribute": "TER",
      "canonical_value": "0.75",
      "corrected_value": "0.82",
      "confidence": 0.92,
      "approved": false,
      "created_at": "2026-01-20T10:35:22Z",
      "expires_at": "2026-01-27T10:35:22Z"
    }
  ]
}
```

**Via Database:**
```sql
sqlite3 backend/data.db

-- Query pending corrections (note: they're in-memory, not in DB unless Redis is used)
SELECT * FROM correction_patches ORDER BY created_at DESC LIMIT 5;

-- Query unified records with repairs
SELECT response_id, repair, repair_target, root_cause 
FROM unified_evaluation_records 
WHERE repair = 1 
ORDER BY created_at DESC 
LIMIT 5;
```

**Via Python REPL:**
```python
from app.graph.correction_patch_layer import get_correction_patch_layer

layer = get_correction_patch_layer()
patches = layer.get_all_pending()

for patch in patches:
    print(f"Patch: {patch.patch_id}")
    print(f"  Entity: {patch.entity_id}")
    print(f"  Attribute: {patch.attribute}")
    print(f"  Value: {patch.canonical_value} → {patch.corrected_value}")
    print(f"  Confidence: {patch.confidence}")
    print()
```

### Step 5: Verify Patches Appear in Query Context

Submit a query for an entity with a pending patch:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the TER for Axis Liquid Fund?"
  }'

# Look in response context for:
# "⚠️ CORRECTION - TER"
# "Entity: INF846K01DP5"
# "Corrected Value: 0.82"
# "⚠️ INSTRUCTION: Use corrected value (0.82)"
```

### Step 6: Test End-to-End Flow

**Complete test scenario:**

```bash
# 1. Query the system to get a baseline response
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the TER for Axis Liquid Fund?"}' \
  > baseline_response.json

# 2. Submit feedback indicating correction needed
curl -X POST http://localhost:8000/api/feedback/submit \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": "resp_12345",
    "session_id": "sess_001",
    "rating": "negative",
    "categories": ["F02"],
    "feedback_text": "TER should be 0.82, not 0.75",
    "corrections": [{
      "entity_name": "Axis Liquid Fund",
      "attribute": "TER",
      "corrected_value": "0.82",
      "original_value": "0.75"
    }]
  }'

# 3. Check if patch was created
curl http://localhost:8000/api/governance/pending-corrections

# 4. Query again - should see correction in context
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the TER for Axis Liquid Fund?"}' \
  > corrected_response.json

# 5. Approve the patch
curl -X POST http://localhost:8000/api/governance/approve/patch_xyz \
  -H "Authorization: Bearer <token>"

# 6. On Friday 9 AM UTC, governance batch will promote it
# (or manually trigger for testing)
```

---

## Data Flow

### Example: TER Correction

**Input (User Feedback):**
```json
{
  "response_id": "resp_12345",
  "feedback_text": "TER should be 0.82, not 0.75",
  "corrections": [{
    "entity_name": "Axis Liquid Fund",
    "attribute": "TER",
    "corrected_value": "0.82",
    "original_value": "0.75"
  }]
}
```

**Processing:**
```
1. Stored in response_feedback table
2. trigger_feedback_loop() called
3. Feedback loop creates unified_evaluation_records:
   {
     "response_id": "resp_12345",
     "repair": true,
     "repair_target": "vector",
     "dissatisfaction_evidence_json": {
       "correction_claims": [{
         "entity_id": "INF846K01DP5",
         "attribute": "TER",
         "asserted_value": "0.82",
         "rejected_value": "0.75",
         "confidence": 0.92
       }]
     }
   }
4. process_unified_record_for_repair_sync() called
5. Correction extracted from dissatisfaction_evidence
6. Patch created in correction_patch_layer:
   {
     "patch_id": "patch_abc123",
     "entity_id": "INF846K01DP5",
     "attribute": "TER",
     "canonical_value": "0.75",
     "corrected_value": "0.82",
     "confidence": 0.92,
     "provenance": {"response_id": "resp_12345", "source": "unified_feedback_loop"}
   }
```

**Output (Next Query Context):**
```
Retrieved facts about Axis Liquid Fund:
  TER: 0.75%
  AUM: ₹4500 Cr
  ...

[CORRECTION - TER]
Entity: INF846K01DP5
Corrected Value: 0.82
Original Value: 0.75
Confidence: 0.92
Created: 2026-01-20T10:35:22Z

⚠️ INSTRUCTION: Use corrected value (0.82) in your response if confidence >= 0.70.
Mention that value was recently updated.

---
Retrieved facts about Axis Liquid Fund:
  TER: 0.75%
  AUM: ₹4500 Cr
  ...
```

---

## Key Functions

### `extract_corrections_from_evidence()`
Extracts correction claims from dissatisfaction_evidence_json.

**Tries in order:**
1. Look for `correction_claims` array in evidence
2. Parse `feedback_text` field if no structured claims
3. Return empty list if nothing found

**Example:**
```python
evidence = {
    "correction_claims": [{
        "entity_id": "INF846K01DP5",
        "attribute": "TER",
        "asserted_value": "0.82",
        "rejected_value": "0.75",
        "confidence": 0.92
    }]
}

corrections = extract_corrections_from_evidence(evidence)
# Returns: [{"entity_id": "INF846K01DP5", ...}]
```

### `resolve_entity_id()`
Maps human-readable fund names to entity IDs (ISIN/dedup_key).

**Uses:**
- `FundNameMatcher` for fuzzy matching
- Supports exact match, fuzzy match, semantic similarity
- Falls back to None if no match found

**Example:**
```python
entity_id = resolve_entity_id("Axis Liquid Fund", "What is TER?")
# Returns: "INF846K01DP5"
```

### `create_patch_from_correction()`
Creates a single correction patch in the shadow layer.

**Steps:**
1. Resolve entity ID (if not already resolved)
2. Validate attribute & values
3. Call `patch_layer.add_correction()`
4. Return patch_id if successful

**Example:**
```python
patch_id = create_patch_from_correction(
    correction={
        "entity_id": "INF846K01DP5",
        "attribute": "TER",
        "asserted_value": "0.82",
        "rejected_value": "0.75",
        "confidence": 0.92
    },
    response_id="resp_12345"
)
# Returns: "patch_abc123"
```

### `process_unified_record_for_repair_sync()`
Main entry point - processes a unified evaluation record.

**Steps:**
1. Fetch unified_evaluation_records by response_id
2. Check if repair=true
3. Extract corrections from evidence
4. Create patches for each correction
5. Return results dict

**Example:**
```python
result = process_unified_record_for_repair_sync("resp_12345")

print(result)
# {
#   "success": true,
#   "patches_created": 1,
#   "patches": ["patch_abc123"],
#   "errors": [],
#   "record_id": "resp_12345"
# }
```

---

## Configuration

### Feature Flags

In `backend/.env` or `backend/app/config.py`:

```ini
# Enable automatic repair processing
ENABLE_REPAIR_PROCESSING=true

# Correction patch layer settings
CORRECTION_PATCH_TTL_DAYS=7
CORRECTION_PATCH_REDIS_HOST=localhost
CORRECTION_PATCH_REDIS_PORT=6379

# Fund matcher confidence threshold
FUND_MATCHER_CONFIDENCE_THRESHOLD=0.7
```

### Logging

Enable detailed repair service logging:

```python
# In backend/app/core/logging.py or logger config
logging.getLogger("app.services.repair").setLevel(logging.DEBUG)
logging.getLogger("app.feedback").setLevel(logging.DEBUG)
```

---

## Troubleshooting

### Problem: No patches created after feedback

**Check 1: Repair flag is set**
```sql
SELECT response_id, repair, repair_target 
FROM unified_evaluation_records 
WHERE response_id = 'resp_xyz';
```
If `repair = 0`, the feedback loop didn't flag it for repair.

**Check 2: Dissatisfaction evidence has data**
```sql
SELECT dissatisfaction_evidence_json 
FROM unified_evaluation_records 
WHERE response_id = 'resp_xyz';
```
Should contain `correction_claims` or `feedback_text`.

**Check 3: Entity resolution**
Test fund matcher directly:
```python
from app.feedback.fund_name_matcher import get_fund_name_matcher
matcher = get_fund_name_matcher()
result = matcher.match("Axis Liquid Fund")
print(result)  # Should show resolved_id
```

**Check 4: Logs**
```bash
grep -i "repair\|patch" backend/logs/*.log
```
Look for errors in repair processing.

### Problem: Patches not appearing in query context

**Check 1: Patches exist**
```bash
curl http://localhost:8000/api/governance/pending-corrections
```

**Check 2: Patch layer is accessible**
```python
from app.graph.correction_patch_layer import get_correction_patch_layer
layer = get_correction_patch_layer()
patches = layer.get_all_patches()
print(f"Total patches: {len(patches)}")
```

**Check 3: Patches being applied**
Look for "[CORRECTION -" in query response context.

### Problem: Memory issues with patches

**Solutions:**
1. Enable Redis (recommended for production)
   - Patches stored in Redis, not memory
   - Automatic cleanup after TTL

2. Manually clear expired patches
   ```python
   from app.graph.correction_patch_layer import get_correction_patch_layer
   layer = get_correction_patch_layer()
   # Expired patches are skipped automatically
   ```

---

## Testing

### Run All Tests

```bash
pytest backend/tests/test_repair_service.py -v --tb=short
```

### Run Specific Test Class

```bash
pytest backend/tests/test_repair_service.py::TestExtractCorrectionsFromEvidence -v
```

### Run With Coverage

```bash
pytest backend/tests/test_repair_service.py --cov=app.services.repair_service --cov-report=html
```

### Manual Integration Test

```bash
# 1. Start backend
cd backend && python -m uvicorn app.main:app --reload

# 2. In another terminal, run test script
python << 'EOF'
import asyncio
from app.core.database import SessionLocal
from app.services.feedback import trigger_feedback_loop
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import EntryRoute, RootCause, Severity

# Create a test unified record with repair flag
db = SessionLocal()
record = UnifiedEvaluationRecord(
    session_id="test_sess_001",
    response_id="test_resp_001",
    entry_route=EntryRoute.HITL,
    evidence_snapshot_ref="test_resp_001",
    root_cause=RootCause.KNOWLEDGE,
    severity=Severity.HIGH,
    repair=True,
    repair_target="vector",
    dissatisfaction_evidence_json={
        "correction_claims": [{
            "entity_id": "INF846K01DP5",
            "attribute": "TER",
            "asserted_value": "0.82",
            "rejected_value": "0.75",
            "confidence": 0.92
        }]
    }
)
db.add(record)
db.commit()

# Process it
from app.services.repair_service import process_unified_record_for_repair_sync
result = process_unified_record_for_repair_sync("test_resp_001", db=db)
print(f"Result: {result}")

# Check patches
from app.graph.correction_patch_layer import get_correction_patch_layer
layer = get_correction_patch_layer()
patches = layer.get_all_patches()
print(f"Patches created: {len(patches)}")
for p in patches:
    print(f"  - {p.patch_id}: {p.entity_id}.{p.attribute} = {p.corrected_value}")

db.close()
EOF
```

---

## Next Steps

1. **Monitor in staging** - Watch repair processing logs for 1-2 weeks
2. **Tune extraction** - Adjust confidence thresholds based on false positives
3. **Add metrics** - Track patch creation, approval, and promotion rates
4. **Enable Redis** - For production deployments with multiple instances
5. **Wire Tier 2/3** - Add NLI and LLM evaluation when needed

---

## Related Files

- `backend/app/services/repair_service.py` - Repair service implementation
- `backend/tests/test_repair_service.py` - Test suite
- `backend/app/services/feedback.py` - Feedback service (updated)
- `backend/app/graph/correction_patch_layer.py` - Shadow layer
- `backend/app/tasks/governance_batch.py` - Weekly promotion
- `backend/app/api/routes/governance.py` - Governance API

---

**Last Updated:** January 2026  
**Status:** ✅ Implementation Complete - Ready for Staging/Production
