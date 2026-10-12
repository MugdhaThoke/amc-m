# Feedback Pending Repair Notification Feature - Implementation Plan

## 📋 Executive Summary

This document outlines a comprehensive plan to implement a notification system that informs users when another user has previously submitted feedback for a similar query and repair is still pending.

**Core Requirement**: When User B queries something similar to what User A already reported (with feedback), show User B a message in the feedback tab: *"Another user has previously submitted feedback on a similar query. Repair is pending."*

**Key Constraint**: Message appears ONLY when:
1. Query intent matches an existing feedback entry
2. `selected_categories` is NOT NULL/empty
3. `feedback_text` is NOT NULL/empty  
4. Repair status is "pending" (`lifecycle_status` = 'open' or 'diagnosing')
5. Intent cache has NOT been cleared

---

## 🏗️ Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Flow Entry Point                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│          Intent Matching Service (New Component)             │
│  • Compute query embedding                                   │
│  • Search feedback DB for similar queries                    │
│  • Check repair status in unified_evaluation_records         │
│  • Return notification flag + metadata                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Response Enhancement (Middleware)                │
│  • Inject pending_feedback_notice into response              │
│  • Add to telemetry/metadata                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Frontend Feedback Tab                     │
│  • Check for pending_feedback_notice                         │
│  • Display warning banner if present                         │
│  • Show user-friendly message                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Detailed Component Design

### 1. Intent Matching Service

**File**: `backend/app/feedback/intent_matcher.py` (NEW)

**Purpose**: Determine if current query matches existing feedback entries with pending repairs.

#### Core Algorithm

```python
class FeedbackIntentMatcher:
    """
    Matches query intent against existing feedback database.
    Uses semantic similarity for intent matching.
    """
    
    def __init__(
        self, 
        similarity_threshold: float = 0.88,
        embedder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        self.similarity_threshold = similarity_threshold
        self.embedder = get_embedder(embedder_model)
        
    async def check_pending_feedback(
        self, 
        query: str,
        session_id: str,
        db: Session
    ) -> Optional[PendingFeedbackNotice]:
        """
        Check if similar query has pending feedback.
        
        Returns:
            PendingFeedbackNotice if match found, else None
        """
        # STEP 1: Get query embedding
        query_embedding = self._get_embedding(query)
        
        # STEP 2: Fetch candidate feedback entries
        candidates = self._fetch_feedback_candidates(db)
        
        # STEP 3: Compute similarity scores
        matches = self._compute_similarity(
            query_embedding, 
            candidates
        )
        
        # STEP 4: Check repair status for top matches
        for match in matches:
            if match.similarity >= self.similarity_threshold:
                repair_status = self._check_repair_status(
                    match.response_id, 
                    db
                )
                
                if repair_status.is_pending:
                    return PendingFeedbackNotice(
                        has_pending_feedback=True,
                        similarity_score=match.similarity,
                        original_query_text=match.query_text,
                        feedback_submitted_at=match.created_at,
                        feedback_categories=match.selected_categories,
                        repair_lifecycle_status=repair_status.lifecycle_status
                    )
        
        return None
```

#### Database Query Strategy

**Option A: Sequential Scan with Caching** (Recommended for MVP)
- Query all feedback entries where `selected_categories` IS NOT NULL
- Cache results in Redis/memory (TTL: 5 minutes)
- Compute similarity in-memory using NumPy

**Option B: Database-Level Vector Search** (Production Scale)
- Add `query_embedding` column to `response_feedback` table
- Create vector index (if using PostgreSQL with pgvector)
- Use database-native similarity search

**Option C: Hybrid Approach** (Recommended for Production)
- Pre-filter feedback entries by domain intent (stored in feedback metadata)
- Use intent cache domain classification
- Then compute similarity only within domain bucket

---

### 2. Database Schema Enhancement

#### A. Add Embedding Column (Optional - for Option B)

```sql
-- Add embedding column to response_feedback
ALTER TABLE response_feedback 
ADD COLUMN query_embedding BLOB;

-- Add index for faster lookups
CREATE INDEX idx_feedback_has_content 
ON response_feedback(response_id) 
WHERE selected_categories IS NOT NULL 
  AND feedback_text IS NOT NULL 
  AND feedback_text != '';
```

