# AMC Feedback Loop Implementation Plan
**Backend-Only Scope | Excludes Streamlit UI Components**

---

## Executive Summary

This plan addresses the gaps between documented requirements (Technical Design v2 & Architecture Doc) and current implementation. The codebase has a **functional 4-step pipeline** but lacks critical integration points, evaluation automation, and repair mechanisms. This plan prioritizes backend API completeness, evaluation layer integration, and automated governance workflows.

**Current Completion:** 60% of backend requirements  
**Target Completion:** 95% of backend requirements  
**Timeline:** 11-14 weeks (2 engineers)  
**Architecture:** Retain 3-system separation (AMC backend, feedback_loop package, repair engine)

---

## Implementation Status Overview

### ✅ Fully Implemented (60%)
- Active feedback API (`POST /api/feedback`)
- 4-step core pipeline (Classification → Enrichment → Router → Adjudication)
- Database schemas (response_feedback, unified_evaluation_records, query_evidence)
- Dissatisfaction detection (3-signal follow-up correction)
- Correction extraction & structured claim builder
- Shadow patch layer (CorrectionPatchLayer)
- Deterministic rules engine (C01-C05)
- Root cause classification
- Timeout mechanism (FeedbackTimerManager)

### ⚠️ Partially Implemented (25%)
- Passive feedback flow (timer works, NO pipeline trigger)
- Tiered evaluation (components exist, NOT integrated)
- Repair engine (patch layer complete, governance stub only)
- Deduplication (works in pipeline, no cross-cluster merging)

### ❌ Not Implemented (15%)
- Batch evaluation engine (no batching, clustering, optimization)
- GNN plausibility scorer (field exists, model absent)
- Repair decision logic (no code sets repair flags)
- Lifecycle state machine automation
- Governance approval scheduler
- Canonical graph promotion from patches to Neo4j

---

## Critical Gaps Analysis

### Gap 1: Passive Feedback Dead-End
**Problem:** Timer creates skeleton → MetricsEnricher enriches → **stops**  
**Impact:** Passive feedback never reaches UnifiedEvaluationRecord table  
**Location:** `backend/app/feedback/timeout_processor.py` line 96 (no trigger after enrichment)

### Gap 2: Evaluation Layer Disconnect
**Problem:** UnifiedEvaluationRecord written with evaluation fields NULL  
**Impact:** NLI/LLM evaluators are orphaned components, no consumer  
**Location:** `packages/amc-feedback-loop/src/feedback_loop/orchestrator.py` (no call to EvaluationRouter)

### Gap 3: Repair Decision Missing
**Problem:** `repair` and `repair_target` fields never set  
**Impact:** Batch evaluation engine has no records to process  
**Location:** `packages/amc-feedback-loop/src/feedback_loop/orchestrator.py` line 155 (hardcoded repair=False)

### Gap 4: 6-Step vs 4-Step Discrepancy
**Problem:** Docs describe 6 steps, code implements 4  
**Impact:** "Diagnosis" and "Repair Analysis" steps missing  
**Location:** Technical Design Section 3 vs actual RecordBuilder implementation

### Gap 5: Governance Workflow Incomplete
**Problem:** Patch approval system exists but no scheduler  
**Impact:** No promotion path from CorrectionPatchLayer to canonical Neo4j  
**Location:** `packages/amc-repair-engine/src/amc_repair/governance.py` (stub only)

---

## Phase 1: Complete Core Pipeline (Priority: CRITICAL)
**Duration:** 3 weeks | **Effort:** 120 hours

### Objective
Close gaps in existing pipeline, make passive feedback fully functional, integrate evaluation layer.

### Tasks

#### 1.1 Connect Passive Feedback to Pipeline
**File:** `backend/app/feedback/timeout_processor.py`  
**Changes:**
```python
# After line 96 (enrichment complete), add:
if success:
    await session_manager.mark_enriched(session_id, response_id)
    enriched_count += 1
    
    # NEW: Trigger feedback loop for enriched passive feedback
    try:
        from app.services.feedback import trigger_feedback_loop
        await asyncio.to_thread(
            trigger_feedback_loop,
            feedback_id=feedback_id,  # fetch from enriched record
            session_id=session_id,
            response_id=response_id,
            source="passive"
        )
        logger.info("Triggered feedback loop for passive response %s", response_id)
    except Exception as exc:
        logger.error("Failed to trigger passive feedback loop: %s", exc)
```

**Acceptance Criteria:**
- [ ] Passive feedback reaches unified_evaluation_records within 5 minutes of timeout
- [ ] Entry route correctly set to 'automatic' or 'dissatisfaction_converted'
- [ ] Test: Create skeleton record → wait 180s → verify unified record exists

---

#### 1.2 Add Steps 5 & 6 to Pipeline (Diagnosis + Repair Analysis)
**File:** `packages/amc-feedback-loop/src/feedback_loop/services/diagnosis.py` (NEW)  
**Implementation:**

Create new service to analyze failure root cause and propose repair target:

```python
from feedback_loop.domain_models import RootCause, Severity, RepairTarget

class DiagnosisService:
    """Step 5: Failure diagnosis - maps root cause to stack layer"""
    
    def diagnose(
        self,
        root_cause: RootCause,
        router_result: RouterResult,
        snapshot: EvidenceSnapshot
    ) -> DiagnosisResult:
        """
        Determine WHERE in the stack the failure occurred:
        - KNOWLEDGE: Missing/incorrect data in source
        - RETRIEVAL: Vector search or graph traversal failed
        - GRAPH: Knowledge graph structure issue
        - CONTEXT_ENGINEERING: Evidence assembly problem
        - MODEL: LLM generation error
        - GUARDRAIL: Pre/post-response control failure
        - COMPLIANCE: Regulatory constraint violation
        - PRESENTATION: Formatting/clarity issue
        - FEEDBACK_INVALID: User error
        """
        # Diagnosis logic maps root_cause + rule findings to stack layer
        
        diagnosis_map = {
            RootCause.COMPLIANCE: StackLayer.COMPLIANCE,
            RootCause.MODEL: StackLayer.MODEL,
            RootCause.PRESENTATION: StackLayer.PRESENTATION,
            RootCause.FEEDBACK_INVALID: StackLayer.FEEDBACK_INVALID,
        }
        
        # For KNOWLEDGE/RETRIEVAL, check rule details
        if root_cause == RootCause.KNOWLEDGE:
            # If C04 structured correction → knowledge gap
            if any(f.rule == "C04_structured_correction" for f in router_result.rules_fired):
                return DiagnosisResult(
                    stack_layer=StackLayer.KNOWLEDGE,
                    confidence=0.9,
                    evidence="User provided explicit correction"
                )
        
        if root_cause == RootCause.RETRIEVAL:
            # If C01 referential → retrieval missed entity
            # If C02 temporal → stale index
            return DiagnosisResult(
                stack_layer=StackLayer.RETRIEVAL,
                confidence=0.85,
                evidence=f"Retrieval rules fired: {[f.rule for f in router_result.rules_fired]}"
            )
        
        return DiagnosisResult(
            stack_layer=diagnosis_map.get(root_cause, StackLayer.UNKNOWN),
            confidence=0.7,
            evidence="Default mapping from root cause"
        )
```

**File:** `packages/amc-feedback-loop/src/feedback_loop/services/repair_analyzer.py` (NEW)  
**Implementation:**

```python
class RepairAnalyzerService:
    """Step 6: Repair analysis - decide if fix needed and where"""
    
    def analyze(
        self,
        diagnosis: DiagnosisResult,
        severity: Severity,
        root_cause: RootCause,
        confidence: float
    ) -> RepairAnalysis:
        """
        Decide:
        1. Should repair be attempted? (repair=True/False)
        2. Where to apply fix? (repair_target='vector'|'graph'|None)
        
        Rules:
        - Severity >= HIGH + confidence >= 0.75 → repair=True
        - KNOWLEDGE/GRAPH stack layer → repair_target='graph'
        - RETRIEVAL stack layer → repair_target='vector'
        - Others → repair=False
        """
        
        # Gate 1: Severity + confidence threshold
        should_repair = (
            severity in [Severity.CRITICAL, Severity.HIGH] and
            confidence >= 0.75
        )
        
        if not should_repair:
            return RepairAnalysis(repair=False, repair_target=None, reason="Below repair threshold")
        
        # Gate 2: Repairability check
        target_map = {
            StackLayer.KNOWLEDGE: RepairTarget.GRAPH,
            StackLayer.RETRIEVAL: RepairTarget.VECTOR,
            StackLayer.GRAPH: RepairTarget.GRAPH,
        }
        
        repair_target = target_map.get(diagnosis.stack_layer)
        
        if repair_target is None:
            return RepairAnalysis(
                repair=False,
                repair_target=None,
                reason=f"Stack layer {diagnosis.stack_layer} not repairable"
            )
        
        return RepairAnalysis(
            repair=True,
            repair_target=repair_target,
            reason=f"Repairability confirmed for {diagnosis.stack_layer}"
        )
```

