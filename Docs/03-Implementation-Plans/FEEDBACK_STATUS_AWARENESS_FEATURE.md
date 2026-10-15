# Feature Design: Contextual Feedback-Status Awareness in the Feedback Modal

**Project:** AMC Context Engineering Platform
**Component:** Feedback & Issue-Tracking Subsystem
**Status:** Proposed (Design Only — No Implementation)
**Author:** Design draft generated from `PROJECT_OVERVIEW.md`
**Date:** October 14, 2026

---

## 1. Problem Statement

Today, when a user opens the feedback modal for a query response, the modal has no awareness of whether another user has already reported the same (or a semantically equivalent) problem. This leads to:

- Duplicate reports for the same underlying issue, with no visibility for the reporting user.
- No signal to the user that their problem is already known and "in flight."
- Potential duplicate repair tasks being created in the repair engine for what is effectively one root-cause issue.
- Lost traceability — there is no single place that aggregates "who reported this, and how many times."

**Goal:** When Bob opens the feedback modal for a query that matches (exactly or semantically) a query Alice already flagged, show Bob a concise, non-blocking status banner (e.g. *"A similar query has already been reported. The issue is pending review or repair."*) — without preventing Bob from still submitting his own feedback.

### Non-Goals
- This design does not implement automated answer repair or the repair engine's internal workflow — it only prevents *duplicate* repair tasks from being spawned and surfaces status.
- It does not change how answers are generated, cached, or synthesized (Sections 4, 7 of the existing pipeline are untouched).
- It does not restrict or gate feedback submission — submission always remains allowed.

---

## 2. Analysis of the Existing System

Derived from `PROJECT_OVERVIEW.md`:

| Existing Component | Relevance to This Feature |
|---|---|
| `backend/app/retrieval/cache.py` → `SemanticQueryCache` | Already implements the **exact-hash + semantic (FAISS) two-stage match pattern** we need (hash lookup <1ms, embedding similarity ~20–30ms, threshold 0.92 for cache hits). This is the template for issue matching, not something to duplicate. |
| `backend/app/retrieval/intent.py` → `IntentClassifier` | Already extracts query type, entities, and taxonomy path per query — needed to disambiguate structurally-similar-but-different-subject queries (see §5.3). |
| `backend/app/retrieval/resolver.py` → `EntityResolver` | Produces canonical entity names (e.g. "Adani Enterprises" → "AEL") — used to confirm two queries are about the *same* entity, not just similarly worded. |
| `backend/app/feedback/session_manager.py` → `SessionManager` | Existing passive/active feedback tracking. This is the natural home for the new "issue" concept — it already tracks response/query pairs and correction signals. |
| SQLite `data.db` (Feedback table, Audit logs) | Existing feedback storage — extended, not replaced (see §6). |
| `/api/feedback` route | Existing submission endpoint — extended additively; existing clients/behavior unaffected. |
| Repair Engine (🔄 Partial — "Modular service client ready, needs full deployment") | The feature must *avoid creating duplicate repair tasks* against this service when one is already active for the same issue. |
| React frontend, feedback action modal (implied by `/api/feedback`) | New UI surface: a status banner inside the existing modal, populated by a new read endpoint. |

**Key existing pattern we reuse rather than reinvent:** the cache's two-stage exact→semantic lookup, and the already-computed intent/entity metadata from the retrieval pipeline. This keeps the feature consistent with the platform's established approach and avoids a second, divergent matching implementation.

---

## 3. Proposed Architecture

### 3.1 New Logical Component: `IssueMatcher`

A new module alongside the existing feedback code:

```
backend/app/feedback/
  ├── session_manager.py        (existing)
  ├── issue_store.py            (new — CRUD for FeedbackIssue)
  ├── issue_matcher.py          (new — exact + semantic + entity matching)
  └── routes.py                 (extended — new GET status endpoint)
```

`IssueMatcher` does **not** stand up a new embedding pipeline. It calls the same `Embedder` (FastEmbed `BAAI/bge-small-en-v1.5`) already used by `VectorStore` and `SemanticQueryCache`, and queries a small, dedicated FAISS index (`feedback_issue_index`) containing only the canonical query embeddings of **open** issues (`reported`, `under_review`, `in_repair`). Keeping this index separate and small (rather than reusing the full document/query corpus index) keeps lookups fast and keeps resolved/closed issues out of the matching surface by construction.

### 3.2 High-Level Flow