#### B. Repair Status Query

```sql
-- Query to check if repair is pending
SELECT 
    uer.lifecycle_status,
    uer.repair,
    uer.repair_target,
    uer.updated_at
FROM unified_evaluation_records uer
WHERE uer.response_id = ?
  AND uer.lifecycle_status IN ('open', 'diagnosing')
  AND uer.repair = 1;
```

---

### 3. Clear Intent Cache Handler

**File**: `backend/app/engine/intent_cache.py` (MODIFY)

**Purpose**: Invalidate pending feedback notices when intent cache is cleared.

#### Implementation

```python
class IntentAwareCache:
    # ... existing code ...
    
    def clear_all(self) -> None:
        """Clear all cache buckets AND pending feedback index."""
        for d in self._entries_by_domain:
            self._entries_by_domain[d].clear()
        self._fingerprint_index.clear()
        
        # NEW: Clear pending feedback notice cache
        self._clear_pending_feedback_cache()
        
        self._persist_to_disk()
        print("  [IntentCache] Cleared all cache buckets + pending feedback index.", flush=True)
    
    def _clear_pending_feedback_cache(self) -> None:
        """Invalidate pending feedback notice cache."""
        try:
            from app.feedback.intent_matcher import clear_pending_feedback_cache
            clear_pending_feedback_cache()
            logger.info("Cleared pending feedback notice cache")
        except Exception as e:
            logger.warning(f"Failed to clear pending feedback cache: {e}")
```

#### Cache Invalidation Strategy

```python
# backend/app/feedback/intent_matcher.py

_pending_feedback_cache: Dict[str, Optional[PendingFeedbackNotice]] = {}
_cache_ttl_seconds = 300  # 5 minutes

def clear_pending_feedback_cache() -> None:
    """Clear the pending feedback notice cache."""
    global _pending_feedback_cache
    _pending_feedback_cache.clear()
    logger.info("Pending feedback cache cleared")

class FeedbackIntentMatcher:
    def _get_cached_result(self, query_hash: str) -> Optional[PendingFeedbackNotice]:
        """Get cached result with TTL check."""
        if query_hash in _pending_feedback_cache:
            cached_entry = _pending_feedback_cache[query_hash]
            if cached_entry and (time.time() - cached_entry.cached_at) < _cache_ttl_seconds:
                return cached_entry
            else:
                del _pending_feedback_cache[query_hash]
        return None
```

---

### 4. API Response Enhancement

**File**: `backend/app/api/routes/query.py` (MODIFY)

**Purpose**: Inject pending feedback notice into query response.

#### Implementation

```python
@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    db: Session = Depends(get_db)
):
    # ... existing query handling ...
    
    # NEW: Check for pending feedback
    pending_feedback_notice = None
    try:
        from app.feedback.intent_matcher import get_intent_matcher
        matcher = get_intent_matcher()
        pending_feedback_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=request.session_id,
            db=db
        )
    except Exception as e:
        logger.warning(f"Failed to check pending feedback: {e}")
    
    # Enhance response with notice
    response = QueryResponse(
        answer=answer,
        response_id=response_id,
        # ... other fields ...
        pending_feedback_notice=pending_feedback_notice
    )
    
    return response
```

---

### 5. Frontend Display Component

**Location**: Frontend feedback tab component

#### Display Logic

```typescript
interface PendingFeedbackNotice {
  has_pending_feedback: boolean;
  similarity_score: number;
  original_query_text?: string;
  feedback_submitted_at: string;
  feedback_categories: string[];
  repair_lifecycle_status: string;
}

function FeedbackTab({ response }) {
  const notice = response.pending_feedback_notice;
  
  if (!notice?.has_pending_feedback) {
    return <NormalFeedbackForm />;
  }
  
  return (
    <div>
      {/* Warning Banner */}
      <div className="pending-feedback-banner">
        <Icon name="info-circle" />
        <div>
          <strong>Similar Feedback Already Submitted</strong>
          <p>
            Another user has previously submitted feedback on a similar query. 
            Repair is currently {notice.repair_lifecycle_status}.
          </p>
          <details>
            <summary>Details</summary>
            <ul>
              <li>Similarity: {(notice.similarity_score * 100).toFixed(1)}%</li>
              <li>Categories: {notice.feedback_categories.join(', ')}</li>
              <li>Submitted: {formatDate(notice.feedback_submitted_at)}</li>
            </ul>
          </details>
        </div>
      </div>
      
      {/* Still allow user to submit if they want */}
      <NormalFeedbackForm 
        prefilledNotice="You can still submit additional feedback if needed."
      />
    </div>
  );
}
```