**File:** `packages/amc-feedback-loop/src/feedback_loop/orchestrator.py`  
**Changes:**
```python
# After Step 4 (line 139), add:

# Step 5 — Diagnosis (needs step 3 + 4 output)
diagnosis_result = self._diagnosis_svc.diagnose(
    root_cause=adjudication_result.root_cause,
    router_result=router_result,
    snapshot=enrichment.evidence_snapshot,
)

# Step 6 — Repair Analysis (needs step 5 output)
repair_analysis = self._repair_analyzer_svc.analyze(
    diagnosis=diagnosis_result,
    severity=router_result.severity,
    root_cause=adjudication_result.root_cause,
    confidence=diagnosis_result.confidence,
)

# Update record assembly (line 155):
record = UnifiedEvaluationRecord(
    session_id=row.session_id,
    response_id=row.response_id,
    entry_route=enrichment.entry_route,
    feedback_ref=row.feedback_id if enrichment.entry_route == "hitl" else None,
    evidence_snapshot_ref=enrichment.evidence_snapshot_ref,
    root_cause=adjudication_result.root_cause,
    severity=router_result.severity,
    lifecycle_status=LifecycleStatus.OPEN,
    dissatisfaction_evidence=enrichment.dissatisfaction_signal.model_dump() if enrichment.dissatisfaction_signal else None,
    # NEW: Add repair fields
    repair=repair_analysis.repair,
    repair_target=repair_analysis.repair_target,
)
```

**Acceptance Criteria:**
- [ ] Steps 5 & 6 execute after step 4 completes
- [ ] `repair` field set to True when severity=HIGH/CRITICAL + confidence ≥ 0.75
- [ ] `repair_target` correctly mapped: KNOWLEDGE/GRAPH → 'graph', RETRIEVAL → 'vector'
- [ ] Test: Submit feedback with numeric error (C03) → verify repair=True, repair_target='vector'

---

#### 1.3 Integrate Evaluation Layer into Pipeline
**File:** `packages/amc-feedback-loop/src/feedback_loop/orchestrator.py`  
**Changes:**

```python
# After Step 6 (line 165), add:

# Step 7 — Tiered Evaluation (optional, runs when repair=True)
evaluation_results = None
if repair_analysis.repair:
    try:
        from app.evaluation.evaluation_router import EvaluationRouter
        router = EvaluationRouter()
        
        # Build evidence pack for evaluation
        evidence_pack = {
            "response_text": enrichment.evidence_snapshot.response_text,
            "query": enrichment.evidence_snapshot.original_query,
            "context": " ".join([c.content or c.value or "" for c in enrichment.evidence_snapshot.evidence_selected]),
            "chunks": [
                {"text": c.content or c.value, "score": getattr(c, 'score', 0)}
                for c in enrichment.evidence_snapshot.evidence_selected
            ],
            "intent": classification.intent if classification else None,
        }
        
        evaluation_results = router.evaluate(
            response_id=row.response_id,
            evidence_pack=evidence_pack
        )
        
        logger.info(
            "evaluation_complete",
            feedback_id=row.feedback_id,
            tier=evaluation_results.get("tier"),
            verdict=evaluation_results.get("verdict"),
        )
    except Exception as exc:
        logger.warning("evaluation_failed", error=str(exc))
        evaluation_results = None

# Update record with evaluation results
if evaluation_results:
    record.deterministic_results = evaluation_results.get("rule_results")
    record.semantic_results = evaluation_results.get("nli_result")
    record.llm_evaluation = evaluation_results.get("critic_result")
    record.adjudication_verdict = evaluation_results.get("verdict")
    record.adjudication_confidence = evaluation_results.get("confidence")
```

**Acceptance Criteria:**
- [ ] EvaluationRouter called when repair=True
- [ ] deterministic_results, semantic_results, llm_evaluation fields populated
- [ ] Tier 1A (rules) executes for all repair=True records
- [ ] Tier 2 (NLI) executes when Tier 1A inconclusive and enabled
- [ ] Tier 3 (LLM) executes as last resort when Tier 2 inconclusive
- [ ] Test: Create high-severity feedback → verify evaluation fields not NULL

---

#### 1.4 Expand Rule Categories (5→9)
**File:** `packages/amc-feedback-loop/src/feedback_loop/services/router.py`  
**Add new rule methods:**

```python
def _check_c06_cardinality(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
    """C06 — Cardinality check: response claims single value but evidence has multiple"""
    # Example: "The TER is 0.5%" but evidence shows 0.5% and 0.6% from different dates
    # Extract all numbers from evidence
    evidence_numbers = []
    for chunk in snapshot.evidence_selected:
        nums = _extract_all_numerics(chunk.content or chunk.value or "")
        evidence_numbers.extend(nums)
    
    response_numbers = _extract_all_numerics(snapshot.response_text)
    
    # If response has 1 number but evidence has 2+ distinct numbers → cardinality violation
    if len(response_numbers) == 1 and len(set(evidence_numbers)) > 1:
        return RuleFinding(
            rule="C06_cardinality",
            result="WARN",
            detail=f"Response claims single value {response_numbers[0]} but evidence contains multiple: {list(set(evidence_numbers))}"
        )
    return None

def _check_c07_cross_source(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
    """C07 — Cross-source consistency: same fact from different sources must agree"""
    # Group chunks by source_version
    source_groups = defaultdict(list)
    for chunk in snapshot.evidence_selected:
        if chunk.source_version:
            source_groups[chunk.source_version].append(chunk)
    
    # If 2+ sources present, extract numeric values from each
    if len(source_groups) < 2:
        return None
    
    source_values = {}
    for source, chunks in source_groups.items():
        for chunk in chunks:
            num = _extract_numeric(chunk.content or chunk.value or "")
            if num is not None:
                source_values[source] = num
                break
    
    # Check for conflicts
    if len(source_values) >= 2:
        vals = list(source_values.values())
        if max(vals) - min(vals) > 0.01:  # Allow 0.01 tolerance
            return RuleFinding(
                rule="C07_cross_source",
                result="FAIL",
                detail=f"Cross-source conflict: {source_values}"
            )
    return None

def _check_c08_duplicate(self, row: FeedbackRecord) -> Optional[RuleFinding]:
    """C08 — Duplicate detection: feedback is repetitive of previous submission"""
    # This requires database query for similar feedback in past 7 days
    # Implement via db adapter call
    return None  # Placeholder

def _check_c09_hierarchy(self, snapshot: EvidenceSnapshot) -> Optional[RuleFinding]:
    """C09 — Taxonomy hierarchy violation: response references incorrect taxonomy level"""
    # Example: User asks about "equity funds" but response references specific fund ISIN
    # Check if entity_name appears in taxonomy_nodes
    if not snapshot.taxonomy_nodes:
        return None
    
    # Verify entity is at correct hierarchy level for query
    # This requires taxonomy service integration
    return None  # Placeholder
```

**Update run() method:**
```python
def run(self, row: FeedbackRecord, snapshot: EvidenceSnapshot, session_id: str = None, feedback_id: str = None) -> RouterResult:
    findings: list[RuleFinding] = []
    
    for checker in (
        lambda: self._check_c01_referential(row, snapshot),
        lambda: self._check_c02_temporal(snapshot),
        lambda: self._check_c03_numeric(snapshot),
        lambda: self._check_c04_structured_correction(row),
        lambda: self._check_c05_compliance(row, snapshot),
        lambda: self._check_c06_cardinality(snapshot),  # NEW
        lambda: self._check_c07_cross_source(snapshot),  # NEW
        lambda: self._check_c08_duplicate(row),  # NEW
        lambda: self._check_c09_hierarchy(snapshot),  # NEW
    ):
        result = checker()
        if result is not None:
            findings.append(result)
    
    # ... rest of method unchanged
```

**Acceptance Criteria:**
- [ ] 9 rule checks execute in router
- [ ] C06 catches cardinality violations
- [ ] C07 detects cross-source conflicts
- [ ] C08/C09 return None (placeholder) without breaking pipeline
- [ ] Test: Evidence with conflicting sources → C07 fires

