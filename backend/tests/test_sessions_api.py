# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_sessions_api.py
====================
Unit tests for session management API routes (/api/sessions).
"""
import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import sessions as sessions_route

# Build test app with sessions router
test_app = FastAPI()
test_app.include_router(sessions_route.router, prefix="/api")


@pytest.fixture
def temp_sessions_dir(monkeypatch):
    """Create a temporary directory for session storage tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_chat_sessions_"))
    monkeypatch.setattr(sessions_route, "SESSIONS_DIR", temp_dir)
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_list_sessions_empty(temp_sessions_dir):
    client = TestClient(test_app)
    response = client.get("/api/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_save_and_get_session(temp_sessions_dir):
    client = TestClient(test_app)
    session_id = "test-session-uuid-1234"
    payload = {
        "session_id": session_id,
        "history": [
            {"role": "user", "content": "What is the NAV of HDFC Top 100?", "turn_index": 0},
            {"role": "assistant", "content": "The NAV is 950.50", "turn_index": 0},
        ]
    }

    # Save session
    save_resp = client.post(f"/api/sessions/{session_id}", json=payload)
    assert save_resp.status_code == 200
    assert save_resp.json() == {"status": "ok", "session_id": session_id}

    # Verify file exists on disk with 2-space indentation and UTF-8
    file_path = temp_sessions_dir / f"{session_id}.json"
    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert '  "session_id": "test-session-uuid-1234"' in content

    # Get session
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["session_id"] == session_id
    assert len(data["history"]) == 2


def test_list_sessions_preview_and_sorting(temp_sessions_dir):
    client = TestClient(test_app)

    # Create session 1
    s1 = temp_sessions_dir / "sess-1.json"
    s1.write_text(json.dumps([
        {"role": "user", "content": "Short query"},
        {"role": "assistant", "content": "Short answer"}
    ]), encoding="utf-8")
    os.utime(s1, (1000, 1000))

    # Create session 2 with long query (> 45 chars)
    s2 = temp_sessions_dir / "sess-2.json"
    s2.write_text(json.dumps([
        {"role": "user", "content": "What are the SEBI limits on large cap equity funds under Regulation 16C?"},
        {"role": "assistant", "content": "Here is the answer"}
    ]), encoding="utf-8")
    os.utime(s2, (2000, 2000))

    # Create corrupt file
    corrupt = temp_sessions_dir / "corrupt.json"
    corrupt.write_text("invalid json content {{{", encoding="utf-8")

    list_resp = client.get("/api/sessions")
    assert list_resp.status_code == 200
    items = list_resp.json()

    # Corrupt file should be skipped gracefully
    assert len(items) == 2

    # Newest first
    assert items[0]["session_id"] == "sess-2"
    assert items[0]["preview"] == "What are the SEBI limits on large cap equity…"
    assert len(items[0]["preview"]) == 45
    assert items[0]["turn_count"] == 1

    assert items[1]["session_id"] == "sess-1"
    assert items[1]["preview"] == "Short query"
    assert items[1]["turn_count"] == 1


def test_delete_session(temp_sessions_dir):
    client = TestClient(test_app)
    session_id = "sess-to-delete"
    path = temp_sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps({"session_id": session_id, "history": []}), encoding="utf-8")

    del_resp = client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "deleted", "session_id": session_id}
    assert not path.exists()

    # Delete non-existent
    del_resp2 = client.delete(f"/api/sessions/{session_id}")
    assert del_resp2.status_code == 200
    assert del_resp2.json() == {"status": "not_found", "session_id": session_id}


def test_list_sessions_skips_empty_conversations(temp_sessions_dir):
    """Ensure that only conversations with at least one actual user message appear in Recent Chats."""
    client = TestClient(test_app)

    # 1. Blank session file (empty history)
    blank = temp_sessions_dir / "blank-session.json"
    blank.write_text(json.dumps({"session_id": "blank-session", "history": []}), encoding="utf-8")

    # 2. Assistant-only messages (no user message)
    asst_only = temp_sessions_dir / "asst-only.json"
    asst_only.write_text(json.dumps({
        "session_id": "asst-only",
        "history": [{"role": "assistant", "content": "How can I help you today?"}]
    }), encoding="utf-8")

    # 3. Whitespace-only user message
    whitespace = temp_sessions_dir / "whitespace-user.json"
    whitespace.write_text(json.dumps({
        "session_id": "whitespace-user",
        "history": [{"role": "user", "content": "   "}]
    }), encoding="utf-8")

    # 4. Valid session with actual user query
    valid = temp_sessions_dir / "valid-chat.json"
    valid.write_text(json.dumps({
        "session_id": "valid-chat",
        "title": "SEBI Compliance Review",
        "history": [
            {"role": "user", "content": "What are the SEBI limits?"},
            {"role": "assistant", "content": "The limits are defined in Circular 3."}
        ]
    }), encoding="utf-8")

    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    items = resp.json()

    # Only valid-chat should appear! Empty/blank/whitespace/assistant-only must not appear.
    assert len(items) == 1
    assert items[0]["session_id"] == "valid-chat"
    assert items[0]["title"] == "SEBI Compliance Review"
    assert items[0]["turn_count"] == 1


def test_save_empty_session_skipped(temp_sessions_dir):
    """Ensure saving a blank/empty session without user queries does not write files to disk."""
    client = TestClient(test_app)
    empty_id = "empty-attempt"
    payload = {
        "session_id": empty_id,
        "title": "New Conversation",
        "history": []
    }
    resp = client.post(f"/api/sessions/{empty_id}", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"

    file_path = temp_sessions_dir / f"{empty_id}.json"
    assert not file_path.exists()


def test_delete_reflow_chats_without_gaps_or_stale_entries(temp_sessions_dir):
    """
    If list contains Chat 1, Chat 2, Chat 3, Chat 4 and Chat 2 is deleted,
    the remaining chats must immediately reflow to Chat 1, Chat 3, Chat 4
    without gaps, stale entries, or incorrect ordering.
    """
    client = TestClient(test_app)

    # Create Chat 1 (oldest) to Chat 4 (newest)
    chat_configs = [
        ("chat-1", "Chat 1 Query", 1000),
        ("chat-2", "Chat 2 Query", 2000),
        ("chat-3", "Chat 3 Query", 3000),
        ("chat-4", "Chat 4 Query", 4000),
    ]

    for sid, query, mtime in chat_configs:
        file = temp_sessions_dir / f"{sid}.json"
        file.write_text(json.dumps({
            "session_id": sid,
            "title": f"Title for {sid}",
            "history": [{"role": "user", "content": query}]
        }), encoding="utf-8")
        os.utime(file, (mtime, mtime))

    # Initial list: [chat-4, chat-3, chat-2, chat-1]
    list1 = client.get("/api/sessions").json()
    assert [c["session_id"] for c in list1] == ["chat-4", "chat-3", "chat-2", "chat-1"]

    # Delete chat-2
    del_resp = client.delete("/api/sessions/chat-2")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Reflowed list: [chat-4, chat-3, chat-1]
    list2 = client.get("/api/sessions").json()
    assert [c["session_id"] for c in list2] == ["chat-4", "chat-3", "chat-1"]
    assert len(list2) == 3
    # Check that deleted file is gone from disk
    assert not (temp_sessions_dir / "chat-2.json").exists()

