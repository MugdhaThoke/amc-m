# Repair Engine - Complete Setup Summary

## What You Now Have

You have the **amc-repair-engine** microservice ready to run as a standalone service or embedded in the backend. The repair engine manages correction patches for self-improving knowledge graphs.

---

## Quick Start (Choose One)

### 🚀 **Option A: Run Now (Fastest)**
```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --port 8002

# Verify
curl http://localhost:8002/api/health
```

### 🐳 **Option B: Docker**
```bash
cd packages/amc-repair-engine
docker build -t amc-repair-engine .
docker run -p 8002:8002 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  amc-repair-engine
```

### 💻 **Option C: Scripts**
```bash
# Linux/Mac
cd packages/amc-repair-engine && bash run_repair_engine.sh

# Windows
cd packages\amc-repair-engine && run_repair_engine.bat
```

---

## Configure Backend

Update `backend/.env`:
```ini
REPAIR_SERVICE_URL=http://localhost:8002
SERVICE_TIMEOUT=30.0
```

---

## Test It

```bash
# Create a patch
curl -X POST http://localhost:8002/api/patches \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "ISIN_TEST",
    "attribute": "category",
    "canonical_value": "Large Cap",
    "corrected_value": "Mid Cap",
    "confidence": 0.95
  }'

# Get pending patches
curl http://localhost:8002/api/patches/pending

# Approve patch
curl -X POST http://localhost:8002/api/patches/{patch_id}/approve

# Run governance batch
curl -X POST http://localhost:8002/api/governance/run-batch
```

---

## Documentation Files Created

| File | Purpose |
|------|---------|
| **REPAIR_ENGINE_MICROSERVICE_GUIDE.md** | Comprehensive guide (standalone vs embedded, Docker, troubleshooting) |
| **REPAIR_ENGINE_QUICK_START.md** | 5-minute setup and testing |
| **REPAIR_ENGINE_INTEGRATION_GUIDE.md** | How to integrate with feedback loop and backend |
| **packages/amc-repair-engine/Dockerfile** | Docker containerization |
| **packages/amc-repair-engine/run_repair_engine.sh** | Linux/Mac startup script |
| **packages/amc-repair-engine/run_repair_engine.bat** | Windows startup script |

---

## Architecture

```
Feedback Loop (Port 8000)
       ↓ (submits corrections)
Repair Engine (Port 8002)
       ↓ (creates patches)
Correction Patch Layer (in-memory cache)
       ↓ (injected into queries)
Query Context
       ↓ (uses corrected values)
LLM Synthesis
       ↓ (returns corrected response)
User
```

---

## Key Features

✅ **Correction Patch Management**
- Create patches from feedback corrections
- Store in-memory with optional Redis persistence
- Auto-expire patches after TTL

✅ **Governance Batch Processing**
- Review pending patches
- Auto-approve based on confidence threshold
- Promote approved patches to Neo4j

✅ **Graph Integration**
- Apply patches to Neo4j entities
- Update properties with timestamps
- Track provenance

✅ **Context Injection**
- Patches automatically injected into query context
- LLM uses corrected values
- Transparent to users

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/patches` | Create patch |
| `GET` | `/api/patches/pending` | Get unapproved patches |
| `GET` | `/api/patches/for-entities` | Get patches for entities |
| `POST` | `/api/patches/{id}/approve` | Approve patch |
| `POST` | `/api/patches/{id}/reject` | Reject patch |
| `POST` | `/api/patches/batch-approve` | Batch approve |
| `POST` | `/api/governance/run-batch` | Run governance batch |

**API Documentation:** Visit `http://localhost:8002/docs` when running

---

## Configuration

### Environment Variables

```bash
# Service
REPAIR_ENGINE_PORT=8002
REPAIR_ENGINE_HOST=0.0.0.0
LOG_LEVEL=info

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=amc@1234

# Redis (optional)
USE_REDIS=false
REDIS_HOST=localhost

# Governance
PATCH_TTL_DAYS=7
AUTO_APPROVE_THRESHOLD=0.95
GOVERNANCE_SCHEDULE="0 9 * * FRI"
```