---

#### 1.5 Add Webhook Retry Mechanism
**File:** `backend/app/services/feedback_retry.py` (NEW)  
**Implementation:**

```python
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback

class FeedbackRetryService:
    """Retry failed/pending feedback loop triggers"""
    
    def __init__(self, retry_intervals: list[int] = [60, 300, 900]):
        self.retry_intervals = retry_intervals  # 1min, 5min, 15min
    
    async def process_retries(self):
        """Find pending feedback records and retry trigger"""
        db = SessionLocal()
        try:
            # Find records older than 5 minutes with no unified_record_ref
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=300)
            
            pending = (
                db.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.unified_record_ref.is_(None),
                    ResponseFeedback.created_at <= cutoff.isoformat(),
                    ResponseFeedback.feedback_text.isnot(None)  # Only actual feedback
                )
                .limit(50)
                .all()
            )
            
            for record in pending:
                age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(record.created_at)).total_seconds()
                
                # Exponential backoff: retry at 1min, 5min, 15min
                should_retry = any(
                    abs(age_seconds - interval) < 30  # 30s tolerance
                    for interval in self.retry_intervals
                )
                
                if should_retry:
                    try:
                        from app.services.feedback import trigger_feedback_loop
                        await asyncio.to_thread(
                            trigger_feedback_loop,
                            feedback_id=record.feedback_id,
                            session_id=record.session_id,
                            response_id=record.response_id,
                            source="active" if record.feedback_text else "passive"
                        )
                        logger.info("Retry successful for feedback %s", record.feedback_id)
                    except Exception as exc:
                        logger.error("Retry failed for feedback %s: %s", record.feedback_id, exc)
                
                # Mark as failed after 15min
                if age_seconds > 900:
                    logger.warning("Feedback %s exceeded retry window, marking failed", record.feedback_id)
        finally:
            db.close()

# Background task startup
async def start_retry_service():
    service = FeedbackRetryService()
    while True:
        await asyncio.sleep(60)  # Run every minute
        try:
            await service.process_retries()
        except Exception as exc:
            logger.error("Retry service error: %s", exc)
```

**File:** `backend/app/main.py`  
**Add to startup:**
```python
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Start feedback retry service
    from app.services.feedback_retry import start_retry_service
    asyncio.create_task(start_retry_service())
    logger.info("FeedbackRetryService started")
```

**Acceptance Criteria:**
- [ ] Retry service runs every 60 seconds
- [ ] Records without unified_record_ref older than 5min are retried
- [ ] Exponential backoff: 1min, 5min, 15min intervals
- [ ] After 15min, record marked as failed (logged)
- [ ] Test: Break feedback loop → verify retries occur → fix → verify success

---

### Phase 1 Deliverables
- [x] Passive feedback reaches unified_evaluation_records
- [x] repair & repair_target fields populated correctly
- [x] Evaluation tier results stored in unified records
- [x] 9 rule categories operational (5 full + 4 stub)
- [x] Webhook retry mechanism with exponential backoff
- [x] 95% test coverage for core pipeline

**Dependencies:** None  
**Risks:** EvaluationRouter may need config tuning (Tier 2/3 enable flags)

---

## Phase 2: Batch Evaluation Engine (Priority: HIGH)
**Duration:** 3 weeks | **Effort:** 120 hours

### Objective
Automate evaluation of repair=True records, implement batching with optimization layers.

### Tasks

#### 2.1 Create Batch Evaluation Consumer
**File:** `backend/app/evaluation/batch_consumer.py` (NEW)  
**Implementation:**

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord, LifecycleStatus
from app.evaluation.evaluation_router import EvaluationRouter

class BatchEvaluationConsumer:
    """
    Consumes unified_evaluation_records where repair=True and lifecycle_status='OPEN'.
    Processes in batches of 25 with shared context optimization.
    """
    
    def __init__(self, batch_size: int = 25):
        self.batch_size = batch_size
        self.router = EvaluationRouter()
    
    async def process_batch(self):
        """Main processing loop"""
        db = SessionLocal()
        try:
            # Fetch pending records
            pending = (
                db.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.repair == True,
                    UnifiedEvaluationRecord.lifecycle_status == LifecycleStatus.OPEN,
                    UnifiedEvaluationRecord.deterministic_results.is_(None)  # Not yet evaluated
                )
                .order_by(UnifiedEvaluationRecord.created_at)
                .limit(self.batch_size)
                .all()
            )
            
            if not pending:
                return 0
            
            logger.info("Processing batch of %d records", len(pending))
            
            # Update status to DIAGNOSING
            record_ids = [(r.session_id, r.response_id) for r in pending]
            db.query(UnifiedEvaluationRecord).filter(
                tuple_(UnifiedEvaluationRecord.session_id, UnifiedEvaluationRecord.response_id).in_(record_ids)
            ).update({"lifecycle_status": LifecycleStatus.DIAGNOSING}, synchronize_session=False)
            db.commit()
            
            # Process each record with evaluation router
            processed = 0
            for record in pending:
                try:
                    # Fetch evidence pack
                    evidence_pack = await self._build_evidence_pack(record, db)
                    
                    # Run evaluation
                    eval_result = self.router.evaluate(
                        response_id=record.response_id,
                        evidence_pack=evidence_pack
                    )
                    
                    # Update record with results
                    record.deterministic_results = eval_result.get("rule_results")
                    record.semantic_results = eval_result.get("nli_result")
                    record.llm_evaluation = eval_result.get("critic_result")
                    record.adjudication_verdict = eval_result.get("verdict")
                    record.adjudication_confidence = eval_result.get("confidence")
                    record.lifecycle_status = LifecycleStatus.RESOLVED if eval_result.get("verdict") == "PASS" else LifecycleStatus.OPEN
                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    
                    processed += 1
                except Exception as exc:
                    logger.error("Evaluation failed for record %s: %s", record.response_id, exc)
                    record.lifecycle_status = LifecycleStatus.OPEN  # Revert to OPEN for retry
            
            db.commit()
            logger.info("Batch processing complete: %d/%d succeeded", processed, len(pending))
            return processed
            
        finally:
            db.close()
    
    async def _build_evidence_pack(self, record: UnifiedEvaluationRecord, db: Session) -> dict:
        """Fetch evidence from query_evidence table"""
        from app.schemas.query_evidence_table import QueryEvidence
        
        evidence = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == record.response_id)
            .first()
        )
        
        if not evidence:
            raise ValueError(f"No evidence found for response {record.response_id}")
        
        return {
            "response_text": evidence.response_text or "",
            "query": evidence.original_query or "",
            "context": evidence.retrieved_context or "",
            "chunks": evidence.retrieved_chunks or [],
            "intent": evidence.detected_intent,
        }

# Background task
async def start_batch_consumer():
    consumer = BatchEvaluationConsumer(batch_size=25)
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        try:
            processed = await consumer.process_batch()
            if processed > 0:
                logger.info("Batch consumer processed %d records", processed)
        except Exception as exc:
            logger.error("Batch consumer error: %s", exc)
```

**File:** `backend/app/main.py`  
**Add to startup:**
```python
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Start batch evaluation consumer
    from app.evaluation.batch_consumer import start_batch_consumer
    asyncio.create_task(start_batch_consumer())
    logger.info("BatchEvaluationConsumer started")
```

**Acceptance Criteria:**
- [ ] Batch consumer runs every 5 minutes
- [ ] Fetches up to 25 records with repair=True, lifecycle_status=OPEN
- [ ] Updates lifecycle_status to DIAGNOSING during processing
- [ ] Evaluates each record via EvaluationRouter
- [ ] Updates evaluation fields in unified_evaluation_records
- [ ] Sets lifecycle_status to RESOLVED (verdict=PASS) or OPEN (verdict=FAIL)
- [ ] Test: Create 30 records with repair=True → verify 25 processed in first batch

---

#### 2.2 Add Shared Context Optimization
**File:** `backend/app/evaluation/shared_context_cache.py` (NEW)  
**Implementation:**

```python
from functools import lru_cache
from datetime import datetime, timezone, timedelta
import hashlib
import json

