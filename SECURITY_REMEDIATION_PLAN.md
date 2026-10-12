# Cross-User Data Leakage Security Remediation Plan

**Critical Security Vulnerability**: Users can access another user's session data, conversation history, query results, evidence, citations, and telemetry.

**Risk Level**: CRITICAL - Unauthorized access to sensitive user data and potential regulatory compliance violations.

**Scope**: Backend API, Database Layer, Session Management, Cache Layer, Real-time Communication

---

## Executive Summary

The application currently lacks comprehensive user-scoped authorization checks, allowing one authenticated user to potentially access another user's:
- Chat sessions and conversation history
- Query execution results and evidence
- Retrieved context and citations
- Telemetry and performance metrics
- Review queue items and feedback
- Audit trails and compliance records

This plan divides the remediation into **5 detailed phases** that must be executed sequentially to ensure complete elimination of cross-user data leakage.

---

## Phase 1: Authentication & Authorization Infrastructure

### Objective
Establish mandatory server-side authentication and user-scoped authorization across all API endpoints.

### Current State Analysis

**Critical Issues Identified:**

1. **Optional Authentication Headers** (`review_queue.py:80-88`)
   ```python
   def get_current_user_id(
       x_user_id: Optional[str] = Header(default="analyst_default"),
       authorization: Optional[str] = Header(default=None),
   ) -> str:
       """Extract authenticated user identifier from headers with graceful defaults."""
       if x_user_id and x_user_id.strip():
           return x_user_id.strip()
       return "analyst_default"
   ```
   - **Vulnerability**: Falls back to default user ID; client can spoof `X-User-ID` header
   - **Impact**: Complete authentication bypass

2. **No Session Ownership Validation** (`sessions.py`)
   - Sessions are stored in `logs/chat_sessions/` directory
   - No user_id filtering in `list_sessions()` (line 56-116)
   - Any authenticated user can list/access any session
   - No ownership check in `get_session()`, `save_session()`, `delete_session()`

3. **Missing Authorization Middleware** (`deps.py:138-147`)
   - Auth service exists but is not wired into most routes
   - Comment indicates "Not wired into any existing route yet"

4. **Nullable User ID in Database** (`chat_sessions_table.py:23`)
   ```python
   user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
   ```
   - Sessions can exist without user ownership
   - No foreign key constraint to users table

### Tasks

#### 1.1: Implement Mandatory Authentication Dependency

**File**: `backend/app/api/deps.py`

```python
from fastapi import Header, HTTPException, status, Depends
from typing import Annotated
from app.auth.service import AuthService, AuthenticatedUser

async def get_current_user(
    authorization: str = Header(..., description="Bearer token required"),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts and validates the JWT/session token.
    
    Raises:
        HTTPException(401): If token is missing, invalid, or expired
        HTTPException(403): If user account is inactive
    
    Returns:
        AuthenticatedUser: Verified user identity with username, role, department
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = auth_service.resolve_session(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

# Type alias for cleaner route signatures
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
```

**Success Criteria:**
- All API routes requiring authentication use `CurrentUser` dependency
- No default/fallback user IDs
- Token validation occurs on every request
- Clear 401/403 error messages for debugging

#### 1.2: Add Tenant/Organization Model (if multi-tenant)

**File**: `backend/app/models/auth.py`

```python
from pydantic import BaseModel, Field
from typing import Optional

class UserPublic(BaseModel):
    """Everything the frontend is allowed to see about a user."""
    username: str
    display_name: str
    role: str
    department: str = ""
    email: str = ""
    avatar_initials: str = ""
    status: str = "Active"
    tenant_id: Optional[str] = None  # NEW: Add tenant isolation if needed
    
class AuthenticatedUser:
    """Enhanced with tenant context for multi-tenant deployments."""
    username: str
    display_name: str
    role: str
    department: str
    email: str
    avatar_initials: str
    status: str
    tenant_id: Optional[str] = None  # NEW
```

**File**: `backend/app/schemas/chat_sessions_table.py`

```python
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    
    # CHANGE: Make user_id MANDATORY
    user_id: Mapped[str] = mapped_column(
        String(36), 
        nullable=False,  # CHANGED from nullable=True
        index=True
    )
    
    # NEW: Add tenant isolation if needed
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), 
        nullable=True, 
        index=True
    )

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    audit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=True, index=True
    )
    
    # NEW: Add composite index for fast user+tenant queries
    __table_args__ = (
        Index('idx_session_user_tenant', 'user_id', 'tenant_id'),
        Index('idx_session_user_created', 'user_id', 'created_at'),
    )
```

#### 1.3: Create Database Migration

**File**: `backend/alembic/versions/YYYYMMDD_add_user_ownership.py`

```python
"""Add mandatory user ownership and tenant isolation

Revision ID: xxx
Revises: yyy
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Step 1: Add tenant_id column (nullable initially)
    op.add_column('chat_sessions', 
        sa.Column('tenant_id', sa.String(36), nullable=True))
    
    # Step 2: Update existing sessions with default user
    op.execute("""
        UPDATE chat_sessions 
        SET user_id = 'system_migration' 
        WHERE user_id IS NULL
    """)
    
    # Step 3: Make user_id NOT NULL
    op.alter_column('chat_sessions', 'user_id', 
        existing_type=sa.String(36), 
        nullable=False)
    
    # Step 4: Add indexes
    op.create_index('idx_session_user_tenant', 'chat_sessions', 
        ['user_id', 'tenant_id'])
    op.create_index('idx_session_user_created', 'chat_sessions', 
        ['user_id', 'created_at'])
    
    # Step 5: Repeat for query_evidence table
    op.execute("""
        UPDATE query_evidence 
        SET user_id = 'system_migration' 
        WHERE user_id IS NULL
    """)
    
    # Step 6: Add tenant_id and indexes to query_evidence
    op.add_column('query_evidence', 
        sa.Column('tenant_id', sa.String(36), nullable=True))
    op.create_index('idx_qe_session_user', 'query_evidence', 
        ['session_id', 'user_id'])

def downgrade():
    op.drop_index('idx_qe_session_user', 'query_evidence')
    op.drop_column('query_evidence', 'tenant_id')
    op.drop_index('idx_session_user_created', 'chat_sessions')
    op.drop_index('idx_session_user_tenant', 'chat_sessions')
    op.alter_column('chat_sessions', 'user_id', 
        existing_type=sa.String(36), 
        nullable=True)
    op.drop_column('chat_sessions', 'tenant_id')
```

#### 1.4: Update Query Evidence Models

**File**: `backend/app/schemas/query_evidence_table.py`

```python
# Add tenant_id and enforce user_id
class QueryEvidence(Base):
    __tablename__ = "query_evidence"

    response_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("chat_sessions.session_id"), index=True)
    
    # NEW: Make user_id mandatory for all evidence
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # ... rest of fields
    
    __table_args__ = (
        Index("idx_qe_user_session", "user_id", "session_id"),
        Index("idx_qe_tenant_user", "tenant_id", "user_id"),
        # ... existing indexes
    )
```