---

## Integration with Backend

### Feedback Flow

```
User Feedback
   ↓
Backend API (/api/feedback/submit)
   ↓
Feedback Loop Pipeline
   • Classification
   • Evidence Enrichment
   • Adaptive Routing
   • Adjudication
   ↓
UnifiedEvaluationRecord
   ↓
Check: Has corrections?
   ↓ YES
HTTP POST to Repair Engine
   ↓
Create Patches
   ↓
Store in Patch Layer
   ↓
Next Query: Inject Patches
   ↓
LLM Synthesis (with corrections)
```

---

## Monitoring

### Health Check
```bash
curl http://localhost:8002/api/health
```

### Pending Patches Count
```bash
curl http://localhost:8002/api/patches/pending | jq '.total'
```

### Governance Status
```bash
curl -X POST http://localhost:8002/api/governance/run-batch | jq '.'
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8002 in use | Kill process: `lsof -ti:8002 \| xargs kill -9` |
| Neo4j connection failed | Verify Neo4j running, check credentials |
| Patches not creating | Check entity_id format, verify entity exists |
| Memory growing | Check patch TTL, use Redis adapter |

---

## Production Deployment

### Docker Compose (Recommended)

```bash
# Edit docker-compose.yml with your settings
docker-compose up -d

# Verify
docker-compose ps
docker-compose logs repair-engine
```

### Kubernetes (Future)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: repair-engine
spec:
  replicas: 2
  selector:
    matchLabels:
      app: repair-engine
  template:
    metadata:
      labels:
        app: repair-engine
    spec:
      containers:
      - name: repair-engine
        image: amc-repair-engine:latest
        ports:
        - containerPort: 8002
        env:
        - name: NEO4J_URI
          value: bolt://neo4j:7687
        - name: PATCH_TTL_DAYS
          value: "7"
```

---

## Performance Considerations

- **Memory**: ~10MB per 1000 patches
- **Neo4j**: Indexes recommended on entity_id, created_at
- **Redis**: Use for distributed deployments (optional)
- **Batch Size**: Configure in governance settings

---

## Next Steps

1. **Start Repair Engine**
   ```bash
   cd packages/amc-repair-engine
   python -m uvicorn src.amc_repair.server:app --port 8002
   ```

2. **Configure Backend**
   - Update `backend/.env` with `REPAIR_SERVICE_URL=http://localhost:8002`
   - Restart backend

3. **Test Feedback Loop**
   - Submit feedback through backend API
   - Verify patches created in repair engine
   - Check governance batch promotes patches

4. **Monitor**
   - Watch `/api/patches/pending` endpoint
   - Set up alerts for creation/approval rates
   - Track graph update success

5. **Deploy**
   - Use provided Dockerfile
   - Set up Docker Compose for full stack
   - Configure governance batch schedule

---

## Support Resources

- **Quick Start:** `REPAIR_ENGINE_QUICK_START.md`
- **Comprehensive Guide:** `REPAIR_ENGINE_MICROSERVICE_GUIDE.md`
- **Integration Details:** `REPAIR_ENGINE_INTEGRATION_GUIDE.md`
- **API Docs:** `http://localhost:8002/docs`
- **Source Code:** `packages/amc-repair-engine/`

---

## Summary

The repair engine is now ready to:
- ✅ Accept corrections from feedback loop
- ✅ Create and manage patches
- ✅ Inject patches into query context
- ✅ Run governance batches
- ✅ Promote patches to production graph

**Start it now:**
```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --port 8002
```

**Configure backend:**
```bash
# Edit backend/.env
REPAIR_SERVICE_URL=http://localhost:8002
```

**Test it:**
```bash
curl http://localhost:8002/api/health
```

🚀 **You're ready to go!**