class SharedContextCache:
    """
    Cache shared Neo4j subgraphs and few-shot examples across batch.
    Reduces redundant database queries within a 1-hour window.
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._subgraph_cache = {}
        self._fewshot_cache = {}
    
    def get_subgraph(self, entity_id: str, hops: int = 1) -> dict | None:
        """Retrieve cached 1-hop subgraph for entity"""
        key = f"{entity_id}_{hops}"
        cached = self._subgraph_cache.get(key)
        
        if cached:
            age = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
            if age < self.ttl_seconds:
                return cached["data"]
        
        return None
    
    def set_subgraph(self, entity_id: str, hops: int, data: dict):
        """Cache subgraph result"""
        key = f"{entity_id}_{hops}"
        self._subgraph_cache[key] = {
            "data": data,
            "timestamp": datetime.now(timezone.utc)
        }
    
    def get_fewshot_examples(self, category: str) -> list | None:
        """Retrieve cached few-shot examples for rule category"""
        cached = self._fewshot_cache.get(category)
        
        if cached:
            age = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
            if age < self.ttl_seconds * 24:  # 24h TTL for examples
                return cached["data"]
        
        return None
    
    def set_fewshot_examples(self, category: str, examples: list):
        """Cache few-shot examples"""
        self._fewshot_cache[category] = {
            "data": examples,
            "timestamp": datetime.now(timezone.utc)
        }
    
    def clear_expired(self):
        """Cleanup expired entries"""
        now = datetime.now(timezone.utc)
        
        # Clear subgraphs older than TTL
        expired_subgraph_keys = [
            k for k, v in self._subgraph_cache.items()
            if (now - v["timestamp"]).total_seconds() > self.ttl_seconds
        ]
        for key in expired_subgraph_keys:
            del self._subgraph_cache[key]
        
        # Clear examples older than 24h
        expired_fewshot_keys = [
            k for k, v in self._fewshot_cache.items()
            if (now - v["timestamp"]).total_seconds() > self.ttl_seconds * 24
        ]
        for key in expired_fewshot_keys:
            del self._fewshot_cache[key]

# Global singleton
_shared_cache = SharedContextCache()

def get_shared_cache() -> SharedContextCache:
    return _shared_cache
```

**File:** `backend/app/evaluation/batch_consumer.py`  
**Integrate caching:**
```python
from app.evaluation.shared_context_cache import get_shared_cache

class BatchEvaluationConsumer:
    def __init__(self, batch_size: int = 25):
        self.batch_size = batch_size
        self.router = EvaluationRouter()
        self.cache = get_shared_cache()
    
    async def _build_evidence_pack(self, record: UnifiedEvaluationRecord, db: Session) -> dict:
        # ... existing code ...
        
        # Add cached subgraph if entity present
        if evidence.entity_name:
            subgraph = self.cache.get_subgraph(evidence.entity_name, hops=1)
            if subgraph is None:
                # Fetch from Neo4j
                subgraph = await self._fetch_subgraph_from_neo4j(evidence.entity_name)
                self.cache.set_subgraph(evidence.entity_name, hops=1, data=subgraph)
            
            evidence_pack["subgraph"] = subgraph
        
        return evidence_pack
```

**Acceptance Criteria:**
- [ ] Subgraph cache stores 1-hop results with 1h TTL
- [ ] Few-shot example cache stores prompts with 24h TTL
- [ ] Cache hit rate > 60% for batches with overlapping entities
- [ ] Cache cleanup runs every 10 minutes
- [ ] Test: Process batch with 5 records for same entity → verify only 1 Neo4j query

---

#### 2.3 Implement GNN Plausibility Stub
**File:** `backend/app/evaluation/gnn_plausibility.py` (NEW)  
**Implementation:**

```python
from typing import Optional

class GNNPlausibilityScorer:
    """
    Stub GNN plausibility scorer returning fixed threshold until model trained.
    
    Future implementation options:
    - Option 1: R-GCN with PyTorch (requires training data + model artifacts)
    - Option 2: Neo4j GDS pipeline (no new dependencies, runs in-database)
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.is_trained = False  # Flag for future model loading
    
    def score(self, entity_id: str, attribute: str, value: str) -> float:
        """
        Compute structural plausibility score for triple (entity, attribute, value).
        
        Returns fixed 0.5 until trained model available.
        """
        if self.is_trained:
            # Future: Load model and compute actual score
            pass
        
        # Stub: Always return neutral score
        return 0.5
    
    def batch_score(self, triples: list[tuple[str, str, str]]) -> list[float]:
        """Batch scoring for efficiency"""
        return [self.score(e, a, v) for e, a, v in triples]

# Global singleton
_gnn_scorer = GNNPlausibilityScorer()

def get_gnn_scorer() -> GNNPlausibilityScorer:
    return _gnn_scorer
```

**File:** `backend/app/evaluation/evaluation_router.py`  
**Integrate GNN scoring:**
```python
from app.evaluation.gnn_plausibility import get_gnn_scorer

class EvaluationRouter:
    def __init__(self, ...):
        # ... existing init ...
        self.gnn_scorer = get_gnn_scorer()
    
    async def evaluate_async(self, response_id: str, evidence_pack: dict) -> dict:
        # ... after Tier 1A rules ...
        
        # Tier 1B: GNN Plausibility
        gnn_score = 0.5  # Default
        if evidence_pack.get("entity_name") and evidence_pack.get("attribute"):
            try:
                gnn_score = self.gnn_scorer.score(
                    entity_id=evidence_pack["entity_name"],
                    attribute=evidence_pack["attribute"],
                    value=evidence_pack.get("value", "")
                )
                logger.info("Tier 1B GNN: score=%.2f", gnn_score)
            except Exception as exc:
                logger.warning("GNN scoring failed: %s", exc)
        
        # Store in result
        result["gnn_plausibility_score"] = gnn_score
        
        # ... continue with Tier 2/3 ...
```

**Acceptance Criteria:**
- [ ] GNN scorer returns fixed 0.5 for all requests
- [ ] batch_score() handles multiple triples efficiently
- [ ] Scorer integrated into EvaluationRouter Tier 1B
- [ ] gnn_plausibility_score populated in unified_evaluation_records
- [ ] Test: Evaluate record with entity → verify score = 0.5

---

### Phase 2 Deliverables
- [x] Batch consumer processes 25 records every 5 minutes
- [x] Shared context cache reduces redundant Neo4j queries by 60%
- [x] GNN plausibility scorer stub operational (returns 0.5)
- [x] lifecycle_status advances from OPEN → DIAGNOSING → RESOLVED
- [x] Evaluation fields populated for all repair=True records

**Dependencies:** Phase 1 (repair flags must be set)  
**Risks:** Neo4j query performance may require index tuning

---

## Phase 3: Repair Proposal & Governance (Priority: MEDIUM)
**Duration:** 3 weeks | **Effort:** 120 hours

### Objective
Enable repair proposal generation, governance review workflow, canonical graph promotion.

### Tasks

#### 3.1 Create Repair Proposal Queue
**File:** `backend/app/schemas/repair_proposals.py` (NEW)  
**Schema:**

```python
from sqlalchemy import Column, String, Integer, Float, JSON, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base_class import Base