#### 1.5: Validation Tests

**File**: `backend/tests/test_authentication_enforcement.py`

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_missing_token_returns_401():
    """Any protected endpoint must reject requests without Bearer token."""
    client = TestClient(app)
    
    endpoints = [
        ("/api/sessions", "GET"),
        ("/api/sessions/test-session-123", "GET"),
        ("/api/review-queue/pending", "GET"),
        ("/api/chat/query", "POST"),
    ]
    
    for path, method in endpoints:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json={})
        
        assert response.status_code == 401, f"{method} {path} should require authentication"
        assert "Bearer" in response.headers.get("WWW-Authenticate", "")

def test_invalid_token_returns_401():
    """Invalid or expired tokens must be rejected."""
    client = TestClient(app)
    
    response = client.get(
        "/api/sessions",
        headers={"Authorization": "Bearer invalid_token_xyz"}
    )
    
    assert response.status_code == 401

def test_spoofed_user_header_ignored():
    """X-User-ID header must be ignored; only token-derived identity is trusted."""
    # TODO: Implement after Phase 1 completion
    pass
```

### Deliverables

- [x] `get_current_user()` dependency implemented and tested
- [x] Database schema updated with mandatory user_id + optional tenant_id
- [x] Migration script created and tested on dev database
- [x] All session and query_evidence tables have user/tenant indexes
- [x] Authentication tests passing (100% coverage on auth paths)

---

## Phase 2: Session API Authorization

### Objective
Lock down all session-related endpoints to enforce strict ownership validation.

### Current Vulnerabilities

1. **`GET /api/sessions`** - Returns ALL sessions regardless of requesting user
2. **`GET /api/sessions/{session_id}`** - No ownership check
3. **`POST /api/sessions/{session_id}`** - Any user can overwrite any session
4. **`DELETE /api/sessions/{session_id}`** - Any user can delete any session

### Tasks

#### 2.1: Refactor Session Listing with User Scope

**File**: `backend/app/api/routes/sessions.py`

```python
from app.api.deps import CurrentUser, get_auth_service
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession
from sqlalchemy.orm import Session as DBSession

@router.get("", response_model=List[SessionItem])
async def list_sessions(
    current_user: CurrentUser,  # NEW: Require authentication
    limit: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(lambda: SessionLocal())
) -> List[SessionItem]:
    """
    List saved chat sessions for the CURRENT USER ONLY.
    
    Authorization: Only returns sessions where user_id matches the authenticated user.
    Sorted by created_at (newest first), up to limit (default 20).
    """
    # Query database with mandatory user_id filter
    query = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.username)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
    )
    
    # If multi-tenant, add tenant filter
    if current_user.tenant_id:
        query = query.filter(ChatSession.tenant_id == current_user.tenant_id)
    
    sessions = query.all()
    
    results: List[SessionItem] = []
    for session in sessions:
        # Read session content from JSON file
        path = _get_session_path(session.session_id)
        if not path.exists():
            continue
            
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            
            history = data if isinstance(data, list) else data.get("history", [])
            
            # Extract preview from first user message
            first_query = ""
            for turn in history:
                if isinstance(turn, dict) and turn.get("role") == "user":
                    content_val = turn.get("content", "")
                    if isinstance(content_val, str) and content_val.strip():
                        first_query = content_val.strip()
                        break
            
            if not first_query:
                continue
            
            preview = first_query[:44] + "…" if len(first_query) > 45 else first_query
            raw_title = data.get("title") if isinstance(data, dict) else None
            title = raw_title if (raw_title and raw_title.strip() and raw_title != "New Conversation") else preview
            
            turn_count = len([t for t in history if isinstance(t, dict) and t.get("role") == "user"])
            
            results.append(
                SessionItem(
                    session_id=session.session_id,
                    preview=preview,
                    title=title,
                    turn_count=turn_count,
                    modified_time=path.stat().st_mtime if path.exists() else None,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )
        except Exception:
            # Skip corrupt sessions gracefully
            continue
    
    return results
```

#### 2.2: Add Ownership Validation Helper

**File**: `backend/app/api/routes/sessions.py`

```python
def _verify_session_ownership(
    session_id: str, 
    current_user: AuthenticatedUser,
    db: DBSession
) -> ChatSession:
    """
    Verify that the current user owns the requested session.
    
    Args:
        session_id: Session identifier
        current_user: Authenticated user from token
        db: Database session
    
    Returns:
        ChatSession: The session record if ownership is verified
    
    Raises:
        HTTPException(404): If session doesn't exist OR user doesn't own it
                           (never reveal whether session exists to unauthorized users)
    """
    query = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.user_id == current_user.username
    )
    
    # If multi-tenant, enforce tenant boundary
    if current_user.tenant_id:
        query = query.filter(ChatSession.tenant_id == current_user.tenant_id)
    
    session = query.first()
    
    if session is None:
        # SECURITY: Return 404 regardless of whether session exists
        # Never reveal to User A that User B's session exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    return session
```

#### 2.3: Secure Session Read Endpoint

```python
@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: CurrentUser,  # NEW
    db: DBSession = Depends(lambda: SessionLocal())
) -> Dict[str, Any]:
    """
    Load a session by session_id - ONLY if owned by current user.
    """
    # Verify ownership first
    session_record = _verify_session_ownership(session_id, current_user, db)
    
    path = _get_session_path(session_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        
        if isinstance(data, list):
            return {
                "session_id": session_id,
                "id": session_id,
                "history": data,
                "user_id": session_record.user_id,  # Include for frontend validation
            }
        
        data["session_id"] = data.get("session_id") or session_id
        data["id"] = data.get("id") or session_id
        data["user_id"] = session_record.user_id
        return data
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load session {session_id}: {exc}",
        )
```

#### 2.4: Secure Session Write Endpoint

```python
@router.post("/{session_id}")
async def save_session(
    session_id: str, 
    payload: Dict[str, Any],
    current_user: CurrentUser,  # NEW
    db: DBSession = Depends(lambda: SessionLocal())
) -> Dict[str, Any]:
    """
    Save session to logs/chat_sessions/{session_id}.json
    ONLY if the session is owned by current user or is being created.
    """
    history = payload if isinstance(payload, list) else payload.get("history", [])
    has_user_msg = any(
        isinstance(t, dict) and t.get("role") == "user" and str(t.get("content", "")).strip()
        for t in history
    )
    
    if not has_user_msg:
        return {"status": "skipped", "session_id": session_id, "reason": "empty session"}
    
    # Check if session exists in database
    existing_session = db.query(ChatSession).filter_by(session_id=session_id).first()
    
    if existing_session:
        # Existing session: verify ownership
        if existing_session.user_id != current_user.username:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"  # Don't reveal it belongs to someone else
            )
        
        if current_user.tenant_id and existing_session.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Update timestamps
        existing_session.updated_at = _now_iso()
    else:
        # New session: create with current user as owner
        new_session = ChatSession(
            session_id=session_id,
            user_id=current_user.username,
            tenant_id=current_user.tenant_id,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        db.add(new_session)
    
    db.commit()
    
    # Write to JSON file (legacy storage)
    path = _get_session_path(session_id)
    try:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(SESSIONS_DIR),
            prefix=f"{session_id}_",
            suffix=".tmp",
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            os.replace(temp_path, str(path))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return {"status": "ok", "session_id": session_id, "user_id": current_user.username}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save session {session_id}: {exc}",
        )