---

## 🎯 Edge Cases & Handling

### Edge Case 1: Multiple Pending Feedbacks

**Scenario**: Query matches 3 different pending feedbacks.

**Solution**: 
- Return the MOST SIMILAR match (highest similarity score)
- Log other matches for analytics
- Display count: "Another user (and 2 others) have submitted similar feedback"

```python
def check_pending_feedback(self, query: str, db: Session):
    matches = self._find_all_matches(query, db)
    
    if not matches:
        return None
    
    # Return highest similarity match
    top_match = max(matches, key=lambda m: m.similarity_score)
    
    return PendingFeedbackNotice(
        has_pending_feedback=True,
        match_count=len(matches),
        top_match=top_match,
        # ... other fields ...
    )
```

---

### Edge Case 2: Feedback Without Unified Evaluation Record

**Scenario**: `response_feedback` entry exists but no corresponding `unified_evaluation_records` entry.

**Solution**: 
- Treat as "repair status unknown"
- Do NOT show notification
- Log warning for data integrity check

```python
def _check_repair_status(self, response_id: str, db: Session) -> RepairStatus:
    uer = db.query(UnifiedEvaluationRecord).filter_by(
        response_id=response_id
    ).first()
    
    if not uer:
        logger.warning(
            f"No unified evaluation record found for response_id={response_id}"
        )
        return RepairStatus(is_pending=False, status="unknown")
    
    is_pending = (
        uer.repair == True and 
        uer.lifecycle_status in ['open', 'diagnosing']
    )
    
    return RepairStatus(
        is_pending=is_pending,
        lifecycle_status=uer.lifecycle_status,
        repair_target=uer.repair_target
    )
```

---

### Edge Case 3: Resolved Repairs Still in Database

**Scenario**: Feedback exists, repair was completed, but query still matches.

**Solution**: 
- Check `lifecycle_status NOT IN ('resolved', 'monitoring')`
- Do NOT show notification if repair is resolved
- Optional: Show positive message "This issue has been resolved!"

```python
def _should_show_notice(self, repair_status: RepairStatus) -> bool:
    """Determine if notice should be shown."""
    if not repair_status.is_pending:
        return False
    
    # Only show for active repair statuses
    pending_statuses = ['open', 'diagnosing']
    return repair_status.lifecycle_status in pending_statuses
```

---

### Edge Case 4: Same User Re-querying

**Scenario**: User A submits feedback, then asks the same query again.

**Solution**: 
- Track user identity (actor_id, session_id)
- Do NOT show notification to the same user
- Optional: Show "You previously submitted feedback on this query"

```python
async def check_pending_feedback(
    self, 
    query: str,
    session_id: str,
    actor_id: Optional[str],
    db: Session
) -> Optional[PendingFeedbackNotice]:
    
    matches = self._find_matches(query, db)
    
    for match in matches:
        # Skip if same user
        if actor_id and match.actor_id == actor_id:
            continue
        
        # Check repair status
        if self._has_pending_repair(match.response_id, db):
            return self._build_notice(match)
    
    return None
```

---

### Edge Case 5: Intent Cache Cleared During Active Session

**Scenario**: User A loads page, admin clears cache, User A submits query.

**Solution**: 
- Add cache generation timestamp to response
- Frontend checks if cache was cleared after page load
- Gracefully handle missing notice (fail-safe)

```python
class QueryResponse(BaseModel):
    answer: str
    response_id: str
    pending_feedback_notice: Optional[PendingFeedbackNotice]
    cache_generation_ts: float  # NEW
    
def handle_query(request: QueryRequest):
    # ... query processing ...
    
    response = QueryResponse(
        # ... fields ...
        cache_generation_ts=time.time()
    )
    
    return response
```

---

### Edge Case 6: Partial Feedback (Only Category or Only Text)

