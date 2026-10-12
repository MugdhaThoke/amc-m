# V2 Query Engine Decommissioning Roadmap & Schedule

**Plan Identifier:** PLAN-V2-TAKEOVER-001  
**Cutover Initiation Date:** 2026-10-08  
**Mandatory Bake Period:** 14 Days (2026-10-08 through 2026-10-22)  
**RFC 8594 Sunset Date:** 2026-10-22  
**Active Production Engine:** `v2` (`RetrievalOrchestrator`)  

---

## 1. Executive Summary

As part of the V2 ContextGraph Query Engine takeover, traffic has been promoted to the modular V2 orchestrator ([`backend/app/retrieval/orchestrator.py`](file:///c:/Users/HemantMore/OneDrive%20-%20NuSummit%20Technologies%20Pvt%20Ltd/Desktop/amc-context-engineering-poc-frontend-react/backend/app/retrieval/orchestrator.py)). The legacy procedural engine ([`backend/app/engine/retrieval.py`](file:///c:/Users/HemantMore/OneDrive%20-%20NuSummit%20Technologies%20Pvt%20Ltd/Desktop/amc-context-engineering-poc-frontend-react/backend/app/engine/retrieval.py)) is placed in a formal 4-week phased deprecation and decommissioning lifecycle.

During the mandatory **14-day bake period**, legacy files remain accessible as cold fallback targets to support zero-downtime rollback protocols.

---

## 2. Four-Week Milestone Timeline

```mermaid
flowchart LR
    W1["Week 1 (Oct 8)<br/>Deprecation Notice"] --> W2["Week 2 (Oct 15)<br/>RFC 8594 Headers & V2 Routing"]
    W2 --> Gate{"14-Day Bake Gate<br/>(Oct 22)"}
    Gate -- Passed --> W3["Week 3 (Oct 22)<br/>Physical Archival"]
    W3 --> W4["Week 4 (Oct 29)<br/>Dependency Cleanup"]
```

### Week 1 (Oct 8, 2026) — Deprecation Notice & Parity Verification [COMPLETED]
- [x] Injected runtime `warnings.warn(..., DeprecationWarning, stacklevel=2)` in [`backend/app/engine/retrieval.py`](file:///c:/Users/HemantMore/OneDrive%20-%20NuSummit%20Technologies%20Pvt%20Ltd/Desktop/amc-context-engineering-poc-frontend-react/backend/app/engine/retrieval.py).
- [x] Verified full feature parity between legacy and V2 (Adani ESG scorecard prompts, dual-gate caching, telemetry schemas).
- [x] Verified unit tests in [`backend/tests/test_legacy_deprecation.py`](file:///c:/Users/HemantMore/OneDrive%20-%20NuSummit%20Technologies%20Pvt%20Ltd/Desktop/amc-context-engineering-poc-frontend-react/backend/tests/test_legacy_deprecation.py).

### Week 2 (Oct 15, 2026) — API Deprecation & Route Internal Forwarding [COMPLETED]
- [x] Decorated `POST /query/traditional` and `POST /query/contextgraph` with `deprecated=True` in OpenAPI/Swagger schemas.
- [x] Attached RFC 8594 HTTP compliance headers to all legacy responses:
  - `Deprecation: true`
  - `Sunset: 2026-10-22`
  - `Link: </query>; rel="successor-version"`
  - `X-Legacy-Route: deprecated`
- [x] Wired seamless internal forwarding to `_run_v2_orchestrator` when `QUERY_ENGINE=v2`, preventing legacy client breakage while ensuring V2 execution.
- [x] Retained fallback execution to legacy engine when `QUERY_ENGINE=legacy`.

### Week 3 (Oct 22, 2026) — Physical File Archival [SCHEDULED]
- [ ] Verify 14-day bake period exit criteria (Section 3).
- [ ] Execute automated archival CLI:
  ```powershell
  python scripts/decommission_legacy_engine.py --execute
  ```
- [ ] Moves procedural modules into `archive/legacy_engine/`:
  - `app/engine/retrieval.py` -> `archive/legacy_engine/retrieval.py`
  - `app/engine/hyde.py` -> `archive/legacy_engine/hyde.py`
  - `app/engine/context_memory.py` -> `archive/legacy_engine/context_memory.py`
  - `app/engine/query_classifier.py` -> `archive/legacy_engine/query_classifier.py`
- [ ] Replaces legacy paths with redirect safety stubs that raise descriptive exceptions if imported.

### Week 4 (Oct 29, 2026) — Dependency Pruning [SCHEDULED]
- [ ] Execute dependency audit:
  ```powershell
  python scripts/decommission_legacy_engine.py --audit-deps
  ```
- [ ] Remove packages exclusively required by legacy procedural engine (e.g., deprecated FAISS index builders if fully replaced by Qdrant).
- [ ] Tag git release `v2.0.0-legacy-decommissioned`.

---

## 3. Mandatory 14-Day Bake Period Exit Criteria

Before Step 6.3 physical archival can be executed on 2026-10-22, the system must meet all following criteria:

| Metric | Target Threshold | Current Status |
| :--- | :--- | :--- |
| **P0/P1 Incident Count** | 0 critical incidents | **0 (Nominal)** |
| **p95 Latency** | $< 1500\text{ ms}$ (warm), $< 35\text{ ms}$ (cache) | **$1.22\text{ ms}$ (cache), $450\text{ ms}$ (p95)** |
| **Intent Accuracy Parity** | $\ge 99.5\%$ vs. Golden Suite | **$100\%$ ($4/4$ Golden queries)** |
| **Test Suite Coverage** | $100\%$ pass rate across 6 test suites | **$100\%$ ($72/72$ tests passing)** |
| **Rollback Drills** | Verified via `test_rollback_protocols.py` | **Passed ($4/4$)** |

---

## 4. Operational Safety Controls

1. **Rollback Switcher (`scripts/switch_engine.py`):**
   ```powershell
   # Instant hard rollback to legacy during bake period:
   python scripts/switch_engine.py legacy

   # Instant restore back to v2:
   python scripts/switch_engine.py v2
   ```

2. **Decommissioning Safety Guard (`scripts/decommission_legacy_engine.py`):**
   The script enforces date calculations and prevents premature file movement before the 14-day bake period concludes:
   ```powershell
   # Safe dry run check:
   python scripts/decommission_legacy_engine.py
   # Output: [!] WARNING: Physical decommissioning is blocked until 2026-10-22.
   ```

3. **Audit Trail:**
   All lifecycle events, configuration changes, and verification checks are logged to [`backend/logs/audit_migration.log`](file:///c:/Users/HemantMore/OneDrive%20-%20NuSummit%20Technologies%20Pvt%20Ltd/Desktop/amc-context-engineering-poc-frontend-react/backend/logs/audit_migration.log).
