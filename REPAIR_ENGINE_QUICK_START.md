# Repair Engine - Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Python 3.10+
- Neo4j running on `bolt://localhost:7687`
- Virtual environment activated

### Option 1: Direct Python (Fastest)

```bash
# 1. Navigate to repair engine
cd packages/amc-repair-engine

# 2. Start the microservice
python -m uvicorn src.amc_repair.server:app --host 0.0.0.0 --port 8002

# 3. Verify it's running
curl http://localhost:8002/api/health
```

**Output:**
```
2024-10-12 10:30:45 INFO: Uvicorn running on http://0.0.0.0:8002
2024-10-12 10:30:45 INFO: Application startup complete

{
  "status": "healthy",
  "service": "repair-engine",
  "version": "0.1.0",
  "timestamp": "2024-10-12T10:30:45.123456Z"
}
```

### Option 2: Using Startup Scripts

#### On Linux/Mac
```bash
cd packages/amc-repair-engine
bash run_repair_engine.sh
```

#### On Windows
```cmd
cd packages\amc-repair-engine
run_repair_engine.bat
```

### Option 3: Docker

```bash
# Build image
cd packages/amc-repair-engine
docker build -t amc-repair-engine:latest .

# Run container
docker run -p 8002:8002 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=amc@1234 \
  amc-repair-engine:latest

# Verify
curl http://localhost:8002/api/health
```

---

## Configure Backend to Use It

Update `backend/.env`:
```
REPAIR_SERVICE_URL=http://localhost:8002
SERVICE_TIMEOUT=30.0
```

---

## Test It

### 1. Create a Patch
```bash
curl -X POST http://localhost:8002/api/patches \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "ISIN_AXIS_BLUECHIP",
    "attribute": "fund_category",
    "canonical_value": "Large Cap",
    "corrected_value": "Mid Cap",
    "confidence": 0.95,
    "provenance": {
      "source": "test",
      "response_id": "resp_test_001"
    }
  }'
```

**Response:**
```json
{
  "status": "created",
  "patch_id": "patch_001_ISIN_AXIS_BLUECHIP_fund_category"
}
```

### 2. Get Pending Patches
```bash
curl http://localhost:8002/api/patches/pending | jq
```

**Response:**
```json
{
  "total": 1,
  "patches": [
    {
      "patch_id": "patch_001_ISIN_AXIS_BLUECHIP_fund_category",
      "entity_id": "ISIN_AXIS_BLUECHIP",
      "attribute": "fund_category",
      "canonical_value": "Large Cap",
      "corrected_value": "Mid Cap",
      "confidence": 0.95,
      "created_at": "2024-10-12T10:30:45Z",
      "expires_at": "2024-10-19T10:30:45Z"
    }
  ]
}
```

### 3. Approve a Patch
```bash
curl -X POST http://localhost:8002/api/patches/patch_001_ISIN_AXIS_BLUECHIP_fund_category/approve
```

**Response:**
```json
{
  "status": "approved",
  "patch_id": "patch_001_ISIN_AXIS_BLUECHIP_fund_category"
}
```

### 4. Run Governance Batch
```bash
curl -X POST http://localhost:8002/api/governance/run-batch \
  -H "Content-Type: application/json" \
  -d '{
    "auto_approve_threshold": 0.95
  }'
```

**Response:**
```json
{
  "status": "completed",
  "total_evaluated": 1,
  "approved": 1,
  "rejected": 0,
  "needs_review": 0,
  "deployed": 1,
  "timestamp": "2024-10-12T10:30:45Z"
}
```

---

## Integration Test

### Full Feedback → Patch → Governance Flow

```bash
#!/bin/bash

# 1. Create patch from feedback correction
PATCH=$(curl -s -X POST http://localhost:8002/api/patches \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "ISIN_TEST",
    "attribute": "test_attr",
    "canonical_value": "old_value",
    "corrected_value": "new_value",
    "confidence": 0.90
  }' | jq -r '.patch_id')

echo "✅ Patch created: $PATCH"

# 2. Verify patch is pending
curl -s http://localhost:8002/api/patches/pending | jq '.patches[0]'

# 3. Approve patch
curl -s -X POST http://localhost:8002/api/patches/$PATCH/approve | jq '.'

# 4. Run governance batch
curl -s -X POST http://localhost:8002/api/governance/run-batch | jq '.'

echo "✅ Full flow completed!"
```

---

## Monitoring

### Health Status
```bash
watch -n 5 'curl -s http://localhost:8002/api/health | jq'
```

### Patch Statistics
```bash
curl -s http://localhost:8002/api/patches/pending | jq '{total: .total, patches: [.patches[] | {entity_id, attribute, confidence}]}'
```

### Logs (when running with --reload)
```bash
# Linux/Mac: tail the output
# Windows: check console output
```

---

## Troubleshooting

### Port Already in Use
```bash
# Kill process using port 8002 (Linux/Mac)
lsof -ti:8002 | xargs kill -9

# Kill process using port 8002 (Windows)
netstat -ano | findstr :8002
taskkill /PID <PID> /F
```

### Neo4j Connection Failed
```bash
# Verify Neo4j is running
curl bolt://localhost:7687

# Check credentials in .env
echo $NEO4J_PASSWORD

# Test connection manually
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'amc@1234')); print('OK'); d.close()"
```

### Module Not Found
```bash
# Reinstall repair engine
cd packages/amc-repair-engine
pip install -e .
```

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
NEO4J_DATABASE=neo4j

# Redis (optional)
USE_REDIS=false
REDIS_HOST=localhost
REDIS_PORT=6379

# Governance
PATCH_TTL_DAYS=7
AUTO_APPROVE_THRESHOLD=0.95
GOVERNANCE_SCHEDULE=0 9 * * FRI
```

---

## API Documentation

```
http://localhost:8002/docs       # Swagger UI
http://localhost:8002/redoc      # ReDoc documentation
```

---

## Next Steps

1. **Configure Backend** - Update `backend/.env` with `REPAIR_SERVICE_URL=http://localhost:8002`
2. **Test Feedback Loop** - Submit feedback and verify patches are created
3. **Set Up Governance** - Configure auto-approval threshold and batch schedule
4. **Monitor** - Use `/api/patches/pending` to track active patches
5. **Deploy** - Use Docker Compose for production setup

---

## Common Commands

| Task | Command |
|------|---------|
| Start | `python -m uvicorn src.amc_repair.server:app --port 8002` |
| Health | `curl http://localhost:8002/api/health` |
| Pending patches | `curl http://localhost:8002/api/patches/pending` |
| API Docs | Visit `http://localhost:8002/docs` |
| Logs | Check console output or use `--log-level debug` |

---

## Support

For issues or questions:
1. Check the comprehensive guide: `REPAIR_ENGINE_MICROSERVICE_GUIDE.md`
2. View API docs: `http://localhost:8002/docs`
3. Check logs for errors
4. Verify Neo4j connectivity

