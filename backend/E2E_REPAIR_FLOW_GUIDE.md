# End-to-End Repair Flow - Complete Guide

## Overview

This guide demonstrates how to test the complete feedback → repair → correction workflow with full logging visibility.

**The Flow:**
```
1. User submits query          → Gets initial response
2. User submits feedback       → With correction ("should be X not Y")
3. Feedback loop processes    → Creates UnifiedEvaluationRecord  
4. Repair engine triggered    → Creates patches
5. User submits follow-up     → Gets corrected response!
6. Logs show entire journey   → ✅ 🚀 📋 🎯 indicators
```

---

## Prerequisites

### 1. Services Must Be Running

**Backend:**
```bash
cd backend
python -m uvicorn app.main:app --port 8000 --log-level info
```

**Repair Engine (in new terminal):**
```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --port 8002 --log-level info
```

### 2. Verify Configuration

Check `backend/.env`:
```ini
MICROSERVICES_MODE=true
REPAIR_SERVICE_URL=http://localhost:8002
SERVICE_TIMEOUT=30.0
```

### 3. Database Setup

Ensure Neo4j is running and accessible:
```bash
# Verify Neo4j
curl bolt://localhost:7687
# Should not fail
```

---

## Running the Test

### Option 1: Automated Test Script (Recommended)

```bash
cd backend
python test_e2e_repair_flow.py
```

**What it does:**
1. Checks service health
2. Submits initial query
3. Submits feedback with correction
4. Verifies unified record creation
5. Checks repair engine patches
6. Approves patches
7. Runs governance batch
8. Submits follow-up query
9. Shows final results

**Output includes:**
```
📥 FEEDBACK LOOP START
✅ Feedback loop pipeline completed
📊 Unified record created
🔧 REPAIR FLAGGED
🚀 REPAIR ENGINE TRIGGER
✅ Patch 1/1 created: patch_001_...
🎯 REPAIR ENGINE RESULT
```

### Option 2: Manual Step-by-Step

#### Step 1: Submit Initial Query

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the fund category of Axis Bluechip Fund?",
    "session_id": "test_session_001",
    "actor_id": "test_user_001",
    "top_k": 5
  }'
```

**Save the `response_id` from response.**

#### Step 2: Submit Feedback with Correction

```bash
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": "<response_id_from_step_1>",
    "session_id": "test_session_001",
    "interaction_id": "inter_test_001",
    "turn_number": 1,
    "query_text": "What is the fund category of Axis Bluechip Fund?",
    "actor_id": "test_user_001",
    "actor_role": "reviewer",
    "feedback_text": "The fund category is actually Mid Cap, not Large Cap",
    "selected_categories": ["F04"],
    "client_timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }'
```

**Watch the backend logs for:**
```
📥 FEEDBACK LOOP START
✅ Feedback loop pipeline completed
📊 Unified record created: entry_route=hitl, root_cause=knowledge, repair=True
🔧 REPAIR FLAGGED
🚀 REPAIR ENGINE TRIGGER: Processing 1 correction(s)
📡 HTTP POST to repair engine
✅ Patch created
🎯 REPAIR ENGINE RESULT
```

#### Step 3: Check Repair Engine Patches

```bash
curl http://localhost:8002/api/patches/pending | jq '.'
```

**Should show patches with:**
- `entity_id`: ISIN_AXIS_BLUECHIP (or similar)
- `attribute`: fund_category
- `corrected_value`: Mid Cap
- `canonical_value`: Large Cap
- `confidence`: 0.95

#### Step 4: Approve Patches

```bash
curl -X POST http://localhost:8002/api/patches/<patch_id>/approve
```

#### Step 5: Run Governance Batch

```bash
curl -X POST http://localhost:8002/api/governance/run-batch \
  -H "Content-Type: application/json" \
  -d '{"auto_approve_threshold": 0.95}'