```
┌────────────────────────────────────────────────────────────────────┐
│  Alice: submits query → gets response → opens feedback modal        │
│  → submits feedback ("incorrect")                                   │
└───────────────────────────────┬────────────────────────────────────┘
                                 ▼
                   POST /api/feedback (existing, extended)
                                 ▼
              ┌──────────────────────────────────┐
              │  IssueMatcher.find_or_create()    │
              │  1. Exact hash check               │
              │  2. Semantic (FAISS) check          │
              │  3. Entity/taxonomy cross-check     │
              │  → No match → CREATE new Issue      │
              └──────────────────────────────────┘
                                 ▼
          FeedbackIssue(status=reported) + FeedbackEntry(Alice)
                                 ▼
          Alice is recorded as an active feedback contributor


┌────────────────────────────────────────────────────────────────────┐
│  Bob: submits a same/similar query → gets response →                │
│  opens feedback modal                                               │
└───────────────────────────────┬────────────────────────────────────┘
                                 ▼
        On modal open → GET /api/feedback/status (new, read-only)
                                 ▼
              ┌──────────────────────────────────┐
              │  IssueMatcher.lookup()             │
              │  1. Exact hash check               │
              │  2. Semantic (FAISS) check          │
              │  3. Entity/taxonomy cross-check     │
              │  → MATCH found (issue_id=...)       │
              └──────────────────────────────────┘
                                 ▼
     Modal renders banner: "A similar query has already been
     reported. The issue is pending review or repair."
                                 ▼
     Bob's feedback form remains fully usable (non-blocking)
                                 ▼
     Bob submits → POST /api/feedback with matched issue_id
                                 ▼
     New FeedbackEntry(Bob) linked to the SAME FeedbackIssue
     → no new repair task created; existing one is reused
```

---

## 4. Data Model

Additive changes to the existing SQLite application database (`data.db`). No existing columns are removed or repurposed, so this is backward-compatible.

### 4.1 New table: `feedback_issues`

| Column | Type | Notes |
|---|---|---|
| `issue_id` | TEXT (PK, UUID) | Stable identifier shared across all related feedback entries |
| `canonical_query_text` | TEXT | The first (triggering) query text, normalized |
| `query_hash` | TEXT (indexed) | `md5(normalize(query))`, mirrors `SemanticQueryCache`'s exact-match key |
| `query_embedding_ref` | TEXT | Pointer into `feedback_issue_index` (FAISS vector id) |
| `primary_entities` | JSON | Canonical entity list from `EntityResolver` at creation time |
| `taxonomy_paths` | JSON | From `IntentClassifier`, used to scope semantic matching |
| `status` | TEXT (enum) | `reported` \| `under_review` \| `in_repair` \| `resolved` \| `closed` |
| `repair_task_id` | TEXT (nullable) | FK-like reference into the Repair Engine, set once a repair task is actually opened |
| `contributor_count` | INTEGER | Denormalized count of distinct users who have submitted feedback on this issue |
| `created_at` / `updated_at` | DATETIME | Standard audit fields |
| `resolution_notes` | TEXT (nullable) | Set when status moves to `resolved`/`closed` |

### 4.2 Extended table: `feedback_entries` (existing feedback table)

Add two nullable columns so existing rows and existing write paths remain valid:

| New Column | Type | Notes |
|---|---|---|
| `issue_id` | TEXT (nullable FK → `feedback_issues.issue_id`) | Null for pre-migration rows; populated for all new submissions |
| `match_type` | TEXT (nullable enum) | `exact` \| `semantic` \| `new` — records *how* this entry was associated with its issue, for later tuning/auditing |

### 4.3 Derived concept: "Active feedback contributor"

Rather than a new table, this is computed as: a user with ≥1 row in `feedback_entries`. If the platform wants this as a first-class, queryable flag (e.g. for the Admin Panel), a lightweight `user_feedback_stats` view/materialized table can be added later — not required for v1 of this feature.

---

## 5. Matching Strategy

Matching happens in two call sites that share the same `IssueMatcher` logic: the read-only status check (modal open) and the write path (feedback submission). Using one shared function guarantees Bob never gets a different answer when he submits versus when he looked.

### 5.1 Stage 1 — Exact Match (<1ms)
Normalize and hash the incoming query exactly as `SemanticQueryCache` does today (`md5(query.lower().strip())`). If an **open** `feedback_issues` row has the same `query_hash`, it's an exact match — skip to §5.4.