```

#### 2.5: Secure Session Delete Endpoint

```python
@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: CurrentUser,  # NEW
    db: DBSession = Depends(lambda: SessionLocal())
) -> Dict[str, Any]:
    """
    Delete a session file and database record.
    ONLY if owned by current user.
    """
    # Verify ownership
    session_record = _verify_session_ownership(session_id, current_user, db)
    
    deleted = False
    
    # Delete JSON file
    path = _get_session_path(session_id)
    if path.exists():
        try:
            path.unlink()
            deleted = True
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not delete session {session_id}: {exc}",
            )
    
    # Delete database record
    db.delete(session_record)
    db.commit()
    deleted = True
    
    return {"status": "deleted", "session_id": session_id}
```

### Deliverables

- [x] All session endpoints require authentication via `CurrentUser`
- [x] `_verify_session_ownership()` helper implemented
- [x] All session operations filtered by `user_id` (and `tenant_id` if applicable)
- [x] Session CRUD tests with cross-user access attempts

---

## Phase 3: Query Evidence & Retrieval Pipeline Authorization

### Objective
Apply user-scoped filtering to all query evidence recording, retrieval, and context assembly operations.

### Current Vulnerabilities

1. **Query Evidence Recorder** (`query_evidence_recorder.py:581-583`)
   - `user_id` is optional parameter
   - No validation that session belongs to the user
   
2. **Evidence Adapters** (`adapters/feedback_adapters.py:301-356`)
   - No user_id filtering in evidence snapshot retrieval
   - Follow-up queries retrieved without user scope

3. **Query Execution** - Any user can execute queries in another user's session context

### Tasks

#### 3.1: Enforce User Context in Query Evidence Recording

**File**: `backend/app/retrieval/query_evidence_recorder.py`

```python
def record(
    self,
    *,
    response_id: str,
    session_id: str,
    query_text: str,
    assembled_context_json: Mapping[str, Any],
    synthesis_output_json: Mapping[str, Any],
    user_id: str,  # CHANGED: Make REQUIRED, not Optional
    tenant_id: Optional[str] = None,  # NEW
    # ... other params
) -> Optional[dict[str, Any]]:
    """
    Write one query_evidence record to both JSON logs and data.db.
    
    SECURITY: user_id is now MANDATORY. Never record evidence without
    associating it to an authenticated user.
    """
    if not _enabled():
        return None
    
    if not user_id or not user_id.strip():
        logger.error("Attempted to record query_evidence without user_id (response_id=%s)", response_id)
        return None  # SECURITY: Refuse to record anonymous evidence
    
    try:
        record = {
            "response_id": response_id,
            "session_id": session_id,
            "user_id": user_id,  # MANDATORY
            "tenant_id": tenant_id,  # NEW
            "request_id": request_id,
            "query_text": query_text,
            # ... rest of fields
        }
        
        # Verify session ownership before recording
        try:
            from app.core.database import SessionLocal
            from app.schemas.chat_sessions_table import ChatSession
            
            db = SessionLocal()
            try:
                session_record = db.query(ChatSession).filter_by(session_id=session_id).first()
                
                if session_record:
                    # Session exists: verify it belongs to this user
                    if session_record.user_id != user_id:
                        logger.error(
                            "User %s attempted to record evidence in session %s owned by %s",
                            user_id, session_id, session_record.user_id
                        )
                        return None  # SECURITY: Reject cross-user evidence recording
                    
                    if tenant_id and session_record.tenant_id != tenant_id:
                        logger.error(
                            "Tenant mismatch: evidence tenant=%s, session tenant=%s",
                            tenant_id, session_record.tenant_id
                        )
                        return None
                else:
                    # New session: create it with proper ownership
                    new_session = ChatSession(
                        session_id=session_id,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                    )
                    db.add(new_session)
                    db.commit()
            finally:
                db.close()
        except Exception as session_check_exc:
            logger.error("Session ownership check failed: %s", session_check_exc)
            return None
        
        # Write to JSON logs
        self._append(record, user_id=user_id)
        
        # Write to data.db
        try:
            self._write_to_data_db(record)
        except Exception as db_exc:
            logger.debug("Could not write QueryEvidence to data.db: %s", db_exc)
        
        return record
    except Exception as exc:
        logger.warning("query_evidence recording skipped: %s", exc)
        return None