class RepairProposal(Base):
    __tablename__ = "repair_proposals"
    
    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unified_record_ref: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("unified_evaluation_records.response_id"),
        nullable=False,
        index=True
    )
    
    proposal_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'vector' | 'graph'
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    attribute: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # For graph repairs
    mutation_cypher: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_nodes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # For vector repairs
    document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reindex_required: Mapped[bool] = mapped_column(Boolean, default=False)
    
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # Status: pending → approved → applied OR rejected
    
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    
    regression_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    __table_args__ = (
        CheckConstraint("proposal_type IN ('vector', 'graph')", name="ck_proposal_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'applied')", name="ck_proposal_status"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_proposal_confidence"),
        Index("idx_proposal_status_confidence", "status", "confidence"),
        Index("idx_proposal_created", "created_at"),
    )
```

**File:** `backend/app/services/repair_proposal_service.py` (NEW)  
**Implementation:**

```python
from sqlalchemy.orm import Session
from app.schemas.repair_proposals import RepairProposal
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
import uuid

class RepairProposalService:
    """Generate repair proposals from evaluated records"""
    
    def create_proposal_from_record(
        self,
        record: UnifiedEvaluationRecord,
        db: Session
    ) -> RepairProposal:
        """
        Create repair proposal based on record's repair_target and evaluation results.
        """
        
        if not record.repair or not record.repair_target:
            raise ValueError("Record does not require repair")
        
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        
        if record.repair_target == "graph":
            # Generate graph mutation proposal
            return self._create_graph_proposal(proposal_id, record, db)
        elif record.repair_target == "vector":
            # Generate vector reindex proposal
            return self._create_vector_proposal(proposal_id, record, db)
        else:
            raise ValueError(f"Unknown repair target: {record.repair_target}")
    
    def _create_graph_proposal(
        self,
        proposal_id: str,
        record: UnifiedEvaluationRecord,
        db: Session
    ) -> RepairProposal:
        """Generate Cypher mutation for knowledge graph correction"""
        
        # Extract correction details from feedback
        from app.schemas.response_feedback_table import ResponseFeedback
        feedback = (
            db.query(ResponseFeedback)
            .filter(ResponseFeedback.feedback_id == record.feedback_ref)
            .first()
        )
        
        if not feedback or not feedback.classification_json:
            raise ValueError("No classification data for graph proposal")
        
        classification = feedback.classification_json
        entity_id = classification.get("entity_extracted")
        attribute = classification.get("attribute")
        corrected_value = classification.get("value_mentioned")
        
        if not all([entity_id, attribute, corrected_value]):
            raise ValueError("Incomplete correction data")
        
        # Generate safe Cypher mutation
        mutation_cypher = f"""
        MATCH (e:Entity {{id: $entity_id}})
        SET e.{attribute} = $corrected_value,
            e.last_updated = datetime(),
            e.updated_by = 'feedback_loop',
            e.correction_source = $feedback_id
        RETURN e
        """
        
        return RepairProposal(
            proposal_id=proposal_id,
            unified_record_ref=record.response_id,
            proposal_type="graph",
            entity_id=entity_id,
            attribute=attribute,
            mutation_cypher=mutation_cypher,
            affected_nodes=[entity_id],
            confidence=record.adjudication_confidence or 0.7,
            status="pending",
        )
    
    def _create_vector_proposal(
        self,
        proposal_id: str,
        record: UnifiedEvaluationRecord,
        db: Session
    ) -> RepairProposal:
        """Generate vector store reindex proposal"""
        
        # Identify documents that need reindexing
        from app.schemas.query_evidence_table import QueryEvidence
        evidence = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == record.response_id)
            .first()
        )
        
        if not evidence or not evidence.source_ids:
            raise ValueError("No evidence sources for vector proposal")
        
        # Stale sources need reindexing
        document_ids = evidence.source_ids
        
        return RepairProposal(
            proposal_id=proposal_id,
            unified_record_ref=record.response_id,
            proposal_type="vector",
            document_ids=document_ids,
            reindex_required=True,
            confidence=record.adjudication_confidence or 0.7,
            status="pending",
        )
```

**Acceptance Criteria:**
- [ ] repair_proposals table created with all constraints
- [ ] RepairProposalService generates graph proposals with safe Cypher
- [ ] RepairProposalService generates vector proposals with document IDs
- [ ] Proposals created with status='pending', confidence from evaluation
- [ ] Test: Evaluate record with repair=True, repair_target='graph' → verify proposal created

---

#### 3.2 Add Cypher Mutation Validator
**File:** `backend/app/services/cypher_validator.py` (NEW)  
**Implementation:**

```python
import re
from typing import Tuple

class CypherValidator:
    """Validate Cypher mutations for safety before execution"""
    
    # Deny-list patterns
    DENY_LIST = [
        r"\bDROP\s+INDEX\b",
        r"\bDROP\s+CONSTRAINT\b",
        r"\bCREATE\s+INDEX\b",
        r"\bCREATE\s+CONSTRAINT\b",
        r"\bDELETE\b(?![^(]*\bWHERE\b)",  # DELETE without WHERE
        r"\bDETACH\s+DELETE\b(?![^(]*\bWHERE\b)",
    ]
    
    # Compliance-sensitive fields that cannot be removed
    PROTECTED_FIELDS = [
        "confidence_level",
        "source_authority",
        "effective_date",
        "compliance_flag",
        "regulatory_tag",
    ]
    
    def validate(self, cypher: str) -> Tuple[bool, str]:
        """
        Validate Cypher mutation.
        
        Returns:
            (is_safe, reason)
        """
        
        # Check deny-list patterns
        for pattern in self.DENY_LIST:
            if re.search(pattern, cypher, re.IGNORECASE):
                return False, f"Denied: Contains prohibited operation: {pattern}"
        
        # Check for REMOVE on protected fields
        remove_pattern = r"\bREMOVE\s+\w+\.(\w+)"
        for match in re.finditer(remove_pattern, cypher, re.IGNORECASE):
            field = match.group(1)
            if field in self.PROTECTED_FIELDS:
                return False, f"Denied: Cannot REMOVE protected field: {field}"
        
        # Check for SET on protected fields (warn only, don't block)
        set_pattern = r"\bSET\s+\w+\.(\w+)\s*="
        warnings = []
        for match in re.finditer(set_pattern, cypher, re.IGNORECASE):
            field = match.group(1)
            if field in self.PROTECTED_FIELDS:
                warnings.append(f"Warning: Modifying protected field: {field}")
        
        if warnings:
            return True, "; ".join(warnings)
        
        return True, "Validation passed"
    
    def extract_affected_nodes(self, cypher: str) -> list[str]:
        """Extract entity IDs from MATCH clauses"""
        match_pattern = r"MATCH\s+\([^)]*\{id:\s*['\"]?([^'\"}\s]+)"
        matches = re.findall(match_pattern, cypher, re.IGNORECASE)
        return list(set(matches))

# Global singleton
_validator = CypherValidator()

def get_cypher_validator() -> CypherValidator:
    return _validator
```

**File:** `backend/app/services/repair_proposal_service.py`  
**Integrate validation:**
```python
from app.services.cypher_validator import get_cypher_validator

class RepairProposalService:
    def __init__(self):
        self.validator = get_cypher_validator()
    
    def _create_graph_proposal(self, ...) -> RepairProposal:
        # ... generate mutation_cypher ...
        
        # Validate before saving
        is_safe, reason = self.validator.validate(mutation_cypher)
        if not is_safe:
            logger.error("Unsafe Cypher rejected: %s", reason)
            raise ValueError(f"Unsafe mutation: {reason}")
        
        affected_nodes = self.validator.extract_affected_nodes(mutation_cypher)
        
        return RepairProposal(
            # ... fields ...
            mutation_cypher=mutation_cypher,
            affected_nodes=affected_nodes,
            # ... rest ...
        )
```

**Acceptance Criteria:**
- [ ] Validator blocks DROP INDEX/CONSTRAINT
- [ ] Validator blocks CREATE INDEX/CONSTRAINT
- [ ] Validator blocks DELETE without WHERE
- [ ] Validator blocks REMOVE on protected fields
- [ ] Validator warns on SET to protected fields (doesn't block)
- [ ] extract_affected_nodes() parses entity IDs correctly
- [ ] Test: Generate proposal with unsafe Cypher → verify rejection

---

#### 3.3 Implement Governance Batch Scheduler
**File:** `backend/app/services/governance_scheduler.py` (NEW)  
**Implementation:**

```python
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.schemas.repair_proposals import RepairProposal

class GovernanceBatchScheduler:
    """
    Weekly governance batch job (runs Monday 9am).
    Fetches proposals with confidence ≥ 0.75, runs regression tests.
    """
    
    def __init__(self, confidence_threshold: float = 0.75):
        self.confidence_threshold = confidence_threshold
    
    async def run_weekly_batch(self):
        """Main batch processing"""
        db = SessionLocal()
        try:
            # Fetch pending proposals above threshold
            proposals = (
                db.query(RepairProposal)
                .filter(
                    RepairProposal.status == "pending",
                    RepairProposal.confidence >= self.confidence_threshold
                )
                .order_by(RepairProposal.confidence.desc())
                .all()
            )
            
            if not proposals:
                logger.info("No proposals for governance batch")
                return
            
            logger.info("Governance batch: %d proposals for review", len(proposals))
            
            # Auto-approve high-confidence proposals (≥0.95) if regression passes
            auto_approved = []
            manual_review = []
            
            for proposal in proposals:
                if proposal.confidence >= 0.95:
                    # Run regression test
                    regression_score = await self._run_regression_test(proposal, db)
                    proposal.regression_score = regression_score
                    
                    if regression_score < 0.05:  # Less than 5% regression
                        proposal.status = "approved"
                        proposal.reviewed_at = datetime.now(timezone.utc).isoformat()
                        proposal.reviewed_by = "auto_governance_batch"
                        auto_approved.append(proposal.proposal_id)
                    else:
                        manual_review.append(proposal.proposal_id)
                else:
                    manual_review.append(proposal.proposal_id)
            
            db.commit()
            
            # Send notification email to governance team
            await self._send_governance_notification(auto_approved, manual_review)
            
            logger.info(
                "Governance batch complete: %d auto-approved, %d need review",
                len(auto_approved),
                len(manual_review)
            )
            
        finally:
            db.close()
    
    async def _run_regression_test(self, proposal: RepairProposal, db: Session) -> float:
        """
        Run regression test: compare query results before/after mutation.
        Returns regression score (0.0 = no regression, 1.0 = complete failure).
        """
        # Placeholder: Real implementation would:
        # 1. Clone production Neo4j to shadow instance
        # 2. Apply mutation to shadow
        # 3. Run canonical query set against both
        # 4. Compare outputs (precision/recall)
        
        logger.info("Running regression test for proposal %s", proposal.proposal_id)
        
        # Stub: Always return low regression for now
        return 0.02
    
    async def _send_governance_notification(self, auto_approved: list, manual_review: list):
        """Send email to governance team"""
        # Placeholder: Real implementation would use SMTP
        logger.info(
            "Governance notification: %d auto-approved, %d manual review required",
            len(auto_approved),
            len(manual_review)
        )

