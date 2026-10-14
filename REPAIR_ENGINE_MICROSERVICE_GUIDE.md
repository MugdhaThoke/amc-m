# Running the Repair Engine as a Microservice

## Overview

The `amc-repair-engine` is a standalone microservice that manages correction patches for the knowledge graph. It can be run:

1. **Embedded** in the main backend (current setup via `app.state.repair_engine`)
2. **Standalone** as a separate microservice on port 8002 (recommended for production)

This guide covers both approaches, focusing on the standalone microservice setup.

---

## Architecture

```
┌──────────────────────────────────┐
│  Backend (Port 8000)             │
│  ├─ Query Engine                 │
│  ├─ Graph API                    │
│  └─ Feedback Loop Integration    │
└────────────┬─────────────────────┘
             │ REPAIR_SERVICE_URL
             │ http://repair:8002
             ▼
┌──────────────────────────────────┐
│  Repair Engine (Port 8002)       │
│  ├─ Create Patches               │
│  ├─ Manage Corrections           │
│  ├─ Governance Batch             │
│  └─ Graph Integration            │
└────────────┬─────────────────────┘
             │
             ▼
         ┌─────────┐
         │ Neo4j   │
         │ Graph   │
         └─────────┘
```

---

## Option 1: Run as Standalone Microservice (Recommended)

### Step 1: Install the Repair Engine

The repair engine is already installed in the venv from `packages/amc-repair-engine`. To reinstall or verify:

```bash
cd packages/amc-repair-engine
pip install -e .
```

### Step 2: Configure Environment

The repair engine uses the `.env` file settings. Verify these are set in `backend/.env`:

```bash
# Neo4j configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=amc@1234
NEO4J_DATABASE=neo4j

# Repair engine specific
REPAIR_SERVICE_URL=http://repair:8002
SERVICE_TIMEOUT=30.0

# Optional: Redis (for distributed caching)
USE_REDIS=false
REDIS_HOST=localhost
REDIS_PORT=6379

# Optional: Governance settings
PATCH_TTL_DAYS=7
AUTO_APPROVE_THRESHOLD=0.95
GOVERNANCE_SCHEDULE=0 9 * * FRI
```

### Step 3: Start the Repair Engine Microservice

Option A: **Direct Python Execution**
```bash
cd packages/amc-repair-engine
python -m uvicorn src.amc_repair.server:app --host 0.0.0.0 --port 8002 --reload
```

Option B: **Via Environment Variables**
```bash
export REPAIR_SERVICE_PORT=8002
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=amc@1234

python -m uvicorn packages/amc-repair-engine/src/amc_repair.server:app \
  --host 0.0.0.0 \
  --port 8002
```

Option C: **Docker Compose** (for production)
```yaml
# docker-compose.yml
version: '3.8'

services:
  neo4j:
    image: neo4j:5.x
    ports:
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/amc@1234

  repair-engine:
    build:
      context: packages/amc-repair-engine
      dockerfile: Dockerfile  # Create if doesn't exist
    ports:
      - "8002:8002"
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: amc@1234
      PATCH_TTL_DAYS: 7
    depends_on:
      - neo4j

  backend:
    build:
      context: backend
    ports:
      - "8000:8000"
    environment:
      REPAIR_SERVICE_URL: http://repair-engine:8002
      NEO4J_URI: bolt://neo4j:7687
    depends_on:
      - repair-engine
```

### Step 4: Verify Repair Engine is Running

```bash
# Health check
curl http://localhost:8002/api/health

# Expected response:
{
  "status": "healthy",
  "service": "repair-engine",
  "version": "0.1.0",
  "timestamp": "2024-10-12T10:30:45.123456Z"
}
```

### Step 5: Configure Backend to Use Repair Microservice

Update `backend/.env`:
```
REPAIR_SERVICE_URL=http://localhost:8002
```

Or if using Docker:
```
REPAIR_SERVICE_URL=http://repair-engine:8002
```

---

## Option 2: Run Embedded in Backend (Current Setup)

If you want to keep the repair engine running within the main backend process:

### Step 1: Verify Integration

Check that `backend/app/main.py` initializes the repair engine:

```python
# In lifespan() function:
try:
    from app.core.adapters import get_repair_engine
    app.state.repair_engine = get_repair_engine()
    logger.info("Repair engine wired into app.state")
except Exception as exc:
    logger.warning("Could not initialize repair engine: %s", exc)
```

### Step 2: Start Backend (Includes Repair Engine)

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The repair engine will be available at `http://localhost:8000/repair/*` (if you add routes) or accessed via `app.state.repair_engine` in Python code.

---

## Integration with Feedback Loop

The feedback loop automatically triggers the repair engine when a correction is detected:

### Flow

