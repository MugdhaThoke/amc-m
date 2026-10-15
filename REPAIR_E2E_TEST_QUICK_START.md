# Repair Engine E2E Test - Quick Start

## Run This Now (5 Minutes)

### 1️⃣ Start Backend (Terminal 1)
```bash
cd backend
python -m uvicorn app.main:app --port 8000 --log-level info
```

Watch for logs with 🚀 🎯 ✅ indicators

### 2️⃣ Start Repair Engine (Terminal 2)
```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --port 8002 --log-level info
```

### 3️⃣ Run End-to-End Test (Terminal 3)
```bash
cd backend
python test_e2e_repair_flow.py
```

### 4️⃣ Watch Logs

**Backend logs should show:**
```
📥 FEEDBACK LOOP START
✅ Feedback loop pipeline completed
📊 Unified record created: repair=True
🚀 REPAIR ENGINE TRIGGER: Processing 1 correction(s)
✅ Patch created
🎯 REPAIR ENGINE RESULT
```

**Repair engine logs should show:**
```
🔧 REPAIR SERVICE: Processing unified record
📋 Extracting corrections
✅ Extracted 1 correction(s)
🛠️ Creating patches
✅ Patch created
✅ REPAIR SERVICE COMPLETE
```

---

## What Happens

```
USER: Query about "Axis Bluechip Fund"
  ↓
SYSTEM: Response (with initial category value)
  ↓
USER: Submits feedback "It's actually Mid Cap not Large Cap"
  ↓
BACKEND: Creates UnifiedEvaluationRecord with repair=true
  ↓
REPAIR ENGINE: Creates patch
  ↓
BACKEND: Approves and deploys patch
  ↓
USER: Submits follow-up query
  ↓
SYSTEM: Response now uses corrected value! ✨
```

---

## Expected Output

```
🧪 END-TO-END REPAIR FLOW TEST
================================

STEP 1️⃣: USER SUBMITS INITIAL QUERY
Query: "What is the fund category of Axis Bluechip Fund?"
✅ Query successful!

STEP 2️⃣: USER SUBMITS FEEDBACK WITH CORRECTION  
Feedback: "The fund category is actually Mid Cap, not Large Cap"
✅ Feedback submitted successfully!

STEP 3️⃣: CHECKING UNIFIED EVALUATION RECORD
✅ Unified record found!
   Entry Route: hitl
   Root Cause: knowledge
   Repair Required: True
   Correction Claims: 1

STEP 4️⃣: CHECKING REPAIR ENGINE PATCHES
✅ Repair engine status retrieved!
   Total Pending Patches: 1
   [1] Entity: ISIN_AXIS_BLUECHIP
       Attribute: fund_category
       Value: Mid Cap
       Confidence: 0.95

STEP 5️⃣: APPROVING PATCHES
   ✅ Approved: patch_001_...

STEP 6️⃣: RUNNING GOVERNANCE BATCH
✅ Governance batch completed!
   Total Evaluated: 1
   Approved: 1
   Deployed to Graph: 1

STEP 7️⃣: USER SUBMITS FOLLOW-UP QUERY
Query: "What is Axis Bluechip Fund's category again?"
✅ Follow-up query successful!
   Response: "...Mid Cap..." ✨
```

---

## Logs to Look For

### Backend (`http://localhost:8000`)

| Log | What It Means |
|-----|---------------|
| `📥 FEEDBACK LOOP START` | Feedback received, processing beginning |
| `✅ Feedback loop pipeline completed` | Steps 1-4 done, unified record created |
| `🔧 REPAIR FLAGGED` | Record needs repair |
| `🚀 REPAIR ENGINE TRIGGER` | Calling repair engine microservice |
| `📡 HTTP POST to repair engine` | Sending patch request |
| `✅ Patch created` | Repair engine received and created patch |
| `🎯 REPAIR ENGINE RESULT` | Final result from repair engine call |

### Repair Engine (`http://localhost:8002`)

| Log | What It Means |
|-----|---------------|
| `🔧 REPAIR SERVICE: Processing unified record` | Received patch request |
| `📋 Extracting corrections` | Reading correction claims |
| `✅ Extracted 1 correction(s)` | Found the user's correction |
| `🛠️ Creating patches` | Creating patches in layer |
| `✅ Patch created: patch_001_...` | Individual patch created |
| `✅ REPAIR SERVICE COMPLETE` | All done, patches ready |

---

## Troubleshooting

### ❌ "Backend not responding"
- Verify port 8000: `curl http://localhost:8000/api/health`
- Check backend is running in Terminal 1

### ❌ "Repair Engine not responding"
- Verify port 8002: `curl http://localhost:8002/api/health`
- Check repair engine is running in Terminal 2

### ❌ No logs appearing
- Add `--log-level info` to uvicorn command
- Add `export PYTHONUNBUFFERED=1` before starting

### ❌ "No patches created"
- Check unified record has `repair=true`:
  ```bash
  sqlite3 backend/data.db "SELECT response_id, repair FROM unified_evaluation_records LIMIT 3;"
  ```
- Check dissatisfaction_evidence has corrections:
  ```bash
  sqlite3 backend/data.db "SELECT dissatisfaction_evidence_json FROM unified_evaluation_records LIMIT 1;" | jq '.correction_claims'
  ```

---

## Key Configuration

Verify `backend/.env` has:
```
MICROSERVICES_MODE=true
REPAIR_SERVICE_URL=http://localhost:8002
SERVICE_TIMEOUT=30.0
```

---

## Under the Hood

The test script:
1. ✅ Checks both services are healthy
2. ✅ Submits a query (gets response_id)
3. ✅ Submits feedback with correction (triggers feedback loop)
4. ✅ Waits 2 seconds for processing
5. ✅ Checks unified record was created with `repair=true`
6. ✅ Checks repair engine has patches
7. ✅ Approves patches via API
8. ✅ Runs governance batch
9. ✅ Submits follow-up query
10. ✅ Verifies response uses corrected value

---

## Success!

If you see:
- ✅ All steps completed in test output
- 🚀 Logs with repair engine indicators
- Patches created (non-zero)
- Patches deployed (non-zero)

**Then the end-to-end flow is working!** 🎉

---

## Next: Monitor Real-Time

Open 3 terminals and run simultaneously to watch the flow in real-time:

```bash
# Terminal 1: Backend with logs
cd backend && python -m uvicorn app.main:app --port 8000 --log-level info

# Terminal 2: Repair engine with logs
cd packages/amc-repair-engine && python -m uvicorn src.amc_repair.server:app --port 8002 --log-level info

# Terminal 3: Run test
cd backend && python test_e2e_repair_flow.py
```

Watch logs in Terminal 1 and 2 as test runs in Terminal 3!

---

## Questions?

Refer to full guide: `backend/E2E_REPAIR_FLOW_GUIDE.md`