```

**Should show:**
```json
{
  "status": "completed",
  "total_evaluated": 1,
  "approved": 1,
  "deployed": 1
}
```

#### Step 6: Submit Follow-Up Query

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is Axis Bluechip Fund'"'"'s category again?",
    "session_id": "test_session_001",
    "actor_id": "test_user_001",
    "top_k": 5
  }'
```

**Expected:** Response now uses corrected value "Mid Cap"

---

## Expected Logs

### Backend Logs (Port 8000)

```
📥 FEEDBACK LOOP START: feedback_id=fb_abc123, response_id=resp_xyz789, session_id=test_001, source=active
✅ RECORD_INSERTED: feedback record into data.db: feedback_id=fb_abc123, response_id=resp_xyz789

📋 Running feedback loop pipeline (Steps 1-4)...
✅ Feedback loop pipeline completed: success=True

📊 Unified record created: entry_route=hitl, root_cause=knowledge, severity=medium, repair=True

🔧 REPAIR FLAGGED: response_id=resp_xyz789, root_cause=knowledge, repair_target=vector

🚀 REPAIR ENGINE TRIGGER: Processing 1 correction(s) for response_id=resp_xyz789

📡 HTTP POST to repair engine: http://localhost:8002/api/patches with entity_id=ISIN_AXIS, attr=fund_category

📥 Repair engine response: {'status': 'created', 'patch_id': 'patch_001_ISIN_AXIS_fund_category'}

✅ Patch 1/1 created: patch_001_ISIN_AXIS_fund_category (entity=ISIN_AXIS, attr=fund_category)

🎯 REPAIR ENGINE RESULT: response_id=resp_xyz789, created=1, failed=0
```

### Repair Engine Logs (Port 8002)

```
INFO: Application startup complete [lifespan]
INFO repair_service: 
================================================================================
🔧 REPAIR SERVICE: Processing unified record for response_id=resp_xyz789
================================================================================
   Entry Route: hitl
   Root Cause: knowledge
   Repair Required: True
   Repair Target: vector
🚀 Processing repair...

📋 Extracting corrections from dissatisfaction evidence...
✅ Extracted 1 correction(s)
   [1] ISIN_AXIS.fund_category: Large Cap → Mid Cap (conf=0.95)

🛠️  Creating patches...
✅ Patch created: patch_001_ISIN_AXIS_fund_category
================================================================================
✅ REPAIR SERVICE COMPLETE
   Patches Created: 1
   Response ID: resp_xyz789
================================================================================

INFO repair_service: ✅ Patch created: patch_001_ISIN_AXIS_fund_category
INFO: Received GET /api/patches/pending
INFO repair_service: {'total': 1, 'patches': [...]}
```

---

## Troubleshooting

### No Logs Appearing?

**Issue:** Logs not showing in backend

**Solution:**
1. Start backend with explicit log level:
   ```bash
   python -m uvicorn app.main:app --port 8000 --log-level info
   ```

2. Check that `PYTHONUNBUFFERED=1`:
   ```bash
   export PYTHONUNBUFFERED=1
   python -m uvicorn app.main:app --port 8000
   ```

### Repair Engine Not Called?

**Issue:** No `🚀 REPAIR ENGINE TRIGGER` in logs

**Solution:**
1. Verify `REPAIR_SERVICE_URL` in `backend/.env`:
   ```
   REPAIR_SERVICE_URL=http://localhost:8002
   ```

2. Check repair engine is running:
   ```bash
   curl http://localhost:8002/api/health
   ```

3. Check unified record has `repair=true`:
   ```bash
   sqlite3 backend/data.db "SELECT response_id, repair, root_cause FROM unified_evaluation_records LIMIT 5;"
   ```

### Patches Not Created?

**Issue:** No patches appear in repair engine

**Solution:**
1. Check dissatisfaction_evidence has correction_claims:
   ```bash
   sqlite3 backend/data.db "SELECT response_id, dissatisfaction_evidence_json FROM unified_evaluation_records LIMIT 1;" | jq '.correction_claims'
   ```