```
1. User submits feedback
   └─ ResponseFeedback created

2. Feedback Loop Processing
   └─ Extracts correction claims
   └─ Creates UnifiedEvaluationRecord with repair=true

3. Trigger Repair Engine
   └─ HTTP POST to REPAIR_SERVICE_URL/api/patches
   └─ Create patch from correction
   └─ Store in correction_patch_layer

4. Patch Available
   └─ Included in next query retrieval
   └─ Injected into assembled_context
   └─ LLM uses corrected values
```

### Implementation

In `backend/app/api/routes/feedback.py` or similar:

```python
import httpx
from app.config import get_settings

async def trigger_repair_engine(response_id: str, correction_claims: dict):
    """Trigger repair engine to create patches from corrections."""
    settings = get_settings()
    
    if not settings.repair_service_url:
        logger.debug("Repair service URL not configured, skipping patch creation")
        return
    
    async with httpx.AsyncClient(timeout=settings.service_timeout) as client:
        try:
            for claim in correction_claims.get("correction_claims", []):
                response = await client.post(
                    f"{settings.repair_service_url}/api/patches",
                    json={
                        "entity_id": claim.get("entity_id"),
                        "attribute": claim.get("attribute"),
                        "canonical_value": claim.get("rejected_value"),
                        "corrected_value": claim.get("asserted_value"),
                        "confidence": claim.get("confidence", 0.75),
                        "provenance": {
                            "source": "unified_feedback_loop",
                            "response_id": response_id
                        }
                    }
                )
                if response.status_code == 200:
                    logger.info(f"✅ Patch created for {claim.get('entity_id')}")
                else:
                    logger.warning(f"⚠️  Failed to create patch: {response.text}")
        
        except httpx.TimeoutError:
            logger.warning("Repair service timeout")
        except Exception as exc:
            logger.error(f"Repair service error: {exc}")
```

---

## API Endpoints

### Create Patch
```
POST /api/patches
Content-Type: application/json

{
  "entity_id": "ISIN_AXIS_BLUECHIP",
  "attribute": "fund_category",
  "canonical_value": "Large Cap",
  "corrected_value": "Mid Cap",
  "confidence": 0.95,
  "provenance": {
    "source": "unified_feedback_loop",
    "response_id": "resp_123"
  }
}

Response:
{
  "status": "created",
  "patch_id": "patch_001_ISIN_AXIS_BLUECHIP_fund_category"
}
```

### Get Pending Patches
```
GET /api/patches/pending

Response:
{
  "total": 5,
  "patches": [
    {
      "patch_id": "patch_001",
      "entity_id": "ISIN_AXIS",
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

### Get Patches for Entities
```
GET /api/patches/for-entities?entity_ids=ISIN_001,ISIN_002

Response:
{
  "patches": [
    {
      "patch_id": "patch_001",
      "entity_id": "ISIN_001",
      "attribute": "aum",
      "canonical_value": "2000 Cr",
      "corrected_value": "5000 Cr",
      "confidence": 0.90,
      "approved": false
    }
  ]
}
```

### Approve Patch
```
POST /api/patches/{patch_id}/approve

Response:
{
  "status": "approved",
  "patch_id": "patch_001"
}
```

### Reject Patch
```
POST /api/patches/{patch_id}/reject

Response:
{
  "status": "rejected",
  "patch_id": "patch_001"
}
```

### Batch Approve
```
POST /api/patches/batch-approve
Content-Type: application/json

{
  "patch_ids": ["patch_001", "patch_002", "patch_003"]
}

Response:
{
  "approved": ["patch_001", "patch_002"],
  "failed": ["patch_003"]
}
```

### Run Governance Batch
```
POST /api/governance/run-batch
Content-Type: application/json

{
  "auto_approve_threshold": 0.95
}

Response:
{
  "status": "completed",
  "total_evaluated": 10,
  "approved": 7,
  "rejected": 2,
  "needs_review": 1,
  "deployed": 7,
  "timestamp": "2024-10-12T10:30:45Z"
}
```

---

## Monitoring and Logging

### Health Check
```bash
curl http://localhost:8002/api/health
```

### View Logs (when running standalone)
```bash
# Real-time logs with INFO level
PYTHONUNBUFFERED=1 python -m uvicorn packages/amc-repair-engine/src/amc_repair.server:app \
  --host 0.0.0.0 \
  --port 8002 \
  --log-level info

# Save to file
PYTHONUNBUFFERED=1 python -m uvicorn packages/amc-repair-engine/src/amc_repair.server:app \
  --host 0.0.0.0 \
  --port 8002 \
  --log-level info > repair_engine.log 2>&1 &
```

### Log Format
```
[INFO] repair_service: Patch created: patch_001_ISIN_AXIS_fund_category
[INFO] repair_service: Patch approved: patch_001_ISIN_AXIS_fund_category
[INFO] repair_service: Governance batch completed: 7 promoted to graph
[WARNING] repair_service: Patch not found: patch_999
[ERROR] repair_service: Create patch error: Invalid entity_id
```

---

## Troubleshooting

### Issue: Connection Refused
```
Error: Cannot connect to http://repair:8002
```

**Solution:**
- Verify repair engine is running: `curl http://localhost:8002/api/health`
- Check `REPAIR_SERVICE_URL` in `.env`
- If using Docker: service name should be `repair-engine` in compose, not `repair`

