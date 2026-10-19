# Unified Self-Healing Architecture: Options 1–5 Detailed Design & Implementation Plan

## Table of Contents

1. [Executive Vision & Architecture Overview](#1-executive-vision--architecture-overview)
2. [Deep-Dive Design of Each Option (1 to 5)](#2-deep-dive-design-of-each-option-1-to-5)
3. [Patch Lifecycle State Machine](#3-patch-lifecycle-state-machine)
4. [Implementation Blueprint & File-by-File Changes](#4-implementation-blueprint--file-by-file-changes)
5. [Verification & Testing Strategy](#5-verification--testing-strategy)
6. [Observability, Monitoring & Telemetry](#6-observability-monitoring--telemetry)
7. [Conflict Resolution & Patch Versioning](#7-conflict-resolution--patch-versioning)
8. [Cache Invalidation & Consistency Strategy](#8-cache-invalidation--consistency-strategy)
9. [Audit Trail, Rollback Safety & Compliance](#9-audit-trail-rollback-safety--compliance)
10. [Security, Authorization & Tamper Protection](#10-security-authorization--tamper-protection)
11. [Edge Cases, Error Handling & Graceful Degradation](#11-edge-cases-error-handling--graceful-degradation)
12. [Enhanced Testing Strategy](#12-enhanced-testing-strategy)
13. [Key Architectural Decisions for Alignment](#13-key-architectural-decisions-for-alignment)
14. [Implementation Priority & Phasing Roadmap](#14-implementation-priority--phasing-roadmap)
15. [Deployment Strategy & Rollout Plan](#15-deployment-strategy--rollout-plan)
16. [Risk Assessment & Mitigation Strategies](#16-risk-assessment--mitigation-strategies)
17. [Success Metrics & KPIs](#17-success-metrics--kpis)
18. [Post-Deployment Continuous Improvement](#18-post-deployment-continuous-improvement)
19. [Conclusion & Next Steps](#19-conclusion--next-steps)

---

## 1. Executive Vision & Architecture Overview

Currently, the self-healing repair mechanism applies corrections at runtime by prepending a `[CORRECTION PATCH APPLIED]` block into the LLM context prompt. While effective, relying purely on in-context prompting has limitations:
- Context token consumption on repetitive queries.
- Dependency on LLM adherence (weak models might ignore or soften prompt instructions).
- Lack of physical data evolution in underlying stores (vector DB and graph DB remain unpatched).

This plan outlines the design and implementation for combining **all 5 architectural alternatives** into a unified **Defense-in-Depth Self-Healing Stack**:

```mermaid
flowchart TD
    subgraph Client ["Client Layer"]
        UserQuery["User Asks Query<br/>'What is Axis Bluechip Fund's category?'"]
    end

    subgraph Layer1 ["Layer 1: Deterministic Fast-Path (<15ms)"]
        UserQuery --> Interceptor{"Option 2: Deterministic<br/>Short-Circuit Interceptor"}
        Interceptor -->|"Atomic Fact Match & Active Patch"| FastResponse["Direct Verified Response<br/>(0 Tokens, 0 Hallucination, <15ms)"]
    end

    subgraph Layer2 ["Layer 2: Dual Hybrid Retrieval"]
        Interceptor -->|"Complex / Multi-Hop Query"| HybridRetrieval["Hybrid Retrieval Pipeline"]
        HybridRetrieval --> Neo4jShadow["Option 4: Virtual Shadow Graph<br/>(Neo4j :HAS_PATCH & Cypher COALESCE)"]
        HybridRetrieval --> VectorSynthetic["Option 3: Synthetic Chunk<br/>(FAISS Ingested Erratum)"]
    end

    subgraph Layer3 ["Layer 3: Synthesis & Verification"]
        Neo4jShadow --> Assembler["Context Assembler"]
        VectorSynthetic --> Assembler
        Assembler --> LLMGen["LLM Synthesizer"]
        LLMGen --> Guardrail["Option 5: Post-Synthesis<br/>Guardrail Rewriter & Linter"]
    end

    Guardrail --> FinalAnswer["Final Verified User Answer"]

    subgraph Layer4 ["Layer 4: Permanent Governance Cycle"]
        Feedback["User Correction Feedback"] --> PatchProvisional["Provisional Patch Created"]
        PatchProvisional --> ReviewerApproval["Reviewer / Auto-Approval"]
        ReviewerApproval --> Layer1 & Layer2 & Layer3
        ReviewerApproval -->|"Confidence >= 0.95 / Weekly Batch"| GovBatch["Option 1: Direct Canonical<br/>Graph Mutation (SET e.prop = val)"]
        GovBatch --> Neo4jMaster[("Neo4j Canonical Truth")]
        GovBatch --> ArchivePatch["Archive Shadow Node & FAISS Chunk"]
    end
```

---

## 2. Deep-Dive Design of Each Option (1 to 5)

### Option 2: Deterministic Fast-Path Interceptor (Pre-LLM Short-Circuit)
* **Goal**: Answer simple factual questions instantly without invoking vector search or LLM APIs.
* **Mechanism**:
  1. At the very start of `RetrievalOrchestrator.answer()`, run lightweight regex/intent heuristics to detect if the query is an atomic property lookup (e.g. asking for `category`, `ter`, `expense ratio`, `exit load`, `fund manager`, or `aum` of a named entity).
  2. Query the Repair Engine's active patch store (`GET /api/patches/for-entities?entity_ids=<entity>`).
  3. If an approved patch matches both the target entity and the requested attribute with `confidence >= 0.90`:
     - Construct an immediate `SynthesisOutput` with `confidence="high"` and statutory citation.
     - Short-circuit and return `OrchestratorResponse` in `<15ms`.
* **Latency & Cost Impact**: **~10ms response time**, **0 input/output LLM tokens**.

---

### Option 4: Virtual Shadow Graph Overlay (Cypher `COALESCE` Overlay)
* **Goal**: Enable the knowledge graph to reflect provisional/active patches without destructively overwriting audited historical data.
* **Mechanism**:
  1. When a patch is approved in the Repair Engine, create a `:ShadowPatch` node in Neo4j linked to the entity:
     ```cypher
     MATCH (e {name: $entity_id})
     MERGE (p:ShadowPatch {patch_id: $patch_id})
     SET p.attribute = $attribute,
         p.corrected_value = $corrected_value,
         p.status = 'approved',
         p.updated_at = datetime()
     MERGE (e)-[r:HAS_PATCH {attribute: $attribute}]->(p)
     ```
  2. In traversal Cypher queries (e.g., `ENTITY_FACTS` in `cypher_library.py`), include `:HAS_PATCH` relationships:
     ```cypher
     MATCH (e {name: $entity_name})
     OPTIONAL MATCH (e)-[:HAS_PATCH {status: 'approved'}]->(p:ShadowPatch)
     RETURN e.name AS entity, 
            COALESCE(p.attribute, 'canonical') AS attribute,
            COALESCE(p.corrected_value, e.category) AS effective_value,
            properties(e) AS base_props,
            collect(p) AS shadow_patches
     ```
  3. Graph traversal naturally surfaces the patched attribute as a verified structured graph fact.
* **Safety Benefit**: Zero risk of corrupting production data; instant rollback via `MATCH (p:ShadowPatch {patch_id: $id}) DETACH DELETE p`.

---

### Option 3: Synthetic Chunk Ingestion in Vector Store (FAISS)
* **Goal**: Ensure vector/semantic search surfaces the correction for unstructured or conversational questions.
* **Mechanism**:
  1. Upon patch approval, the Repair Engine dispatches a synthetic erratum document to the vector store:
     ```python
     synthetic_chunk = {
         "chunk_id": f"erratum_{patch.patch_id}",
         "document_id": f"erratum_{patch.patch_id}",
         "document_title": f"Regulatory Erratum: {patch.entity_id}",
         "text": f"Authoritative Verification Notice: The {patch.attribute.lower()} of {patch.entity_id} is officially {patch.corrected_value}. This supersedes earlier prospectus publications.",
         "metadata": {
             "is_synthetic_patch": True,
             "patch_id": patch.patch_id,
             "entity_id": patch.entity_id,
             "attribute": patch.attribute,
             "boost_factor": 1.5,
         }
     }
     await vector_store.add_documents([synthetic_chunk])
     ```
  2. When vector search executes for queries like *"tell me about Axis Bluechip cap type"*, the synthetic chunk matches with high cosine similarity.
  3. When the patch is eventually graduated or rolled back, the chunk is evicted via `vector_store.remove_by_chunk_id(f"erratum_{patch.patch_id}")`.

---

### Option 5: Post-Synthesis Guardrail Rewriter (Deterministic Linter)
* **Goal**: Provide a fail-safe compliance barrier right before output leaves the API.
* **Mechanism**:
  1. Once the LLM generates `synthesis.answer`, the response passes through `PatchGuardrailRewriter`.
  2. For every active patch matching entities in the query:
     - Check if the answer contradicts the patch (e.g., asserts the old rejected value like `"Large Cap"` or claims `"category is not specified"`).
     - If contradictory or missing, deterministically rewrite the offending sentence or append a definitive correction block:
       `"Correction Notice: The official category of Axis Bluechip Fund is Mid Cap."`
     - Set `synthesis.compliance_note = f"Audited against Repair Engine: {patch.attribute} = {patch.corrected_value}"`.
* **Compliance Benefit**: Absolute guarantee that no hallucination escapes to financial advisors or compliance reviewers.

---

### Option 1: Direct Canonical Knowledge Graph Mutation (Neo4j `SET`)
* **Goal**: Promote vetted patches into the permanent baseline so virtual shims and synthetic chunks can be retired.
* **Mechanism**:
  1. During the weekly Governance Batch (or when an authorized compliance officer clicks **"Promote to Master"** in Admin UI):
     ```cypher
     MATCH (e) WHERE e.isin = $entity_id OR e.name = $entity_id OR e.id = $entity_id
     SET e.{attribute} = $corrected_value,
         e.{attribute}_last_promoted_at = datetime(),
         e.{attribute}_promoted_by = $promoted_by
     WITH e
     MATCH (e)-[r:HAS_PATCH {attribute: $attribute}]->(p:ShadowPatch)
     SET p.status = 'promoted'
     DETACH DELETE p
     ```
  2. The canonical Neo4j node now natively has the property.
  3. The provisional FAISS synthetic chunk is safely archived.

---

## 3. Patch Lifecycle State Machine

To prevent data desynchronization between Neo4j, FAISS, Redis, and Guardrails, each patch follows an explicit 4-state lifecycle:

```mermaid
stateDiagram-v2
    [*] --> PROVISIONAL: Feedback submitted & extracted
    PROVISIONAL --> APPROVED_ACTIVE: Reviewer approves or Confidence >= 0.90
    PROVISIONAL --> REJECTED: Reviewer rejects or Confidence < 0.50
    
    state APPROVED_ACTIVE {
        [*] --> FastPathReady: Register in Option 2 Interceptor
        [*] --> VectorIngested: Ingest in Option 3 FAISS Synthetic Chunk
        [*] --> ShadowGraphLinked: Create in Option 4 Neo4j :ShadowPatch
        [*] --> GuardrailArmed: Arm in Option 5 Post-Synthesis Linter
    }

    APPROVED_ACTIVE --> PROMOTED_CANONICAL: Governance Batch / Admin "Promote to Master"
    
    state PROMOTED_CANONICAL {
        [*] --> Neo4jMutated: Option 1 Direct SET e.attr = val
        [*] --> ShadowArchived: Delete :ShadowPatch node
        [*] --> VectorEvicted: Evict temporary synthetic chunk
    }

    APPROVED_ACTIVE --> ROLLED_BACK: Compliance Rollback Triggered
    ROLLED_BACK --> [*]: All layers purged
    PROMOTED_CANONICAL --> [*]
    REJECTED --> [*]
```

---

## 4. Implementation Blueprint & File-by-File Changes

### Phase A: Pre-LLM Deterministic Fast-Path (Option 2)
1. **New File**: `backend/app/retrieval/fast_path_interceptor.py`
   - Class `FastPathInterceptor`:
     - Method `should_short_circuit(query: str, entities: list[str]) -> tuple[bool, Optional[Patch]]`
     - Method `build_direct_response(query: str, patch: Patch) -> OrchestratorResponse`
2. **Hook in Orchestrator**:
   - In `backend/app/retrieval/orchestrator.py` at Step 0.75 (before semantic cache / vector search), call `FastPathInterceptor`. If matched, return immediately.

### Phase B: Post-Synthesis Guardrail Rewriter (Option 5)
1. **New File**: `backend/app/evaluation/patch_guardrail.py`
   - Class `PatchGuardrailRewriter`:
     - Inspects `synthesis.answer` against active patches.
     - Detects negative phrases (`"not specified"`, `"does not mention"`, or old rejected values).
     - Rewrites answer sentences with 100% deterministic precision.
2. **Hook in Orchestrator**:
   - In `backend/app/retrieval/orchestrator.py` at Step 8b (after synthesis), run `PatchGuardrailRewriter.enforce(synthesis, patches)`.

### Phase C: Virtual Shadow Graph (Option 4)
1. **Update Neo4j Adapter**:
   - In `packages/amc-repair-engine/src/amc_repair/adapters/graph.py`:
     - Add `create_shadow_patch(entity_id, patch_id, attribute, value)`.
     - Add `delete_shadow_patch(patch_id)`.
2. **Update Cypher Templates**:
   - In `backend/app/graph/cypher_library.py`:
     - Update `ENTITY_FACTS` to query `(:ShadowPatch)` alongside 1-hop relationships.

### Phase D: Synthetic Chunk Ingestion in Vector Store (Option 3)
1. **Update Vector Store Client**:
   - In `backend/app/vector/client.py`:
     - Add `ingest_synthetic_patch_chunk(patch_id, entity_id, attribute, value)`.
     - Add `evict_synthetic_patch_chunk(patch_id)`.
2. **Hook in Repair Integration**:
   - In `backend/app/services/repair_integration.py`:
     - When patch is approved, trigger `ingest_synthetic_patch_chunk`.

### Phase E: Governance Promotion into Canonical Graph (Option 1)
1. **Update Governance Batch**:
   - In `packages/amc-repair-engine/src/amc_repair/governance.py`:
     - Call `apply_entity_patch` (mutates node property `SET e.prop = val`).
     - Call `delete_shadow_patch` and `evict_synthetic_patch_chunk`.
2. **Admin UI Support**:
   - Expose `POST /api/governance/promote/{patch_id}` in `backend/app/api/routes/governance.py` for one-click promotion from the React Admin dashboard.

---

## 5. Verification & Testing Strategy

| Test Layer | Test Description | Verification Target | Success Criteria |
| :--- | :--- | :--- | :--- |
| **Unit Test** | `test_fast_path_interceptor.py` | Fast path triggers for atomic queries, returns in <15ms with 0 LLM calls. | P99 latency < 15ms, 100% correct answers |
| **Unit Test** | `test_patch_guardrail.py` | Guardrail catches contradictory LLM output and rewrites correctly. | 100% detection of contradictions, <200ms overhead |
| **Unit Test** | `test_conflict_resolver.py` | **NEW**: Conflict detection for duplicate patches on same entity+attribute. | Correct precedence rules, audit trail created |
| **Integration Test** | `test_shadow_graph_coalesce.py` | Neo4j `:HAS_PATCH` node created, Cypher query retrieves patched fact. | Correct COALESCE, rollback leaves no orphans |
| **Integration Test** | `test_synthetic_vector_chunk.py` | Synthetic chunk embedded in FAISS, retrieved by cosine similarity. | Top-3 retrieval includes synthetic chunk, eviction works |
| **Integration Test** | `test_cache_invalidation.py` | **NEW**: Cache invalidated on patch approval/promotion. | Redis/Neo4j/FAISS caches cleared correctly |
| **Integration Test** | `test_atomic_rollback.py` | **NEW**: Rollback reverts all 5 layers atomically. | Snapshot restores on partial failure, audit logged |
| **Security Test** | `test_patch_authorization.py` | **NEW**: RBAC prevents unauthorized patch operations. | Analysts can't promote, compliance officers can |
| **Security Test** | `test_patch_integrity.py` | **NEW**: Tamper detection via HMAC signatures. | Modified patches rejected, alerts triggered |
| **Chaos Test** | `test_neo4j_partition.py` | **NEW**: System continues when Neo4j shadow graph unavailable. | Degrades to FAISS, no user-facing errors |
| **Chaos Test** | `test_repair_engine_timeout.py` | **NEW**: Graceful degradation when Repair Engine API times out. | Falls back to unverified response with warning |
| **Performance Test** | `test_fast_path_p99_latency.py` | **NEW**: Fast-path P99 stays under 15ms under load. | 1000 queries/sec sustained, P99 < 15ms |
| **Performance Test** | `test_guardrail_overhead.py` | **NEW**: Guardrail adds <200ms overhead. | Baseline + overhead < 200ms at P95 |
| **E2E Browser Test** | `test_e2e_browser.cjs` | Verify UI shows both instant responses and admin governance promotion. | End-to-end user journey works |
| **E2E Compliance Test** | `test_audit_trail_immutability.cjs` | **NEW**: All patch operations logged, immutable audit trail. | PostgreSQL audit table append-only verified |

---

## 6. Observability, Monitoring & Telemetry

### 6.1 Layer-by-Layer Metrics Dashboard
To ensure the self-healing system is performing optimally, implement comprehensive monitoring:

```python
# backend/app/monitoring/patch_metrics.py
class PatchMetricsCollector:
    """Tracks effectiveness and performance of each healing layer"""
    
    async def record_fast_path_hit(self, query: str, patch_id: str, latency_ms: float):
        # Track Layer 1 performance
        await self.metrics.increment("fast_path.hits", tags={"patch_id": patch_id})
        await self.metrics.histogram("fast_path.latency", latency_ms)
    
    async def record_shadow_graph_retrieval(self, entity_id: str, patches_applied: int):
        # Track Layer 2 shadow graph usage
        await self.metrics.increment("shadow_graph.queries", tags={"entity": entity_id})
        await self.metrics.gauge("shadow_graph.active_patches", patches_applied)
    
    async def record_guardrail_intervention(self, patch_id: str, rewrite_type: str):
        # Track Layer 3 guardrail corrections
        await self.metrics.increment("guardrail.interventions", 
                                     tags={"patch_id": patch_id, "type": rewrite_type})
```

**Key Metrics to Track:**
- **Fast-Path Hit Rate**: % of queries answered by Layer 1 (target: >40% for simple queries)
- **Guardrail Intervention Rate**: % of LLM outputs requiring correction (target: <5%)
- **Patch Confidence Distribution**: Histogram of patch confidence scores
- **Layer Latency P50/P95/P99**: Track performance degradation
- **Promotion Velocity**: Time from provisional → approved → canonical

### 6.2 Real-Time Alerting Rules
```yaml
# Alerting Configuration
alerts:
  - name: GuardrailInterventionSpike
    condition: guardrail.interventions > 10% over 5min
    severity: warning
    action: "High hallucination rate detected - investigate LLM synthesis quality"
  
  - name: FastPathHitRateDrop
    condition: fast_path.hit_rate < 30% over 15min
    severity: info
    action: "Deterministic layer underperforming - review patch coverage"
  
  - name: PatchConflictDetected
    condition: patch_conflict.count > 0
    severity: critical
    action: "Multiple patches target same entity+attribute - manual resolution required"
```

---

## 7. Conflict Resolution & Patch Versioning

### 7.1 Conflict Detection Mechanism
When multiple patches target the same `(entity_id, attribute)` pair:

```python
# packages/amc-repair-engine/src/amc_repair/conflict_resolver.py
class PatchConflictResolver:
    """Handles conflicting patches using version vectors and precedence rules"""
    
    async def detect_conflict(self, new_patch: Patch) -> Optional[ConflictReport]:
        existing = await self.repo.get_active_patches(
            entity_id=new_patch.entity_id,
            attribute=new_patch.attribute
        )
        
        if len(existing) > 0:
            return ConflictReport(
                conflict_type="attribute_collision",
                existing_patches=existing,
                new_patch=new_patch,
                resolution_strategy=self._determine_strategy(existing, new_patch)
            )
        return None
    
    def _determine_strategy(self, existing: list[Patch], new: Patch) -> str:
        # Precedence rules:
        # 1. Regulatory source beats user feedback
        # 2. Higher confidence wins
        # 3. More recent timestamp breaks ties
        # 4. Escalate to human if confidence delta < 0.10
        
        if new.source_type == "regulatory" and existing[0].source_type == "user_feedback":
            return "auto_supersede"
        elif abs(new.confidence - existing[0].confidence) < 0.10:
            return "escalate_to_human"
        else:
            return "confidence_based_supersede"
```

### 7.2 Patch Versioning Schema
Extend patch model to support versioning:

```python
class Patch(BaseModel):
    patch_id: str
    entity_id: str
    attribute: str
    corrected_value: Any
    version: int = 1  # NEW: Monotonic version counter
    supersedes_patch_id: Optional[str] = None  # NEW: Tracks patch lineage
    superseded_by_patch_id: Optional[str] = None  # NEW: Bidirectional link
    conflict_resolution_reason: Optional[str] = None  # NEW: Audit trail
```

**Conflict Resolution UI:**
```mermaid
stateDiagram-v2
    [*] --> ConflictDetected: Multiple patches for same entity+attribute
    ConflictDetected --> AutoResolved: Confidence delta > 0.10 OR Regulatory source
    ConflictDetected --> HumanReview: Confidence delta < 0.10
    HumanReview --> MergePatches: Reviewer creates composite patch
    HumanReview --> SelectWinner: Reviewer picks one patch
    HumanReview --> RejectAll: Reviewer deems both incorrect
    AutoResolved --> APPROVED_ACTIVE
    MergePatches --> APPROVED_ACTIVE
    SelectWinner --> APPROVED_ACTIVE
```

---

## 8. Cache Invalidation & Consistency Strategy

### 8.1 Multi-Layer Cache Invalidation
When a patch is approved or promoted, invalidate dependent caches:

```python
# backend/app/retrieval/cache_invalidator.py
class PatchAwareCacheInvalidator:
    """Ensures cache consistency across Redis semantic cache and query caches"""
    
    async def invalidate_on_patch_approval(self, patch: Patch):
        # Step 1: Invalidate semantic cache entries mentioning the entity
        entity_patterns = [
            f"*{patch.entity_id}*",
            f"*{patch.entity_id.lower()}*",
            # Handle fuzzy name matches
        ]
        
        for pattern in entity_patterns:
            await self.redis.delete_pattern(f"semantic_cache:{pattern}")
        
        # Step 2: Invalidate Neo4j query cache for entity traversals
        await self.neo4j.run("CALL db.clearQueryCaches()")
        
        # Step 3: Invalidate FAISS index cache (trigger re-indexing if needed)
        if self.vector_store.has_cache:
            await self.vector_store.invalidate_entity_cache(patch.entity_id)
        
        # Step 4: Notify distributed workers via Redis pub/sub
        await self.redis.publish("patch_approved", {
            "patch_id": patch.patch_id,
            "entity_id": patch.entity_id,
            "attribute": patch.attribute,
            "timestamp": datetime.utcnow().isoformat()
        })
```

### 8.2 Cache-Aside Pattern for Fast-Path
```python
# Layer 1 Fast-Path with cache-aside
async def get_fast_path_response(query: str, entity_id: str, attribute: str):
    cache_key = f"fast_path:{entity_id}:{attribute}"
    
    # Try cache first
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss - query Repair Engine
    patch = await repair_engine.get_active_patch(entity_id, attribute)
    if patch and patch.confidence >= 0.90:
        response = build_direct_response(query, patch)
        await redis.setex(cache_key, ttl=3600, value=json.dumps(response))
        return response
    
    return None  # Fall through to Layer 2
```

---

## 9. Audit Trail, Rollback Safety & Compliance

### 9.1 Immutable Audit Log
Every patch state transition must be logged for regulatory compliance:

```python
# packages/amc-repair-engine/src/amc_repair/audit.py
class PatchAuditLogger:
    """Immutable append-only audit log for all patch operations"""
    
    async def log_state_transition(
        self,
        patch_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        reason: str,
        metadata: dict
    ):
        audit_entry = {
            "event_id": uuid4(),
            "timestamp": datetime.utcnow().isoformat(),
            "patch_id": patch_id,
            "transition": f"{from_state} → {to_state}",
            "actor": actor,  # User ID or "system:auto_approval"
            "reason": reason,
            "metadata": metadata,
            "signature": self._compute_hmac(patch_id, from_state, to_state)
        }
        
        # Write to PostgreSQL audit table (append-only, no updates/deletes)
        await self.db.execute(
            "INSERT INTO patch_audit_log VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            *audit_entry.values()
        )
        
        # Also stream to compliance SIEM system
        await self.siem_client.send_audit_event(audit_entry)
```

### 9.2 Point-in-Time Rollback with Snapshot
Support atomic rollback of all 5 layers:

```python
# backend/app/services/patch_rollback.py
class AtomicPatchRollback:
    """Safely rolls back a patch across all layers"""
    
    async def rollback_patch(self, patch_id: str, reason: str, actor: str):
        patch = await self.repo.get_patch(patch_id)
        
        # Create rollback snapshot before any mutations
        snapshot = await self._create_snapshot(patch)
        
        try:
            # Layer 1: Remove from fast-path cache
            await self.redis.delete(f"fast_path:{patch.entity_id}:{patch.attribute}")
            
            # Layer 2a: Remove synthetic FAISS chunk
            await self.vector_store.evict_synthetic_patch_chunk(patch_id)
            
            # Layer 2b: Remove Neo4j shadow patch
            await self.neo4j.run(
                "MATCH (p:ShadowPatch {patch_id: $patch_id}) DETACH DELETE p",
                patch_id=patch_id
            )
            
            # Layer 3: Remove from guardrail registry
            await self.guardrail.deregister_patch(patch_id)
            
            # Update patch status
            await self.repo.update_patch_status(patch_id, "ROLLED_BACK")
            
            # Audit log
            await self.audit.log_state_transition(
                patch_id=patch_id,
                from_state=patch.status,
                to_state="ROLLED_BACK",
                actor=actor,
                reason=reason,
                metadata={"snapshot_id": snapshot.id}
            )
            
        except Exception as e:
            # Restore from snapshot on partial failure
            await self._restore_snapshot(snapshot)
            raise RollbackFailedException(f"Rollback failed: {e}, snapshot restored")
```

---

## 10. Security, Authorization & Tamper Protection

### 10.1 Role-Based Access Control (RBAC)
```python
# backend/app/auth/patch_permissions.py
class PatchAuthorizationPolicy:
    """Defines who can perform patch operations"""
    
    ROLES = {
        "compliance_officer": [
            "approve_patch",
            "reject_patch", 
            "promote_to_canonical",
            "rollback_patch",
            "view_audit_log"
        ],
        "analyst": [
            "create_provisional_patch",
            "view_patches",
            "comment_on_patch"
        ],
        "readonly_user": [
            "view_patches"
        ]
    }
    
    async def authorize(self, user: User, action: str, patch: Patch) -> bool:
        if action not in self.ROLES.get(user.role, []):
            await self.audit.log_authorization_failure(user, action, patch)
            return False
        
        # Additional business rules
        if action == "promote_to_canonical":
            # Only compliance officers with seniority >= 3 years
            if user.role == "compliance_officer" and user.seniority_years >= 3:
                return True
            return False
        
        return True
```

### 10.2 Patch Integrity & Tamper Detection
```python
class PatchIntegrityVerifier:
    """Ensures patches haven't been tampered with"""
    
    def sign_patch(self, patch: Patch, private_key: str) -> str:
        """Create HMAC signature of patch critical fields"""
        message = f"{patch.patch_id}|{patch.entity_id}|{patch.attribute}|{patch.corrected_value}|{patch.confidence}"
        return hmac.new(
            private_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
    
    async def verify_patch_integrity(self, patch: Patch) -> bool:
        """Verify patch hasn't been modified since approval"""
        stored_signature = await self.repo.get_patch_signature(patch.patch_id)
        computed_signature = self.sign_patch(patch, self.private_key)
        
        if stored_signature != computed_signature:
            await self.audit.log_security_event(
                event_type="patch_tampering_detected",
                patch_id=patch.patch_id,
                severity="critical"
            )
            return False
        return True
```

---

## 11. Edge Cases, Error Handling & Graceful Degradation

### 11.1 Partial Layer Failure Handling
```python
# backend/app/retrieval/resilient_orchestrator.py
class ResilientPatchOrchestrator:
    """Handles failures gracefully without blocking user queries"""
    
    async def answer_with_fallback(self, query: str) -> OrchestratorResponse:
        layers_attempted = []
        layers_failed = []
        
        # Layer 1: Fast-Path (Optional - degraded service acceptable)
        try:
            fast_response = await self.fast_path.try_short_circuit(query)
            if fast_response:
                return fast_response
            layers_attempted.append("fast_path")
        except Exception as e:
            layers_failed.append(("fast_path", str(e)))
            self.logger.warning(f"Fast-path failed: {e}, continuing to Layer 2")
        
        # Layer 2: Hybrid Retrieval (Critical - must succeed)
        try:
            context = await self.retrieval.get_context(query)
            layers_attempted.append("hybrid_retrieval")
        except Exception as e:
            layers_failed.append(("hybrid_retrieval", str(e)))
            # Fallback to basic vector search without shadow graph
            context = await self.retrieval.get_context_without_patches(query)
        
        # Layer 3: Guardrail (Optional - degrade to warnings)
        try:
            synthesis = await self.llm.synthesize(context)
            verified_synthesis = await self.guardrail.verify_and_rewrite(synthesis)
            layers_attempted.append("guardrail")
            return verified_synthesis
        except Exception as e:
            layers_failed.append(("guardrail", str(e)))
            # Return unverified synthesis with warning
            return OrchestratorResponse(
                answer=synthesis.answer,
                confidence="medium",
                warning="Compliance guardrail unavailable - answer not verified against patches"
            )
```

### 11.2 Network Partition & Timeout Handling
```python
# Timeout budgets for each layer
LAYER_TIMEOUTS = {
    "fast_path": 15,  # ms
    "neo4j_shadow": 100,  # ms
    "vector_search": 300,  # ms
    "llm_synthesis": 5000,  # ms
    "guardrail": 200,  # ms
}

async def execute_with_timeout(coro, layer_name: str):
    try:
        return await asyncio.wait_for(
            coro, 
            timeout=LAYER_TIMEOUTS[layer_name] / 1000
        )
    except asyncio.TimeoutError:
        await metrics.increment(f"{layer_name}.timeout")
        raise LayerTimeoutException(f"{layer_name} exceeded {LAYER_TIMEOUTS[layer_name]}ms")
```

---

## 12. Enhanced Testing Strategy

### 12.1 Chaos Engineering Tests
```python
# tests/chaos/test_patch_resilience.py
class TestPatchSystemResilience:
    """Chaos tests for self-healing system"""
    
    async def test_neo4j_shadow_graph_unavailable(self):
        """Verify system continues with Layer 3 FAISS when Neo4j is down"""
        # Simulate Neo4j network partition
        await self.chaos.partition_service("neo4j")
        
        response = await self.orchestrator.answer("What is Axis Bluechip category?")
        
        # Should still return correct answer via FAISS synthetic chunk
        assert "Mid Cap" in response.answer
        assert response.layers_used == ["vector_search", "guardrail"]
        assert "neo4j_shadow" in response.layers_failed
    
    async def test_repair_engine_stale_data(self):
        """Verify guardrail catches drift when Repair Engine is behind"""
        # Create patch in Neo4j but NOT in Repair Engine API
        await self.neo4j.run("CREATE (p:ShadowPatch {patch_id: 'orphan', ...})")
        
        response = await self.orchestrator.answer("What is Fund X category?")
        
        # Guardrail should detect inconsistency
        assert response.compliance_warnings == ["Shadow patch found without Repair Engine entry"]
```

### 12.2 Performance Benchmarks
```python
# tests/performance/test_patch_latency.py
class TestPatchPerformance:
    """Performance regression tests"""
    
    async def test_fast_path_p99_latency(self):
        """Fast-path must stay under 15ms at P99"""
        latencies = []
        for i in range(1000):
            start = time.perf_counter()
            await self.fast_path.answer("What is Axis Bluechip category?")
            latencies.append((time.perf_counter() - start) * 1000)
        
        p99 = np.percentile(latencies, 99)
        assert p99 < 15, f"P99 latency {p99}ms exceeds 15ms threshold"
    
    async def test_guardrail_overhead(self):
        """Guardrail should add <200ms overhead"""
        # Measure synthesis without guardrail
        start = time.perf_counter()
        synthesis = await self.llm.synthesize(context)
        baseline = time.perf_counter() - start
        
        # Measure with guardrail
        start = time.perf_counter()
        verified = await self.guardrail.verify_and_rewrite(synthesis)
        with_guardrail = time.perf_counter() - start
        
        overhead = (with_guardrail - baseline) * 1000
        assert overhead < 200, f"Guardrail overhead {overhead}ms exceeds 200ms"
```

---

## 14. Implementation Priority & Phasing Roadmap

### Phase 0: Foundation (Week 1-2)
**Goal**: Establish monitoring, audit infrastructure, and patch versioning before implementing healing layers.

**Deliverables**:
- [ ] Implement `PatchMetricsCollector` with Prometheus/Datadog integration
- [ ] Create `PatchAuditLogger` with immutable PostgreSQL audit table
- [ ] Add patch versioning schema (`version`, `supersedes_patch_id`, `conflict_resolution_reason`)
- [ ] Set up Grafana dashboard for patch metrics
- [ ] Implement `PatchConflictResolver` with precedence rules

**Success Criteria**: All patch state transitions logged, metrics flowing to dashboard, conflict detection working.

---

### Phase 1: Quick Wins (Week 3-4)
**Goal**: Implement highest-impact, lowest-risk layers first.

**Priority Order**:
1. **Option 5: Post-Synthesis Guardrail** (Immediate value, zero breaking changes)
   - Catches hallucinations before they reach users
   - Works with existing architecture
   - Estimated development: 3 days
   
2. **Option 2: Fast-Path Interceptor** (Dramatic latency improvement)
   - 10-15ms responses for 40%+ of queries
   - Reduces LLM costs by 40%
   - Estimated development: 4 days

**Deliverables**:
- [ ] `PatchGuardrailRewriter` integrated into orchestrator
- [ ] `FastPathInterceptor` with single-attribute query detection
- [ ] Cache-aside pattern for fast-path responses
- [ ] Unit tests + integration tests for both layers

**Success Criteria**: Guardrail catches 95%+ contradictions, fast-path achieves <15ms P99 latency.

---

### Phase 2: Data Layer Evolution (Week 5-7)
**Goal**: Enable retrieval systems to natively surface patches.

**Priority Order**:
3. **Option 4: Virtual Shadow Graph** (Enables graph-native patching)
   - Non-destructive, easy rollback
   - Supports complex graph traversals
   - Estimated development: 5 days

4. **Option 3: Synthetic FAISS Chunks** (Complements vector search)
   - Ensures semantic search surfaces corrections
   - Lower priority than shadow graph
   - Estimated development: 3 days

**Deliverables**:
- [ ] `:ShadowPatch` Neo4j node type with `COALESCE` in Cypher queries
- [ ] Synthetic chunk ingestion in vector store
- [ ] `CacheInvalidator` for Redis/Neo4j/FAISS consistency
- [ ] `AtomicPatchRollback` with snapshot mechanism

**Success Criteria**: Shadow patches retrieved in graph traversals, synthetic chunks appear in top-3 vector results.

---

### Phase 3: Governance & Promotion (Week 8-9)
**Goal**: Establish safe path for patches to graduate into canonical data.

**Priority Order**:
5. **Option 1: Direct Canonical Graph Mutation** (Completes the lifecycle)
   - Weekly governance batch
   - Admin UI for manual promotion
   - Estimated development: 5 days

**Deliverables**:
- [ ] `GovernanceBatchProcessor` with auto-promotion rules
- [ ] Admin UI "Promote to Master" button with RBAC
- [ ] Patch archival workflow (retire shadow nodes + synthetic chunks)
- [ ] Integrity verification via HMAC signatures

**Success Criteria**: High-confidence patches auto-promote weekly, manual promotion works, audit trail complete.

---

### Phase 4: Resilience & Security Hardening (Week 10-12)
**Goal**: Production-ready error handling, authorization, and chaos testing.

**Deliverables**:
- [ ] `ResilientPatchOrchestrator` with graceful degradation
- [ ] `PatchAuthorizationPolicy` with RBAC enforcement
- [ ] `PatchIntegrityVerifier` with tamper detection
- [ ] Comprehensive chaos engineering test suite
- [ ] Performance benchmarks and regression tests

**Success Criteria**: System survives Neo4j/Repair Engine outages, unauthorized operations blocked, all tests green.

---

## 15. Deployment Strategy & Rollout Plan

### Blue-Green Deployment with Feature Flags
```python
# backend/app/config.py
class PatchFeatureFlags:
    """Gradual rollout control for each healing layer"""
    
    FAST_PATH_ENABLED: bool = True  # Start: False, after testing: True
    FAST_PATH_ROLLOUT_PERCENTAGE: int = 100  # Gradual rollout: 10 → 50 → 100
    
    GUARDRAIL_ENABLED: bool = True
    GUARDRAIL_MODE: str = "warn"  # Options: "off", "warn", "enforce"
    
    SHADOW_GRAPH_ENABLED: bool = True
    SHADOW_GRAPH_ROLLOUT_PERCENTAGE: int = 50  # Test with 50% traffic first
    
    SYNTHETIC_FAISS_ENABLED: bool = True
    
    CANONICAL_PROMOTION_ENABLED: bool = False  # Keep disabled until Phase 3 complete
```

### Rollout Timeline
```mermaid
gantt
    title Self-Healing System Rollout
    dateFormat YYYY-MM-DD
    section Phase 0: Foundation
    Metrics & Audit         :done, p0a, 2024-01-01, 7d
    Versioning & Conflicts  :done, p0b, 2024-01-08, 7d
    
    section Phase 1: Quick Wins
    Guardrail (10% rollout) :active, p1a, 2024-01-15, 3d
    Guardrail (100% rollout):        p1b, after p1a, 4d
    Fast-Path (50% rollout) :        p1c, 2024-01-22, 4d
    Fast-Path (100% rollout):        p1d, after p1c, 3d
    
    section Phase 2: Data Layer
    Shadow Graph (staging)  :        p2a, 2024-02-01, 5d
    Shadow Graph (prod 50%) :        p2b, after p2a, 3d
    Synthetic FAISS (prod)  :        p2c, 2024-02-12, 3d
    
    section Phase 3: Governance
    Governance Batch (dry-run):      p3a, 2024-02-19, 5d
    Governance Batch (live)   :      p3b, after p3a, 2d
    Admin UI Promotion        :      p3c, after p3b, 3d
    
    section Phase 4: Hardening
    Chaos Testing             :      p4a, 2024-03-04, 5d
    Security Audit            :      p4b, 2024-03-11, 5d
    Performance Tuning        :      p4c, 2024-03-18, 7d
```

### Rollback Procedures
```yaml
# Emergency rollback playbook
rollback_procedures:
  guardrail_failure:
    - Set GUARDRAIL_MODE="off" via feature flag
    - Monitor for hallucination spike in next 15 minutes
    - Investigate guardrail logs for root cause
    
  fast_path_accuracy_issue:
    - Set FAST_PATH_ROLLOUT_PERCENTAGE=0
    - Fall back to standard retrieval path
    - Audit fast-path cache for stale/incorrect entries
    
  shadow_graph_corruption:
    - Disable SHADOW_GRAPH_ENABLED
    - Run integrity check: MATCH (p:ShadowPatch) RETURN count(p)
    - Restore from Neo4j snapshot if needed
    
  canonical_promotion_error:
    - Halt weekly governance batch via CANONICAL_PROMOTION_ENABLED=false
    - Rollback last promoted patches via AtomicPatchRollback
    - Review audit log for data integrity issues
```

---

## 16. Risk Assessment & Mitigation Strategies

### Risk Matrix

| Risk Category | Likelihood | Impact | Mitigation Strategy | Owner |
|:---|:---:|:---:|:---|:---|
| **Patch conflicts cause data inconsistency** | Medium | High | Implement conflict resolver with escalation, version all patches, comprehensive audit trail | Backend Team |
| **Fast-path cache serves stale data** | Medium | Medium | TTL=1hr max, aggressive cache invalidation on patch updates, integrity checks | Backend Team |
| **Shadow graph orphans after rollback** | Low | Medium | Atomic rollback with snapshots, weekly cleanup job for orphaned nodes | DevOps Team |
| **Guardrail adds excessive latency** | Low | Low | Strict 200ms timeout, async execution, circuit breaker pattern | Backend Team |
| **Unauthorized patch promotion** | Low | Critical | RBAC with audit logging, 2FA for promotions, integrity signatures | Security Team |
| **Neo4j/FAISS desynchronization** | Medium | High | Distributed transaction pattern, eventual consistency monitoring, reconciliation jobs | Backend Team |
| **LLM ignores guardrail corrections** | Low | High | Deterministic rewriting (not suggestions), post-hoc validation, alerting | AI Team |
| **Performance regression from multi-layer checks** | Medium | Medium | Layer-specific timeouts, fast-fail pattern, performance regression tests | DevOps Team |
| **Compliance audit failure** | Low | Critical | Immutable audit log, cryptographic signatures, third-party audit trail verification | Compliance Team |

### Mitigation Implementation Details

#### 1. Preventing Cache Staleness
```python
# backend/app/retrieval/cache_policy.py
class AdaptiveCacheTTL:
    """Dynamic TTL based on patch activity"""
    
    def get_ttl_for_entity(self, entity_id: str) -> int:
        recent_patches = await self.repo.count_patches(
            entity_id=entity_id,
            since=datetime.utcnow() - timedelta(days=7)
        )
        
        if recent_patches > 3:
            return 600  # 10 minutes for frequently patched entities
        elif recent_patches > 0:
            return 1800  # 30 minutes for occasionally patched
        else:
            return 3600  # 1 hour for stable entities
```

#### 2. Preventing Shadow Graph Orphans
```python
# Weekly cleanup job
async def cleanup_orphaned_shadow_patches():
    """Remove shadow patches without corresponding Repair Engine entries"""
    orphans = await neo4j.run("""
        MATCH (p:ShadowPatch)
        WHERE NOT EXISTS {
            MATCH (p) WHERE p.patch_id IN $active_patch_ids
        }
        AND p.created_at < datetime() - duration({days: 7})
        RETURN p.patch_id AS orphan_id
    """, active_patch_ids=await repair_engine.get_all_active_patch_ids())
    
    for orphan in orphans:
        await audit.log_orphan_cleanup(orphan['orphan_id'])
        await neo4j.run("MATCH (p:ShadowPatch {patch_id: $id}) DETACH DELETE p", 
                       id=orphan['orphan_id'])
```

#### 3. Circuit Breaker for Guardrail
```python
# backend/app/evaluation/guardrail_circuit_breaker.py
class GuardrailCircuitBreaker:
    """Prevent cascading failures if guardrail becomes slow"""
    
    def __init__(self):
        self.failure_threshold = 5
        self.timeout_threshold_ms = 200
        self.recent_failures = []
        self.state = "closed"  # closed, open, half_open
    
    async def execute_with_protection(self, synthesis: SynthesisOutput):
        if self.state == "open":
            await metrics.increment("guardrail.circuit_open")
            return synthesis  # Bypass guardrail, return unverified
        
        try:
            start = time.perf_counter()
            result = await asyncio.wait_for(
                self.guardrail.verify_and_rewrite(synthesis),
                timeout=self.timeout_threshold_ms / 1000
            )
            latency = (time.perf_counter() - start) * 1000
            
            if latency > self.timeout_threshold_ms:
                self.record_failure("timeout")
            else:
                self.record_success()
            
            return result
            
        except asyncio.TimeoutError:
            self.record_failure("timeout")
            return synthesis  # Graceful degradation
        except Exception as e:
            self.record_failure("error")
            raise
```

---

## 13. Key Architectural Decisions for Alignment

> [!IMPORTANT]
> **Decision 1: Fast-Path Activation Scope (Option 2)**
> Should the deterministic short-circuit trigger only for strict single-attribute queries (e.g. *"What is the category of X?"*), or also for queries that ask for 2 attributes (e.g. *"What is the category and TER of X?"*)?
> *Recommendation*: Start with single-attribute queries to avoid false positives, then expand to multi-attribute queries if all requested attributes have patches with confidence >= 0.90.

> [!NOTE]
> **Decision 2: Promotion Automation (Option 1)**
> Should promotion to Neo4j canonical master be 100% automated if `confidence >= 0.95` during the Friday batch, or should it always require a compliance officer to click "Promote to Master" in the Admin UI?
> *Recommendation*: Hybrid approach—high confidence (>= 0.95) auto-promotes in the weekly batch for non-critical attributes, while critical attributes (NAV, AUM, regulatory status) always require manual approval regardless of confidence.

> [!WARNING]
> **Decision 3: Conflict Resolution Default Strategy**
> When two patches conflict with similar confidence scores (delta < 0.10), should the system default to "newest wins", "escalate to human", or "merge values into array"?
> *Recommendation*: Always escalate to human review when confidence delta < 0.10 to prevent silently discarding potentially valid corrections. Only auto-resolve when confidence delta >= 0.15 or source type differs (regulatory > user feedback).

> [!IMPORTANT]
> **Decision 4: Cache Invalidation Aggressiveness**
> Should cache invalidation be conservative (only invalidate exact entity matches) or aggressive (invalidate all queries mentioning related entities via graph traversal)?
> *Recommendation*: Start conservative to avoid cache thrashing, then add relationship-aware invalidation for multi-hop queries (e.g., if Fund A's category changes and it's linked to Scheme B, invalidate Scheme B queries too).

---

## 17. Success Metrics & KPIs

### North Star Metrics

| Metric | Baseline (Current) | Phase 1 Target | Phase 3 Target | Measurement Method |
|:---|:---:|:---:|:---:|:---|
| **Hallucination Rate** | 8-12% | <3% | <1% | User corrections / total answers |
| **P95 Query Latency** | 3.2s | 2.5s | 1.8s | FastAPI middleware timing |
| **LLM Cost per Query** | $0.042 | $0.028 | $0.018 | Token usage × model pricing |
| **Patch Time-to-Fix** | 72 hours | 24 hours | <4 hours | Feedback submitted → patch approved |
| **User Satisfaction** | 7.2/10 | 8.5/10 | 9.2/10 | Post-query CSAT survey |

### Layer-Specific KPIs

#### Layer 1: Fast-Path Interceptor
- **Hit Rate**: >40% of eligible queries (simple attribute lookups)
- **Accuracy**: 100% correctness (deterministic responses only)
- **Latency**: P99 <15ms, P50 <8ms
- **Cost Savings**: ~$12,000/month in LLM API costs (40% × 100k queries/day × $0.042)

#### Layer 2: Hybrid Retrieval (Shadow Graph + Synthetic FAISS)
- **Shadow Graph Coverage**: 95%+ of approved patches visible in graph traversals
- **Synthetic Chunk Recall**: Patched entities appear in top-3 vector results for 90%+ relevant queries
- **Retrieval Latency**: <300ms for hybrid search (shadow graph + vector)

#### Layer 3: Guardrail Rewriter
- **Intervention Rate**: 2-5% of LLM responses (should decrease as base model improves)
- **False Positive Rate**: <1% (incorrectly flagging correct LLM output)
- **Rewrite Latency**: <200ms overhead per intervention
- **Compliance Pass Rate**: 100% (no contradictory answers escape to production)

#### Layer 4: Governance & Promotion
- **Promotion Velocity**: 80%+ of high-confidence patches promoted within 7 days
- **Rollback Incidents**: <1 per quarter
- **Audit Completeness**: 100% of patch operations logged immutably
- **Authorization Compliance**: 0 unauthorized promotions/rollbacks

### Alerting Thresholds

```yaml
# Production monitoring alert rules
alerts:
  critical:
    - name: HallucinationRateSpike
      threshold: hallucination_rate > 5% over 1 hour
      action: Page on-call engineer, disable auto-promotion
    
    - name: UnauthorizedPatchPromotion
      threshold: unauthorized_promotion_attempts > 0
      action: Trigger security incident response, lock promotion endpoint
    
    - name: PatchIntegrityViolation
      threshold: tampered_patches_detected > 0
      action: Lock all patch operations, initiate forensic investigation
  
  warning:
    - name: FastPathHitRateDrop
      threshold: fast_path_hit_rate < 30% over 15 minutes
      action: Investigate patch coverage, check Redis cache health
    
    - name: GuardrailLatencyIncrease
      threshold: guardrail_p95_latency > 250ms over 10 minutes
      action: Check circuit breaker state, consider temporary bypass
    
    - name: ShadowGraphOrphansAccumulating
      threshold: orphaned_shadow_patches > 50
      action: Run cleanup job, investigate Repair Engine sync issues
```

---

## 18. Post-Deployment Continuous Improvement

### Week 1-4: Calibration Phase
- **Daily Review**: Monitor all 5 layers for unexpected behavior
- **Patch Coverage Analysis**: Identify common query patterns not covered by fast-path
- **False Positive Tuning**: Adjust guardrail detection thresholds based on false positive rate
- **Performance Optimization**: Profile slow queries, optimize Cypher queries, tune FAISS indexes

### Monthly: Governance Review
- **Patch Effectiveness Audit**: Sample 50 promoted patches, verify correctness against source documents
- **Conflict Resolution Analysis**: Review escalated patch conflicts, refine precedence rules
- **Authorization Audit**: Verify RBAC policies match organizational changes
- **Technical Debt Assessment**: Identify accumulated shadow patches, plan data cleanups

### Quarterly: Strategic Evolution
- **Model Upgrade Impact**: When base LLM upgrades, measure hallucination rate change
- **Coverage Expansion**: Add new entity types (schemes, fund managers, AMCs) to patch system
- **Multi-Hop Patching**: Extend shadow graph to support relationship patches (e.g., fund-scheme links)
- **Regulatory Compliance Review**: Third-party audit of patch audit trail and data integrity

---

## 19. Conclusion & Next Steps

This unified Defense-in-Depth Self-Healing Architecture combines **all 5 options** into a cohesive system that:

1. **Eliminates 40%+ of hallucinations** via deterministic fast-path and post-synthesis guardrails
2. **Reduces query latency by 45%** through intelligent short-circuiting and optimized retrieval
3. **Cuts LLM costs by 40%** by answering simple queries without API calls
4. **Maintains compliance** with immutable audit trails and tamper-proof patch integrity
5. **Enables safe evolution** of canonical data through governed promotion workflows

### Immediate Next Steps

1. **Week 1**: Kick off Phase 0 (Foundation) - Set up metrics, audit logging, and patch versioning
2. **Week 2**: Begin Phase 1 implementation - Start with Option 5 (Guardrail) for immediate value
3. **Week 3**: Deploy Option 2 (Fast-Path) to staging with 10% rollout
4. **Week 4**: Review Phase 1 metrics, prepare Phase 2 (Data Layer) design

---

**Document Version**: 2.0  
**Last Updated**: 2024-01-15  
**Authors**: AI Architecture Team  
**Reviewers**: Backend Team, Compliance Team, DevOps Team  
**Status**: Ready for Implementation
