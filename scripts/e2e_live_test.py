import json
import urllib.error
import urllib.request
import sys

BASE_URL_BACKEND = "http://127.0.0.1:8000"
BASE_URL_FRONTEND = "http://localhost:5173"

def request(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    req_data = None
    if data is not None:
        if isinstance(data, dict):
            req_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, str):
            req_data = data.encode("utf-8")
        else:
            req_data = data

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            content = res.read().decode("utf-8")
            try:
                parsed = json.loads(content)
            except Exception:
                parsed = content
            return res.status, parsed, res.headers
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = content
        return e.code, parsed, e.headers
    except Exception as e:
        return 500, str(e), {}

def test_e2e(base_url, prefix=""):
    print(f"\n==========================================")
    print(f"RUNNING E2E TESTS AGAINST: {base_url} ({prefix})")
    print(f"==========================================")
    failures = []

    # 1. Health check
    status, body, _ = request(f"{base_url}/api/health")
    assert status == 200, f"Health check failed: {status} {body}"
    print(f"[PASS] 1. Live health check OK (status={body.get('status')})")

    # 2. X-User-ID header fallback rejection (Security Remediation 1)
    status, body, _ = request(f"{base_url}/api/auth/me", headers={"X-User-ID": "admin"})
    if status != 401:
        failures.append(f"X-User-ID fallback not rejected: got status {status}")
        print(f"[FAIL] 2. X-User-ID header alone returned {status}, expected 401")
    else:
        print("[PASS] 2. X-User-ID header fallback without Bearer token properly rejected with 401 Unauthorized")

    status, body, _ = request(f"{base_url}/api/sessions", headers={"X-User-ID": "sarah.compliance"})
    if status != 401:
        failures.append(f"X-User-ID on /api/sessions not rejected: got status {status}")
        print(f"[FAIL] 2b. X-User-ID on /api/sessions returned {status}, expected 401")
    else:
        print("[PASS] 2b. X-User-ID on /api/sessions properly rejected with 401 Unauthorized")

    # 3. Login as Sarah (compliance)
    status, body, _ = request(
        f"{base_url}/api/auth/login",
        method="POST",
        data={"username": "sarah.compliance", "password": "Compliance@2026"}
    )
    if status != 200 or "token" not in body:
        failures.append(f"Login Sarah failed: {status} {body}")
        print(f"[FAIL] 3. Login as sarah.compliance failed: {status} {body}")
        return failures
    sarah_token = body["token"]
    sarah_headers = {"Authorization": f"Bearer {sarah_token}"}
    print(f"[PASS] 3. Login as sarah.compliance successful (role={body['user']['role']})")

    # 4. Login as Vikram (portfolio manager)
    status, body, _ = request(
        f"{base_url}/api/auth/login",
        method="POST",
        data={"username": "vikram.pm", "password": "Welcome@2026"}
    )
    if status != 200 or "token" not in body:
        failures.append(f"Login Vikram failed: {status} {body}")
        print(f"[FAIL] 4. Login as vikram.pm failed: {status} {body}")
        return failures
    vikram_token = body["token"]
    vikram_headers = {"Authorization": f"Bearer {vikram_token}"}
    print(f"[PASS] 4. Login as vikram.pm successful (role={body['user']['role']})")

    # 5. User identity verification via /api/auth/me
    status, body, _ = request(f"{base_url}/api/auth/me", headers=sarah_headers)
    assert status == 200 and body.get("user", {}).get("username") == "sarah.compliance"
    print(f"[PASS] 5a. /api/auth/me verified for sarah.compliance (role={body['user'].get('role')})")

    status, body, _ = request(f"{base_url}/api/auth/me", headers=vikram_headers)
    assert status == 200 and body.get("user", {}).get("username") == "vikram.pm"
    print(f"[PASS] 5b. /api/auth/me verified for vikram.pm (role={body['user'].get('role')})")

    # 6. Session Creation & Isolation (Security Remediation 3)
    clean_prefix = prefix.lower().replace(" ", "-")
    session_id_sarah = f"e2e-live-{clean_prefix}-sarah-001"
    session_data_sarah = {
        "session_id": session_id_sarah,
        "title": "Sarah Live E2E Audit Session",
        "history": [
            {"role": "user", "content": "Check compliance for Large Cap Fund"}
        ]
    }
    # Sarah saves session
    status, body, _ = request(
        f"{base_url}/api/sessions/{session_id_sarah}",
        method="POST",
        headers=sarah_headers,
        data=session_data_sarah
    )
    assert status == 200, f"Sarah failed to save session: {status} {body}"
    print(f"[PASS] 6a. Sarah created chat session (status={body.get('status')})")

    # Sarah gets session
    status, body, _ = request(f"{base_url}/api/sessions/{session_id_sarah}", headers=sarah_headers)
    assert status == 200 and body.get("title") == "Sarah Live E2E Audit Session", f"Unexpected get_session: {status} {body}"
    print("[PASS] 6b. Sarah successfully retrieved her session")

    # Vikram attempts to read Sarah's session -> must return 404
    status, body, _ = request(f"{base_url}/api/sessions/{session_id_sarah}", headers=vikram_headers)
    if status != 404:
        failures.append(f"Cross-user read isolation violated: Vikram got {status} instead of 404")
        print(f"[FAIL] 6c. Vikram read Sarah's session got {status}, expected 404")
    else:
        print("[PASS] 6c. Vikram cross-user read of Sarah's session returned 404 Not Found")

    # Vikram attempts to tamper/overwrite Sarah's session -> must return 404
    status, body, _ = request(
        f"{base_url}/api/sessions/{session_id_sarah}",
        method="POST",
        headers=vikram_headers,
        data={"session_id": session_id_sarah, "title": "Hacked Title", "history": [{"role": "user", "content": "hack"}]}
    )
    if status != 404:
        failures.append(f"Cross-user overwrite isolation violated: Vikram got {status} instead of 404")
        print(f"[FAIL] 6d. Vikram overwrite Sarah's session got {status}, expected 404")
    else:
        print("[PASS] 6d. Vikram cross-user overwrite of Sarah's session returned 404 Not Found")

    # Vikram attempts to delete Sarah's session -> must return 404
    status, body, _ = request(
        f"{base_url}/api/sessions/{session_id_sarah}",
        method="DELETE",
        headers=vikram_headers
    )
    if status != 404:
        failures.append(f"Cross-user delete isolation violated: Vikram got {status} instead of 404")
        print(f"[FAIL] 6e. Vikram delete Sarah's session got {status}, expected 404")
    else:
        print("[PASS] 6e. Vikram cross-user delete of Sarah's session returned 404 Not Found")

    # 7. Session listing isolation
    status, body, _ = request(f"{base_url}/api/sessions", headers=vikram_headers)
    assert status == 200
    vikram_sessions = body if isinstance(body, list) else body.get("sessions", [])
    sarah_sessions_in_vikram = [s for s in vikram_sessions if s.get("session_id") == session_id_sarah]
    if sarah_sessions_in_vikram:
        failures.append("Vikram sees Sarah's session in session list")
        print("[FAIL] 7. Vikram session listing includes Sarah's session")
    else:
        print(f"[PASS] 7. Vikram session list is isolated (0 cross-user sessions visible)")

    # 8. User-scoped Scorecard / Compliance Caching (Security Remediation 4)
    status, body_sarah, _ = request(f"{base_url}/api/compliance/scorecard?region=SEBI", headers=sarah_headers)
    assert status == 200
    status, body_vikram, _ = request(f"{base_url}/api/compliance/scorecard?region=SEBI", headers=vikram_headers)
    assert status == 200
    print("[PASS] 8. Scorecard endpoints return 200 under user-scoped caching")

    # 9. Clean up Sarah's test session
    status, body, _ = request(
        f"{base_url}/api/sessions/{session_id_sarah}",
        method="DELETE",
        headers=sarah_headers
    )
    assert status == 200
    print("[PASS] 9. Sarah cleanly deleted her test session")

    # 10. Chat title endpoint with Bearer auth
    chat_title_data = {
        "query": "What are SEBI regulations for mid cap mutual funds?",
        "session_id": f"test-title-{clean_prefix}"
    }
    status, body, _ = request(
        f"{base_url}/api/chat/title",
        method="POST",
        headers=sarah_headers,
        data=chat_title_data
    )
    if status == 200:
        print(f"[PASS] 10. /api/chat/title generated title: '{body.get('title')}'")
    else:
        failures.append(f"/api/chat/title returned {status}: {body}")
        print(f"[FAIL] 10. /api/chat/title returned status {status}: {body}")

    # 11. Chat endpoint unauthorized without Bearer token
    status, body, _ = request(
        f"{base_url}/api/chat",
        method="POST",
        headers={"X-User-ID": "admin"},
        data={"query": "test query", "session_id": "anon-session"}
    )
    if status != 401:
        failures.append(f"/api/chat unauthenticated returned {status}")
        print(f"[FAIL] 11. /api/chat without Bearer returned {status}, expected 401")
    else:
        print("[PASS] 11. /api/chat properly rejects unauthenticated request with 401")

    return failures

if __name__ == "__main__":
    # Test directly against backend
    failures_backend = test_e2e(BASE_URL_BACKEND, prefix="Direct Backend")
    # Test through Vite proxy
    failures_frontend = test_e2e(BASE_URL_FRONTEND, prefix="Vite Frontend Proxy")

    total_failures = len(failures_backend) + len(failures_frontend)
    print("\n" + "=" * 50)
    if total_failures == 0:
        print("ALL END-TO-END TESTS PASSED (Backend + Frontend Proxy)!")
        print("=" * 50)
        sys.exit(0)
    else:
        print(f"FAILED WITH {total_failures} ERRORS")
        print("=" * 50)
        sys.exit(1)
