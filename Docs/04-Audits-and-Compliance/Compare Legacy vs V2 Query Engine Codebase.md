# Detailed Prompt: Compare Legacy vs V2 Query Engine Codebase

## Objective
Conduct a comprehensive architectural and implementation-level comparison of the **legacy query engine** (`app/engine/retrieval.py`) and the **v2 query engine** (`app/retrieval/orchestrator.py`), with focus on execution flow, data structures, component interactions, and design patterns. Produce a structured analysis suitable for migration planning and technical decision-making.

---

## Scope of Comparison

### 1. **Entry Point & Architecture**

**Legacy Engine:**
- Analyze the entry points: `traditional_rag(query, store, ...)` and `hybrid_graphrag(query, store, ...)`
- Document the procedural execution flow—how parameters flow through each stage
- Identify all nested conditionals and branching logic
- List all external dependencies (FAISS store, Neo4j, LLM client, NER pipeline, etc.)

**V2 Engine:**
- Analyze the entry point: `RetrievalOrchestrator.answer(query, top_k, ...)`
- Document the dependency-injected constructor—what components are injected and why
- Identify how v2 differs in initialization vs. runtime execution
- List all external dependencies and how they differ from legacy

**Comparison Output:**
- Side-by-side pseudocode showing entry point differences
- Dependency diagram (visual or text) for each engine
- Explain the architectural rationale for each design choice

---

### 2. **Query Execution Pipeline (Stages & Phases)**

**Legacy Engine:**
- Map every stage of `hybrid_graphrag()`:
  - Intent cache lookup (fingerprint probe + semantic lookup)
  - NER processing (Layer A + Layer B)
  - Query classification
  - Graph traversal with fallback
  - Vector retrieval with reranking
  - Entity resolution & enrichment (Cypher generation for aggregation)
  - Context assembly
  - LLM synthesis
  - Cross-validation & caching
- Document the decision points that determine which path is taken (e.g., "if graph has strong signal, bypass vector")
- Identify early-exit conditions (cache hits, sufficient graph signal)

**V2 Engine:**
- Map every phase in the `answer()` method:
  - Intent classification
  - Entity resolution
  - Plan execution (simple vs. complex branching)
  - Graph traversal
  - Adaptive retrieval (round 2 relaxation, if present)
  - Context assembly with correction patches
  - Synthesis
  - Validation & caching
- Document the `QueryPhase` abstraction—how phases are registered and executed
- Identify the execution pipeline's early-exit conditions and dependency graph

**Comparison Output:**
- Sequential flow diagram for legacy (showing all decision points)
- Phase pipeline diagram for v2 (showing dependencies and early exits)
- Table mapping legacy stages to v2 phases (with notes on logic differences)
- Highlight which stages/phases are new in v2 vs. removed from legacy

---

### 3. **Core Data Structures & Models**

**Legacy Engine:**
- Trace through `traditional_rag()` and identify the data passed between stages:
  - What does `store.retrieve()` return? (structure, fields)
  - What does NER pipeline return?
  - What structure is passed to LLM?
  - What does the final `telemetry_breakdown` contain?
- List all intermediate representations and transformations
- Document telemetry & trace object structure

**V2 Engine:**
- Trace through `answer()` and identify data passed between phases:
  - What does `intent_classifier.classify()` return?
  - What does `resolver.resolve()` return?
  - What does `traversal.traverse()` return?
  - What does `assembler.assemble()` return?
  - What does `OrchestratorResponse` wrap?
- List all intermediate representations and transformations
- Document metrics, trace, and response structure

**Comparison Output:**
- Schema comparison table: legacy vs. v2 for each major data structure
- JSON example outputs for identical query in both engines
- Document field mapping (e.g., "legacy's `telemetry_breakdown.latency_llm_generation_ms`" → "v2's `trace.generation_ms`")

---

### 4. **Query Classification & Routing**

**Legacy Engine:**
- How does `query_classifier.classify_query()` determine query type?
- How does classification drive branching (which enrichment path is taken)?
- For aggregation queries: trace the Cypher generation fallback logic
- For comparison queries: how are queries branched?

**V2 Engine:**
- How does intent classification work in v2?
- How does `planner.get_planner()` decompose complex queries?
- How are execution branches merged (dedup + re-rank)?
- What happens if plan is simple vs. complex?

**Comparison Output:**
- Decision tree showing legacy's classification → enrichment path
- Execution plan structure in v2 (pseudocode or JSON example)
- Comparison table: query types handled and branching strategy

---

