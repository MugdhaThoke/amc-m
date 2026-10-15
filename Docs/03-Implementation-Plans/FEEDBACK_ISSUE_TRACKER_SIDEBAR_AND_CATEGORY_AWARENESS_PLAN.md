# Feature Design (Phase 2): Feedback Issue Tracker — Sidebar Navigation, Per-User Visibility & Category-Aware Banner

**Project:** AMC Context Engineering Platform
**Builds on:** `FEEDBACK_STATUS_AWARENESS_FEATURE.md` (Phase 1 — status banner + `IssueMatcher` + `feedback_issues` table, already implemented per the attached screenshots)
**Status:** Proposed (Design Only — No Implementation)
**Date:** October 14, 2026

---

## 1. What's Being Added

Three changes on top of the already-implemented Phase 1 ("Issue Status Awareness" banner + Admin → "Feedback Issues & Triage" tab):

1. **Promote the admin triage queue out of the Admin & Governance tab bar and into its own sidebar entry**, nested under "Admin & Governance" in the left `Sidebar.jsx`. It keeps showing **all** issues, across all users — unchanged scope, new location.
2. **Add a parallel, non-admin sidebar entry** ("My Feedback" / "My Reported Issues") that any authenticated user can see, scoped strictly to **that user's own** submitted feedback — never another user's queries or identity.
3. **Extend the feedback modal's "Issue Status Awareness" banner** to show *which* taxonomy categories (`F01`–`F12`) previous users already flagged for this query, not just the status text — e.g. the admin table's "1 feedback" entry should translate into something like `Missing Key Documents ×2`, `Wrong Numbers or Dates ×1` as small pills under the existing banner.

Everything below assumes the current state captured in the two screenshots: the Admin & Governance page has five inner tabs (`User Profile Management`, `Role Access Matrix`, `Security & Audit Logs`, `Authorized Ingest & Pipeline`, `Feedback Issues & Triage`), and the feedback modal already shows a blue "Issue Status Awareness" banner with a status badge, match-type badge, contributor count, and a 12-item `F01`–`F12` checkbox grid grouped into three sections (*Understanding the Question*, *Sources & Accuracy*, *Clarity & Risk*).

---

## 2. Current vs. Proposed Navigation

**Current (`Sidebar.jsx` + `AdminPanel`)**
```
WORKSPACE
 ├─ Chat
 ├─ Compare
 ├─ Analytics
 └─ Admin & Governance            ← single page, 5 inner tabs
      ├─ User Profile Management
      ├─ Role Access Matrix
      ├─ Security & Audit Logs
      ├─ Authorized Ingest & Pipeline
      └─ Feedback Issues & Triage  ← tab #5 (being relocated)
COMPLIANCE MODULES (collapsed)
```

**Proposed**
```
WORKSPACE
 ├─ Chat
 ├─ Compare
 ├─ Analytics
 ├─ My Feedback                    ← NEW, visible to every authenticated user
 └─ Admin & Governance  ▾          ← becomes an expandable sidebar group (admin-only)
      ├─ Overview                  (User Profile Mgmt / Role Matrix / Security / Ingest — unchanged, 4 tabs remain)
      └─ Feedback Issues & Triage  ← NEW top-level sidebar item under this group (moved out of the tab bar)
COMPLIANCE MODULES (collapsed)
```

This is a **navigation refactor only** for the admin side — the triage queue's table, stat cards (`Total Reported Issues`, `Pending Review`, `In Repair (Linked)`, `Contributors Impacted`, `Resolved/Closed`), search box, filter dropdown, and triage actions (`Repair` / `Resolve` / view) are unchanged in behavior; they simply render at their own route instead of as the 5th tab.

---

## 3. Visibility & Access Model

| Sidebar Entry | Visible to | Data Scope | Enforcement |
|---|---|---|---|
| `Admin & Governance → Feedback Issues & Triage` | Users with an admin-tier role | **All** issues, all contributing users, across the tenant | Route guard (frontend) **and** server-side role check on the API (never rely on hiding the sidebar item alone) |
| `My Feedback` | Every authenticated user | Only issues where `feedback_entries.user_id = current_user.id` | Server-side `WHERE user_id = :current_user_id` filter baked into the query — not a client-supplied parameter |

