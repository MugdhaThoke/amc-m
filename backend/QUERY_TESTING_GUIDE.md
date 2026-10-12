# Query Testing Guide - Compliance Officer

This guide shows how to test that the seeded **Compliance Officer** user can run queries and interact with the application.

## Quick Start

### 1. Verify User is Seeded

```bash
cd backend
python scripts/test_compliance_officer.py
```

Expected output:
```
✓ ALL TESTS PASSED!
Compliance Officer user is ready to use:
  Login: compliance_officer
  Password: Compliance@2026
  Role: Compliance & Regulatory Officer
```

### 2. Start the Backend Server

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 3. Login via API

```bash
# Store credentials
USERNAME="compliance_officer"
PASSWORD="Compliance@2026"

# Login and get token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{
    \"username\": \"$USERNAME\",
    \"password\": \"$PASSWORD\"
  }"
```

Response:
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "expires_at": 1791825936,
  "user": {
    "username": "compliance_officer",
    "display_name": "Compliance Officer",
    "role": "Compliance & Regulatory Officer",
    "department": "Regulatory & Legal Compliance",
    "email": "compliance@amc.com",
    "avatar_initials": "CO",
    "status": "Active"
  }
}
```

### 4. Store the Token

```bash
TOKEN="<paste_token_from_response_above>"
```

### 5. Verify Authentication

```bash
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "user": {
    "username": "compliance_officer",
    "display_name": "Compliance Officer",
    "role": "Compliance & Regulatory Officer",
    "department": "Regulatory & Legal Compliance",
    "email": "compliance@amc.com",
    "status": "Active"
  }
}
```

## Test Query Execution

### Compliance & Regulatory Queries

The Compliance Officer can execute various types of queries:

#### Query 1: Fund Compliance Requirements

```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the compliance requirements for mutual fund distribution?",
    "session_id": "compliance_test_1"
  }'
```

Expected: Returns analysis of compliance requirements

#### Query 2: ESG and Sustainability

```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What ESG criteria are applied to our investment universe?",
    "session_id": "compliance_test_2"
  }'
```

Expected: Returns ESG analysis and criteria

#### Query 3: Regulatory Disclosures

```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List all SEBI mandatory disclosures for our funds",
    "session_id": "compliance_test_3"
  }'
```

Expected: Returns list of required disclosures

## Test Session Management

### Create a Session

```bash
curl -X POST http://localhost:8000/api/sessions/test_compliance_session \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "history": [
      {
        "role": "user",
        "content": "What are the NAV rules for equity funds?"
      },
      {
        "role": "assistant",
        "content": "Equity funds must calculate NAV daily based on market value..."
      }
    ]
  }'
```

Response:
```json
{
  "status": "ok",
  "session_id": "test_compliance_session"
}
```

### Retrieve Session

```bash
curl -X GET http://localhost:8000/api/sessions/test_compliance_session \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "session_id": "test_compliance_session",
  "history": [
    {
      "role": "user",
      "content": "What are the NAV rules for equity funds?"
    },
    {
      "role": "assistant",
      "content": "Equity funds must calculate NAV daily..."
    }
  ],
  "user_id": "compliance_officer"
}
```

### List Sessions

```bash
curl -X GET http://localhost:8000/api/sessions \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
[
  {
    "session_id": "test_compliance_session",
    "preview": "What are the NAV rules for equity funds?",
    "turn_count": 1,
    "title": "NAV Rules Discussion"
  }
]
```

## Test Using Python Client

Create a test script `test_compliance_queries.py`:

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Credentials
USERNAME = "compliance_officer"
PASSWORD = "Compliance@2026"

# Step 1: Login
print("1. Logging in...")
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    json={"username": USERNAME, "password": PASSWORD}
)
login_data = login_response.json()
token = login_data["token"]
user = login_data["user"]

print(f"   ✓ Logged in as {user['username']}")
print(f"   Role: {user['role']}")
print(f"   Token: {token[:20]}...")

# Step 2: Verify auth
print("\n2. Verifying authentication...")
me_response = requests.get(
    f"{BASE_URL}/api/auth/me",
    headers={"Authorization": f"Bearer {token}"}
)
me_data = me_response.json()
print(f"   ✓ Authenticated as {me_data['user']['username']}")

# Step 3: Execute query
print("\n3. Executing query...")
query_response = requests.post(
    f"{BASE_URL}/api/chat/query",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "query": "What are the regulatory requirements for mutual funds?",
        "session_id": "python_test_1"
    }
)

if query_response.status_code == 200:
    query_data = query_response.json()
    print(f"   ✓ Query executed successfully")
    print(f"   Response ID: {query_data.get('response_id', 'N/A')}")
    print(f"   Status: {query_response.status_code}")
else:
    print(f"   ✗ Query failed with status {query_response.status_code}")
    print(f"   Error: {query_response.text}")

# Step 4: Create session
print("\n4. Creating session...")
session_response = requests.post(
    f"{BASE_URL}/api/sessions/python_test_session",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "history": [
            {"role": "user", "content": "Test query"},
            {"role": "assistant", "content": "Test response"}
        ]
    }
)

if session_response.status_code == 200:
    print(f"   ✓ Session created successfully")
else:
    print(f"   ✗ Session creation failed: {session_response.status_code}")

# Step 5: List sessions
print("\n5. Listing sessions...")
list_response = requests.get(
    f"{BASE_URL}/api/sessions",
    headers={"Authorization": f"Bearer {token}"}
)

if list_response.status_code == 200:
    sessions = list_response.json()
    print(f"   ✓ Retrieved {len(sessions)} session(s)")
    for session in sessions:
        print(f"      - {session['session_id']}: {session['preview'][:50]}")

print("\n✓ All tests completed successfully!")
```