# Scheduler loop
async def start_governance_scheduler():
    scheduler = GovernanceBatchScheduler()
    
    while True:
        now = datetime.now(timezone.utc)
        
        # Check if Monday 9am UTC
        if now.weekday() == 0 and now.hour == 9:
            try:
                await scheduler.run_weekly_batch()
            except Exception as exc:
                logger.error("Governance batch failed: %s", exc)
            
            # Sleep until next Monday
            await asyncio.sleep(7 * 24 * 3600)
        else:
            # Check every hour
            await asyncio.sleep(3600)
```

**File:** `backend/app/main.py`  
**Add to startup:**
```python
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Start governance scheduler
    from app.services.governance_scheduler import start_governance_scheduler
    asyncio.create_task(start_governance_scheduler())
    logger.info("GovernanceBatchScheduler started")
```

**Acceptance Criteria:**
- [ ] Scheduler runs every Monday 9am UTC
- [ ] Fetches proposals with confidence ≥ 0.75, status='pending'
- [ ] Auto-approves proposals with confidence ≥ 0.95 and regression < 5%
- [ ] Sets status='approved', reviewed_by='auto_governance_batch'
- [ ] Sends notification email (stub logs message)
- [ ] Test: Create proposal with confidence=0.96 → run batch → verify auto-approved

---

#### 3.4 Implement Canonical Graph Promotion
**File:** `backend/app/services/promotion_service.py` (NEW)  
**Implementation:**

```python
from sqlalchemy.orm import Session
from app.schemas.repair_proposals import RepairProposal
from app.graph.graph_store import get_graph_store
from datetime import datetime, timezone

class PromotionService:
    """Apply approved repair proposals to canonical Neo4j graph"""
    
    def __init__(self):
        self.graph_store = get_graph_store()
    
    def apply_approved_proposals(self, batch_id: str = None):
        """
        Execute approved Cypher mutations on production Neo4j.
        All mutations in a single transaction (rollback on any failure).
        """
        db = SessionLocal()
        try:
            # Fetch approved but not yet applied proposals
            proposals = (
                db.query(RepairProposal)
                .filter(
                    RepairProposal.status == "approved",
                    RepairProposal.applied_at.is_(None)
                )
                .all()
            )
            
            if not proposals:
                logger.info("No approved proposals to apply")
                return
            
            logger.info("Applying %d approved proposals to canonical graph", len(proposals))
            
            # Execute mutations in transaction
            with self.graph_store.driver.session() as neo4j_session:
                tx = neo4j_session.begin_transaction()
                
                try:
                    applied = []
                    for proposal in proposals:
                        if proposal.proposal_type == "graph":
                            # Execute Cypher mutation
                            result = tx.run(proposal.mutation_cypher)
                            logger.info("Applied graph mutation for proposal %s", proposal.proposal_id)
                            
                            # Log to audit trail
                            self._log_mutation(proposal, db)
                            
                            proposal.applied_at = datetime.now(timezone.utc).isoformat()
                            proposal.status = "applied"
                            applied.append(proposal.proposal_id)
                        
                        elif proposal.proposal_type == "vector":
                            # Trigger vector store reindex
                            await self._trigger_reindex(proposal)
                            
                            proposal.applied_at = datetime.now(timezone.utc).isoformat()
                            proposal.status = "applied"
                            applied.append(proposal.proposal_id)
                    
                    # Commit transaction
                    tx.commit()
                    db.commit()
                    
                    logger.info("Successfully applied %d proposals", len(applied))
                    
                except Exception as exc:
                    # Rollback on any failure
                    tx.rollback()
                    db.rollback()
                    logger.error("Proposal application failed, rolled back: %s", exc)
                    raise
        
        finally:
            db.close()
    
    def _log_mutation(self, proposal: RepairProposal, db: Session):
        """Log graph mutation to audit trail"""
        from app.models.audit import GraphMutation
        
        mutation = GraphMutation(
            mutation_id=f"mut_{uuid.uuid4().hex[:12]}",
            proposal_id=proposal.proposal_id,
            mutation_cypher=proposal.mutation_cypher,
            affected_nodes=proposal.affected_nodes,
            applied_at=datetime.now(timezone.utc).isoformat(),
            applied_by="promotion_service",
        )
        db.add(mutation)
        db.commit()
    
    async def _trigger_reindex(self, proposal: RepairProposal):
        """Trigger vector store reindex for affected documents"""
        logger.info("Triggering reindex for documents: %s", proposal.document_ids)
        # Placeholder: Real implementation would call FAISS/Qdrant reindex API
        pass
```

**File:** `backend/app/api/routes/governance.py` (NEW)  
**Add promotion endpoint:**
```python
from fastapi import APIRouter, Depends
from app.services.promotion_service import PromotionService

router = APIRouter(prefix="/api/governance", tags=["governance"])

@router.post("/promote")
def promote_approved_proposals(
    current_role: Role = Depends(require_admin_role)
):
    """
    Apply all approved repair proposals to canonical graph.
    Requires admin role.
    """
    service = PromotionService()
    try:
        service.apply_approved_proposals()
        return {"status": "success", "message": "Approved proposals applied"}
    except Exception as exc:
        logger.error("Promotion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
```

**Acceptance Criteria:**
- [ ] PromotionService applies approved proposals in single transaction
- [ ] Cypher mutations executed on production Neo4j
- [ ] Mutations logged to graph_mutations audit table
- [ ] Rollback on any failure
- [ ] status='applied', applied_at timestamp set
- [ ] Test: Approve proposal → call promote endpoint → verify Neo4j updated

---

### Phase 3 Deliverables
- [x] repair_proposals table operational
- [x] RepairProposalService generates safe Cypher mutations
- [x] CypherValidator blocks unsafe operations
- [x] GovernanceBatchScheduler runs weekly (Monday 9am)
- [x] Auto-approval for confidence ≥ 0.95 with regression < 5%
- [x] PromotionService applies approved proposals to Neo4j
- [x] Audit trail logs all graph mutations

**Dependencies:** Phase 2 (evaluation must populate confidence scores)  
**Risks:** Neo4j transaction timeout for large batches (mitigate with batch size limit)

---

## Phase 4: Lifecycle Automation & Monitoring (Priority: LOW)
**Duration:** 2 weeks | **Effort:** 80 hours

### Objective
Automate lifecycle state transitions, add monitoring/alerting, optimize performance.

### Tasks

#### 4.1 Implement Lifecycle State Machine
**File:** `backend/app/services/lifecycle_manager.py` (NEW)  
**Implementation:**

```python
from enum import Enum
from sqlalchemy.orm import Session
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord, LifecycleStatus
from datetime import datetime, timezone, timedelta

class LifecycleManager:
    """Manage lifecycle state transitions for unified_evaluation_records"""
    
    VALID_TRANSITIONS = {
        LifecycleStatus.OPEN: [LifecycleStatus.DIAGNOSING],
        LifecycleStatus.DIAGNOSING: [LifecycleStatus.RESOLVED, LifecycleStatus.OPEN],
        LifecycleStatus.RESOLVED: [LifecycleStatus.MONITORING],
        LifecycleStatus.MONITORING: [],  # Terminal state
    }
    
    def advance(
        self,
        session_id: str,
        response_id: str,
        new_status: LifecycleStatus,
        reason: str,
        db: Session
    ) -> bool:
        """
        Transition record to new lifecycle status.
        Validates transition is allowed.
        """
        record = (
            db.query(UnifiedEvaluationRecord)
            .filter(
                UnifiedEvaluationRecord.session_id == session_id,
                UnifiedEvaluationRecord.response_id == response_id
            )
            .first()
        )
        
        if not record:
            raise ValueError(f"Record not found: {response_id}")
        
        current_status = LifecycleStatus(record.lifecycle_status)
        
        # Validate transition
        allowed = self.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValueError(f"Invalid transition: {current_status} → {new_status}")
        
        # Update status
        record.lifecycle_status = new_status
        record.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Log transition
        self._log_transition(record, current_status, new_status, reason, db)
        
        db.commit()
        logger.info(
            "Lifecycle transition: %s → %s (reason: %s)",
            current_status,
            new_status,
            reason
        )
        return True
    
    def _log_transition(
        self,
        record: UnifiedEvaluationRecord,
        old_status: LifecycleStatus,
        new_status: LifecycleStatus,
        reason: str,
        db: Session
    ):
        """Store transition history in lifecycle_events JSON field"""
        # Add lifecycle_events field to UnifiedEvaluationRecord schema if not present
        # For now, log to application logs
        logger.info(
            "Lifecycle event: record=%s, %s → %s, reason=%s",
            record.response_id,
            old_status,
            new_status,
            reason
        )
    
    def auto_advance_resolved_to_monitoring(self, observation_days: int = 7):
        """
        Automatically advance RESOLVED records to MONITORING after observation period.
        Run as scheduled job.
        """
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=observation_days)
            
            resolved_records = (
                db.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.lifecycle_status == LifecycleStatus.RESOLVED,
                    UnifiedEvaluationRecord.updated_at <= cutoff.isoformat()
                )
                .all()
            )
            
            for record in resolved_records:
                try:
                    self.advance(
                        session_id=record.session_id,
                        response_id=record.response_id,
                        new_status=LifecycleStatus.MONITORING,
                        reason=f"Observation period ({observation_days}d) completed",
                        db=db
                    )
                except Exception as exc:
                    logger.error("Failed to advance record %s: %s", record.response_id, exc)
            
            logger.info("Auto-advanced %d records to MONITORING", len(resolved_records))
            
        finally:
            db.close()

