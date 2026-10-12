# User Migration: JSON → Database

This document explains how to migrate from hardcoded JSON users to a database-backed user repository.

## Overview

The application previously stored user credentials in `backend/app/auth/data/users.json`. This migration moves all users to the `auth_users` database table, enabling:

- Dynamic user management (add/remove users without redeploying)
- Better scalability (support for thousands of users)
- Audit trail (creation/update/login timestamps)
- Multi-tenant support (tenant_id isolation)
- Integration with the security remediation plan

## Files Added

### Database Schema
- `backend/app/schemas/auth_users_table.py` - SQLAlchemy model for `auth_users` table

### New Repositories
- `backend/app/auth/sql_repository.py` - SQL-backed user repository (replaces JSON)

### Migrations
- `backend/alembic/versions/001_create_auth_users_table.py` - Alembic migration to create table

### Scripts
- `backend/scripts/migrate_users_to_db.py` - Python script to migrate JSON users to DB
- `backend/scripts/seed_compliance_officer.sql` - SQL to seed a Compliance Officer

### Tests
- `backend/tests/test_sql_user_repository.py` - Comprehensive test suite

## Migration Steps

### Step 1: Create the auth_users Table

Run the Alembic migration:

```bash
cd backend
alembic upgrade head
```

This creates:
- `auth_users` table with all necessary columns
- Indexes for email, role, status, tenant_id, created_at

### Step 2: Migrate Existing JSON Users to Database

Option A: Using Python script (recommended)

```bash
cd backend
python scripts/migrate_users_to_db.py
```

This will:
1. Read all users from `app/auth/data/users.json`
2. Insert them into `auth_users` table
3. Seed a new "compliance_officer" user
4. Display all migrated users

Option B: Using SQL directly (SQLite)

```bash
cd backend
sqlite3 data.db < scripts/seed_compliance_officer.sql
```

Option C: Using SQL directly (PostgreSQL)

```bash
psql -d amc_db -U postgres -f scripts/seed_compliance_officer.sql
```

### Step 3: Verify Migration

Check that users were migrated:

```sql
SELECT COUNT(*) FROM auth_users;
SELECT username, role, status FROM auth_users ORDER BY created_at DESC;
```

Expected output:
```
username              | role                           | status
-----------
compliance_officer    | Compliance & Regulatory Officer | Active
sarah.compliance      | Compliance & Regulatory Officer | Active
vikram.pm             | Fund Manager / Portfolio Manager | Active
ananya.esg            | ESG & Sustainability Analyst     | Active
rahul.sales           | Sales & Distribution Manager     | Active
priya.investor        | Retail Investor / Public Client  | Active
admin                 | Compliance & Regulatory Officer | Active
```

### Step 4: Update Application Config

The application now uses database-backed users by default. Verify in `.env`:

```bash
# .env
AUTH_USE_DATABASE=true
```

This setting is already enabled by default in `backend/app/config.py`:

```python
auth_use_database: bool = True  # Use database-backed user repository
```

### Step 5: Run Tests

Verify the migration works end-to-end:

```bash
cd backend
pytest tests/test_sql_user_repository.py -v
```

Expected: All tests pass, including:
- `test_create_compliance_officer` - Creating new users
- `test_get_by_username` - User lookup
- `test_login_success` - Authentication
- `test_me_endpoint_with_token` - Token validation
- `test_compliance_officer_can_execute_query` - Query execution

## Compliance Officer User

A new "Compliance Officer" user has been seeded with:

| Field | Value |
|-------|-------|
| **Username** | `compliance_officer` |
| **Password** | `Compliance@2026` |
| **Role** | Compliance & Regulatory Officer |
| **Email** | compliance@amc.com |
| **Department** | Regulatory & Legal Compliance |
| **Status** | Active |

### Login Test

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "compliance_officer",
    "password": "Compliance@2026"
  }'
```

Expected response:
```json
{
  "token": "eyJ...",
  "expires_at": 1728345600,
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

### Query Test

After logging in, execute a test query:

```bash
TOKEN="<token_from_login>"

curl -X POST http://localhost:8000/api/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the compliance requirements for mutual funds?",
    "session_id": "compliance_test_1"
  }'
```

Expected: Query executes successfully and returns analysis results.

## Creating Additional Users

After migration, create new users via the admin tab or SQL:

### Via Admin Tab (UI)

1. Login as `compliance_officer`
2. Navigate to "Admin" tab
3. Click "Manage Users"
4. Add new user details

### Via SQL

```sql
INSERT INTO auth_users (
    username,
    password_hash,
    display_name,
    email,
    role,
    department,
    avatar_initials,
    status,
    created_at,
    updated_at
) VALUES (
    'new_analyst',
    'pbkdf2_sha256$260000$...',  -- Use hash_password() to generate
    'New Analyst',
    'analyst@amc.com',
    'Compliance Officer',
    'Risk & Compliance',
    'NA',
    'Active',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);
```

To generate the password hash in Python:

```python
from app.auth.security import hash_password
print(hash_password("NewPassword@2026"))
```

## Backward Compatibility

If needed, the application can fall back to JSON users by setting:

```python
# In .env or config.py
AUTH_USE_DATABASE=false
```

However, this is **NOT recommended** for production. Always use the database-backed repository.

## API Changes

### Before (JSON users)
- Users were hardcoded in `app/auth/data/users.json`
- Changes required code deployment
- No audit trail of user modifications

### After (Database users)
- Users stored in `auth_users` table
- Users can be added/modified/removed without redeploying
- Full audit trail (created_at, updated_at, last_login, last_login_ip)
- Support for future features (2FA, password reset, etc.)

### API Endpoints (No change)
- `POST /api/auth/login` - Works exactly as before
- `GET /api/auth/me` - Works exactly as before
- Logout is client-side (token invalidation via expiry)

## Troubleshooting

### "Table auth_users not found"
→ Run `alembic upgrade head` to create the table

### "User not found in database"
→ Run `python scripts/migrate_users_to_db.py` to seed users

### "Password mismatch on login"
→ Verify the password_hash in the database matches the stored hash
→ Run login test with known credentials (compliance_officer / Compliance@2026)

### "Cannot connect to database"
→ Verify database connection string in `.env`
→ Check that database service is running
→ For SQLite: verify `data.db` exists in backend directory

## Security Notes

1. **Never commit plaintext passwords** to version control
2. **Always use `hash_password()`** when creating users programmatically
3. **Rotate credentials** when migrating to new systems
4. **Audit access logs** regularly for unauthorized login attempts
5. **Use HTTPS** in production (not just for tokens, but all endpoints)
6. **Database passwords** should be rotated after migration
7. **Backup the database** before and after migration

## Related Documentation

- [Security Remediation Plan](../SECURITY_REMEDIATION_PLAN.md) - Comprehensive security fixes
- [Backend Setup](../README.md) - General setup instructions
- [Authentication Flow](../app/auth/README.md) - How authentication works

## Support

For questions about the migration:

1. Check the test suite: `backend/tests/test_sql_user_repository.py`
2. Review the SQL repository: `backend/app/auth/sql_repository.py`
3. Check database schema: `backend/app/schemas/auth_users_table.py`
4. Run tests: `pytest tests/test_sql_user_repository.py -v`

---

**Last Updated**: 2026-10-12
**Status**: ✓ Ready for production deployment