### Issue: Neo4j Connection Failed
```
Neo4j driver connection failed: Failed to establish connection
```

**Solution:**
- Verify Neo4j is running: `curl bolt://localhost:7687`
- Check credentials in `.env`
- Use `bolt://` not `http://` for Neo4j

### Issue: Patches Not Creating
```
Create patch error: Invalid entity_id
```

**Solution:**
- Verify `entity_id` format matches your graph (ISIN, dedup_key, etc.)
- Check if entity exists in Neo4j
- Test directly: `curl -X POST http://localhost:8002/api/patches -d '{...}'`

### Issue: High Memory Usage
```
Memory leak or unbounded growth
```

**Solution:**
- Set `PATCH_TTL_DAYS` to auto-expire old patches
- Use Redis adapter for distributed caching
- Monitor patch layer size: `GET /api/patches/pending`

---

## Docker Setup

### Create Dockerfile for Repair Engine

```dockerfile
# packages/amc-repair-engine/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install amc-repair-engine from source
COPY . .
RUN pip install -e .

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8002/api/health')"

# Start server
CMD ["python", "-m", "uvicorn", "src.amc_repair.server:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Docker Compose Full Stack

```yaml
# docker-compose.yml
version: '3.8'

services:
  neo4j:
    image: neo4j:5.15
    ports:
      - "7687:7687"
    volumes:
      - neo4j_data:/data
    environment:
      NEO4J_AUTH: neo4j/amc@1234
      NEO4J_apoc_import_file_enabled: "true"
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:7687"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  repair-engine:
    build:
      context: packages/amc-repair-engine
    ports:
      - "8002:8002"
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: amc@1234
      REDIS_HOST: redis
      REDIS_PORT: 6379
      USE_REDIS: "true"
      PATCH_TTL_DAYS: 7
      AUTO_APPROVE_THRESHOLD: 0.95
    depends_on:
      neo4j:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  backend:
    build:
      context: backend
    ports:
      - "8000:8000"
    environment:
      REPAIR_SERVICE_URL: http://repair-engine:8002
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: amc@1234
      REDIS_HOST: redis
      REDIS_PORT: 6379
    depends_on:
      repair-engine:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  neo4j_data:
  redis_data:

networks:
  default:
    name: amc_network
```

### Start Full Stack
```bash
docker-compose up -d

# View logs
docker-compose logs -f repair-engine

# Stop
docker-compose down
```

---

## Best Practices

### 1. **Separate Microservices for Production**

- Run repair-engine on separate container/server
- Better resource isolation
- Independent scaling
- Easier to update without downtime

### 2. **Use Redis for Distributed Caching**

```bash
# In .env
USE_REDIS=true
REDIS_HOST=redis-server
REDIS_PORT=6379
```

### 3. **Set Patch Expiry**

```bash
# In .env
PATCH_TTL_DAYS=7  # Auto-expire old patches
```

### 4. **Monitor Patch Creation**

```bash
# Check pending patches regularly
curl http://localhost:8002/api/patches/pending | jq '.total'
```

### 5. **Implement Governance Batch Jobs**

```bash
# Run weekly (Friday 9 AM)
GOVERNANCE_SCHEDULE="0 9 * * FRI"

# Or manually trigger
curl -X POST http://localhost:8002/api/governance/run-batch
```

### 6. **Use Circuit Breaker Pattern**

In backend's .env:
```
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60.0
```

---

## Performance Tuning

### Patch Layer Optimization

```python
# In packages/amc-repair-engine/src/amc_repair/config.py
class RepairConfig:
    # Cache settings
    patch_cache_size = 10000  # Max patches in memory
    cache_ttl_seconds = 3600  # Refresh every hour
    
    # Batch processing
    batch_size = 100  # Governance batch size
    parallel_workers = 4  # Graph writes in parallel
    
    # Timeouts
    neo4j_timeout = 30  # seconds
    approval_timeout = 5  # seconds
```

### Database Indexes

Create these in Neo4j for performance:

```cypher
CREATE INDEX entity_isin FOR (e) ON (e.isin);
CREATE INDEX entity_id FOR (e) ON (e.id);
CREATE INDEX patch_created FOR (p:Patch) ON (p.created_at);
```

---

## Summary

| Aspect | Embedded | Standalone |
|--------|----------|------------|
| **Port** | 8000 | 8002 |
| **Startup** | With backend | Separate process |
| **Scaling** | Limited | Independent |
| **Resources** | Shared | Isolated |
| **Recommended** | Dev/Test | Production |

Choose **Standalone** for production deployments to enable independent scaling and better resource management.