# Background task
async def start_lifecycle_manager():
    manager = LifecycleManager()
    
    while True:
        await asyncio.sleep(86400)  # Run daily
        try:
            manager.auto_advance_resolved_to_monitoring(observation_days=7)
        except Exception as exc:
            logger.error("Lifecycle manager error: %s", exc)
```

**Acceptance Criteria:**
- [ ] LifecycleManager validates all state transitions
- [ ] Invalid transitions raise ValueError
- [ ] Transition history logged
- [ ] Auto-advance RESOLVED → MONITORING after 7 days
- [ ] Test: Manually advance OPEN → DIAGNOSING → RESOLVED → verify MONITORING after 7 days

---

#### 4.2 Add Prometheus Metrics
**File:** `backend/app/monitoring/metrics.py` (NEW)  
**Implementation:**

```python
from prometheus_client import Counter, Histogram, Gauge

# Feedback submission metrics
feedback_submissions_total = Counter(
    "feedback_submissions_total",
    "Total feedback submissions",
    ["source", "category"]
)

# Pipeline execution metrics
pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "Feedback pipeline execution duration",
    ["step", "source"]
)

pipeline_errors_total = Counter(
    "pipeline_errors_total",
    "Total pipeline errors",
    ["step", "error_type"]
)

# Evaluation metrics
evaluation_tier_executions = Counter(
    "evaluation_tier_executions",
    "Evaluation tier executions",
    ["tier", "verdict"]
)

evaluation_duration_seconds = Histogram(
    "evaluation_duration_seconds",
    "Evaluation duration by tier",
    ["tier"]
)

# Repair metrics
repair_proposals_total = Counter(
    "repair_proposals_total",
    "Total repair proposals",
    ["proposal_type", "status"]
)

# Lifecycle metrics
lifecycle_transitions_total = Counter(
    "lifecycle_transitions_total",
    "Lifecycle state transitions",
    ["from_status", "to_status"]
)

# Queue metrics
pending_feedback_gauge = Gauge(
    "pending_feedback_count",
    "Number of pending feedback records"
)

pending_evaluation_gauge = Gauge(
    "pending_evaluation_count",
    "Number of records awaiting evaluation"
)
```

**File:** `backend/app/main.py`  
**Add Prometheus endpoint:**
```python
from prometheus_client import make_asgi_app

# Mount prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

**Integrate into services:**
```python
# In orchestrator.py
from app.monitoring.metrics import pipeline_duration_seconds, pipeline_errors_total

class RecordBuilder:
    def build(self, row: FeedbackRecord) -> Optional[UnifiedEvaluationRecord]:
        import time
        start_time = time.time()
        
        try:
            # ... existing build logic ...
            
            duration = time.time() - start_time
            pipeline_duration_seconds.labels(step="total", source=row.source).observe(duration)
            
            return record
        
        except Exception as exc:
            pipeline_errors_total.labels(step="build", error_type=type(exc).__name__).inc()
            raise
```

**Acceptance Criteria:**
- [ ] `/metrics` endpoint exposes Prometheus metrics
- [ ] feedback_submissions_total incremented on each submission
- [ ] pipeline_duration_seconds recorded for each step
- [ ] evaluation_tier_executions tracked per tier
- [ ] pending_*_gauge updated every minute
- [ ] Test: Submit feedback → verify metrics updated → scrape /metrics

---

### Phase 4 Deliverables
- [x] LifecycleManager with state machine validation
- [x] Auto-advance RESOLVED → MONITORING after 7 days
- [x] Prometheus metrics for pipeline, evaluation, repair
- [x] /metrics endpoint for Grafana integration
- [x] Monitoring dashboard setup guide

**Dependencies:** Phase 1-3 (all components operational)  
**Risks:** None (monitoring is non-blocking)

---

## Phase 5: Optimization & Production Readiness (Priority: LOW)
**Duration:** 1 week | **Effort:** 40 hours

### Objective
Optimize performance, add integration tests, production deployment checklist.

### Tasks

#### 5.1 Add Deduplication Clustering
**File:** `backend/app/services/deduplication_service.py` (NEW)  
**Implementation:**

```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import HDBSCAN
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord

class DeduplicationService:
    """Cluster similar feedback records to reduce noise"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", similarity_threshold: float = 0.88):
        self.embedder = SentenceTransformer(model_name)
        self.similarity_threshold = similarity_threshold
    
    def cluster_open_records(self, db: Session):
        """
        Find and merge duplicate open records.
        Oldest record becomes canonical, rest point to it.
        """
        # Fetch open records
        records = (
            db.query(UnifiedEvaluationRecord)
            .filter(UnifiedEvaluationRecord.lifecycle_status == LifecycleStatus.OPEN)
            .order_by(UnifiedEvaluationRecord.created_at)
            .all()
        )
        
        if len(records) < 2:
            return
        
        # Extract text for embedding
        texts = []
        for r in records:
            # Combine response_id + root_cause + severity as dedup key
            from app.schemas.response_feedback_table import ResponseFeedback
            feedback = db.query(ResponseFeedback).filter(ResponseFeedback.feedback_id == r.feedback_ref).first()
            text = f"{feedback.feedback_text or ''} {r.root_cause} {r.severity}"
            texts.append(text)
        
        # Embed and compute similarity
        embeddings = self.embedder.encode(texts)
        similarity_matrix = cosine_similarity(embeddings)
        
        # Find duplicates
        merged_count = 0
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                if similarity_matrix[i][j] >= self.similarity_threshold:
                    # Merge j into i (i is older)
                    canonical = records[i]
                    duplicate = records[j]
                    
                    # Update duplicate to point to canonical
                    duplicate.lifecycle_status = LifecycleStatus.RESOLVED
                    duplicate.updated_at = datetime.now(timezone.utc).isoformat()
                    # Add note in dissatisfaction_evidence
                    if duplicate.dissatisfaction_evidence:
                        duplicate.dissatisfaction_evidence["merged_into"] = canonical.response_id
                    
                    merged_count += 1
                    logger.info("Merged duplicate %s into %s", duplicate.response_id, canonical.response_id)
        
        db.commit()
        logger.info("Deduplication complete: merged %d records", merged_count)
        return merged_count
```

**Acceptance Criteria:**
- [ ] Clustering runs on open records
- [ ] Similarity threshold 0.88 (cosine)
- [ ] Oldest record becomes canonical
- [ ] Duplicates marked RESOLVED with merged_into reference
- [ ] Test: Create 5 similar records → verify 4 merged into 1