**Why server-side enforcement matters here specifically:** the admin table already displays an `issue_id` (e.g. `iss_250a60e32cd2`) in its UI. If the "My Feedback" endpoint ever accepted an `issue_id` or `user_id` from the client without re-validating ownership, a user could enumerate or guess another user's issue and view their query/contributor details (an IDOR — insecure direct object reference — vulnerability). The personal endpoint must derive scope from the authenticated session only, never from a request parameter.

---

## 4. "My Feedback" Page — What It Shows vs. Hides

Reusing the existing triage-queue table component, but with these deliberate differences:

| Column (Admin view) | Column (My Feedback view) | Change |
|---|---|---|
| Query & Entities | Query & Entities | Same — but only rows the user personally reported or matched into |
| Contributors (`👥 1`, "1 feedback") | **Removed or anonymized** to `Also reported by N other user(s)` | Never name other contributors to a non-admin user |
| Status | Status | Same badge styling (`UNDER REVIEW`, `IN REPAIR`, etc.) |
| Repair Linkage | Repair Linkage | Same (read-only — a user can see *that* a repair task exists, not its internal Repair Engine details) |
| Triage Actions (`Repair` / `Resolve` / 👁) | **Removed** | Triage actions are an admin privilege; the personal view is read-only |

Additional field unique to this view: **"Your reported categories"** — the `F01`–`F12` codes *this specific user* selected when they submitted feedback, so they can see what they flagged without needing to reopen the modal.

---

## 5. Category-Aware Feedback Banner

### 5.1 Current banner (Phase 1, already live)
```
ⓘ Issue Status Awareness   [IN REPAIR]  [EXACT MATCH]
A similar query has already been reported. The issue is pending review or repair.
👥 3 users have reported this issue so far
You can still submit additional feedback below.
```

### 5.2 Proposed addition — category breakdown
```
ⓘ Issue Status Awareness   [IN REPAIR]  [EXACT MATCH]
A similar query has already been reported. The issue is pending review or repair.
👥 3 users have reported this issue so far

Previously flagged:
 [F08 Wrong Numbers or Dates ×2]  [F04 Missing Key Documents ×1]  [F06 Incorrect Citations / Sources ×1]

You can still submit additional feedback below.
```

- Pills are sorted by count, descending; cap at **top 5** with a `+N more` expander to avoid overwhelming the modal for issues with many distinct categories flagged.
- Each pill reuses the existing `F01`–`F12` code + label + tooltip styling already in the checkbox grid below it, so the banner visually "previews" which boxes other users ticked — purely informational, no checkboxes are pre-ticked for the current user, and nothing here restricts which boxes they can still select.
- This directly helps triage: a reviewer (or even the next reporting user) can see *why* an issue was flagged without opening each individual feedback entry.

---

## 6. Data Model Changes

Builds additively on Phase 1's `feedback_issues` / `feedback_entries` tables — no breaking changes.

### 6.1 `feedback_entries` — store selected categories
The modal already lets a user tick multiple `F01`–`F12` boxes in one submission (per the screenshot). Add:

| Column | Type | Notes |
|---|---|---|
| `categories` | JSON array | e.g. `["F04", "F08"]` — the codes selected in that specific submission |

### 6.2 New table: `feedback_issue_category_counts`
Rather than re-scanning all `feedback_entries` rows every time a banner needs a breakdown (expensive at scale and race-prone under concurrent writes), maintain a **denormalized, atomically-updated counter table**:

| Column | Type | Notes |
|---|---|---|
| `issue_id` | TEXT | FK → `feedback_issues.issue_id` |
| `category_code` | TEXT | `F01`…`F12` |
| `count` | INTEGER | Running total of how many feedback entries on this issue selected this code |
| `updated_at` | DATETIME | |

Primary key: `(issue_id, category_code)`.

**Write pattern (race-safe, works in SQLite today):**
```sql
INSERT INTO feedback_issue_category_counts (issue_id, category_code, count, updated_at)
VALUES (:issue_id, :code, 1, CURRENT_TIMESTAMP)
ON CONFLICT (issue_id, category_code)
DO UPDATE SET count = count + 1, updated_at = CURRENT_TIMESTAMP;
```
One `UPSERT` per selected category, inside the same transaction as the `feedback_entries` insert — so a submission with 2 categories ticked does 2 upserts, atomically alongside the entry write. This avoids read-then-write races when multiple users submit near-simultaneously on the same issue (the classic "lost update" problem of computing counts in application code).