**Scenario**: Feedback has `selected_categories` but empty `feedback_text`, or vice versa.

**Solution**: 
- Enforce BOTH must be non-null/non-empty
- Database query includes: `WHERE selected_categories IS NOT NULL AND feedback_text IS NOT NULL AND feedback_text != ''`

```python
def _fetch_feedback_candidates(self, db: Session) -> List[FeedbackCandidate]:
    """Fetch feedback entries with complete feedback."""
    return db.query(ResponseFeedback).filter(
        ResponseFeedback.selected_categories.isnot(None),
        ResponseFeedback.feedback_text.isnot(None),
        ResponseFeedback.feedback_text != ''
    ).all()
```

---

### Edge Case 7: High Volume Concurrent Queries

**Scenario**: 100 users querying simultaneously.

**Solution**: 
- Implement in-memory cache with TTL (5 minutes)
- Use connection pooling for database queries
- Async I/O for non-blocking operations
- Circuit breaker pattern for failure isolation

```python
class FeedbackIntentMatcher:
    def __init__(self):
        self._cache = TTLCache(maxsize=1000, ttl=300)  # 5 min TTL
        self._semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
        
    async def check_pending_feedback(self, query: str, db: Session):
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        # Check cache first
        if query_hash in self._cache:
            return self._cache[query_hash]
        
        # Limit concurrency
        async with self._semaphore:
            result = await self._compute_pending_feedback(query, db)
            self._cache[query_hash] = result
            return result
```

---

### Edge Case 8: Domain Mismatch

**Scenario**: Query about "SEBI regulations" matches feedback about "ESG sustainability".

**Solution**: 
- Classify domain intent for both query and feedback
- Only match within same domain
- Use domain-specific similarity thresholds

```python
def check_pending_feedback(self, query: str, db: Session):
    # Classify query domain
    query_domain = classify_domain_intent(query)
    
    # Fetch candidates from same domain only
    candidates = self._fetch_feedback_by_domain(query_domain, db)
    
    # Use domain-specific threshold
    threshold = DOMAIN_SIMILARITY_THRESHOLDS.get(
        query_domain, 
        DEFAULT_THRESHOLD
    )
    
    matches = self._compute_similarity(
        query, 
        candidates, 
        threshold
    )
    
    return self._select_best_match(matches)
```

---

### Edge Case 9: Null/Empty Query Text in Feedback

**Scenario**: `response_feedback.query_text` is NULL or empty.

**Solution**: 
- Skip entries with NULL/empty query_text
- Log data quality issue
- Consider using `response_text` as fallback

```python
def _fetch_feedback_candidates(self, db: Session):
    return db.query(ResponseFeedback).filter(
        ResponseFeedback.selected_categories.isnot(None),
        ResponseFeedback.feedback_text.isnot(None),
        ResponseFeedback.feedback_text != '',
        ResponseFeedback.query_text.isnot(None),  # NEW
        ResponseFeedback.query_text != ''  # NEW
    ).all()
```

---

### Edge Case 10: Database Connection Failure

**Scenario**: Database is temporarily unavailable.

**Solution**: 
- Graceful degradation: proceed without notice
- Log error for monitoring
- Return None (no notice)

```python
async def check_pending_feedback(self, query: str, db: Session):
    try:
        return await self._check_pending_feedback_impl(query, db)
    except OperationalError as e:
        logger.error(f"Database error checking pending feedback: {e}")
        return None  # Fail gracefully
    except Exception as e:
        logger.exception(f"Unexpected error checking pending feedback: {e}")
        return None
```

---

## 🔐 Security Considerations

### 1. Privacy Protection

**Issue**: Showing original query text may leak sensitive information.

**Solution**:
- Do NOT show `original_query_text` to other users
- Show only: "Another user submitted feedback on a similar query"
- Admin-only: full query text visibility

```python
class PendingFeedbackNotice(BaseModel):
    has_pending_feedback: bool
    similarity_score: float
    feedback_categories: List[str]
    feedback_submitted_at: str
    repair_lifecycle_status: str
    
    # Do NOT include original_query_text in API response
    # Only show in admin dashboard
```

---

### 2. Rate Limiting

**Issue**: Malicious user spamming queries to probe for existing feedback.