### 5.2 Stage 2 — Semantic Match (~20–30ms)
If no exact match, embed the query (reusing the existing `Embedder`) and search `feedback_issue_index` (FAISS) for the nearest open issue.

- Proposed similarity threshold: **≥ 0.85** cosine similarity (slightly more permissive than the 0.92 used for cache hits, since this is an informational match rather than one that reuses a cached *answer* — a false positive here only shows an extra banner, not a wrong answer).
- Threshold is a configuration value (`FEEDBACK_MATCH_THRESHOLD`), tunable independently of the cache's threshold.

### 5.3 Stage 3 — Entity/Taxonomy Cross-Check (guards against false positives)
Semantic similarity alone is **not sufficient** on this platform: structurally similar queries about *different* entities ("ESG score of Adani Enterprises?" vs. "ESG score of Ambuja?") can score highly similar while referring to unrelated issues. Stage 2 candidates are therefore confirmed against:

- `primary_entities` overlap (using the same canonical entity names `EntityResolver` already produces), and
- `taxonomy_paths` overlap from `IntentClassifier`.

A semantic candidate is only accepted as a match if entity and taxonomy overlap confirm it; otherwise it is treated as a new, distinct issue. This reuses pipeline outputs that are already computed per query — no extra classification cost.

### 5.4 Resulting Match Object
```json
{
  "matched": true,
  "issue_id": "iss_8f21...",
  "status": "in_repair",
  "match_type": "semantic",
  "similarity_score": 0.91,
  "message": "A similar query has already been reported. The issue is pending review or repair."
}
```

---

## 6. Status Lifecycle

```
 reported ──► under_review ──► in_repair ──► resolved ──► closed
    ▲                                            │
    └────────────── reopened ◄───────────────────┘
                 (new feedback after resolution)
```