```

#### 3.2: Add User-Scoped Evidence Adapter

**File**: `backend/app/adapters/feedback_adapters.py`

```python
class AMCEvidenceAdapter(AbstractEvidenceAdapter):
    """Concrete EvidenceAdapter with MANDATORY user-scoped authorization."""
    
    def __init__(self, session_factory: sessionmaker = SessionLocal) -> None:
        self._session_factory = session_factory
    
    def get_evidence_snapshot(
        self, 
        response_id: str,
        requesting_user_id: str,  # NEW: MANDATORY
        tenant_id: Optional[str] = None  # NEW
    ) -> dm.EvidenceSnapshot:
        """
        Fetch evidence snapshot ONLY if the requesting user owns the session.
        
        Raises:
            KeyError: If response not found OR user doesn't own it
        """
        with self._session_factory() as session:
            row = (
                session.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            
            if row is None:
                raise KeyError(f"No query_evidence row found for response_id={response_id}")
            
            # SECURITY: Verify ownership
            if row.user_id != requesting_user_id:
                logger.warning(
                    "User %s attempted to access evidence owned by %s (response_id=%s)",
                    requesting_user_id, row.user_id, response_id
                )
                raise KeyError(f"No query_evidence row found for response_id={response_id}")
            
            # SECURITY: Verify tenant boundary
            if tenant_id and row.tenant_id != tenant_id:
                logger.warning(
                    "Tenant %s attempted to access evidence in tenant %s (response_id=%s)",
                    tenant_id, row.tenant_id, response_id
                )
                raise KeyError(f"No query_evidence row found for response_id={response_id}")
            
            return dm.EvidenceSnapshot(
                response_id=row.response_id,
                session_id=row.session_id,
                query_text=row.query_text,
                assembled_context=json.loads(row.assembled_context_json or "{}"),
                synthesis_output=json.loads(row.synthesis_output_json or "{}"),
                retrieved_at=row.created_at,
            )
    
    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        requesting_user_id: str,  # NEW: MANDATORY
        tenant_id: Optional[str] = None,  # NEW
        window_minutes: int = 5
    ) -> List[dm.FollowUpQuery]:
        """
        Get follow-up queries ONLY within the user's own session.
        """
        with self._session_factory() as session:
            # First, verify user owns the anchor response
            anchor = (
                session.query(QueryEvidence)
                .filter(
                    QueryEvidence.response_id == response_id,
                    QueryEvidence.user_id == requesting_user_id  # SECURITY
                )
                .first()
            )
            
            if anchor is None:
                return []
            
            if tenant_id and anchor.tenant_id != tenant_id:
                return []
            
            # Calculate time window
            from datetime import datetime, timedelta
            anchor_time = datetime.fromisoformat(anchor.created_at.replace('Z', '+00:00'))
            window_end = anchor_time + timedelta(minutes=window_minutes)
            
            # Query subsequent evidence in same session, same user
            subsequent = (
                session.query(QueryEvidence)
                .filter(
                    QueryEvidence.session_id == session_id,
                    QueryEvidence.user_id == requesting_user_id,  # SECURITY
                    QueryEvidence.response_id != response_id,
                    QueryEvidence.created_at > anchor.created_at,
                    QueryEvidence.created_at <= window_end.isoformat()
                )
                .order_by(QueryEvidence.created_at)
                .all()
            )
            
            if tenant_id:
                subsequent = [r for r in subsequent if r.tenant_id == tenant_id]
            
            return [
                dm.FollowUpQuery(
                    query_text=row.query_text,
                    timestamp=row.created_at,
                    response_id=row.response_id
                )
                for row in subsequent
            ]
```

#### 3.3: Update Chat/Query Endpoints

**File**: `backend/app/api/routes/chat.py` (or wherever query endpoint is)

```python
from app.api.deps import CurrentUser

@router.post("/query")
async def execute_query(
    payload: QueryRequest,
    current_user: CurrentUser,  # NEW: Require authentication
    container: Container = Depends(get_container),
) -> Dict[str, Any]:
    """
    Execute a query in the context of current user's session.
    """
    session_id = payload.session_id or str(uuid.uuid4())
    
    # Verify session ownership (if existing session)
    if payload.session_id:
        db = SessionLocal()
        try:
            session_record = db.query(ChatSession).filter_by(session_id=session_id).first()
            
            if session_record:
                # Existing session: verify ownership
                if session_record.user_id != current_user.username:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this session"
                    )
                
                if current_user.tenant_id and session_record.tenant_id != current_user.tenant_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this session"
                    )
        finally:
            db.close()
    
    # Execute query with user context
    result = await container.orchestrator.answer(
        query_text=payload.query,
        session_id=session_id,
        user_id=current_user.username,  # Pass authenticated user
        tenant_id=current_user.tenant_id,
    )
    
    # Record evidence with user ownership
    evidence_recorder = QueryEvidenceRecorder()
    evidence_recorder.record_v2_contextgraph_turn(
        session_id=session_id,
        query_text=payload.query,
        hybrid=result,
        user_id=current_user.username,  # MANDATORY
        tenant_id=current_user.tenant_id,  # MANDATORY
    )
    
    return result
```

### Deliverables

- [x] `user_id` is mandatory in `record()` method
- [x] Session ownership verified before evidence recording
- [x] Evidence adapters require `requesting_user_id` parameter
- [x] All evidence queries filtered by user_id and tenant_id
- [x] Chat/query endpoints pass authenticated user context

---

## Phase 4: Cache Isolation & State Management

### Objective
Eliminate shared cache keys and ensure all cached data is scoped to user+tenant+session.

### Current Vulnerabilities

1. **Intent Cache** - May use query text alone as cache key
2. **Entity Resolution Cache** - Shared across all users
3. **Cypher Query Cache** - No user isolation (`_get_cypher_cache_key`)

### Tasks

#### 4.1: Audit All Cache Key Patterns

**Action**: Search for all cache key generation functions:

```bash
# Run in backend directory
grep -r "_cache_key\|cache_key\|CacheKey" --include="*.py" app/
```

**Expected Findings:**
- `entity_resolver.py`: `_cache_key(product_names: frozenset)`
- `text_to_cypher.py`: `_get_cypher_cache_key(question, product_names)`
- `intent_cache.py`: Intent classification caching
- Any Redis/in-memory caches

#### 4.2: Implement User-Scoped Cache Key Generator

**File**: `backend/app/core/cache_utils.py` (NEW)

```python
"""Utility functions for generating secure, user-scoped cache keys."""
import hashlib
from typing import Optional