**Solution**:
- Rate limit: 10 queries per minute per session
- Implement sliding window rate limiter

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/query")
@limiter.limit("10/minute")
async def handle_query(request: QueryRequest):
    # ... query handling ...
```

---

### 3. Access Control

**Issue**: Unauthorized users viewing feedback notices.

**Solution**:
- Require authentication for query endpoint
- Role-based notice detail level

```python
@require_roles([Role.USER, Role.REVIEWER, Role.ADMIN])
async def handle_query(
    request: QueryRequest,
    current_role: Role = Depends(get_client_role)
):
    notice = await matcher.check_pending_feedback(query, db)
    
    # Admin gets full details, users get summary only
    if current_role != Role.ADMIN:
        notice = notice.to_user_summary()
    
    return QueryResponse(pending_feedback_notice=notice)
```

---

## 📊 Performance Optimization

### 1. Embedding Computation Caching

**Problem**: Computing embeddings for every query is expensive.

**Solution**: 
- Cache query embeddings (TTL: 1 hour)
- Reuse embeddings from intent cache

```python
class FeedbackIntentMatcher:
    def __init__(self):
        self._embedding_cache = TTLCache(maxsize=10000, ttl=3600)
    
    def _get_embedding(self, query: str) -> np.ndarray:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        if query_hash not in self._embedding_cache:
            embedding = self.embedder.encode(query)
            self._embedding_cache[query_hash] = embedding
        
        return self._embedding_cache[query_hash]
```

---

### 2. Batch Similarity Computation

**Problem**: Computing similarity one-by-one is slow.

**Solution**: 
- Vectorized NumPy operations
- Batch process all candidates at once

```python
def _compute_similarity_batch(
    self, 
    query_embedding: np.ndarray,
    candidates: List[FeedbackCandidate]
) -> List[SimilarityMatch]:
    """Vectorized similarity computation."""
    
    # Stack all candidate embeddings
    candidate_embeddings = np.vstack([
        c.query_embedding for c in candidates
    ])
    
    # Normalize
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    candidates_norm = candidate_embeddings / np.linalg.norm(
        candidate_embeddings, axis=1, keepdims=True
    )
    
    # Compute all similarities at once
    similarities = np.dot(candidates_norm, query_norm)
    
    # Build result list
    matches = [
        SimilarityMatch(
            candidate=candidates[i],
            similarity=float(similarities[i])
        )
        for i in range(len(candidates))
        if similarities[i] >= self.similarity_threshold
    ]
    
    return sorted(matches, key=lambda m: m.similarity, reverse=True)
```

---

### 3. Database Query Optimization

**Problem**: Full table scan on `response_feedback` is slow.

**Solution**: 
- Add composite index
- Partition by domain intent (if metadata stores domain)
- Use query result caching (5 min TTL)

```sql
-- Composite index for faster filtering
CREATE INDEX idx_feedback_complete_with_repair 
ON response_feedback(
    created_at DESC,
    response_id
) 
WHERE 
    selected_categories IS NOT NULL 
    AND feedback_text IS NOT NULL 
    AND feedback_text != '';

-- Index on unified_evaluation_records
CREATE INDEX idx_uer_pending_repairs
ON unified_evaluation_records(
    response_id,
    lifecycle_status,
    repair
)
WHERE repair = 1 
  AND lifecycle_status IN ('open', 'diagnosing');
```

---

### 4. Lazy Loading

**Problem**: Loading notice data slows down primary query response.

**Solution**: 
- Return query answer immediately
- Load pending feedback notice asynchronously
- Frontend polls for notice after 100ms delay

```python
# Option 1: Background task (recommended)
@router.post("/query")
async def handle_query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # Process main query
    answer = await process_query(request)
    
    # Store response ID for async notice check
    response_id = generate_response_id()
    
    # Check pending feedback in background
    background_tasks.add_task(
        check_and_store_pending_feedback,
        request.query,
        response_id,
        db
    )
    
    return QueryResponse(
        answer=answer,
        response_id=response_id,
        pending_feedback_notice=None  # Will be populated async
    )

# Separate endpoint to fetch notice
@router.get("/query/{response_id}/pending-feedback")
async def get_pending_feedback_notice(
    response_id: str,
    db: Session = Depends(get_db)
):
    notice = await fetch_stored_notice(response_id, db)
    return {"pending_feedback_notice": notice}