2. Verify Neo4j connectivity from repair engine:
   ```bash
   # In repair engine logs, look for connection errors
   # Or test manually:
   python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'amc@1234')); d.verify_connectivity()"
   ```

---

## Understanding the Logs

### Log Markers

| Marker | Meaning |
|--------|---------|
| `📥` | Data input/entry point |
| `🔍` | Checking/verifying |
| `✅` | Success |
| `❌` | Failure |
| `⚠️` | Warning |
| `📋` | Processing/workflow step |
| `🚀` | Launching/triggering |
| `🔧` | Repair/correction activity |
| `🎯` | Result/completion |

### Log Levels

- **INFO**: Major workflow steps, successes, results
- **DEBUG**: Detailed steps, decisions, data flow
- **WARNING**: Issues that don't stop execution
- **ERROR**: Failures that need attention

---

## Complete User Story Example

### Scenario: User Discovers Fund Category Error

**Step 1: User Queries**
```
User: "What is Axis Bluechip Fund's category?"
System: "Axis Bluechip Fund is categorized as Large Cap..."
```

**Logs:**
```
📥 Query received
✅ Response generated: resp_xyz789
```

**Step 2: User Submits Correction**
```
User: (Submits feedback) "It's actually Mid Cap, not Large Cap"
System: "Thank you for the correction!"
```

**Logs:**
```
📥 FEEDBACK LOOP START
✅ Unified record created with repair=True
🔧 REPAIR FLAGGED
🚀 REPAIR ENGINE TRIGGER
✅ Patch created
🎯 REPAIR ENGINE RESULT
```

**Step 3: Governance Process**
```
Admin: (Reviews pending patches)
Admin: (Approves high-confidence patches)
System: Deploys to Neo4j
```

**Logs:**
```
📋 Governance batch started
✅ Evaluated 1 patch
✅ Approved 1 patch
✅ Deployed to graph
```

**Step 4: User Gets Corrected Response**
```
User: "What's Axis Bluechip Fund's category again?"
System: "Axis Bluechip Fund is categorized as Mid Cap..." ✨
```

**Logs:**
```
📥 Query received
🔍 Fetching patches for entity
✅ 1 patch applied to context
✅ Response synthesized with corrected data
```

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/repair_integration.py` | Handles HTTP calls to repair engine |
| `backend/app/services/feedback.py` | Triggers feedback loop and repair integration |
| `backend/app/api/routes/feedback.py` | Feedback submission endpoint |
| `backend/test_e2e_repair_flow.py` | Complete end-to-end test script |
| `backend/.env` | Configuration (REPAIR_SERVICE_URL) |

---

## Performance Notes

- **Feedback → Unified Record:** ~1-2 seconds
- **Unified Record → Patches:** ~0.5-1 second (HTTP call)
- **Approval → Deployment:** ~0.5 seconds
- **Query with Patches:** No additional latency

---

## Success Criteria

✅ **Test Successful If:**
- Backend logs show `🚀 REPAIR ENGINE TRIGGER`
- Repair engine logs show patch creation
- Repair engine `/api/patches/pending` returns patches
- Governance batch shows "deployed": > 0
- Follow-up query uses corrected value

---

## Running in Production

For production deployment:

1. Run repair engine on separate server (not localhost)
2. Use full `REPAIR_SERVICE_URL`: `http://repair-engine:8002`
3. Configure Redis for distributed caching
4. Schedule governance batch as cron job
5. Monitor patch creation and approval rates
6. Set up alerts for failures

---

## Next Steps

1. **Run the test:** `python test_e2e_repair_flow.py`
2. **Check logs:** Verify markers appear in both services
3. **Query database:** Verify records and patches created
4. **Test variations:** Try different feedback types
5. **Monitor:** Track patch creation and approval rates

---

## Support

For issues:
- Check `REPAIR_SERVICE_URL` in backend `.env`
- Verify repair engine is running on port 8002
- Check logs for error messages
- Verify Neo4j connectivity
- Ensure feedback loop data created properly

Good luck! 🚀