### 5. **Graph & Vector Retrieval Integration**

**Legacy Engine:**
- When does graph traversal run? (always, or conditionally?)
- What is the "fallback" strategy in `graph_store.get_subgraph_for_query_with_fallback()`?
- When is vector retrieval bypassed? (conditions: graph has ≥3 edges + query type allows)
- How are graph results and vector results merged for synthesis?

**V2 Engine:**
- When does graph traversal run? (always, or conditionally?)
- What is the traversal strategy in `traversal.traverse()`?
- How does adaptive retrieval work? (round 2 relaxation, entity expansion)
- How are results from parallel graph + vector pipelines merged?
- What role does entity resolution play in refinement?

**Comparison Output:**
- Side-by-side pseudocode for graph traversal triggering logic
- Fallback strategy comparison (legacy vs. v2)
- Vector bypass conditions (legacy explicit bypass vs. v2's plan-based approach)
- Merging/assembly strategy for graph + vector results

---

### 6. **LLM Synthesis & Prompt Engineering**

**Legacy Engine:**
- What is `SYSTEM_SYNTHESIS_PROMPT`? (document the full system prompt)
- How is the user prompt constructed? (context assembly order, graph inclusion criteria)
- Which context is included based on query type? (traditional RAG vs. ContextGraph)
- How are streaming and non-streaming calls handled?

**V2 Engine:**
- What is the synthesis prompt in v2?
- How does context assembly differ? (order, inclusion criteria, correction patches)
- How does v2's synthesizer construct prompts vs. legacy's inline approach?
- Does v2 have different prompt templates for different query types?

**Comparison Output:**
- Document both system prompts (highlight differences)
- Example prompt construction for identical query in both engines
- Note which context is included/excluded by query type

---

### 7. **Microservices Integration & Repair Engine**

**Legacy Engine:**
- Is there any microservices integration? (check for repair client references)
- How are external service calls made (if any)?

**V2 Engine:**
- What is `RepairServiceClient`? (when is it initialized, when called?)
- What does `CircuitBreaker` protect against?
- How are correction patches applied? (HTTP call vs. local fallback)
- What is the error handling strategy?

**Comparison Output:**
- Architecture diagram showing microservices integration in v2 only
- Document the repair service endpoint and API contract
- Circuit breaker configuration and failure handling

---

### 8. **Caching Strategy (Intent Cache & Semantic Cache)**

**Legacy Engine:**
- How does intent cache work? (fingerprint O(1) probe vs. semantic lookup)
- What triggers a cache hit? (token savings calculation)
- Cache key strategy (query hash, domain intent, etc.)
- What is stored in cache? (answer, provenance, graph nodes/edges)

**V2 Engine:**
- How is semantic cache accessed in v2?
- What is the cache hit strategy? (same as legacy or different?)
- What metrics are recorded for cache hits?
- Early-exit behavior when cache hits

**Comparison Output:**
- Cache flow diagram for both engines
- Cache key generation strategy (legacy vs. v2)
- Document cache storage format and what's stored

---

### 9. **Telemetry, Metrics & Cross-Validation**

**Legacy Engine:**
- What is tracked in `telemetry_breakdown`? (all latencies, token counts, badges)
- How does `cross_validate_answer()` work? (what badge is generated?)
- What audit log is written? (format, contents, where stored)

**V2 Engine:**
- What is tracked in `QueryTrace` and `QueryMetrics`?
- How does v2 validate answers and generate badges?
- What evidence tracking happens in `query_evidence_recorder.py`?
- How does quality assessment work?

**Comparison Output:**
- Telemetry field mapping (legacy field → v2 field)
- Example telemetry_breakdown for identical query in both
- Badge generation criteria comparison
- Evidence tracking schema in v2

---

### 10. **Multi-Turn Conversation & Context Handling**

**Legacy Engine:**
- How is conversation history compressed? (`compress_history()`)
- How are coreferences resolved? (`resolve_coreferences()`)
- What is the max history turns window?
- Where in the pipeline does history get injected?

**V2 Engine:**
- Does v2 handle multi-turn differently?
- Is there equivalent coreference resolution?
- How is history injected into the synthesis prompt?

**Comparison Output:**
- Multi-turn flow comparison (legacy vs. v2)
- Document history compression and coreference resolution logic

---

### 11. **Error Handling & Fallback Strategies**

**Legacy Engine:**
- What happens if NER fails?
- What happens if graph traversal returns empty?
- What happens if Cypher generation fails? (fallback to deterministic aggregate)
- What happens if LLM call fails?
- What happens if cache lookup fails?

**V2 Engine:**
- What are the error handling boundaries in each phase?
- What fallback strategies exist? (e.g., if round 1 retrieval insufficient, trigger round 2)
- What happens if external service (repair client) fails? (circuit breaker behavior)

**Comparison Output:**
- Error handling flow chart for both engines
- Fallback strategy decision tree

---

### 12. **API Routing & Feature Flags**

**Legacy & V2:**
- How does the `run_query()` endpoint route between engines?
- What is the `query_engine` configuration? (values: legacy, v2, canary, shadow)
- Canary deployment strategy (percentage-based bucketing)
- Shadow mode execution (what happens to shadow results?)

**Comparison Output:**
- Routing decision tree based on engine configuration
- Canary deployment probability calculation
- Shadow execution flow

---

### 13. **Performance & Scalability Considerations**

**Legacy Engine:**
- Are vector + graph retrievals parallelized? (check for concurrent.futures usage)
- What are the bottlenecks? (NER, Cypher generation, LLM, graph traversal, reranking)
- Adaptive retrieval: when is round 2 triggered?

**V2 Engine:**
- Are phases parallelized? (check async/await patterns)
- What are the bottlenecks?
- How does plan decomposition improve performance for complex queries?
- What caching strategies improve latency?

**Comparison Output:**
- Performance profile: latency breakdown for identical query
- Parallelization strategy comparison
- Scalability improvements in v2

---

### 14. **Code Quality & Maintainability**

**Legacy Engine:**
- Code organization (single file vs. multiple modules)
- Function complexity (lines of code, nested conditionals, cyclomatic complexity)
- Test coverage (identify test files and coverage gaps)
- Documentation (docstrings, comments, type hints)

**V2 Engine:**
- Code organization (modular phase-based architecture)
- Class/method complexity
- Test coverage
- Documentation

**Comparison Output:**
- Maintainability metrics (SLOC, cyclomatic complexity, etc.)
- Documentation coverage comparison
- Test organization and gaps

---

## Deliverables

1. **Execution Flow Comparison**: Detailed narrative with pseudocode examples showing stage-by-stage differences
2. **Data Structure Mapping**: Schema comparison with JSON examples for both engines on identical queries
3. **Architecture Diagram**: Visual (ASCII or Mermaid) showing component interactions and dependencies for both
4. **Decision Point Matrix**: All branching conditions (query type, graph signal strength, cache hits, etc.) and how v2 differs
5. **Configuration & Routing Table**: How queries are routed to legacy vs. v2, including canary/shadow modes
6. **Migration Checklist**: What functionality from legacy would need porting to v2 for full replacement
7. **Performance Comparison**: Latency breakdown, parallelization strategy, and bottleneck analysis
8. **Testing & Coverage Report**: Test file locations, coverage gaps, and recommendations

---

## Analysis Instructions

### For Each Section:
1. **Read the Code**: Examine the exact implementation (not assumptions)
2. **Trace Execution**: Follow a sample query through both engines
3. **Document Behavior**: Note what happens at each stage for different query types
4. **Highlight Differences**: Explicitly call out architectural/implementation differences
5. **Identify Gaps**: Note missing features or areas that diverge significantly

### Code Files to Analyze:
- **Legacy**: `backend/app/engine/retrieval.py` (primary), `backend/app/engine/intent_cache.py`, `backend/app/engine/context_memory.py`, `backend/app/engine/query_classifier.py`
- **V2**: `backend/app/retrieval/orchestrator.py` (primary), `backend/app/retrieval/query_phases.py`, `backend/app/retrieval/planner.py`, `backend/app/retrieval/adaptive_retriever.py`
- **Shared**: `backend/app/api/routes/query.py`, `backend/app/models/query.py`

### Key Queries to Trace:
1. Simple aggregation: "What is the EBITDA of Adani Enterprises?"
2. Comparison: "Compare Ambuja Cements vs. ACC Limited on ESG scores."
3. Direct lookup: "What are the credit ratings of Adani Power?"
4. Cached query: (Run same query twice to see cache behavior)

---

## Success Criteria

The comparison is complete when:
- [ ] Entry point and architectural differences are clearly documented
- [ ] All execution stages/phases are mapped between engines
- [ ] Data structure transformations are traced and documented
- [ ] Query classification and branching logic is explained
- [ ] Microservices integration differences are noted
- [ ] Telemetry and metrics mapping is complete
- [ ] Error handling and fallback strategies are documented
- [ ] Performance implications are analyzed
- [ ] A migration checklist is provided