```

---

## 🧪 Testing Strategy

### Unit Tests

```python
# tests/test_intent_matcher.py

async def test_exact_match_shows_notice():
    """Test that exact same query shows notice."""
    matcher = FeedbackIntentMatcher()
    
    # Setup: create existing feedback with pending repair
    existing_feedback = create_feedback(
        query="What is the TER of Axis Bluechip Fund?",
        selected_categories=["F02"],
        feedback_text="TER value is incorrect",
        repair_status="open"
    )
    
    # Test: query with same intent
    notice = await matcher.check_pending_feedback(
        query="What is the TER of Axis Bluechip Fund?",
        session_id="test_session",
        db=test_db
    )
    
    assert notice is not None
    assert notice.has_pending_feedback == True
    assert notice.similarity_score >= 0.99

async def test_different_domain_no_notice():
    """Test that different domain queries don't match."""
    matcher = FeedbackIntentMatcher()
    
    # Setup: SEBI regulation feedback
    create_feedback(
        query="What is the SEBI circular on categorization?",
        domain="sebi_regulation",
        repair_status="open"
    )
    
    # Test: ESG query
    notice = await matcher.check_pending_feedback(
        query="What is the carbon footprint of the fund?",
        session_id="test_session",
        db=test_db
    )
    
    assert notice is None

async def test_resolved_repair_no_notice():
    """Test that resolved repairs don't show notice."""
    matcher = FeedbackIntentMatcher()
    
    create_feedback(
        query="What is the expense ratio?",
        repair_status="resolved"  # Resolved, not pending
    )
    
    notice = await matcher.check_pending_feedback(
        query="What is the expense ratio?",
        session_id="test_session",
        db=test_db
    )
    
    assert notice is None

async def test_cache_cleared_no_notice():
    """Test that clearing intent cache also clears pending feedback."""
    matcher = FeedbackIntentMatcher()
    
    # Create feedback
    create_feedback(query="Test query", repair_status="open")
    
    # First query should show notice
    notice1 = await matcher.check_pending_feedback("Test query", "s1", test_db)
    assert notice1 is not None
    
    # Clear intent cache (which should clear pending feedback cache)
    from app.engine.intent_cache import clear_cache
    clear_cache()
    
    # Second query should NOT show notice (cache was cleared)
    # This assumes cache clearing invalidates the pending feedback system
    # Implementation: check if a cache_clear_timestamp exists and is recent
    notice2 = await matcher.check_pending_feedback("Test query", "s2", test_db)
    # Decision: After cache clear, should we still show notice?
    # Option A: Still show (persistent data check)
    # Option B: Don't show (cache clear = full reset)
    # Assuming Option B per requirements
    assert notice2 is None or notice2.suppressed_by_cache_clear == True
```

---

### Integration Tests

```python
# tests/integration/test_feedback_notice_flow.py

async def test_end_to_end_feedback_notice():
    """Test complete flow from query to frontend display."""
    
    # Step 1: User A submits feedback
    feedback_response = client.post("/api/feedback", json={
        "response_id": "resp_123",
        "session_id": "session_a",
        "query_text": "What is the TER of Axis Bluechip Fund?",
        "selected_categories": ["F02"],
        "feedback_text": "TER value seems incorrect",
        "actor_id": "user_a"
    })
    assert feedback_response.status_code == 201
    
    # Step 2: Create unified evaluation record with pending repair
    create_unified_evaluation_record(
        response_id="resp_123",
        lifecycle_status="open",
        repair=True,
        repair_target="vector"
    )
    
    # Step 3: User B queries similar question
    query_response = client.post("/api/query", json={
        "query": "What is the expense ratio for Axis Bluechip Fund?",
        "session_id": "session_b"
    })
    
    assert query_response.status_code == 200
    data = query_response.json()
    
    # Step 4: Verify notice is present
    assert data["pending_feedback_notice"] is not None
    notice = data["pending_feedback_notice"]
    assert notice["has_pending_feedback"] == True
    assert notice["feedback_categories"] == ["F02"]
    assert notice["repair_lifecycle_status"] in ["open", "diagnosing"]
    
    # Step 5: Verify User B can still submit feedback
    feedback_response_b = client.post("/api/feedback", json={
        "response_id": data["response_id"],
        "session_id": "session_b",
        "query_text": "What is the expense ratio for Axis Bluechip Fund?",
        "selected_categories": ["F02"],
        "feedback_text": "I also noticed this issue",
        "actor_id": "user_b"
    })
    assert feedback_response_b.status_code == 201