### 6.3 Why not just `COUNT(*) GROUP BY category` on read?
At low volume it's fine, but the banner's `GET /api/feedback/status` is called **every time any modal opens** (per Phase 1 §7.1) — a read-heavy, latency-sensitive path. A pre-aggregated counter table turns that into an indexed point-lookup instead of a scan/group-by over a growing `feedback_entries` table, which matters as issues accumulate feedback over months.

---

## 7. API Changes

### 7.1 `GET /api/feedback/status` — extended response
```json
{
  "has_existing_issue": true,
  "issue_id": "iss_250a60e32cd2",
  "status": "in_repair",
  "message": "A similar query has already been reported. The issue is pending review or repair.",
  "match_type": "exact",
  "contributor_count": 3,
  "category_breakdown": [
    { "code": "F08", "label": "Wrong Numbers or Dates", "count": 2 },
    { "code": "F04", "label": "Missing Key Documents", "count": 1 },
    { "code": "F06", "label": "Incorrect Citations / Sources", "count": 1 }
  ]
}
```
Additive field — existing consumers that ignore `category_breakdown` keep working.

### 7.2 `GET /api/feedback/mine` (new)
Returns only the current user's own reported/matched issues, with the Repair Linkage/Status fields but **without** other contributors' identities (see §4). Scope is derived server-side from the session, not from a query parameter.

### 7.3 `GET /api/admin/feedback/issues` (relocated, not renamed in behavior)
This is effectively the data source already powering the "Feedback Issues & Triage Queue" table. No contract change — it now simply backs its own route/page instead of the 5th Admin & Governance tab. Role-gated as it is today.

---

## 8. Edge Cases & Real-Time / Scale Considerations