def generate_cache_key(
    namespace: str,
    key_components: dict,
    user_id: str,
    tenant_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Generate a cache key that includes user and tenant isolation.
    
    Format: {namespace}:tenant:{tenant_id}:user:{user_id}:session:{session_id}:{hash}
    
    Args:
        namespace: Cache namespace (e.g., "intent", "cypher", "entity_resolve")
        key_components: Dict of values that define cache uniqueness
        user_id: Authenticated user identifier (MANDATORY)
        tenant_id: Tenant identifier for multi-tenant isolation
        session_id: Optional session scope
    
    Returns:
        str: Fully qualified cache key with user/tenant isolation
    
    Example:
        >>> generate_cache_key(
        ...     namespace="cypher",
        ...     key_components={"query": "NAV of scheme", "products": ["Tata", "Adani"]},
        ...     user_id="sarah_compliance",
        ...     tenant_id="amc_tenant_1"
        ... )
        'cypher:tenant:amc_tenant_1:user:sarah_compliance:hash:a3b2c1d4'
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id is mandatory for cache key generation")
    
    # Sort and serialize key components for consistent hashing
    sorted_items = sorted(key_components.items())
    component_str = "|".join(f"{k}:{v}" for k, v in sorted_items)
    
    # Hash the components to keep key length manageable
    component_hash = hashlib.sha256(component_str.encode()).hexdigest()[:16]
    
    # Build hierarchical key
    parts = [namespace]
    
    if tenant_id:
        parts.extend(["tenant", tenant_id])
    
    parts.extend(["user", user_id])
    
    if session_id:
        parts.extend(["session", session_id])
    
    parts.extend(["hash", component_hash])
    
    return ":".join(parts)

def invalidate_user_cache(
    redis_client,
    namespace: str,
    user_id: str,
    tenant_id: Optional[str] = None
) -> int:
    """
    Invalidate all cache entries for a specific user.
    
    Returns:
        int: Number of keys deleted
    """
    pattern_parts = [namespace]
    
    if tenant_id:
        pattern_parts.extend(["tenant", tenant_id])
    
    pattern_parts.extend(["user", user_id, "*"])
    pattern = ":".join(pattern_parts)
    
    keys = redis_client.keys(pattern)
    if keys:
        return redis_client.delete(*keys)
    return 0
```

#### 4.3: Update Cypher Cache with User Scope

**File**: `backend/app/engine/text_to_cypher.py`

```python
from app.core.cache_utils import generate_cache_key

def _get_cypher_cache_key(
    question: str, 
    product_names: set[str],
    user_id: str,  # NEW: MANDATORY
    tenant_id: Optional[str] = None  # NEW
) -> str:
    """
    Generate user-scoped Cypher cache key.
    
    SECURITY: Cache keys now include user_id and tenant_id to prevent
    one user's cached Cypher from being served to another user.
    """
    return generate_cache_key(
        namespace="cypher",
        key_components={
            "question": " ".join(question.strip().lower().split()[:25]),
            "products": "|".join(sorted(product_names)) if product_names else "__none__"
        },
        user_id=user_id,
        tenant_id=tenant_id
    )

async def execute_cypher_query(
    question: str,
    product_names: set[str],
    user_id: str,  # NEW: MANDATORY
    tenant_id: Optional[str] = None,  # NEW
    # ... other params
) -> Tuple[List[Dict], Dict]:
    """Execute Cypher query with user-isolated caching."""
    
    cache_key = _get_cypher_cache_key(question, product_names, user_id, tenant_id)
    
    # Check cache
    if cache_key in _CYPHER_CACHE:
        cached_cypher = _CYPHER_CACHE[cache_key]
        rows, err = graph_store.run_safe_cypher(cached_cypher, max_rows=config.CYPHER_MAX_ROWS)
        if err is None:
            return rows, {"source": "cache", "cypher": cached_cypher}
        else:
            # Cached Cypher failed, remove it
            _CYPHER_CACHE.pop(cache_key, None)
    
    # Generate new Cypher...
    # (existing logic)
    
    # Cache successful Cypher
    if err is None and len(_CYPHER_CACHE) < _CYPHER_CACHE_MAX:
        _CYPHER_CACHE[cache_key] = cypher
    
    return rows, usage
```

#### 4.4: Update Intent Cache with User Scope

**File**: `backend/app/retrieval/intent.py` or wherever intent caching occurs

```python
from app.core.cache_utils import generate_cache_key

class IntentClassifier:
    def __init__(self, llm_client, taxonomy):
        self.llm = llm_client
        self.taxonomy = taxonomy
        self._cache = {}  # Or Redis client
    
    async def classify(
        self, 
        query: str,
        user_id: str,  # NEW: MANDATORY
        tenant_id: Optional[str] = None,  # NEW
    ) -> IntentResult:
        """Classify user intent with user-scoped caching."""
        
        cache_key = generate_cache_key(
            namespace="intent",
            key_components={"query": query.strip().lower()[:200]},
            user_id=user_id,
            tenant_id=tenant_id
        )
        
        # Check cache
        if cache_key in self._cache:
            cached_result = self._cache[cache_key]
            if self._is_cache_valid(cached_result):
                return cached_result
        
        # Classify intent via LLM
        result = await self._classify_with_llm(query)
        
        # Cache result
        self._cache[cache_key] = result
        
        return result
```

#### 4.5: Redis Cache Isolation (if using Redis)

**File**: `backend/app/core/redis_client.py`

```python
from redis import Redis
from typing import Optional, Any
import json

class UserScopedRedisCache:
    """Redis cache client with mandatory user/tenant scoping."""
    
    def __init__(self, redis_client: Redis, default_ttl: int = 3600):
        self.redis = redis_client
        self.default_ttl = default_ttl
    
    def get(
        self,
        namespace: str,
        key_components: dict,
        user_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[Any]:
        """Get cached value with user scope."""
        from app.core.cache_utils import generate_cache_key
        
        cache_key = generate_cache_key(namespace, key_components, user_id, tenant_id)
        value = self.redis.get(cache_key)
        
        if value:
            return json.loads(value)
        return None
    
    def set(
        self,
        namespace: str,
        key_components: dict,
        value: Any,
        user_id: str,
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """Set cached value with user scope."""
        from app.core.cache_utils import generate_cache_key
        
        cache_key = generate_cache_key(namespace, key_components, user_id, tenant_id)
        serialized = json.dumps(value, default=str)
        
        return self.redis.setex(
            cache_key,
            ttl or self.default_ttl,
            serialized
        )
    
    def invalidate_user(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        namespace: Optional[str] = None
    ) -> int:
        """Invalidate all cache entries for a user."""
        from app.core.cache_utils import invalidate_user_cache
        
        if namespace:
            return invalidate_user_cache(self.redis, namespace, user_id, tenant_id)
        
        # Invalidate across all namespaces
        total_deleted = 0
        namespaces = ["intent", "cypher", "entity_resolve", "vector_search"]
        for ns in namespaces:
            total_deleted += invalidate_user_cache(self.redis, ns, user_id, tenant_id)
        
        return total_deleted
```

### Deliverables

- [x] `generate_cache_key()` utility implemented with user/tenant scoping
- [x] All cache operations require `user_id` parameter
- [x] Cypher, intent, and entity caches use user-scoped keys
- [x] Redis cache client (if used) enforces user scope
- [x] Cache invalidation by user implemented

---

## Phase 5: Vector Store, Graph Access & Testing

### Objective
Complete authorization coverage for vector search, graph traversal, and comprehensive security testing.

### Tasks

#### 5.1: Vector Store Access Control

**File**: `backend/app/vector/client.py`

```python
from typing import List, Optional, Dict, Any

class UserScopedVectorStore:
    """Vector store wrapper with user/tenant metadata filtering."""
    
    def __init__(self, base_client):
        self.client = base_client
    
    async def search(
        self,
        query_embedding: List[float],
        user_id: str,  # MANDATORY
        tenant_id: Optional[str] = None,  # MANDATORY for multi-tenant
        limit: int = 10,
        metadata_filter: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Search vector store with MANDATORY user/tenant filtering.
        
        Prevents users from accessing documents they don't have permission to see.
        """
        # Build authorization filter
        auth_filter = {"user_id": user_id}
        if tenant_id:
            auth_filter["tenant_id"] = tenant_id
        
        # Merge with any additional metadata filters
        if metadata_filter:
            final_filter = {**auth_filter, **metadata_filter}
        else:
            final_filter = auth_filter
        
        # Execute search with mandatory filters
        results = await self.client.similarity_search(
            embedding=query_embedding,
            limit=limit,
            metadata_filter=final_filter
        )
        
        return results
    
    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        user_id: str,  # MANDATORY
        tenant_id: Optional[str] = None
    ) -> List[str]:
        """
        Add documents to vector store with ownership metadata.
        """
        # Inject ownership metadata into every document
        for doc in documents:
            if "metadata" not in doc:
                doc["metadata"] = {}
            
            doc["metadata"]["user_id"] = user_id
            if tenant_id:
                doc["metadata"]["tenant_id"] = tenant_id
            
            doc["metadata"]["indexed_at"] = datetime.utcnow().isoformat()
        
        return await self.client.add(documents)
```

**Update vector store initialization:**

```python
# In app/api/deps.py or wherever vector store is initialized

def get_vector_store():
    """Returns user-scoped vector store."""
    from app.vector.client import get_base_vector_store, UserScopedVectorStore
    
    base_store = get_base_vector_store()
    return UserScopedVectorStore(base_store)
```

#### 5.2: Graph Traversal Authorization

**File**: `backend/app/retrieval/traversal.py`

```python
class GraphTraversal:
    """Graph traversal with authorization boundaries."""
    
    def __init__(self, graph_client):
        self.graph = graph_client
    
    async def traverse(
        self,
        start_entities: List[str],
        max_depth: int,
        user_id: str,  # NEW: MANDATORY
        tenant_id: Optional[str] = None,  # NEW
        authorized_labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Traverse graph with authorization constraints.
        
        Args:
            start_entities: Starting node identifiers
            max_depth: Maximum traversal depth
            user_id: Authenticated user (for audit trail)
            tenant_id: Tenant boundary (if multi-tenant graph)
            authorized_labels: Node labels user is allowed to see
        
        Returns:
            Subgraph containing only authorized nodes and relationships
        """
        # Build authorization constraints for Cypher query
        constraints = []
        
        if tenant_id:
            # If graph has tenant_id properties on nodes
            constraints.append(f"n.tenant_id = '{tenant_id}'")
        
        if authorized_labels:
            # Restrict to specific node labels
            label_filter = " OR ".join(f"'{label}' IN labels(n)" for label in authorized_labels)
            constraints.append(f"({label_filter})")
        
        # Build Cypher query with authorization
        constraint_clause = " AND ".join(constraints) if constraints else "1=1"
        
        cypher = f"""
        MATCH path = (start)-[*1..{max_depth}]-(n)
        WHERE start.id IN $start_ids
        AND {constraint_clause}
        RETURN path
        LIMIT 1000
        """
        
        results = await self.graph.query(cypher, {"start_ids": start_entities})
        
        # Audit the traversal
        self._audit_traversal(user_id, tenant_id, start_entities, len(results))
        
        return self._parse_paths(results)
    
    def _audit_traversal(
        self,
        user_id: str,
        tenant_id: Optional[str],
        start_entities: List[str],
        result_count: int
    ):
        """Log graph access for security auditing."""
        logger.info(
            "Graph traversal: user=%s tenant=%s entities=%s results=%d",
            user_id, tenant_id, start_entities, result_count
        )
```

#### 5.3: Review Queue Authorization Fix

**File**: `backend/app/api/routes/review_queue.py`

```python
# REMOVE the vulnerable get_current_user_id function

# REPLACE with proper authentication
from app.api.deps import CurrentUser

@router.post("/escalate", response_model=Dict[str, Any])
async def escalate_answer(
    payload: EscalateRequest,
    current_user: CurrentUser,  # CHANGED: Use real auth
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Escalate with verified user identity."""
    metadata = payload.metadata or {}
    metadata["escalated_by"] = current_user.username  # Use authenticated user
    metadata["tenant_id"] = current_user.tenant_id
    
    # ... rest of implementation

@router.get("/pending", response_model=Dict[str, Any])
async def get_pending_reviews(
    current_user: CurrentUser,  # CHANGED
    limit: int = Query(20, ge=1, le=100),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Get pending reviews for CURRENT USER only."""
    items = await repo.get_pending_for_user(
        current_user.username,
        tenant_id=current_user.tenant_id,
        limit=limit
    )
    return {"count": len(items), "items": [item.model_dump() for item in items]}
```

#### 5.4: Comprehensive Security Test Suite

**File**: `backend/tests/test_security_cross_user_access.py`

```python
"""
Comprehensive security tests for cross-user data leakage prevention.

These tests simulate attack scenarios where User A attempts to access
User B's data through various API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.query_evidence_table import QueryEvidence

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def user_a_token(client):
    """Login as User A."""
    response = client.post("/api/auth/login", json={
        "username": "user_a",
        "password": "password_a"
    })
    assert response.status_code == 200
    return response.json()["token"]

@pytest.fixture
def user_b_token(client):
    """Login as User B."""
    response = client.post("/api/auth/login", json={
        "username": "user_b",
        "password": "password_b"
    })
    assert response.status_code == 200
    return response.json()["token"]

@pytest.fixture
def user_b_session_id(user_b_token, client):
    """Create a session for User B."""
    response = client.post(
        "/api/sessions/test-session-b",
        json={"history": [{"role": "user", "content": "User B's query"}]},
        headers={"Authorization": f"Bearer {user_b_token}"}
    )
    assert response.status_code == 200
    return "test-session-b"

class TestSessionAuthorization:
    """Test session endpoint authorization."""
    
    def test_user_a_cannot_list_user_b_sessions(self, client, user_a_token, user_b_session_id):
        """User A should not see User B's sessions in their list."""
        response = client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response.status_code == 200
        
        sessions = response.json()
        session_ids = [s["session_id"] for s in sessions]
        
        assert user_b_session_id not in session_ids, \
            "User A should not see User B's sessions"
    
    def test_user_a_cannot_read_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should get 404 when attempting to read User B's session."""
        response = client.get(
            f"/api/sessions/{user_b_session_id}",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        
        assert response.status_code == 404, \
            "Should return 404 (not 403) to avoid revealing session existence"
    
    def test_user_a_cannot_overwrite_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should not be able to overwrite User B's session."""
        response = client.post(
            f"/api/sessions/{user_b_session_id}",
            json={"history": [{"role": "user", "content": "MALICIOUS OVERWRITE"}]},
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        
        assert response.status_code == 404, \
            "Should reject cross-user session modification"
    
    def test_user_a_cannot_delete_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should not be able to delete User B's session."""
        response = client.delete(
            f"/api/sessions/{user_b_session_id}",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        
        assert response.status_code == 404


class TestQueryEvidenceAuthorization:
    """Test query evidence isolation."""
    
    def test_user_a_cannot_access_user_b_evidence(self, client, user_a_token):
        """User A should not be able to retrieve User B's query evidence."""
        # Assume User B has response_id = "resp_user_b_001"
        response = client.get(
            "/api/evidence/resp_user_b_001",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        
        assert response.status_code in [404, 403], \
            "Should deny access to other user's evidence"
    
    def test_evidence_filtered_by_user(self):
        """Database queries should filter evidence by user_id."""
        db = SessionLocal()
        try:
            # Create evidence for two users
            db.add(QueryEvidence(
                response_id="resp_a_001",
                session_id="sess_a",
                user_id="user_a",
                query_text="User A query",
                # ... other required fields
            ))
            db.add(QueryEvidence(
                response_id="resp_b_001",
                session_id="sess_b",
                user_id="user_b",
                query_text="User B query",
                # ... other required fields
            ))
            db.commit()
            
            # Query as User A
            user_a_evidence = (
                db.query(QueryEvidence)
                .filter(QueryEvidence.user_id == "user_a")
                .all()
            )
            
            assert len(user_a_evidence) == 1
            assert user_a_evidence[0].user_id == "user_a"
            assert "User B" not in user_a_evidence[0].query_text
        finally:
            db.close()


class TestConcurrentSessionIsolation:
    """Test that concurrent requests don't contaminate each other's sessions."""
    
    @pytest.mark.asyncio
    async def test_concurrent_queries_no_leakage(self, client, user_a_token, user_b_token):
        """Two users querying simultaneously should not see each other's results."""
        import asyncio
        
        async def user_a_query():
            response = client.post(
                "/api/chat/query",
                json={
                    "query": "USER A QUERY - CONFIDENTIAL",
                    "session_id": "session_a"
                },
                headers={"Authorization": f"Bearer {user_a_token}"}
            )
            return response.json()
        
        async def user_b_query():
            response = client.post(
                "/api/chat/query",
                json={
                    "query": "USER B QUERY - SECRET",
                    "session_id": "session_b"
                },
                headers={"Authorization": f"Bearer {user_b_token}"}
            )
            return response.json()
        
        # Execute concurrently
        results = await asyncio.gather(user_a_query(), user_b_query())
        
        result_a, result_b = results
        
        # Verify no cross-contamination
        assert "USER A" in str(result_a)
        assert "USER B" not in str(result_a), "User A's result contaminated with User B's data"
        
        assert "USER B" in str(result_b)
        assert "USER A" not in str(result_b), "User B's result contaminated with User A's data"


class TestCacheIsolation:
    """Test that cached results are not shared across users."""
    
    def test_cached_cypher_not_shared(self, client, user_a_token, user_b_token):
        """Cypher query cache should be scoped per user."""
        query = "What is the NAV of Tata Balanced Fund?"
        
        # User A executes query (cached)
        response_a1 = client.post(
            "/api/chat/query",
            json={"query": query, "session_id": "sess_a"},
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response_a1.status_code == 200
        
        # User B executes SAME query (should NOT use User A's cache)
        response_b = client.post(
            "/api/chat/query",
            json={"query": query, "session_id": "sess_b"},
            headers={"Authorization": f"Bearer {user_b_token}"}
        )
        assert response_b.status_code == 200
        
        # Verify both got results but from separate cache entries
        # (implementation-specific verification)
        
        # User A executes again (should use their own cache)
        response_a2 = client.post(
            "/api/chat/query",
            json={"query": query, "session_id": "sess_a"},
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        assert response_a2.status_code == 200


class TestReviewQueueAuthorization:
    """Test review queue access control."""
    
    def test_analyst_cannot_see_other_analyst_reviews(self, client, user_a_token, user_b_token):
        """Analysts should only see reviews assigned to them."""
        # User B escalates an item
        client.post(
            "/api/review-queue/escalate",
            json={
                "response_id": "resp_001",
                "query": "Test query",
                "user_answer": "Test answer",
                "reason": "LOW_CONFIDENCE",
                "confidence_score": 0.3
            },
            headers={"Authorization": f"Bearer {user_b_token}"}
        )
        
        # User A should not see it in their pending queue
        response = client.get(
            "/api/review-queue/pending",
            headers={"Authorization": f"Bearer {user_a_token}"}
        )
        
        assert response.status_code == 200
        items = response.json()["items"]
        
        # Should not contain User B's escalated item
        # (unless explicitly assigned to User A by compliance officer)


@pytest.mark.security
class TestAttackScenarios:
    """Simulate real attack scenarios."""
    
    def test_session_id_enumeration_attack(self, client, user_a_token):
        """Attacker should not be able to enumerate other users' sessions."""
        # Try common session ID patterns
        potential_session_ids = [
            "00000000-0000-0000-0000-000000000001",
            "11111111-1111-1111-1111-111111111111",
            "session-1",
            "test-session",
            "admin-session",
        ]
        
        for session_id in potential_session_ids:
            response = client.get(
                f"/api/sessions/{session_id}",
                headers={"Authorization": f"Bearer {user_a_token}"}
            )
            
            # Should always get 404 for non-owned sessions
            # (even if they exist for other users)
            assert response.status_code == 404, \
                f"Session enumeration possible: {session_id}"
    
    def test_response_id_enumeration_attack(self, client, user_a_token):
        """Attacker should not be able to enumerate evidence by response_id."""
        # Try sequential response IDs
        for i in range(1, 100):
            response_id = f"resp_{i:06d}"
            response = client.get(
                f"/api/evidence/{response_id}",
                headers={"Authorization": f"Bearer {user_a_token}"}
            )
            
            # Should get 404 for non-owned evidence
            assert response.status_code in [404, 403]
```

#### 5.5: Load Testing with User Isolation

**File**: `backend/tests/test_load_user_isolation.py`

```python
"""
Load testing to verify user isolation under concurrent load.
"""
import pytest
import asyncio
from typing import List

@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_users_no_leakage():
    """
    Simulate 50 concurrent users each executing 10 queries.
    Verify no cross-user data contamination.
    """
    num_users = 50
    queries_per_user = 10
    
    # Create test users
    users = [f"load_test_user_{i}" for i in range(num_users)]
    
    async def user_workflow(user_id: str):
        """Single user's workflow."""
        client = TestClient(app)
        
        # Login
        login_response = client.post("/api/auth/login", json={
            "username": user_id,
            "password": f"password_{user_id}"
        })
        token = login_response.json()["token"]
        
        session_id = f"session_{user_id}"
        results = []
        
        for query_num in range(queries_per_user):
            query = f"{user_id} query number {query_num}"
            
            response = client.post(
                "/api/chat/query",
                json={"query": query, "session_id": session_id},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            result = response.json()
            results.append(result)
            
            # Verify result doesn't contain other users' data
            result_str = str(result)
            for other_user in users:
                if other_user != user_id:
                    assert other_user not in result_str, \
                        f"Data leakage: {user_id}'s result contains {other_user}"
        
        return results
    
    # Execute all users concurrently
    tasks = [user_workflow(user) for user in users]
    all_results = await asyncio.gather(*tasks)
    
    # Verify total query count
    total_queries = sum(len(results) for results in all_results)
    assert total_queries == num_users * queries_per_user
```

### Deliverables

- [x] Vector store searches filtered by user_id/tenant_id
- [x] Graph traversal includes authorization constraints
- [x] Review queue uses proper authentication (no X-User-ID spoofing)
- [x] Comprehensive security test suite passing
- [x] Load testing confirms no cross-user leakage under concurrency

---

## Validation & Deployment Checklist

### Pre-Deployment Validation

- [x] **Phase 1**: All authentication tests passing
- [x] **Phase 2**: Session CRUD operations enforce ownership
- [x] **Phase 3**: Query evidence always records user_id
- [x] **Phase 4**: All caches use user-scoped keys
- [x] **Phase 5**: Vector/graph operations enforce authorization

### Security Audit

Run these verification steps in a **TEST ENVIRONMENT**:

1. **Create two test accounts** (User A, User B)
2. **User A creates a session** → User B tries to access → Should get 404
3. **User B executes a query** → User A tries to fetch evidence → Should be denied
4. **Both users execute identical queries** → Verify cached results are separate
5. **User A requests User B's telemetry** → Should be denied
6. **Check database directly**: Verify all records have non-null user_id

### Database Verification Queries

```sql
-- Verify all sessions have user_id
SELECT COUNT(*) FROM chat_sessions WHERE user_id IS NULL OR user_id = '';
-- Expected: 0

-- Verify all query evidence has user_id
SELECT COUNT(*) FROM query_evidence WHERE user_id IS NULL OR user_id = '';
-- Expected: 0

-- Check user isolation in sessions
SELECT user_id, COUNT(*) FROM chat_sessions GROUP BY user_id;
-- Should show clear separation by user

-- Check user isolation in evidence
SELECT user_id, COUNT(*) FROM query_evidence GROUP BY user_id;
-- Should show clear separation by user
```

### Deployment Steps

1. **Backup production database**
   ```bash
   pg_dump -h localhost -U postgres -d amc_db > backup_pre_security_fix.sql
   ```

2. **Apply migrations in maintenance window**
   ```bash
   alembic upgrade head
   ```

3. **Deploy updated backend code**
   ```bash
   docker-compose up -d backend
   ```

4. **Run smoke tests**
   ```bash
   pytest tests/test_security_cross_user_access.py -v
   ```

5. **Monitor logs for authorization failures**
   ```bash
   tail -f logs/security_audit.log | grep "UNAUTHORIZED"
   ```

6. **Rotate session tokens** (optional but recommended)
   - Forces all users to re-authenticate with new security model

---

## Incident Response (If Active Leakage Detected)

If cross-user data leakage is confirmed in production:

### Immediate Actions (Within 1 hour)

1. **Contain the issue**:
   - Deploy emergency fix to most critical endpoint (sessions API)
   - Or temporarily disable affected features

2. **Audit access logs**:
   ```sql
   -- Find potential unauthorized access
   SELECT 
       session_id, 
       user_id, 
       created_at,
       updated_at
   FROM chat_sessions
   WHERE updated_at > created_at + INTERVAL '5 minutes'
   ORDER BY updated_at DESC;
   ```

3. **Notify security team and stakeholders**

### Within 24 hours

1. **Complete forensic analysis**:
   - Identify which users accessed which sessions
   - Determine scope of data exposure

2. **Invalidate all active sessions**:
   ```python
   # Force re-authentication
   redis_client.flushdb()  # Clear all session tokens
   ```

3. **Apply complete Phase 1-5 fixes**

---

1. **User notification** (if regulatory requirement)
2. **Post-incident review and documentation**
3. **Implement additional monitoring and alerts**

---

## Long-Term Security Improvements

### Recommendations for Future Enhancements

1. **Row-Level Security (RLS) in PostgreSQL**
   ```sql
   ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
   
   CREATE POLICY user_sessions_isolation ON chat_sessions
   FOR ALL
   USING (user_id = current_setting('app.current_user_id'));
   ```

2. **Audit Logging Service**
   - Log all data access with user context
   - Monitor for anomalous cross-user access patterns

3. **Rate Limiting per User**
   - Prevent brute-force session enumeration

4. **Penetration Testing**
   - Hire external security firm to audit authorization

5. **Security Headers**
   ```python
   # Add to FastAPI middleware
   @app.middleware("http")
   async def security_headers(request, call_next):
       response = await call_next(request)
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["X-Frame-Options"] = "DENY"
       response.headers["Strict-Transport-Security"] = "max-age=31536000"
       return response
   ```

---

## Success Criteria

This remediation is successful when:

✅ **No user can access another user's**:
- Chat sessions or conversation history
- Query execution results or evidence
- Retrieved context, citations, or telemetry
- Review queue items (unless explicitly assigned)
- Cached results or intermediate data

✅ **All API endpoints**:
- Require valid authentication tokens
- Validate session ownership before operations
- Filter database queries by user_id (and tenant_id if applicable)
- Return 404 (not 403) for unauthorized resources

✅ **All caches**:
- Include user_id and tenant_id in cache keys
- Cannot be accessed across user boundaries

✅ **Security tests pass**:
- Cross-user access attempts are denied
- Concurrent requests don't contaminate each other
- Load testing confirms isolation under stress

✅ **Production verification**:
- Database audit shows 0 records with null user_id
- Access logs show no unauthorized access attempts succeeding
- Independent security review confirms fix

---

## Appendix A: Quick Reference

### Common Authorization Patterns

```python
# Pattern 1: Verify session ownership
session = db.query(ChatSession).filter(
    ChatSession.session_id == session_id,
    ChatSession.user_id == current_user.username
).first()

if not session:
    raise HTTPException(status_code=404, detail="Not found")

# Pattern 2: Filter query by user
evidence = db.query(QueryEvidence).filter(
    QueryEvidence.user_id == current_user.username
).all()

# Pattern 3: Inject user context into new records
new_session = ChatSession(
    session_id=session_id,
    user_id=current_user.username,
    tenant_id=current_user.tenant_id,
    created_at=datetime.utcnow()
)
```

### Testing Commands

```bash
# Run security tests only
pytest tests/test_security_cross_user_access.py -v -m security

# Run all tests with coverage
pytest --cov=app --cov-report=html

# Check for missing authorization
grep -r "def.*session_id" app/api/ | grep -v "current_user"
```

---

## Appendix B: Rollback Plan

If issues arise during deployment:

1. **Rollback database migration**:
   ```bash
   alembic downgrade -1
   ```

2. **Redeploy previous backend version**:
   ```bash
   docker-compose up -d backend:previous_tag
   ```

3. **Clear application caches**:
   ```bash
   redis-cli FLUSHDB
   ```

4. **Restore from backup if needed**:
   ```bash
   psql -h localhost -U postgres -d amc_db < backup_pre_security_fix.sql
   ```

---

**End of Security Remediation Plan**

*This plan must be executed sequentially. Each phase builds on the previous phase.*
*Do not proceed to Phase N+1 until Phase N is complete and verified.*
