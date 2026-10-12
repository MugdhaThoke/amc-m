#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
decommission_legacy_engine.py
=============================
Automated operational script to execute Step 6.3 & Step 6.4 of the
V2 Query Engine Decommissioning Roadmap (PLAN-V2-TAKEOVER-001).

Safety Controls:
- Enforces mandatory 14-day bake period from cutover date (2026-10-08).
- Dry-run mode by default unless --execute is specified.
- Backs up legacy files before archiving into archive/legacy_engine/.
"""

import argparse
import datetime
import os
import shutil
import sys
from pathlib import Path

CUTOVER_DATE = datetime.date(2026, 10, 8)
BAKE_PERIOD_DAYS = 14
SUNSET_DATE = CUTOVER_DATE + datetime.timedelta(days=BAKE_PERIOD_DAYS)

LEGACY_ENGINE_FILES = [
    "backend/app/engine/retrieval.py",
    "backend/app/engine/hyde.py",
    "backend/app/engine/context_memory.py",
    "backend/app/engine/query_classifier.py",
]


def check_bake_period(force: bool = False) -> bool:
    today = datetime.date.today()
    days_elapsed = (today - CUTOVER_DATE).days
    print(f"[*] Cutover Date: {CUTOVER_DATE.isoformat()}")
    print(f"[*] Sunset Date:  {SUNSET_DATE.isoformat()} (14-day bake period)")
    print(f"[*] Current Date: {today.isoformat()} ({days_elapsed} days elapsed)")

    if days_elapsed < BAKE_PERIOD_DAYS:
        msg = (
            f"[!] WARNING: Only {days_elapsed} of {BAKE_PERIOD_DAYS} bake days have elapsed. "
            f"Physical decommissioning is blocked until {SUNSET_DATE.isoformat()}."
        )
        if not force:
            print(msg)
            print("[!] Use --force to override if this is a staging/testing run.")
            return False
        else:
            print(f"[!] Overriding bake period with --force.")
            return True
    print("[+] 14-day bake period requirement satisfied.")
    return True


def audit_dependencies(repo_root: Path):
    req_file = repo_root / "backend" / "requirements.txt"
    if not req_file.exists():
        print(f"[-] requirements.txt not found at {req_file}")
        return

    print("\n[*] Auditing requirements.txt dependencies for legacy remnants...")
    with open(req_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    legacy_candidates = ["faiss-cpu", "spacy"]
    for line in lines:
        for cand in legacy_candidates:
            if cand in line.lower() and not line.strip().startswith("#"):
                print(f"  - Notice: '{line.strip()}' found in requirements.txt. Note: verify if V2 shared models still utilize this before pruning.")


def execute_archival(repo_root: Path, dry_run: bool = True):
    archive_dir = repo_root / "archive" / "legacy_engine"
    print(f"\n[*] Target Archive Directory: {archive_dir}")

    for rel_path in LEGACY_ENGINE_FILES:
        src = repo_root / rel_path
        dst = archive_dir / Path(rel_path).name

        if not src.exists():
            print(f"  [-] Source not found (already archived?): {src}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would move: {src} -> {dst}")
        else:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            # Create stub in src pointing to archive
            stub_content = f'''"""
DECOMMISSIONED LEGACY MODULE
This module was decommissioned on {datetime.date.today().isoformat()} under Step 6.3 of the V2 Cutover Plan.
Archived copy located at: archive/legacy_engine/{Path(rel_path).name}
All query engine functionality is routed through app.retrieval.orchestrator.
"""
raise RuntimeError(
    "app.engine.{Path(rel_path).stem} has been decommissioned. "
    "Use app.retrieval.orchestrator instead."
)
'''
            with open(src, "w", encoding="utf-8") as f:
                f.write(stub_content)
            print(f"  [MOVED] {src} -> {dst} (stub placed)")

    if dry_run:
        print("\n[+] Dry run complete. No files were modified.")
    else:
        print("\n[+] Legacy modules archived successfully. Stub safety guards placed.")


def main():
    parser = argparse.ArgumentParser(description="Legacy Query Engine Decommissioning CLI")
    parser.add_argument("--execute", action="store_true", help="Execute the actual file movements (default: dry-run)")
    parser.add_argument("--force", action="store_true", help="Bypass the 14-day bake period check")
    parser.add_argument("--audit-deps", action="store_true", help="Audit dependencies in requirements.txt")

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    print("=======================================================")
    print(" AMC Context Engineering: Legacy Engine Decommissioner ")
    print("=======================================================")

    can_proceed = check_bake_period(force=args.force)
    if not can_proceed and not args.force:
        sys.exit(1)

    if args.audit_deps or args.execute:
        audit_dependencies(repo_root)

    execute_archival(repo_root, dry_run=not args.execute)


if __name__ == "__main__":
    main()