Run it:
```bash
python test_compliance_queries.py
```

Expected output:
```
1. Logging in...
   ✓ Logged in as compliance_officer
   Role: Compliance & Regulatory Officer
   Token: eyJ0eXAiOiJKV1...

2. Verifying authentication...
   ✓ Authenticated as compliance_officer

3. Executing query...
   ✓ Query executed successfully
   Response ID: resp_12345...
   Status: 200

4. Creating session...
   ✓ Session created successfully

5. Listing sessions...
   ✓ Retrieved 1 session(s)
      - python_test_session: Test query

✓ All tests completed successfully!
```

## Test Using Web UI

### 1. Navigate to Login Page

Open: `http://localhost:3000` (or wherever frontend runs)

### 2. Login

- Username: `compliance_officer`
- Password: `Compliance@2026`
- Click "Login"

### 3. Expected Result

- Redirected to main interface
- User profile shows: "Compliance Officer"
- Role shows: "Compliance & Regulatory Officer"

### 4. Test Query Execution

- Click "New Chat"
- Enter query: "What are the compliance requirements for fund distribution?"
- Press Enter or click "Send"

### 5. Expected Result

- Query is sent to backend
- Response appears with compliance analysis
- Session is saved automatically

### 6. Test Review Queue (if available)

- Click "Review Queue" (if compliance_officer has access)
- Should show review items for compliance
- Can approve/reject items

## Verify Database State

Check database directly to verify all operations:

```sql
-- Check users table
SELECT username, role, status FROM auth_users WHERE username='compliance_officer';

-- Check sessions
SELECT session_id, user_id, created_at FROM chat_sessions WHERE user_id='compliance_officer';

-- Check query evidence
SELECT response_id, session_id, user_id FROM query_evidence WHERE user_id='compliance_officer';
```

## Troubleshooting

### Login fails
- Verify username: `compliance_officer` (all lowercase)
- Verify password: `Compliance@2026` (exact case)
- Check database: `SELECT * FROM auth_users WHERE username='compliance_officer'`

### Query execution fails
- Verify token is valid: Call `/api/auth/me` endpoint
- Check server logs for errors
- Verify session_id is unique for each query

### Session not saved
- Check database permissions
- Verify `logs/chat_sessions/` directory exists
- Check server logs

### Authorization errors (401/403)
- Token may have expired
- Re-login and get new token
- Verify Authorization header format: `Bearer <token>`

## Next Steps

After successful testing:

1. ✓ Verify Compliance Officer can login
2. ✓ Verify queries execute successfully
3. ✓ Verify sessions are created and retrieved
4. → Create additional users via admin panel
5. → Test multi-user scenarios
6. → Review security implementation from SECURITY_REMEDIATION_PLAN.md

---

**Status**: ✓ Ready to test  
**Last Updated**: 2026-10-12  
**Test User**: compliance_officer / Compliance@2026
