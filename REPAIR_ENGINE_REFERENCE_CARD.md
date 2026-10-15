# Repair Engine - Reference Card

## 🚀 Start Immediately

```bash
# Step 1: Open terminal, go to repair engine
cd packages/amc-repair-engine

# Step 2: Start microservice (port 8002)
python -m uvicorn src.amc_repair.server:app --port 8002

# Step 3: Verify in another terminal
curl http://localhost:8002/api/health
```

**Expected:** Returns `{"status": "healthy", ...}`

---

## 📋 Configure Backend

Edit `backend/.env`:
```
REPAIR_SERVICE_URL=http://localhost:8002
```

Restart backend:
```bash
cd backend
python -m uvicorn app.main:app --port 8000
```

---

## 🧪 Test in 60 Seconds

### Create a Patch
```bash
curl -X POST http://localhost:8002/api/patches \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "ISIN_TEST",
    "attribute": "category",
    "canonical_value": "Large Cap",
    "corrected_value": "Mid Cap",
    "confidence": 0.95
  }'
```

### Check Pending
```bash
curl http://localhost:8002/api/patches/pending
```

### Approve
```bash
curl -X POST http://localhost:8002/api/patches/patch_001/approve
```

### Govern
```bash
curl -X POST http://localhost:8002/api/governance/run-batch
```

---

## 📚 Key Endpoints

| Command | Endpoint |
|---------|----------|
| Health | `GET /api/health` |
| Create | `POST /api/patches` |
| Pending | `GET /api/patches/pending` |
| Approve | `POST /api/patches/{id}/approve` |
| Reject | `POST /api/patches/{id}/reject` |
| Batch Approve | `POST /api/patches/batch-approve` |
| Governance | `POST /api/governance/run-batch` |
| API Docs | `http://localhost:8002/docs` |

---

## 🔧 Common Tasks

### Monitor Patches
```bash
watch -n 5 'curl -s http://localhost:8002/api/patches/pending | jq ".total"'
```

### View Logs
```bash
# Already running: Check console output
# Or restart with debug logging:
python -m uvicorn src.amc_repair.server:app --port 8002 --log-level debug
```

### Kill Process (Port Conflict)
```bash
# Linux/Mac
lsof -ti:8002 | xargs kill -9

# Windows
netstat -ano | findstr :8002
taskkill /PID <PID> /F
```

### Restart Backend
```bash
cd backend
python -m uvicorn app.main:app --port 8000
```

---

## 🐳 Docker Quick Run

### Build
```bash
cd packages/amc-repair-engine
docker build -t amc-repair-engine .
```

### Run
```bash
docker run -p 8002:8002 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  amc-repair-engine
```

### Docker Compose (Full Stack)
```bash
# From root directory
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f repair-engine

# Stop
docker-compose down
```

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| **Connection refused** | Verify running: `curl http://localhost:8002/api/health` |
| **Port 8002 in use** | `lsof -ti:8002 \| xargs kill -9` |
| **Neo4j error** | Check `NEO4J_URI` in `.env`, verify Neo4j running |
| **Module not found** | `pip install -e .` in repair-engine directory |
| **Timeout** | Increase `SERVICE_TIMEOUT` in backend `.env` |

---

## 📊 Integration Checklist

- [ ] Repair engine running on port 8002
- [ ] `http://localhost:8002/api/health` returns 200
- [ ] `REPAIR_SERVICE_URL` set in backend `.env`
- [ ] Backend restarted
- [ ] Created test patch via `POST /api/patches`
- [ ] Verified patch in `GET /api/patches/pending`
- [ ] Approved patch via `POST /api/patches/{id}/approve`
- [ ] Ran governance batch via `POST /api/governance/run-batch`

---

## 🎯 Workflow

```
1. User submits feedback
   ↓
2. Backend creates UnifiedEvaluationRecord
   ↓
3. Backend calls Repair Engine API
   ↓
4. Repair Engine creates patch
   ↓
5. Patch stored in layer
   ↓
6. Next query: patch injected
   ↓
7. User gets corrected result
```

---

## 📈 Files

| What | Where |
|------|-------|
| **Executable** | `packages/amc-repair-engine/src/amc_repair/server.py` |
| **Config** | `backend/.env` (see REPAIR_SERVICE_URL) |
| **Startup script (Linux/Mac)** | `packages/amc-repair-engine/run_repair_engine.sh` |
| **Startup script (Windows)** | `packages/amc-repair-engine/run_repair_engine.bat` |
| **Docker** | `packages/amc-repair-engine/Dockerfile` |
| **Quick Start** | `REPAIR_ENGINE_QUICK_START.md` |
| **Full Guide** | `REPAIR_ENGINE_MICROSERVICE_GUIDE.md` |
| **Integration** | `REPAIR_ENGINE_INTEGRATION_GUIDE.md` |

---

## 💾 Environment Variables

```bash
# Essential
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=amc@1234
REPAIR_SERVICE_URL=http://localhost:8002  # In backend

# Optional
PATCH_TTL_DAYS=7
AUTO_APPROVE_THRESHOLD=0.95
USE_REDIS=false
LOG_LEVEL=info
```

---

## 🎓 Learn More

| Topic | File |
|-------|------|
| Quick start (5 min) | `REPAIR_ENGINE_QUICK_START.md` |
| Full setup | `REPAIR_ENGINE_MICROSERVICE_GUIDE.md` |
| How to integrate | `REPAIR_ENGINE_INTEGRATION_GUIDE.md` |
| Complete summary | `REPAIR_ENGINE_SETUP_SUMMARY.md` |
| API docs | `http://localhost:8002/docs` |

---

## ✅ Status Check

Run this to verify everything is working:

```bash
#!/bin/bash

echo "🔍 Repair Engine Status Check"
echo

echo "1. Repair Engine Health:"
curl -s http://localhost:8002/api/health | jq '.status' || echo "❌ Not running"

echo
echo "2. Pending Patches:"
curl -s http://localhost:8002/api/patches/pending | jq '.total' || echo "❌ Error"

echo
echo "3. Backend Health:"
curl -s http://localhost:8000/api/health | jq '.status' || echo "❌ Not running"

echo
echo "✅ Check complete!"
```

---

## 🚀 Ready to Deploy?

```bash
# Production: Use Docker Compose
docker-compose up -d

# Development: Run directly
python -m uvicorn src.amc_repair.server:app --port 8002
```

---

## 📞 Need Help?

1. Check API docs: `http://localhost:8002/docs`
2. Read comprehensive guide: `REPAIR_ENGINE_MICROSERVICE_GUIDE.md`
3. Check integration: `REPAIR_ENGINE_INTEGRATION_GUIDE.md`
4. View logs for errors
5. Verify Neo4j connectivity

---

## 🎯 Next: Test Full Flow

1. Start repair engine (this guide, step 1)
2. Configure backend (step 2)
3. Create patch (section "Test in 60 Seconds")
4. Verify in backend: Submit feedback → Get correction patch
5. Check governance batch processed it

**You're done!** The repair engine is managing your knowledge graph corrections. 🎉