| Concern | Handling |
|---|---|
| **Concurrent submissions on the same issue** (e.g. 5 users flag the same query within seconds) | Counter updates use `UPSERT ... DO UPDATE SET count = count + 1` (§6.2) inside the same DB transaction as the feedback write — no read-modify-write race, no lost increments |
| **Modal-open read load** (status endpoint called on every open, potentially for popular/controversial queries) | `category_breakdown` and `status` are served from the pre-aggregated counter table (point lookup) rather than computed on the fly; for very hot issues, add a short-TTL (e.g. 5–10s) in-memory/Redis cache keyed by `issue_id` so a burst of modal-opens for the same issue hits one DB read, not N |
| **Personal view data leakage (IDOR)** | `/api/feedback/mine` never accepts a client-supplied `user_id`/`issue_id` filter for scoping — always derived from the authenticated session; covered by a dedicated authorization test (user A cannot retrieve user B's rows by any parameter manipulation) |
| **Admin sidebar item shown to non-admins via stale cached UI state** | Backend authorization is the source of truth; even if the sidebar briefly renders before a role check resolves, the underlying `/api/admin/feedback/issues` call must 403 for non-admin sessions regardless of what the UI shows |
| **Large number of categories flagged on a single issue** | Banner caps to top-5 pills + `+N more` (§5.2); the admin triage table and "My Feedback" table should paginate (e.g. 25/page) rather than load all issues client-side once issue volume grows |
| **Multi-tenant isolation** | Both the admin "all issues" scope and the personal "my issues" scope must additionally filter by `tenant_id` (the platform already scopes cache/query by `tenant_id` per `PROJECT_OVERVIEW.md` §7 `SemanticQueryCache`), so an admin never sees another tenant's issues unless explicitly a cross-tenant super-admin role |
| **Issue reopened after resolution (Phase 1 §6 lifecycle)** | Category counters are **not** reset on reopen — they represent full historical signal for that issue; only `status` changes. A `resolved_at`/`reopened_at` timestamp (if added later) can let the UI distinguish "flagged before vs. after the fix," but is out of scope for this phase |
| **Category counts drifting from raw entries** (e.g. a bug, manual DB edit, migration) | A periodic reconciliation job recomputes `feedback_issue_category_counts` from `feedback_entries` as a background task (low frequency, e.g. nightly) and corrects drift — cheap insurance without making the hot read path do the expensive aggregation |
| **"My Feedback" page for a user with zero issues** | Standard empty state, no special-casing needed — same as any other empty table state in the app today |

---

## 9. Five-Phase Rollout Plan

### **Phase 1 — Backend Foundations for Categories & Personal Scope**
- Add `categories` JSON column to `feedback_entries`.
- Add `feedback_issue_category_counts` table + the atomic `UPSERT` write path wired into the existing feedback-submission transaction.
- Add `GET /api/feedback/mine`, strictly session-scoped, with its own authorization test suite (including explicit IDOR negative tests).
- Extend `GET /api/feedback/status` to return `category_breakdown`.
- **No UI changes yet** — ship behind a feature flag (`FEEDBACK_CATEGORY_BREAKDOWN_ENABLED`), validated against staging traffic first.
- *Edge cases covered:* race-safe counters, tenant scoping on the new endpoint, reconciliation job scaffolding.

### **Phase 2 — Admin Sidebar Restructuring**
- Move "Feedback Issues & Triage" out of the Admin & Governance tab bar into its own route (e.g. `/admin/feedback-issues`), added as a nested sidebar item under an expandable "Admin & Governance" group in `Sidebar.jsx`.
- Admin & Governance page keeps its remaining 4 tabs (`User Profile Management`, `Role Access Matrix`, `Security & Audit Logs`, `Authorized Ingest & Pipeline`).
- No change to the triage table, stat cards, search/filter, or triage actions — a pure relocation, kept behind a flag so it can be toggled back instantly if navigation feedback is negative.
- *Edge cases covered:* stale-UI vs. server-enforced role checks (§8), route-level guard + API-level guard both verified.

### **Phase 3 — "My Feedback" Personal View**
- New sidebar entry visible to all authenticated users, backed by `GET /api/feedback/mine`.
- Reused table component, with Contributors/Triage Actions columns adjusted per §4 (anonymized "also reported by N others" instead of identities; no action buttons).
- Adds "Your reported categories" column from the user's own `feedback_entries.categories`.
- *Edge cases covered:* empty states, pagination from day one (don't assume low volume), explicit test that user A's page never renders user B's query text or identity.

### **Phase 4 — Category-Aware Modal Banner**
- Feedback modal renders the `category_breakdown` pills under the existing status banner (§5.2), sorted descending, capped at top 5 + expander.
- Fully additive to the existing non-blocking banner — never disables the checkbox grid or submit button.
- A/B or staged rollout behind a flag to validate it doesn't increase modal abandonment (i.e., users don't feel discouraged from reporting because "it's already flagged") — track submit-rate before/after.
- *Edge cases covered:* issues with 0 vs. 1 vs. many categories flagged; long category label truncation on small screens.

### **Phase 5 — Scale, Real-Time Hardening & Optimization**
- **Caching:** short-TTL (5–10s) cache for `GET /api/feedback/status` and `category_breakdown` keyed by `issue_id`, to absorb bursts of modal-opens on trending issues without hammering the DB; invalidate/refresh on new feedback writes for that issue.
- **Pagination & server-side search:** both the admin triage queue and "My Feedback" move to server-side pagination/sorting/search once issue volume grows past a UI-comfortable single page.
- **Reconciliation job:** scheduled job recomputing counters from source-of-truth `feedback_entries` to catch any drift (§8).
- **Real-time triage queue (stretch goal):** replace the admin page's manual "Refresh" button with an SSE/WebSocket push so new issues/status changes appear live — reuses the platform's existing SSE infrastructure (already used for chat streaming per `PROJECT_OVERVIEW.md`), feature-flagged and optional.
- **Load/perf targets:** define and test against an explicit latency budget for `GET /api/feedback/status` (e.g. p95 < 50ms warm, < 150ms cold) since it sits on the modal-open critical path.
- **Security pass:** dedicated authorization/penetration test round specifically for the new personal endpoint (IDOR, parameter tampering, role-escalation via stale sidebar state) before full rollout.
- **Telemetry:** dashboards for category-breakdown cache hit rate, `/mine` endpoint latency, and reconciliation-job drift size, so regressions are caught before users notice.

---

## 10. Non-Regression Notes

- All database changes are additive (new columns/tables); Phase 1's schema and endpoints are untouched.
- The admin triage table, its stat cards, search, filters, and triage actions keep identical behavior — only their location in the navigation changes (Phase 2).
- The feedback modal's existing banner text, badges, and checkbox grid are unchanged; the category pills are a pure addition above the existing "You can still submit additional feedback below" line (Phase 4).
- Every new read path (`/mine`, `category_breakdown`) is additive and optional for existing clients to consume — nothing existing breaks if ignored.