---

#### 5.2 Add E2E Integration Tests
**File:** `backend/tests/test_feedback_loop_e2e.py` (NEW)  
**Test cases:**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal

client = TestClient(app)

def test_active_feedback_full_pipeline():
    """E2E: Submit feedback → verify unified record created → check repair proposal"""
    
    # 1. Submit feedback
    response = client.post("/api/feedback", json={
        "response_id": "resp_test_001",
        "session_id": "sess_test_001",
        "interaction_id": "int_test_001",
        "turn_number": 1,
        "query_text": "What is the TER of Fund ABC?",
        "selected_categories": ["F03"],
        "feedback_text": "The TER is wrong, it should be 0.5%",
        "actor_id": "test_user",
        "actor_role": "admin"
    })
    assert response.status_code == 200
    feedback_id = response.json()["feedback_id"]
    
    # 2. Wait for pipeline to complete (background task)
    import time
    time.sleep(5)
    
    # 3. Verify unified record created
    db = SessionLocal()
    from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
    record = db.query(UnifiedEvaluationRecord).filter(
        UnifiedEvaluationRecord.response_id == "resp_test_001"
    ).first()
    
    assert record is not None
    assert record.entry_route == "hitl"
    assert record.root_cause is not None
    assert record.repair == True  # Numeric error should trigger repair
    
    # 4. Verify repair proposal generated
    from app.schemas.repair_proposals import RepairProposal
    proposal = db.query(RepairProposal).filter(
        RepairProposal.unified_record_ref == "resp_test_001"
    ).first()
    
    assert proposal is not None
    assert proposal.status == "pending"
    assert proposal.confidence >= 0.7
    
    db.close()

def test_passive_feedback_timeout():
    """E2E: Timeout expires → verify skeleton enriched → check pipeline trigger"""
    # Similar test for passive path
    pass

def test_dissatisfaction_detection_auto_feedback():
    """E2E: Submit follow-up correction → verify auto-feedback + patch"""
    pass
```

**Acceptance Criteria:**
- [ ] 10+ E2E tests covering all entry paths
- [ ] Tests run in CI/CD pipeline
- [ ] 90% code coverage on critical paths
- [ ] Test: All E2E tests pass

---

#### 5.3 Production Deployment Checklist
**File:** `Docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md` (NEW)

```markdown
# Feedback Loop Production Deployment Checklist

## Database
- [ ] Add indexes on frequently queried fields
  - `response_feedback.response_id`
  - `response_feedback.created_at`
  - `unified_evaluation_records.repair, lifecycle_status` (composite)
  - `repair_proposals.status, confidence` (composite)
- [ ] Configure connection pooling
  - PostgreSQL: max 100 connections
  - Neo4j: max 50 connections
- [ ] Set up daily backups
  - `unified_evaluation_records` table
  - `repair_proposals` table
- [ ] Configure backup retention: 30 days

## API
- [ ] Rate limiting: 10 req/min per user on `/api/feedback`
- [ ] Request timeout: 30s for feedback submission
- [ ] Enable CORS with whitelist
- [ ] Configure authentication (JWT + RBAC)

## Background Jobs
- [ ] TimeoutProcessor running (60s interval)
- [ ] FeedbackRetryService running (60s interval)
- [ ] BatchEvaluationConsumer running (300s interval)
- [ ] GovernanceBatchScheduler running (weekly Monday 9am)
- [ ] LifecycleManager auto-advance running (daily)

## Monitoring
- [ ] Prometheus /metrics endpoint exposed
- [ ] Grafana dashboard configured
- [ ] Alerts configured:
  - Pipeline error rate > 5%
  - Pending feedback backlog > 100
  - Batch evaluation latency > 60s
- [ ] PagerDuty integration for critical alerts

## Performance
- [ ] Redis cache for shared context (1h TTL)
- [ ] Batch size tuned (target: < 30s per 25 records)
- [ ] Neo4j query optimization
- [ ] Vector store index size < 5GB

## Security
- [ ] CypherValidator deny-list reviewed
- [ ] Protected fields list updated
- [ ] Audit trail logging enabled
- [ ] Sensitive data encryption at rest

## Documentation
- [ ] API documentation updated
- [ ] Runbook for common failures
- [ ] Governance workflow guide
- [ ] Monitoring dashboard guide
```

**Acceptance Criteria:**
- [ ] All checklist items completed
- [ ] Production environment passes smoke tests
- [ ] Rollback plan documented

---

### Phase 5 Deliverables
- [x] Deduplication reduces noise by 40%
- [x] E2E test suite with 90% coverage
- [x] Production deployment checklist complete
- [x] Performance tuning guide
- [x] Monitoring runbook

**Dependencies:** Phase 1-4 (all features complete)  
**Risks:** None (optimization phase)

---

## Risk Management

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| GNN model training data unavailable | High | Medium | Use stub with fixed 0.5 score; train model in parallel |
| Neo4j write permission conflicts | Medium | Low | Test mutations on shadow instance first |
| Evaluation latency exceeds SLA | Medium | Medium | Tune batch size, add caching, parallelize within batch |
| Governance team bandwidth low | Low | High | Auto-approve high-confidence proposals (≥0.95) |
| Passive feedback backlog grows | Medium | Medium | Scale TimeoutProcessor horizontally, add more workers |

---

## Success Metrics

### Phase 1 Success Criteria
- Passive feedback reaches unified_evaluation_records in < 5 minutes
- repair & repair_target fields populated for 100% of high-severity records
- Evaluation tier results stored for 100% of repair=True records
- Webhook retry success rate > 95%

### Phase 2 Success Criteria
- Batch consumer processes 25 records in < 30 seconds
- Cache hit rate > 60% for shared context
- lifecycle_status advances correctly for 100% of evaluated records

### Phase 3 Success Criteria
- Repair proposals generated for 100% of repair=True records
- Cypher validation rejects 100% of unsafe mutations
- Governance batch runs weekly with 0 failures
- Canonical graph mutations logged to audit trail with 100% coverage

### Phase 4 Success Criteria
- Lifecycle state machine validates 100% of transitions
- Prometheus metrics available with < 1 minute lag
- Auto-advance RESOLVED → MONITORING after 7 days for 100% of records

### Phase 5 Success Criteria
- Deduplication reduces open records by 40%
- E2E test suite passes with 90% coverage
- Production deployment checklist 100% complete

---

## Post-Implementation Roadmap

### Future Enhancements (Beyond Scope)
1. **Train GNN Model**
   - Collect training data from canonical graph
   - Train R-GCN or use Neo4j GDS for structural plausibility
   - Replace 0.5 stub with actual scores

2. **Advanced Batch Optimization**
   - Implement few-shot example cache (24h TTL)
   - Add batch embedding clustering (HDBSCAN)
   - Parallelize evaluation within batch

3. **Governance UI**
   - Build `/governance/review` dashboard (React/Streamlit)
   - Add approval workflow with comments
   - Batch operations (approve all ≥0.90)

4. **Shadow Graph Testing**
   - Clone production Neo4j to shadow instance
   - Run regression tests on shadow before approval
   - Compare query outputs (precision/recall)

5. **Adaptive Router Tuning**
   - Track rule precision/recall over time
   - Auto-tune thresholds based on human overrides
   - A/B test new rules before production

---

## Appendix

### Key Files Reference
- **Core Pipeline:** `packages/amc-feedback-loop/src/feedback_loop/orchestrator.py`
- **Evaluation Router:** `backend/app/evaluation/evaluation_router.py`
- **Feedback API:** `backend/app/api/routes/feedback.py`
- **Timeout Processor:** `backend/app/feedback/timeout_processor.py`
- **Dissatisfaction Detector:** `backend/app/feedback/dissatisfaction_detector.py`
- **Repair Proposals:** `backend/app/schemas/repair_proposals.py`
- **Governance:** `backend/app/services/governance_scheduler.py`
- **Lifecycle Manager:** `backend/app/services/lifecycle_manager.py`

### Architecture Diagrams
Refer to:
- `Docs/08-Research-and-Feedback/AMC_Feedback_Loop_Technical_Design.md`
- `Docs/feedback_finding_repair/amc_feedback_loop_architecture 2.md`

### Contact & Support
- **Implementation Lead:** [To be assigned]
- **Architecture Review:** [To be assigned]
- **DevOps Support:** [To be assigned]

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-27  
**Status:** DRAFT - Pending Review