```

---

### Load Testing

```python
# tests/load/test_concurrent_queries.py

import asyncio
from locust import HttpUser, task, between

class QueryUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def query_with_pending_feedback_check(self):
        """Simulate user query with pending feedback check."""
        response = self.client.post("/api/query", json={
            "query": "What is the TER of Axis Bluechip Fund?",
            "session_id": f"session_{self.user_id}"
        })
        
        # Verify response includes pending feedback check
        assert "pending_feedback_notice" in response.json()

# Run: locust -f tests/load/test_concurrent_queries.py --users 100 --spawn-rate 10
```

---

## 📈 Monitoring & Observability

### Metrics to Track

```python
# backend/app/feedback/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Counter: Total pending feedback checks
pending_feedback_checks_total = Counter(
    'pending_feedback_checks_total',
    'Total number of pending feedback checks',
    ['result']  # 'match_found', 'no_match', 'error'
)

# Histogram: Latency of pending feedback check
pending_feedback_check_duration = Histogram(
    'pending_feedback_check_duration_seconds',
    'Duration of pending feedback check in seconds'
)

# Gauge: Current number of pending repairs
pending_repairs_count = Gauge(
    'pending_repairs_count',
    'Current number of feedbacks with pending repairs'
)

# Usage in code
@pending_feedback_check_duration.time()
async def check_pending_feedback(self, query: str, db: Session):
    try:
        result = await self._check_impl(query, db)
        if result:
            pending_feedback_checks_total.labels(result='match_found').inc()
        else:
            pending_feedback_checks_total.labels(result='no_match').inc()
        return result
    except Exception as e:
        pending_feedback_checks_total.labels(result='error').inc()
        raise
```

---

### Logging Strategy

```python
# Structured logging for debugging

logger.info(
    "Pending feedback check",
    extra={
        "query_hash": query_hash,
        "session_id": session_id,
        "domain_intent": domain_intent,
        "similarity_threshold": threshold,
        "candidates_count": len(candidates),
        "matches_found": len(matches),
        "top_similarity": matches[0].similarity if matches else None,
        "duration_ms": duration_ms
    }
)
```

---

## 🚀 Deployment Strategy

### Phase 1: MVP (Week 1-2)

- Implement `FeedbackIntentMatcher` with in-memory caching
- Add basic database queries (no vector index yet)
- Frontend banner display
- Basic unit tests

**Success Criteria**: 
- Notice shows for exact query matches
- No performance degradation (< 50ms added latency)

---

### Phase 2: Production Hardening (Week 3-4)

- Add embedding column to `response_feedback`
- Implement domain-aware matching
- Add comprehensive error handling
- Load testing with 100 concurrent users
- Monitoring dashboard

**Success Criteria**:
- Handles 1000 QPS with < 100ms latency
- 99.9% uptime
- Zero false positives in testing

---

### Phase 3: Optimization (Week 5-6)

- Vector database index (pgvector or FAISS)
- Redis caching layer
- Machine learning similarity threshold tuning
- A/B testing for threshold values

**Success Criteria**:
- < 20ms latency for pending feedback check
- > 95% precision (low false positive rate)
- > 90% recall (catches similar queries)

---

## 🔄 Rollback Plan

### Rollback Triggers

1. Latency > 200ms for 5% of queries
2. Error rate > 1%
3. False positive rate > 10%
4. Database connection pool exhaustion

### Rollback Steps

```python
# Feature flag for instant disable
ENABLE_PENDING_FEEDBACK_NOTICE = os.getenv(
    "ENABLE_PENDING_FEEDBACK_NOTICE", 
    "false"
).lower() == "true"

