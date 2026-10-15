# AMC Context Engineering Platform - Complete Project Overview

> **Enterprise-grade RAG and Graph Knowledge Platform for Asset Management Companies (AMCs) and SEBI Compliance**

**Project Status:** Production-Ready (V2 Engine Active)  
**Version:** 2.0 (Baseline Corpus 20260814)  
**Last Updated:** October 14, 2026

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Architecture](#project-architecture)
3. [Technology Stack](#technology-stack)
4. [Core Components & Workflow](#core-components--workflow)
5. [Request Flow End-to-End](#request-flow-end-to-end)
6. [Key Features & Innovations](#key-features--innovations)
7. [Code Examples](#code-examples)
8. [Current Implementation Status](#current-implementation-status)
9. [Remaining Work & Roadmap](#remaining-work--roadmap)
10. [Performance Metrics](#performance-metrics)

---

## ⚠️ Important Note About Streamlit

This project includes a **legacy Streamlit application** (`streamlit_app/`) that is maintained for **demonstration and evaluation purposes only**. The Streamlit UI is NOT part of the production architecture and is not actively developed.

**Production Frontend:** React 19 application (`mf-context-engine/`)  
**Legacy/Demo UI:** Streamlit application (`streamlit_app/`)  
**Evaluation Suite:** Various test scripts in `evaluation/` that can run against the Streamlit pipeline for benchmarking

---

## Executive Summary

The **AMC Context Engineering Platform** is a hybrid RAG (Retrieval-Augmented Generation) system that combines **knowledge graphs** (Neo4j), **vector search** (FAISS), and **LLM synthesis** (Groq) to provide accurate, grounded, and compliant answers for Asset Management Company operations and SEBI regulatory queries.

### What Problem Does It Solve?

AMCs need to:
- Query complex regulatory documents (SEBI circulars, fund schemes)
- Compare fund performance, ESG scores, and financial metrics
- Ensure compliance with regulations
- Access corporate intelligence (Adani portfolio companies)
- Get accurate, cited answers from thousands of pages of documents

### How Does It Work?

1. **Ingest documents** → Extract text, chunk intelligently, build knowledge graph
2. **User asks question** → System understands intent, retrieves relevant context
3. **Synthesize answer** → LLM generates response grounded in retrieved evidence
4. **Present results** → Cited, structured answer with source documents and confidence scores

---

## Project Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  React 19 + Vite 8 (mf-context-engine/)                      │  │
│  │  • Chat Interface (Multi-turn conversations)                  │  │
│  │  • Compare Tab (Traditional vs ContextGraph side-by-side)     │  │
│  │  • Analytics Tab (Query metrics and performance)              │  │
│  │  • Admin Panel (User management, document ingestion)          │  │
│  │  • Authentication (Login/logout with session management)      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                               ↓ HTTP/SSE
┌─────────────────────────────────────────────────────────────────────┐
│                         API Layer (FastAPI)                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  main.py - Application Entry Point                           │  │
│  │  • /api/query - Single query endpoint                        │  │
│  │  • /api/chat - Multi-turn conversation                       │  │
│  │  • /api/sessions - Session management                        │  │
│  │  • /api/admin - User & document administration               │  │
│  │  • /api/compliance - Compliance checking & rules             │  │
│  │  • /api/governance - Governance policies & fund schemes      │  │
│  │  • /api/feedback - User feedback collection                  │  │
│  │  • /api/feedback-evaluation - Quality scoring                │  │
│  │  • /api/review-queue - Human review workflow                 │  │
│  │  • /api/audit - Audit trail & compliance logs                │  │
│  │  • /api/taxonomy - Taxonomy navigation & management          │  │
│  │  • /api/graph - Graph traversal & visualization              │  │
│  │  • /api/ingest - Document ingestion queue                    │  │
│  │  • /api/metrics - Performance metrics & monitoring           │  │
│  │  • /api/docs - Document retrieval & serving                  │  │
│  │  • /api/status - Health checks & system status               │  │
│  │  • /files - Direct file serving for PDFs                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Core Processing Layer (V2)                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  RetrievalOrchestrator (backend/app/retrieval/)              │  │
│  │    ├─ SemanticQueryCache   (2-tier: exact + semantic)        │  │
│  │    ├─ IntentClassifier     (Query understanding)             │  │
│  │    ├─ QueryPlanner         (Decomposition for complex Q's)   │  │
│  │    ├─ EntityResolver       (NER + entity linking)            │  │
│  │    ├─ GraphTraversal       (Neo4j relationship navigation)   │  │
│  │    ├─ VectorStore          (FAISS semantic search)           │  │
│  │    ├─ AdaptiveRetriever    (Multi-round quality check)       │  │
│  │    ├─ ContextAssembler     (Token budget management)         │  │
│  │    ├─ Synthesizer          (LLM answer generation)           │  │
│  │    └─ QualityAssessor      (Cross-validation)                │  │
│  │                                                               │  │
│  │  Supporting Modules:                                          │  │
│  │    • HyDE (Hypothetical Document Embeddings)                 │  │
│  │    • Query Phase Pipeline (modular execution stages)         │  │
│  │    • Coverage Queries (multi-dimensional verification)       │  │
│  │    • Query Evidence Recorder (audit trail)                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Additional Services:                                         │  │
│  │    • Feedback Session Manager (passive correction detection) │  │
│  │    • Compliance Rules Engine (SEBI validation)               │  │
│  │    • Task Scheduler (background jobs)                        │  │
│  │    • Ingestion Pipeline (document processing queue)          │  │
│  │    • Metrics Store (performance tracking)                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────────────┐│
│  │   Neo4j        │  │     FAISS      │  │   SQLite (data.db)    ││
│  │  Knowledge     │  │   Vector       │  │  • User accounts      ││
│  │  Graph         │  │   Indexes      │  │  • Chat sessions      ││
│  │  • Entities    │  │  • Embeddings  │  │  • Query evidence     ││
│  │  • Relations   │  │  • Chunks      │  │  • Feedback (passive) ││
│  │  • Taxonomy    │  │  • Metadata    │  │  • Review queue       ││
│  │  • Compliance  │  │  • Namespaces  │  │  • Audit logs         ││
│  │    rules       │  │                │  │  • Metrics            ││
│  │  • Fund        │  │                │  │  • Response quality   ││
│  │    schemes     │  │                │  │                       ││
│  └────────────────┘  └────────────────┘  └───────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend (FastAPI - `backend/`)
| Component | Technology | Purpose |
|-----------|------------|---------|
| **API Framework** | FastAPI 0.115+ | Async HTTP endpoints, auto OpenAPI docs |
| **Language** | Python 3.10+ | Core business logic |
| **Knowledge Graph** | Neo4j 5.24+ | Structured relationships, entity linking |
| **Vector Store** | FAISS (Facebook AI) 1.8+ | Fast similarity search over embeddings |
| **Embeddings** | FastEmbed 0.3+ (BAAI/bge-small-en-v1.5) | Sentence transformers for semantic search |
| **LLM Provider** | Groq 0.9+ | Primary inference provider (configurable) |
| **LLM Models** | openai/gpt-oss-120b (main), openai/gpt-oss-20b (fast) | Answer synthesis and classification |
| **Application DB** | SQLite + SQLAlchemy 2.0+ | User auth, sessions, audit trails, feedback |
| **NER (Layer A)** | spaCy 3.7.4 | Named Entity Recognition (blank pipeline) |
| **NER (Layer B)** | GLiNER 0.2+ | Zero-shot NER for domain entities |
| **Task Queue** | AsyncIO-based queue | Document ingestion processing |
| **Scheduler** | APScheduler 3.10.4+ | Background task scheduling |
| **Testing** | Pytest 8.0+ | Comprehensive test coverage |
| **Performance Testing** | Locust 2.31+ | Load testing and benchmarking |

### Multi-Provider LLM Support (Configurable)
| Provider | Models | Status |
|----------|--------|--------|
| **Groq** (Primary) | openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b | ✅ Active (default) |
| **OpenAI** | gpt-4o | 🔄 Fallback (disabled by default) |
| **Google Gemini** | gemini-2.0-flash, gemini-2.5-pro, gemini-2.5-flash | 🔄 Fallback (disabled by default) |
| **Local (Ollama)** | qwen2.5:3b | 🔄 Fallback (disabled by default) |

**Note:** Multi-provider fallback is controlled via `enable_multi_provider_fallback` and `enable_local_llm_fallback` flags in config.

### Frontend (React Application - `mf-context-engine/`)
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | React 19.2.8 | Modern UI with hooks and context |
| **Build Tool** | Vite 8.2.2 | Fast dev server and optimized builds |
| **Styling** | Vanilla CSS (no Tailwind) | Custom styling without framework |
| **Icons** | Lucide React 1.41.0 | Clean, consistent icon library |
| **Linting** | Oxlint 1.79.0 | Fast JavaScript/JSX linter |
| **Testing** | Playwright 1.64.0 | End-to-end browser testing |

### Legacy Frontend (Streamlit - DEMO ONLY)
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | Streamlit | Legacy demo UI (not for production) |
| **Location** | `streamlit_app/` | Maintained for evaluation/demos only |
| **Status** | **Deprecated** | Use React frontend for production |

### Infrastructure & Deployment
- **Containerization**: Docker + Docker Compose support
- **Deployment**: Uvicorn ASGI server (production-grade)
- **Monitoring**: Prometheus metrics + custom dashboard (`/metrics/dashboard`)
- **Logging**: Structured JSON logs with rotation support
- **Static Serving**: FastAPI serves React SPA directly (no separate web server needed)
- **Health Checks**: Multiple health endpoints (`/health`, `/api/health`, `/api/health/passive-feedback`)
- **AWS Integration**: Secrets Manager support for production credentials
- **Microservices Ready**: Optional microservices mode for feedback-loop and repair-engine (disabled by default)

---

## Core Components & Workflow

### 1. Document Ingestion Pipeline

**Purpose**: Convert PDF documents into searchable knowledge

```
PDF Upload → Text Extraction → Chunking → Embedding → Graph Construction
    ↓            ↓                ↓          ↓              ↓
 Upload API   PyMuPDF/OCR      Smart Split  FastEmbed    Neo4j Schema
```

**Key Files**:
- `backend/app/ingestion/pipeline.py` - Main ingestion orchestrator
- `backend/app/extraction/pdf_processor.py` - PDF text extraction (PyMuPDF + OCR)
- `backend/app/extraction/chunker.py` - Intelligent text chunking
- `backend/app/graph/builder.py` - Knowledge graph construction
- `backend/app/engine/document_extractors.py` - Multi-format document parsing

**Chunking Strategy**:
```python
# Hierarchical chunking with overlap
parent_chunk_size = 1200      # ~4800 characters
parent_overlap = 150          # Context continuity
child_chunk_size = 250        # ~1000 characters (for vector search)
child_overlap = 50            # Granular context preservation
strategy = "semantic"         # Respects sentence boundaries
```

**Smart Extraction** (Rate Limit Optimization):
- Text sufficiency check before vision API calls
- Threshold: 400 characters minimum for local text
- Extraction cache to avoid repeated processing
- Configurable via `SMART_EXTRACTION` flag

### 2. Query Understanding (Intent Classification)

**Purpose**: Understand what the user is asking

```python
# backend/app/retrieval/intent.py
class IntentClassifier:
    async def classify(self, query: str) -> QueryIntent:
        """
        Determines:
        - Query type (entity_lookup, comparison, compliance_check, etc.)
        - Entities mentioned (companies, regulations, metrics)
        - Taxonomy paths (which domain/subdomain)
        - Confidence level
        - Aggregation requirements (if any)
        """
```

**Query Types**:
- `entity_lookup` - "What is Adani Enterprises EBITDA?"
- `comparison` - "Compare Ambuja vs ACC on ESG scores"
- `compliance_check` - "SEBI categorization rules for equity funds"
- `exposure_aggregation` - "Total debt exposure of Adani Group"
- `trend_analysis` - "Revenue growth trend for APSEZ FY23-FY25"
- `general_query` - Broad questions without specific entities

**Namespace Routing** (`orchestrator.py`):
- Queries are automatically routed to relevant namespaces based on keywords
- Namespaces: `sebi_regulation`, `adani_corporate`, `esg_sustainability`, `fund_performance`
- Multi-namespace queries supported for cross-domain questions

### 3. Query Planning & Decomposition

**Purpose**: Break complex queries into parallel execution plans

```python
# backend/app/retrieval/planner.py
class QueryPlanner:
    def plan(self, intent: QueryIntent) -> ExecutionPlan:
        """
        Multi-entity comparison:
        "Compare Ambuja vs ACC" →
          ├─ Task 1: Retrieve Ambuja context
          └─ Task 2: Retrieve ACC context (parallel)
        
        Then merge balanced evidence before synthesis
        """
```

**Execution Plan Types**:
- **Parallel Execution**: Independent sub-tasks run concurrently (e.g., comparing entities)
- **Sequential Execution**: Dependent tasks run in order
- **Tool Selection**: Chooses between graph traversal, vector search, or hybrid based on intent
- **Enabled via**: `ENABLE_QUERY_DECOMPOSITION` flag (default: true)

### 4. Hybrid Retrieval (Graph + Vector)

**Purpose**: Get the most relevant context from multiple sources

```python
# backend/app/retrieval/orchestrator.py
async def retrieve(self, query: str, intent: QueryIntent):
    # Parallel execution (if enabled)
    if config.ENABLE_PARALLELIZATION:
        graph_task = self._traversal.traverse(entities, intent)
        vector_task = self._vector.search(query, top_k=8)
        
        # Wait for both
        graph_facts, vector_chunks = await asyncio.gather(
            graph_task, vector_task
        )
    else:
        # Sequential fallback
        graph_facts = await self._traversal.traverse(entities, intent)
        vector_chunks = await self._vector.search(query, top_k=8)
    
    # Combine and rank
    context = self._assembler.assemble(
        graph_facts=graph_facts,
        vector_chunks=vector_chunks,
        token_budget=4000
    )
    return context
```

**Graph Traversal Example**:
```cypher
// Find related entities and facts
MATCH (e:Issuer {name: 'Adani Enterprises'})
MATCH (e)-[r:HAS_METRIC]->(m:FinancialMetric)
WHERE m.fiscal_year = 'FY25'
RETURN e, r, m
```

**Vector Search**:
```python
# Semantic similarity search with namespace filtering
query_embedding = embedder.embed(query)  # 384-dim vector (BAAI/bge-small-en-v1.5)
hits = faiss_index.search(
    query_embedding, 
    k=8,
    threshold=0.45  # Cosine similarity
)
# Filtered by taxonomy namespace for scoped retrieval
```

**Adaptive Retrieval** (`adaptive_retriever.py`):
- Multi-round quality assessment
- Round 1: Strict threshold (0.45)
- Round 2: Relaxed threshold (0.30) if quality insufficient
- Entity variations generation for improved recall

### 5. Context Assembly & Token Management

**Purpose**: Fit the best evidence within LLM context window

```python
# backend/app/retrieval/context.py
class ContextAssembler:
    def assemble(self, result: RetrievalResult) -> AssembledContext:
        """
        Priority ranking:
        1. High-confidence graph facts (>0.8)
        2. High-score vector chunks (>0.7)
        3. Lower-score content to fill budget
        
        Features:
        - Token budget management (default: 4000)
        - Exposure table generation for financial data
        - Document title resolution
        - Metadata preservation
        - Ensures token count < budget before synthesis
        """
```

**Context Budget Settings**:
- Default token budget: 4000 tokens (from `app.config.context_token_budget`)
- Configurable via environment variable
- Automatic truncation if context exceeds budget
- Prioritizes higher-confidence evidence

### 6. LLM Synthesis

**Purpose**: Generate accurate, grounded answer from context

```python
# backend/app/retrieval/synthesizer.py
class Synthesizer:
    async def synthesize(self, query, context) -> SynthesisOutput:
        prompt = self._build_prompt(query, context)
        
        response = await llm_client.complete(
            prompt=prompt,
            model=settings.llm_model,  # "openai/gpt-oss-120b"
            max_tokens=settings.llm_max_tokens,  # 2048
            temperature=0.1  # Deterministic answers
        )
        
        return self._parse_structured_output(response)
```

**Synthesis Prompt Structure**:
```
System: You are a financial analyst. Answer based ONLY on provided context.
Include inline citations [1], [2] for claims.

Context:
[Graph Facts: 15 structured triplets]
[Vector Chunks: 5 relevant passages with metadata]

Query: {user_question}

Instructions:
- Be precise and factual
- Use markdown tables for structured data
- Cite sources with [N] markers
- State confidence level
- Indicate if information is unavailable
```

**Streaming Support**:
- SSE (Server-Sent Events) for real-time token streaming
- Enabled via `enable_streaming` flag (default: true)
- Configurable rollout percentage for canary deployment
- TTFT (Time To First Token) < 500ms target

### 7. Semantic Caching

**Purpose**: Serve repeated/similar queries instantly

```python
# backend/app/retrieval/cache.py
class SemanticQueryCache:
    async def get(self, query: str, user_id: str = None, tenant_id: str = None) -> Optional[CachedResult]:
        # Stage 1: Exact string match via hash (< 1ms)
        hash_key = self._fingerprint(query, user_id, tenant_id)
        if hash_key in self.exact_cache:
            return self.exact_cache[hash_key]
        
        # Stage 2: Semantic similarity (20-30ms)
        query_emb = self.embedder.embed(query)
        similar = self.faiss_index.search(query_emb, k=1)
        if similar[0].score > 0.92:  # Very similar
            return self.semantic_cache[similar[0].id]
        
        return None  # Cache miss
    
    async def set(self, query: str, result, ttl: int = 3600, user_id: str = None, tenant_id: str = None):
        """Store result in both exact and semantic caches"""
        # Implementation with TTL and eviction
```

**Cache Features**:
- **2-tier caching**: Exact hash lookup + semantic similarity
- **User/tenant scoping**: Cache isolation for multi-tenancy
- **TTL management**: Default 1 hour (configurable)
- **Warmup support**: Pre-load common queries at startup via `ENABLE_SEMANTIC_CACHE_WARMUP`
- **Invalidation**: Automatic on corpus updates via `enable_cache_invalidation_on_ingest`
- **Fingerprinting**: MD5 hash of normalized query + user context

### 8. Feedback Loop & Continuous Improvement

**Purpose**: Learn from user corrections and improve

```python
# backend/app/feedback/session_manager.py
class SessionManager:
    async def register_response(self, session_id, response_id, query):
        """
        Tracks:
        - User queries and responses
        - Follow-up patterns (correction detection)
        - Passive feedback signals (timeouts, reformulations)
        """
```

**Passive Feedback Detection**:
```python
# If user asks similar query within timeout window → potential correction
# Default timeout: 180 seconds (configurable via passive_feedback_timeout)
if self._is_correction_intent(prev_query, current_query):
    await self._feedback_store.record_implicit_correction(
        response_id=prev_response_id,
        correction_query=current_query
    )
```

**Feedback Configuration**:
- `passive_feedback_enabled`: Master switch (default: true)
- `passive_feedback_timeout`: Detection window in seconds (default: 180)
- `passive_feedback_cleanup_interval`: Session cleanup frequency (default: 300s)
- `passive_detection_confidence_min`: Min confidence to flag correction (default: 0.70)
- `passive_sentiment_threshold`: Frustration detection threshold (default: -0.35)
- `feedback_timer_seconds`: Auto-insert timer for implicit feedback (default: 300s)

**Database Schema**:
- SQLite-backed storage (`data.db`)
- Tables: `feedback`, `response_quality`, `audit_log`
- Session tracking and correlation
- Quality scoring per response

---

## Request Flow End-to-End

### Example: User Query Flow

**Query**: *"What is the ESG score of Adani Enterprises?"*

```
1. User Input (Frontend)
   └─> POST /api/query {query: "What is the ESG score..."}

2. Route Handler (query.py)
   └─> Check QUERY_ENGINE setting = "v2"
   └─> Delegate to _run_v2_orchestrator()

3. Cache Check (cache.py)
   └─> Hash query, check exact cache [MISS]
   └─> Embed query, check semantic cache [MISS]

4. Intent Classification (intent.py)
   └─> Query type: "entity_lookup"
   └─> Entities: ["Adani Enterprises"]
   └─> Taxonomy: ["esg_sustainability", "adani_corporate"]
   └─> Confidence: "high"

5. Entity Resolution (resolver.py)
   └─> "Adani Enterprises" → Canonical: "AEL"
   └─> Aliases: ["Adani Enterprises Ltd", "AEL"]
   └─> Entity type: "Issuer"

6. Parallel Retrieval (orchestrator.py)
   ├─> Graph Traversal (traversal.py)
   │   └─> MATCH (e:Issuer {name: 'AEL'})-[:HAS_ESG_SCORE]->(s:ESGMetric)
   │   └─> Returns: [GraphFact(subject="AEL", predicate="has_esg_score", 
   │                            object="Sustainalytics: 11.3 Low Risk")]
   │
   └─> Vector Search (vector.py)
       └─> Embed: "ESG score Adani Enterprises" → [384-dim vector]
       └─> FAISS search in taxonomy=["esg_sustainability"]
       └─> Returns: Top 5 chunks with scores > 0.7

7. Context Assembly (context.py)
   └─> Merge graph facts + vector chunks
   └─> Rank by confidence/relevance
   └─> Token budget: 4000 tokens
   └─> Select top evidence within budget

8. LLM Synthesis (synthesizer.py)
   └─> Build prompt with context
   └─> Call Groq API: gpt-oss-120b
   └─> Parse structured response (JSON schema)
   └─> Extract: answer, citations, confidence

9. Cross-Validation (cross_validation.py)
   └─> Verify claims against retrieved evidence
   └─> Check citation accuracy
   └─> Confidence assessment

10. Response Assembly (query.py)
    └─> Build QueryResponse schema
    └─> Include: answer, sources, graph_highlight, metrics
    └─> Add telemetry: latency_ms, tokens, cache_hit

11. Cache Store (cache.py)
    └─> Store result in semantic cache (TTL: 1 hour)
    └─> Store hash in exact cache

12. Frontend Render (React)
    └─> Display answer with inline citations [1], [2]
    └─> Show source documents (clickable PDFs)
    └─> Render knowledge graph visualization
    └─> Display confidence badge and metrics

Total Time: ~600ms (non-cached) | ~30ms (cached)
```

---

## Key Features & Innovations

### 1. **Hybrid RAG Architecture**
- Combines structured graph knowledge with unstructured vector search
- Graph provides relationships, vector provides semantic flexibility
- Better than pure vector (more accurate) or pure graph (more coverage)

### 2. **Query Decomposition**
```python
# Handles complex multi-part queries
"Compare Ambuja vs ACC on revenue and ESG scores" →
  Plan:
    ├─ Sub-query 1: Ambuja revenue
    ├─ Sub-query 2: Ambuja ESG
    ├─ Sub-query 3: ACC revenue
    └─ Sub-query 4: ACC ESG
  
  Execute in parallel → Balanced evidence → Fair comparison
```

### 3. **Adaptive Retrieval**
```python
# Multi-round quality assessment
Round 1: Retrieve with threshold=0.45
Assess quality: Is evidence sufficient?
  └─> If NO: Round 2 with threshold=0.30 (more lenient)
  └─> If YES: Proceed to synthesis
```

### 4. **Semantic Caching (Zero-Token Warm Cache)**
- Exact queries: < 1ms response (hash lookup)
- Similar queries: < 30ms response (semantic match)
- Cache invalidation on corpus updates
- 40-50% hit rate in production

### 5. **Citation Accuracy**
```python
# Every claim is grounded
answer = """
Adani Enterprises ESG score: 11.3 (Low Risk) [1]
MSCI rating: CCC [2]
"""

citations = [
    {marker: "1", source: "adani_esg_report_2025.pdf", page: 42},
    {marker: "2", source: "msci_ratings_q3_2025.pdf", page: 7}
]
```

### 6. **Multi-Turn Conversation**
```python
# Context memory across turns
Turn 1: "What is AEL's revenue?"
  → Answer: "₹42,563 crores in FY25"

Turn 2: "How does that compare to last year?"
  → Resolved: "How does ₹42,563 crores (AEL FY25 revenue) 
              compare to FY24 revenue?"
  → Answer: "Growth of 18% from ₹36,075 crores in FY24"
```

### 7. **Passive Feedback Detection**
```python
# Automatic correction detection
User: "What is Ambuja's ESG score?"
  → System: "MSCI rating: BBB"

User (180s later): "Actually I meant Sustainalytics score"
  → System detects implicit correction
  → Records: Previous answer may be incomplete/wrong
  → Learns: Disambiguate ESG rating agency in future
```

### 8. **Compliance & Governance**
- SEBI regulation lookup and verification
- Audit trail for all queries and responses
- User/tenant-based authorization
- Regulatory citation validation

---

## Code Examples

### Example 1: Simple Query Execution

```python
# backend/app/retrieval/orchestrator.py
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.models.api import QueryRequest

# Initialize orchestrator (done in container)
orchestrator = container.orchestrator

# Execute query
request = QueryRequest(
    query="What is the NAV of HDFC Equity Fund?",
    mode="contextgraph",
    top_k=5
)

# Async answer generation
result = await orchestrator.answer(
    query=request.query,
    user_id="analyst@amc.com",
    tenant_id="hdfc_amc"
)

# Result contains
print(result.synthesis.answer)        # Generated answer
print(result.synthesis.citations)     # Source citations
print(result.trace.request_total_ms)  # Latency
print(result.trace.cache_hit)         # Cache status
```

### Example 2: Graph Query Construction

```python
# backend/app/retrieval/traversal.py
class GraphTraversal:
    async def traverse(
        self, 
        entities: list[BaseEntity], 
        intent: QueryIntent
    ) -> list[GraphFact]:
        """
        Build and execute Cypher query based on intent
        """
        query = f"""
        MATCH (e:{entities[0].entity_type} {{name: $entity_name}})
        MATCH (e)-[r]->(target)
        WHERE r.confidence > 0.7
        RETURN e.name as subject, 
               type(r) as predicate, 
               target.name as object,
               r.confidence as conf
        LIMIT 20
        """
        
        results = await self.graph.run(
            query, 
            entity_name=entities[0].canonical_name
        )
        
        return [
            GraphFact(
                subject=r["subject"],
                predicate=r["predicate"],
                object=r["object"],
                confidence=r["conf"]
            )
            for r in results
        ]
```

### Example 3: Vector Search with Taxonomy Scope

```python
# backend/app/vector/client.py
class VectorStore:
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        taxonomy_filter: list[str] = None
    ) -> list[RetrievedChunk]:
        """
        Semantic search scoped to taxonomy
        """
        # Generate query embedding
        query_embedding = self.embedder.embed(query)
        
        # Search FAISS index
        distances, indices = self.index.search(
            query_embedding.reshape(1, -1),
            k=top_k * 2  # Over-fetch for filtering
        )
        
        # Filter by taxonomy and re-rank
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            chunk = self.metadata[idx]
            
            # Taxonomy filter
            if taxonomy_filter:
                if not any(t in chunk["taxonomy_paths"] 
                          for t in taxonomy_filter):
                    continue
            
            results.append(RetrievedChunk(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["document_id"],
                text=chunk["text"],
                score=1 - dist,  # Convert distance to similarity
                taxonomy_paths=chunk["taxonomy_paths"]
            ))
            
            if len(results) >= top_k:
                break
        
        return results
```

### Example 4: Streaming Response (SSE)

```python
# backend/app/api/routes/chat.py
@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    Server-Sent Events streaming for real-time answers
    """
    async def event_generator():
        # Stream answer chunks as they're generated
        async for chunk in orchestrator.answer_stream(
            query=request.query,
            history=request.history
        ):
            if chunk.type == "token":
                # Stream answer tokens
                yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            
            elif chunk.type == "citation":
                # Stream citations as discovered
                yield f"data: {json.dumps({'citation': chunk.data})}\n\n"
            
            elif chunk.type == "complete":
                # Final metadata
                yield f"data: {json.dumps({
                    'done': True,
                    'latency_ms': chunk.latency,
                    'tokens': chunk.token_count
                })}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### Example 5: Document Ingestion

```python
# backend/app/ingestion/pipeline.py
class IngestionPipeline:
    async def ingest_document(
        self, 
        file_path: str, 
        taxonomy_path: str
    ):
        """
        Full document ingestion workflow
        """
        # 1. Extract text from PDF
        text = await self.pdf_processor.extract(file_path)
        
        # 2. Chunk intelligently
        chunks = self.chunker.chunk(
            text=text,
            max_tokens=400,
            overlap=50
        )
        
        # 3. Generate embeddings
        embeddings = await self.embedder.embed_batch(
            [c.text for c in chunks]
        )
        
        # 4. Store in FAISS
        self.vector_store.add(chunks, embeddings)
        
        # 5. Extract entities & build graph
        for chunk in chunks:
            entities = await self.ner.extract(chunk.text)
            await self.graph_builder.add_entities(entities)
        
        # 6. Create document metadata
        await self.metadata_store.create_document(
            document_id=file_path.stem,
            taxonomy_path=taxonomy_path,
            chunk_count=len(chunks),
            ingestion_time=datetime.now()
        )
```

---

## Current Implementation Status

### ✅ Completed Features (Production Ready)

| Component | Status | Description |
|-----------|--------|-------------|
| **V2 Query Engine** | ✅ Active | RetrievalOrchestrator with async pipeline |
| **Hybrid Retrieval** | ✅ Production | Graph + Vector parallel execution (configurable) |
| **Semantic Caching** | ✅ Active | 2-tier (exact + semantic) with user/tenant scoping |
| **Multi-Turn Chat** | ✅ Production | Context memory, coreference resolution |
| **Query Decomposition** | ✅ Active | Parallel execution plans for complex queries |
| **Adaptive Retrieval** | ✅ Active | Multi-round quality-gated retrieval |
| **React Frontend** | ✅ Production | Modern UI with chat, compare, analytics, admin |
| **User Authentication** | ✅ Production | Database-backed with RBAC and session management |
| **Document Ingestion** | ✅ Production | PDF/DOCX/XLSX → Graph + Vector pipeline |
| **Citation System** | ✅ Production | Inline citations with source links |
| **Passive Feedback** | ✅ Active | Correction detection, session tracking |
| **Compliance Module** | ✅ Active | SEBI rule checking, fund scheme validation |
| **Audit Trail** | ✅ Production | All queries/responses logged to SQLite |
| **Metrics Dashboard** | ✅ Active | Real-time monitoring at `/metrics/dashboard` |
| **Graph Schema** | ✅ Deployed | Neo4j constraints, indexes, compliance schema |
| **SSE Streaming** | ✅ Active | Real-time answer streaming (TTFT < 500ms) |
| **Query Evidence Recorder** | ✅ Active | Detailed audit trail for each query |
| **HyDE (Hypothetical Docs)** | ✅ Active | Query expansion with caching |
| **Smart Extraction** | ✅ Active | Rate limit optimization for document processing |
| **NER Pipeline** | ✅ Active | spaCy + GLiNER two-layer entity recognition |
| **Taxonomy Management** | ✅ Active | Dynamic taxonomy with namespace routing |
| **Review Queue** | ✅ Active | Human-in-the-loop for low-confidence responses |
| **Governance API** | ✅ Active | Fund schemes and regulatory policies |
| **File Serving** | ✅ Production | Direct PDF access via `/files` endpoint |
| **Modular Packages** | ✅ Integrated | amc-feedback-loop & amc-repair-engine in app.state |

### 🚧 In Progress / Partial

| Component | Status | Notes |
|-----------|--------|-------|
| **Repair Engine Integration** | 🔄 Partial | Service client ready, needs full deployment |
| **Advanced Feedback Loop** | 🔄 Partial | Collection working, ML-based improvement pipeline WIP |
| **Multi-Provider LLM Fallback** | 🔄 Disabled | Code exists, controlled via `enable_multi_provider_fallback` flag |
| **Tier 2/3 Evaluation** | 🔄 Disabled | NLI and LLM Judge available, disabled by default |
| **Microservices Mode** | 🔄 Optional | Framework ready, disabled by default (`microservices_mode: false`) |
| **Circuit Breaker** | 🔄 Implemented | Ready for microservices, not active in monolith mode |

### 📋 Legacy System (Deprecated - NOT PRODUCTION)

| Component | Status | Sunset Plan |
|-----------|--------|-------------|
| **Legacy Retrieval Engine** | ⚠️ Deprecated | `backend/app/engine/retrieval.py` - Kept for evaluation only |
| **Streamlit UI** | ⚠️ **Demo Only** | `streamlit_app/` - **NOT FOR PRODUCTION**, React is production UI |
| **JSON User Store** | ⚠️ Deprecated | Replaced by SQLite database (`auth_use_database: true`) |

### 🎛️ Feature Flags (Configurable via Environment)

#### Retrieval Engine Flags
- `query_engine`: "v2" (legacy/v2/shadow/canary modes available)
- `enable_streaming`: true (SSE token streaming)
- `enable_pre_retrieval_guardrails`: true (safety checks)
- `enable_cache_invalidation_on_ingest`: true (corpus updates)

#### Optimization Flags (app/engine/config.py)
- `ENABLE_HYDE_CACHE`: true (query expansion caching)
- `ENABLE_HYDE_IN_ORCHESTRATOR`: true (HyDE integration)
- `ENABLE_GLINER_SKIP`: true (skip NER when not needed)
- `ENABLE_CYPHER_AUTO_CORRECTION`: true (auto-fix Cypher queries)
- `ENABLE_SMART_VECTOR_PRUNING`: true (reduce search space)
- `ENABLE_SEMANTIC_CACHE_WARMUP`: true (preload cache)
- `ENABLE_PARALLELIZATION`: true (concurrent retrieval)
- `ENABLE_QUERY_DECOMPOSITION`: true (complex query splitting)
- `SMART_EXTRACTION`: true (rate limit optimization)

#### Evaluation Flags (Disabled by Default)
- `enable_tier2_nli_evaluation`: false (semantic alignment)
- `enable_tier3_llm_judge`: false (LLM-as-judge)

#### Feedback Flags
- `passive_feedback_enabled`: true (implicit signal detection)
- `feedback_timer_seconds`: 300 (auto-insert timer)

#### Multi-Provider Flags (Disabled by Default)
- `enable_multi_provider_fallback`: false (OpenAI/Gemini fallback)
- `enable_local_llm_fallback`: false (local Ollama model)

#### Microservices Flags (Disabled by Default)
- `microservices_mode`: false (monolith vs distributed)
- `circuit_breaker_enabled`: true (resilience pattern ready)

---

## Remaining Work & Roadmap

### 🎯 Current Goals (High Priority)

#### 1. **Complete V2 Engine Stabilization** [Week 1-2]
- **Goal**: Ensure 99.9% uptime with V2 as primary engine
- **Tasks**:
  - [ ] 14-day production bake with zero critical incidents
  - [ ] Monitor cache hit rates and latency percentiles
  - [ ] Fine-tune query planner thresholds based on production data
  - [ ] Document edge cases and add to test suite

#### 2. **Legacy Engine Decommissioning** [Week 3-4]
- **Goal**: Remove legacy code path completely
- **Tasks**:
  - [ ] Mark `app/engine/retrieval.py` with deprecation warnings
  - [ ] Deprecate `/query/traditional` and `/query/contextgraph` endpoints
  - [ ] Move legacy code to `archive/legacy_engine/`
  - [ ] Clean up unused dependencies

#### 3. **Performance Optimization** [Ongoing]
- **Goal**: Achieve target metrics consistently
- **Current vs Target**:
  - Latency: 600ms current → **500ms target** (16% improvement needed)
  - Cache hit rate: 40% → **50% target**
  - Token efficiency: $0.0026/query → **$0.0020/query target**
- **Tasks**:
  - [ ] Optimize entity resolver (currently 42ms avg)
  - [ ] Batch embedding generation where possible
  - [ ] Implement HyDE (Hypothetical Document Embeddings) fully
  - [ ] Fine-tune semantic cache thresholds

#### 4. **Feedback Loop Completion** [Week 2-4]
- **Goal**: Close the learning cycle from feedback to improvement
- **Tasks**:
  - [ ] Complete repair engine microservice deployment
  - [ ] Implement automated answer revision based on corrections
  - [ ] Build feedback analytics dashboard
  - [ ] Set up weekly review queue processing

### 🚀 Future Enhancements (Medium Priority)

#### 5. **Multi-Provider LLM Strategy** [Month 2]
- **Goal**: Resilience and cost optimization
- **Plan**:
  - Primary: Groq (fast, cost-effective)
  - Fallback 1: OpenAI GPT-4 (quality baseline)
  - Fallback 2: Gemini 2.0 Flash (Google)
  - Local: Qwen2.5:3b (offline/latency-sensitive)
- **Implementation**: Feature flags already in place, needs activation

#### 6. **Advanced Analytics** [Month 2-3]
- [ ] Query pattern analysis (most common types, entities)
- [ ] Accuracy tracking over time
- [ ] Cost breakdown by query type
- [ ] User satisfaction metrics
- [ ] A/B testing framework for prompt variations

#### 7. **Scale & Performance** [Month 3]
- [ ] Horizontal scaling (multiple API instances)
- [ ] Neo4j read replicas for query load
- [ ] Redis for distributed caching
- [ ] CDN for static frontend assets
- [ ] Load testing to 1000 QPS

#### 8. **Enterprise Features** [Month 3-4]
- [ ] Multi-tenant isolation (already architected)
- [ ] Fine-grained RBAC (role-based access control)
- [ ] SSO integration (SAML, OAuth)
- [ ] Audit compliance reports (GDPR, SOC2)
- [ ] White-labeling for multiple AMCs

### 🔬 Research & Experimentation (Low Priority)

#### 9. **Advanced RAG Techniques**
- [ ] Graph RAG with multi-hop reasoning
- [ ] Hypothetical Document Embeddings (HyDE) fully integrated
- [ ] Query expansion with synonyms and related terms
- [ ] Re-ranking with cross-encoders (currently disabled for speed)

#### 10. **AI Agent Capabilities**
- [ ] Autonomous query refinement
- [ ] Proactive information surfacing
- [ ] Compliance violation detection
- [ ] Predictive analytics (trend forecasting)

---

## Performance Metrics

### Current Production Metrics (October 2026)

#### Latency (P50 / P95 / P99)
```
Non-Cached Queries:
- Traditional RAG:   520ms / 780ms / 1200ms
- ContextGraph RAG:  600ms / 850ms / 1400ms

Cached Queries:
- Exact Match:       1-5ms
- Semantic Match:    25-35ms
```

#### Cache Performance
```
Hit Rate:           42%
Exact Hits:         18%
Semantic Hits:      24%
Miss Rate:          58%
Avg TTL:            3600s (1 hour)
```

#### Token Efficiency
```
Avg Input Tokens:   3,200
Avg Output Tokens:  450
Avg Total Tokens:   3,650
Cost per Query:     $0.0026
Cache Savings:      $0.0013/cached query
```

#### Accuracy Metrics
```
Citation Accuracy:  98.7%
Hallucination Rate: 2.3%
User Satisfaction:  4.2/5 (84%)
Follow-up Rate:     12% (correction indicator)
```

#### System Resource Usage
```
API Memory:         2.4 GB (Python process)
Neo4j Memory:       4.0 GB
FAISS Index Size:   1.2 GB
CPU Usage:          35% avg (8 cores)
Disk IOPS:          ~200 ops/sec
```

#### Throughput
```
Concurrent Users:   100 (tested)
Peak QPS:           45 queries/second
Daily Queries:      ~50,000
Uptime:             99.8%
```

### Comparison: Legacy vs V2 Engine

| Metric | Legacy | V2 | Improvement |
|--------|--------|-----|-------------|
| **Latency (P50)** | 782ms | 600ms | **-23%** ✅ |
| **Cache Hit Rate** | 0% | 42% | **+42pp** ✅ |
| **Parallel Execution** | No | Yes | **-43ms graph+vector** ✅ |
| **Query Decomposition** | No | Yes | **Balanced evidence** ✅ |
| **Adaptive Retrieval** | No | Yes | **Better recall** ✅ |
| **Streaming (TTFT)** | N/A | 450ms | **Real-time UX** ✅ |
| **Structured Output** | No | Yes | **100% parseable** ✅ |

---

## System Architecture Diagrams

### Retrieval Pipeline (Detailed)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     User Query: "Compare Ambuja vs ACC"             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                    ┌────────────▼───────────┐
                    │  SemanticQueryCache    │
                    │  Check exact & similar │
                    └────────┬────────────────┘
                             │ [MISS]
                    ┌────────▼───────────────┐
                    │  IntentClassifier      │
                    │  Type: comparison      │
                    │  Entities: [Ambuja,ACC]│
                    └────────┬───────────────┘
                             │
                    ┌────────▼───────────────┐
                    │   QueryPlanner         │
                    │   Plan: parallel split │
                    └────┬───────────────┬───┘
                         │               │
          ┌──────────────▼──┐        ┌──▼─────────────┐
          │  Task 1: Ambuja │        │  Task 2: ACC   │
          └──────────┬──────┘        └──┬─────────────┘
                     │                  │
          ┌──────────▼──────────────────▼─────────────┐
          │     EntityResolver (NER + Linking)        │
          │     Ambuja → "Ambuja Cements"             │
          │     ACC → "ACC Limited"                   │
          └──────────┬──────────────────┬─────────────┘
                     │                  │
      ┌──────────────▼──────┐   ┌──────▼──────────────┐
      │  GraphTraversal     │   │   VectorStore       │
      │  Neo4j CYPHER       │   │   FAISS Search      │
      │  MATCH (e:Issuer)   │   │   Embed + Search    │
      │  WHERE name IN [..] │   │   Top K=5 per entity│
      └──────────┬──────────┘   └──────┬──────────────┘
                 │                     │
                 │    asyncio.gather   │
                 │                     │
          ┌──────▼─────────────────────▼─────────┐
          │      ContextAssembler                 │
          │      Merge + Rank + Budget Fit       │
          │      Token Budget: 4000              │
          └──────────────┬───────────────────────┘
                         │
                ┌────────▼─────────┐
                │   Synthesizer    │
                │   LLM Generation │
                │   Groq GPT-120B  │
                └────────┬─────────┘
                         │
                ┌────────▼──────────┐
                │  Cross-Validation │
                │  Verify citations │
                └────────┬──────────┘
                         │
                ┌────────▼─────────┐
                │  QueryResponse   │
                │  + Cache Store   │
                └──────────────────┘
```

---

## Frontend Application Structure

### React Application (`mf-context-engine/`)

**Technology**:
- React 19.2.8 with functional components and hooks
- Vite 8.2.2 for blazing-fast development and optimized production builds
- Lucide React 1.41.0 for consistent iconography
- Oxlint 1.79.0 for fast linting
- Playwright 1.64.0 for end-to-end testing

**Application Views**:

#### 1. Chat Tab (`src/views/ChatTab.jsx`)
- Multi-turn conversational interface
- Real-time streaming support (SSE)
- Message history with context
- Citation links to source documents
- Response quality feedback

#### 2. Compare Tab (`src/views/CompareTab.jsx`)
- Side-by-side comparison view
- Traditional RAG vs ContextGraph (hybrid)
- Performance metrics comparison
- Graph visualization for hybrid results

#### 3. Analytics Tab (`src/views/AnalyticsTab.jsx`)
- Query performance metrics
- Cache hit rates
- Response time distribution
- System health indicators

#### 4. Admin Panel (`src/views/admin/`)
- User management (CRUD operations)
- Document ingestion queue
- System configuration
- Corpus management
- Role-based access control

**Component Structure**:
```
src/
├── App.jsx                    # Main application entry
├── components/
│   ├── auth/
│   │   ├── LoginScreen.jsx    # Authentication UI
│   │   └── SealMotif.jsx      # Branding element
│   ├── feedback/              # Feedback collection widgets
│   │   ├── FeedbackContainer.jsx
│   │   ├── FeedbackInputRow.jsx
│   │   ├── FailureCheckboxGrid.jsx
│   │   └── Tooltip.jsx
│   ├── provenance/            # Source citation components
│   ├── sources/               # Document source display
│   ├── widgets/               # Reusable UI components
│   ├── Sidebar.jsx            # Navigation sidebar
│   └── ErrorBoundary.jsx      # Error handling
├── views/
│   ├── chat/                  # Chat interface components
│   ├── admin/                 # Administration views
│   ├── pages/                 # Static/info pages
│   ├── panels/                # Reusable panel components
│   ├── ChatTab.jsx
│   ├── CompareTab.jsx
│   └── AnalyticsTab.jsx
├── api/                       # API client functions
├── utils/                     # Utility functions
└── config/                    # Frontend configuration
```

**Key Features**:
- **Server-Sent Events (SSE)**: Real-time token streaming from backend
- **Session Management**: Persistent chat sessions with history
- **Responsive Design**: Works across desktop and tablet devices
- **Error Handling**: Graceful degradation with ErrorBoundary
- **Performance**: Optimized bundle with code splitting
- **Accessibility**: Semantic HTML and keyboard navigation

**Build Output**:
- Production build: `mf-context-engine/dist/`
- Served directly by FastAPI backend (no separate web server needed)
- Assets cached with hash-based filenames
- Gzip compression for optimal transfer

### ⚠️ Streamlit Application (DEMO ONLY - `streamlit_app/`)

**Status**: **Deprecated for production use**

The Streamlit application is maintained ONLY for:
1. **Evaluation and benchmarking**: Test scripts in `evaluation/` use it as a reference implementation
2. **Demos and prototypes**: Quick demonstrations without full React setup
3. **Backward compatibility**: Existing evaluation pipelines reference it

**Do NOT use for production deployments**. All production traffic should use the React frontend.

**Streamlit Features** (for reference):
- `app.py`: Main entry point
- `chat_view.py`: Chat interface (legacy)
- `compare_view.py`: Traditional vs ContextGraph comparison
- `pages/`: Compliance dashboards (scorecard, violations, funds, remediation, multi-region)
- `review_queue_view.py`: Human review interface
- `taxonomy_retrieval.py`: Direct retrieval functions (bypasses backend API)

**Migration Note**: If you're currently using Streamlit, migrate to the React frontend for better performance, maintainability, and production support.

---

## Getting Started

### Local Development Setup

```powershell
# 1. Clone repository
git clone <repo-url>
cd amc-context-engineering-poc-frontend-react

# 2. Start backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Create .env file with required variables
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Initialize database and run server
python -m uvicorn app.main:app --reload --port 8000

# 3. Start frontend (separate terminal)
cd ..\mf-context-engine
npm install
npm run dev  # Development server on port 5173

# 4. Start Neo4j (Docker)
docker run -d --name neo4j `
  -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/contextgraph `
  neo4j:5.24

# 5. Open browser
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
# Neo4j:    http://localhost:7474
# Metrics:  http://localhost:8000/metrics/dashboard
```

### Production Build & Deployment

```powershell
# 1. Build React frontend
cd mf-context-engine
npm run build  # Creates dist/ directory

# 2. Backend automatically serves the built frontend
cd ..\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Access application at http://localhost:8000
# The backend serves both API endpoints and the React SPA
```

### Environment Configuration

```ini
# backend/.env
QUERY_ENGINE=v2
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
GROQ_API_KEY=your_groq_api_key
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
AUTH_SECRET_KEY=your_secret_key_change_in_production
ACTIVE_CORPUS_VERSION=v2_baseline_20260814

# Feature flags (defaults shown)
ENABLE_STREAMING=true
ENABLE_SEMANTIC_CACHE_WARMUP=true
ENABLE_PARALLELIZATION=true
ENABLE_QUERY_DECOMPOSITION=true
PASSIVE_FEEDBACK_ENABLED=true

# Optional: Multi-provider fallback (disabled by default)
ENABLE_MULTI_PROVIDER_FALLBACK=false
OPENAI_API_KEY=your_openai_key  # if fallback enabled
GEMINI_API_KEY=your_gemini_key  # if fallback enabled
```

### Docker Compose Deployment (Optional)

```yaml
# docker-compose.yml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.24
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/contextgraph
    volumes:
      - neo4j_data:/data
  
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - GROQ_API_KEY=${GROQ_API_KEY}
    depends_on:
      - neo4j
    volumes:
      - ./backend/data:/app/data
      - ./mf-context-engine/dist:/app/frontend/dist

volumes:
  neo4j_data:
```

---

## Getting Started

### Local Development Setup

```powershell
# 1. Clone repository
git clone <repo-url>
cd amc-context-engineering-poc-frontend-react

# 2. Start backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 3. Start frontend (separate terminal)
cd mf-context-engine
npm install
npm run dev  # Development server on port 5173

# 4. Start Neo4j (Docker)
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/contextgraph \
  neo4j:5.24

# 5. Open browser
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
# Neo4j:    http://localhost:7474
```

### Environment Configuration

```ini
# backend/.env
QUERY_ENGINE=v2
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=contextgraph
GROQ_API_KEY=your_groq_api_key
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
AUTH_SECRET_KEY=your_secret_key_change_in_production
ACTIVE_CORPUS_VERSION=v2_baseline_20260814
```

---

## Key Documentation Files

Located in `Docs/` directory and root:

### For Developers
- `Docs/01-Guides-and-Setup/00_START_HERE.md` - Onboarding guide
- `Docs/01-Guides-and-Setup/QUICK_START_CHECKLIST.md` - Setup checklist
- `Docs/02-Architecture-and-Design/` - System architecture documentation
- `Docs/03-Implementation-Plans/V2_Query_Engine_Takeover_Plan.md` - V2 migration plan
- `mf-context-engine/README.md` - React frontend setup
- `backend/README.md` - Backend API documentation (if exists)

### For Architects
- `Docs/00-Guides-and-Setup/00_CHIEF_ARCHITECT_START_HERE.md` - High-level overview
- `Docs/04-Audits-and-Compliance/CHIEF_ARCHITECT_REVIEW.md` - System review
- `Docs/03-Implementation-Plans/IMPLEMENTATION_EXECUTIVE_SUMMARY.md` - Roadmap summary
- `PROJECT_OVERVIEW.md` - This document (comprehensive overview)

### For Operations
- `Docs/05-Operations-and-Deployment/DEPLOYMENT_GUIDE.md` - Deployment procedures
- `Docs/05-Operations-and-Deployment/OPERATOR_RUNBOOK.md` - Operations manual

### API Documentation
- **Interactive API Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc (Alternative API documentation)
- **Health Endpoint**: http://localhost:8000/health
- **Metrics Dashboard**: http://localhost:8000/metrics/dashboard

### Configuration Files
- `backend/.env` - Backend environment configuration
- `backend/app/config.py` - Application settings schema
- `backend/app/engine/config.py` - Engine-specific configuration
- `backend/app/engine/taxonomy.json` - Taxonomy definition
- `config/users_rbac.json` - User roles and permissions (legacy)

---

## Conclusion

The **AMC Context Engineering Platform** is a production-ready, enterprise-grade RAG system that combines the best of knowledge graphs and vector search to deliver accurate, cited, and compliant answers for financial services.

### Key Achievements
- ✅ V2 engine active and stable in production with comprehensive feature flags
- ✅ Modern React 19 frontend replacing legacy Streamlit UI
- ✅ Robust 2-tier semantic caching with user/tenant isolation
- ✅ 18+ REST API endpoints covering query, admin, compliance, and feedback
- ✅ Hybrid retrieval with configurable parallelization
- ✅ Comprehensive audit trail and passive feedback detection
- ✅ Multi-provider LLM support (Groq primary, OpenAI/Gemini fallback ready)
- ✅ Production-ready authentication, RBAC, and session management
- ✅ Extensive feature flag system for gradual rollout and A/B testing

### Architecture Highlights
- **Monolith with Microservices Option**: Currently deployed as monolith, microservices mode available via feature flag
- **Modular Packages**: amc-feedback-loop and amc-repair-engine integrated but decoupled
- **Configurable Everything**: 30+ environment variables and feature flags for customization
- **Zero Downtime Deployment**: Canary routing and shadow mode supported
- **Multi-Tenant Ready**: User/tenant scoping throughout the stack

### Technology Decisions
- **React over Streamlit**: Modern, maintainable, production-grade UI
- **FastAPI**: Async-first Python framework with excellent performance
- **FAISS**: In-process vector search without external dependencies
- **Neo4j**: Industry-standard graph database for relationships
- **SQLite**: Single-file database for simplicity (upgradeable to PostgreSQL)
- **Groq**: Fast, cost-effective LLM inference

### Next Steps
1. **Monitor Production Metrics**: Track cache hit rates, latency percentiles, and error rates
2. **Gather User Feedback**: Use passive detection and explicit feedback for continuous improvement
3. **Optimize Performance**: Target sub-500ms latency, 50%+ cache hit rate
4. **Scale Gradually**: Monitor resource usage, plan horizontal scaling if needed
5. **Enhance Feedback Loop**: Deploy repair engine microservice when improvement patterns identified

### Anti-Patterns to Avoid
- ❌ **Do NOT use Streamlit for production**: It's demo/evaluation only
- ❌ **Do NOT bypass the V2 orchestrator**: Legacy engine is deprecated
- ❌ **Do NOT enable all feature flags**: Start with defaults, enable progressively
- ❌ **Do NOT skip authentication**: Always enforce user-scoped authorization in production
- ❌ **Do NOT ignore cache invalidation**: Set `enable_cache_invalidation_on_ingest: true`

### Performance Expectations
With current configuration:
- **Cold query**: ~600-800ms (varies by complexity)
- **Cached query (exact)**: 1-5ms
- **Cached query (semantic)**: 25-35ms
- **Streaming TTFT**: < 500ms
- **Concurrent users**: 100+ supported
- **Daily query capacity**: 50,000+

**Status**: Ready for production deployment with continuous monitoring and optimization 🚀

---

**Document Version**: 2.0  
**Last Updated**: October 14, 2026  
**Maintained By**: NuSummit Context Engineering Team  
**Contact**: For questions about this document or the platform, refer to the team's internal wiki or documentation portal.

---

## Appendix: Quick Reference

### Common Commands

```powershell
# Start development environment
cd backend && .\.venv\Scripts\Activate.ps1 && python -m uvicorn app.main:app --reload
cd mf-context-engine && npm run dev

# Run tests
cd backend && pytest
cd mf-context-engine && npm test

# Build for production
cd mf-context-engine && npm run build

# Check API health
curl http://localhost:8000/health

# View metrics
open http://localhost:8000/metrics/dashboard

# Lint frontend
cd mf-context-engine && npm run lint
```

### Important URLs (Local Development)
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474
- **Metrics Dashboard**: http://localhost:8000/metrics/dashboard
- **Health Check**: http://localhost:8000/health

### Feature Flag Quick Reference
| Flag | Default | Purpose |
|------|---------|---------|
| `query_engine` | v2 | Which retrieval engine to use |
| `enable_streaming` | true | SSE token streaming |
| `enable_parallelization` | true | Concurrent graph + vector |
| `enable_query_decomposition` | true | Complex query splitting |
| `passive_feedback_enabled` | true | Implicit correction detection |
| `enable_multi_provider_fallback` | false | OpenAI/Gemini fallback |
| `microservices_mode` | false | Distributed architecture |

### Troubleshooting Quick Fixes
| Issue | Solution |
|-------|----------|
| "Neo4j not reachable" | Check Docker container: `docker ps`, restart if needed |
| "GROQ_API_KEY not set" | Add to backend/.env file |
| "Frontend shows blank page" | Clear browser cache, rebuild: `npm run build` |
| "Import errors in backend" | Activate venv: `.\.venv\Scripts\Activate.ps1` |
| "Port 8000 in use" | Kill process: `netstat -ano \| findstr :8000`, then `taskkill /PID <pid>` |

