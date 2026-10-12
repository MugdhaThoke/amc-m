#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
switch_engine.py
================
Operational CLI tool to switch or rollback the active query serving engine:
  - legacy : Emergency hard rollback to procedural RAG
  - v2     : Target state V2 Retrieval Orchestrator
  - canary : Canary traffic split (% specified via --canary-pct)
  - shadow : Legacy serves synchronously; V2 executes asynchronously

Usage:
  python scripts/switch_engine.py legacy
  python scripts/switch_engine.py v2
  python scripts/switch_engine.py canary --canary-pct 20
  python scripts/switch_engine.py shadow
"""

import argparse
import os
import re
import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / "backend" / ".env"


def update_env_file(engine: str, canary_pct: int = 0) -> None:
    if not ENV_PATH.exists():
        print(f"Error: {ENV_PATH} not found.", file=sys.stderr)
        sys.exit(1)

    content = ENV_PATH.read_text(encoding="utf-8")

    # Update or add QUERY_ENGINE
    if re.search(r"^QUERY_ENGINE=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^QUERY_ENGINE=.*$", f"QUERY_ENGINE={engine}", content, flags=re.MULTILINE)
    else:
        content += f"\nQUERY_ENGINE={engine}\n"

    # Update or add CANARY_PERCENTAGE
    if re.search(r"^CANARY_PERCENTAGE=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^CANARY_PERCENTAGE=.*$", f"CANARY_PERCENTAGE={canary_pct}", content, flags=re.MULTILINE)
    else:
        content += f"\nCANARY_PERCENTAGE={canary_pct}\n"

    ENV_PATH.write_text(content, encoding="utf-8")
    print(f"Updated {ENV_PATH}:")
    print(f"  QUERY_ENGINE={engine}")
    print(f"  CANARY_PERCENTAGE={canary_pct}")


def main():
    parser = argparse.ArgumentParser(description="Switch or Rollback Query Engine")
    parser.add_argument(
        "engine",
        choices=["legacy", "v2", "canary", "shadow"],
        help="Target serving engine",
    )
    parser.add_argument(
        "--canary-pct",
        type=int,
        default=10,
        help="Percentage of traffic routed to V2 in canary mode (0-100, default: 10)",
    )

    args = parser.parse_args()
    update_env_file(args.engine, args.canary_pct if args.engine == "canary" else 0)
    print(f"\nSuccessfully set serving engine to '{args.engine}'.")
    print("If running with reload-enabled Uvicorn, settings reload automatically.")
    print("Otherwise, restart Uvicorn service to apply changes.")


if __name__ == "__main__":
    main()