async def handle_query(request: QueryRequest):
    # ... query processing ...
    
    pending_feedback_notice = None
    if ENABLE_PENDING_FEEDBACK_NOTICE:
        try:
            pending_feedback_notice = await check_pending_feedback(...)
        except Exception as e:
            logger.exception("Pending feedback check failed")
            # Graceful degradation: continue without notice
    
    return QueryResponse(pending_feedback_notice=pending_feedback_notice)
```

### Database Rollback

```sql
-- If embedding column causes issues
ALTER TABLE response_feedback DROP COLUMN IF EXISTS query_embedding;
DROP INDEX IF EXISTS idx_feedback_has_content;
```

---

## 📚 Documentation

### API Documentation

```yaml
# openapi.yaml

/api/query:
  post:
    summary: Submit a query
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              query:
                type: string
                example: "What is the TER of Axis Bluechip Fund?"
              session_id:
                type: string
    responses:
      200:
        content:
          application/json:
            schema:
              type: object
              properties:
                answer:
                  type: string
                response_id:
                  type: string
                pending_feedback_notice:
                  type: object
                  nullable: true
                  properties:
                    has_pending_feedback:
                      type: boolean
                      description: Whether similar feedback with pending repair exists
                    similarity_score:
                      type: number
                      format: float
                      description: Semantic similarity score (0-1)
                    feedback_categories:
                      type: array
                      items:
                        type: string
                      description: Failure taxonomy categories (F01-F12)
                    feedback_submitted_at:
                      type: string
                      format: date-time
                    repair_lifecycle_status:
                      type: string
                      enum: [open, diagnosing]
```

---

### User Documentation

**Title**: Understanding Pending Feedback Notices

When you submit a query, our system checks if other users have previously reported issues with similar queries. If a match is found and the repair is still pending, you'll see a notice in the feedback tab.

**What does this mean?**
- Another user found an issue with a similar query
- The issue is being investigated or repaired
- You can still submit feedback if you'd like to add details

**When will I see this notice?**
- Only when your query is semantically similar to existing feedback
- Only when the repair status is "open" or "diagnosing"
- Never if the intent cache has been recently cleared (for testing)

**Can I still submit feedback?**
- Yes! Your additional feedback helps us understand the issue better
- Your feedback will be linked to the existing repair tracking

---

## ✅ Acceptance Criteria Checklist

- [ ] Notice appears when query intent matches existing feedback with pending repair
- [ ] Notice does NOT appear when `selected_categories` is NULL/empty
- [ ] Notice does NOT appear when `feedback_text` is NULL/empty
- [ ] Notice does NOT appear when repair status is "resolved" or "monitoring"
- [ ] Notice does NOT appear when intent cache is cleared
- [ ] Notice does NOT appear to the same user who submitted original feedback
- [ ] Notice appears in feedback tab only, not in main response
- [ ] User can still submit feedback even when notice is shown
- [ ] Performance impact < 50ms per query
- [ ] Error rate < 0.1%
- [ ] False positive rate < 5%
- [ ] False negative rate < 10%
- [ ] System gracefully degrades if component fails
- [ ] Monitoring dashboard shows pending feedback check metrics
- [ ] Documentation updated for developers and users
- [ ] Unit tests cover all edge cases
- [ ] Integration tests verify end-to-end flow
- [ ] Load tests verify performance under load
- [ ] Security review completed
- [ ] Privacy impact assessment completed

---

## 🎓 Summary

This implementation plan provides a comprehensive, production-ready approach to adding pending feedback notifications. Key highlights:

1. **Semantic Intent Matching**: Uses embeddings for robust query similarity detection
2. **Domain-Aware**: Leverages existing intent classification to avoid cross-domain false positives
3. **Performance Optimized**: Multi-layer caching, vectorized operations, async I/O
4. **Privacy-First**: No sensitive query text exposed to other users
5. **Fail-Safe Design**: Graceful degradation if any component fails
6. **Observable**: Rich metrics and logging for debugging and monitoring
7. **Testable**: Comprehensive test coverage for edge cases
8. **Scalable**: Designed to handle production load with low latency

**Next Steps**:
1. Review and approve plan
2. Create Jira tickets for each component
3. Start with Phase 1 MVP implementation
4. Iterate based on testing and user feedback

---

**Document Version**: 1.0  
**Last Updated**: 2026-10-08  
**Author**: Kiro AI Assistant  
**Status**: Draft - Pending Review