| Status | Meaning | Who/what transitions it |
|---|---|---|
| `reported` | Created from first feedback (Alice's submission) | System, automatically |
| `under_review` | A reviewer/triage process has acknowledged it | Triage workflow / Admin Panel action |
| `in_repair` | A repair task exists in the Repair Engine (`repair_task_id` set) | Repair Engine integration, once a task is actually opened |
| `resolved` | Fix has been applied/verified | Reviewer action |
| `closed` | Issue archived after resolution window | System (TTL) or reviewer action |
| `reopened` | New feedback arrives after `resolved`/`closed` | System, automatically, on new matching feedback |

Only `reported`, `under_review`, `in_repair`, and `reopened` issues are included in `feedback_issue_index` for matching purposes (per §3.1), so users are only told about issues that are genuinely still pending — resolved/closed issues fall out of the matching surface automatically, satisfying the "pending review or repair" framing from the spec without extra filtering logic at query time.

---

## 7. API Design

### 7.1 `GET /api/feedback/status` (new, read-only)

Called when the feedback modal opens, **before** the user submits anything.

**Request**
```
GET /api/feedback/status?response_id={response_id}&query={query_text}
```

**Response (match found)**
```json
{
  "has_existing_issue": true,
  "issue_id": "iss_8f21...",
  "status": "in_repair",
  "message": "A similar query has already been reported. The issue is pending review or repair.",
  "match_type": "semantic",
  "contributor_count": 3
}
```

**Response (no match)**
```json
{ "has_existing_issue": false }
```

This endpoint is read-only, idempotent, and side-effect free — it is safe to call every time the modal opens, including repeatedly, without affecting issue state.

### 7.2 `POST /api/feedback` (existing, extended)

Request body gains one implicit server-side step (no new required client field): the backend runs the same `IssueMatcher` used by §7.1 before persisting. Response payload gains:

```json
{
  "feedback_id": "fb_...",
  "issue_id": "iss_8f21...",
  "issue_status": "in_repair",
  "was_matched_to_existing_issue": true
}
```

Existing clients that ignore these new response fields continue to work unmodified — this is purely additive.

---

## 8. UI Integration (Feedback Action Modal)

**Trigger:** modal mount (on open), via `GET /api/feedback/status`.

**Modal states:**

| State | Rendering |
|---|---|
| Loading status check | Modal opens immediately with the normal feedback form; banner area shows nothing (or a subtle skeleton) — the form is never blocked waiting on this call |
| No existing issue | No banner; modal behaves exactly as it does today |
| Existing issue found | A compact, non-blocking status banner above the feedback form: *"A similar query has already been reported. The issue is pending review or repair."* Optionally, a muted secondary line such as *"3 users have reported this so far."* using `contributor_count` |
| Submission after match | Standard success confirmation; no change to the banner — the form stays fully functional throughout |

**Key UX rule:** the banner is informational only. It never disables the submit button, never requires an extra confirmation step, and never changes the feedback form's fields. This satisfies the "without preventing users from submitting additional feedback" requirement directly.

---

## 9. Preventing Duplicate Repair Tasks

- A `repair_task_id` lives on `feedback_issues`, **not** on individual `feedback_entries`.
- When an issue transitions to `in_repair`, exactly one repair task is created against the Repair Engine client, and `repair_task_id` is stamped onto the issue.
- All subsequent matching feedback (Bob, Carol, …) attaches to the same `issue_id` via `IssueMatcher`, and therefore never triggers a second call into the Repair Engine for the same underlying problem — the repair task creation step is gated on "does this issue already have a `repair_task_id`," not on "did feedback just arrive."
- If an issue is `reopened` after `resolved`/`closed`, the existing `repair_task_id` is cleared and a fresh determination is made at the next triage step — this is a deliberate decision point for reviewers rather than automatic re-ticketing, to avoid repair-task churn from noisy late feedback.

---

## 10. Feedback Traceability

- Every `feedback_entries` row keeps its original `user_id`, `query_text`, `response_id`, and `comment`, exactly as today — nothing about an individual's feedback is overwritten or merged.
- The `issue_id` foreign key is the only addition, giving a one-to-many trace: one issue → many feedback entries → many contributing users.
- `match_type` on each entry (`exact` / `semantic` / `new`) preserves *why* that entry was grouped the way it was, which is useful both for user-facing traceability and for later tuning of the similarity threshold in §5.2.
- `contributor_count` on the issue gives an at-a-glance signal (surfaced in the Admin Panel and optionally in the modal) without needing a join at read time.

---

## 11. Non-Regression & Backward Compatibility

- All schema changes are additive (`nullable` new columns, one new table) — no destructive migration.
- `POST /api/feedback` keeps its existing required fields and existing success path; the only change is an extra, internal matching step and extra (optional-to-consume) response fields.
- `GET /api/feedback/status` is a brand-new, independent endpoint — it cannot break any existing route.
- The matching logic reuses already-computed pipeline outputs (embeddings, intent, entities) rather than adding a new, parallel classification step to the main query-response path — the core `/api/query` flow in `RetrievalOrchestrator` is untouched.
- The feedback-issue FAISS index (`feedback_issue_index`) is isolated from the main document/query vector indexes, so tuning its threshold or rebuilding it cannot affect retrieval quality or the semantic *answer* cache.

---

## 12. Edge Cases & Open Questions

| Case | Handling |
|---|---|
| Two users submit near-simultaneous feedback for a brand-new issue (race condition) | `IssueMatcher.find_or_create()` should use a DB-level unique constraint on `query_hash` for `find-or-create`, with retry-on-conflict, so only one `feedback_issues` row is ever created per race |
| Corpus/index update changes embeddings | `feedback_issue_index` only needs to be rebuilt when its own embedding model changes, not on every corpus ingestion — it is independent of the document/vector corpus |
| Multi-tenant isolation | `feedback_issues` and matching queries should be scoped by `tenant_id`, consistent with the platform's existing multi-tenant model, so Issue matching never crosses tenant boundaries |
| User wants to see "already resolved" status, not just "pending" | Current design intentionally excludes resolved/closed issues from the matching surface so the banner only ever says "pending" per the spec; this can be revisited if product wants a different message for recently-resolved issues |
| Threshold mistuning (too many/few matches) | `match_type` + `similarity_score` logging (§10) gives the data needed to retune `FEEDBACK_MATCH_THRESHOLD` without a design change |

---

## 13. Suggested Rollout Phases

1. **Phase 1 — Data & matching only:** add tables, `IssueMatcher`, `GET /api/feedback/status`; no UI change yet; validate match precision/recall against production feedback logs.
2. **Phase 2 — Modal UI:** wire the banner into the existing feedback modal behind a feature flag.
3. **Phase 3 — Repair Engine linkage:** connect `repair_task_id` creation/reuse once the Repair Engine's "Modular service client" (already noted as partially complete) is fully deployed.
4. **Phase 4 — Admin visibility:** surface `contributor_count` and issue status in the Admin Panel for triage.
