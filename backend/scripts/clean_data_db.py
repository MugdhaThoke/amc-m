#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Script: clean_data_db.py
# Description: Truncate all records from data.db while keeping all table schemas
#              intact, preserving only user 'amc_admin' in the auth_users table,
#              and optionally clearing disk-based chat session logs.
# ===========================================================================

import argparse
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys

# Ensure UTF-8 output if console supports reconfiguration
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Default paths and configurations
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data.db"
DEFAULT_CHAT_SESSIONS_DIR = BACKEND_DIR / "logs" / "chat_sessions"
DEFAULT_KEEP_USER = "amc_admin"


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    """Retrieve list of all user-defined tables (ignoring SQLite internal tables)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_counts(conn: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    """Return dictionary mapping table name to row count."""
    cursor = conn.cursor()
    counts = {}
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        counts[table] = cursor.fetchone()[0]
    return counts


def create_atomic_backup(source_conn: sqlite3.Connection, db_path: Path) -> Path:
    """Create an atomic backup of the SQLite database file before modification."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.bak_{timestamp}"
    dest_conn = sqlite3.connect(str(backup_path))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
    return backup_path


def clean_database(
    db_path: Path = DEFAULT_DB_PATH,
    chat_sessions_dir: Path = DEFAULT_CHAT_SESSIONS_DIR,
    keep_user: str = DEFAULT_KEEP_USER,
    dry_run: bool = False,
    backup: bool = True,
    clear_chat_logs: bool = True,
    skip_vacuum: bool = False,
    force: bool = False,
) -> bool:
    """
    Remove all records from all tables in data.db while preserving table schemas,
    keeping only the specified username in auth_users, and optionally clearing
    backend chat session JSON files.
    """
    db_path = Path(db_path).resolve()
    chat_sessions_dir = Path(chat_sessions_dir).resolve()

    print("=" * 72)
    print(" AMC DATABASE & CHAT HISTORY CLEANUP SCRIPT")
    print("=" * 72)
    print(f"Target Database   : {db_path}")
    print(f"Chat Sessions Dir : {chat_sessions_dir}")
    print(f"Preserved User    : '{keep_user}' in 'auth_users' table")
    print(f"Clear Chat Logs   : {'YES (Will remove .json session files)' if clear_chat_logs else 'NO (Keep .json files)'}")
    print(f"Dry Run Mode      : {'ENABLED (No changes will be written)' if dry_run else 'DISABLED (Changes will be applied)'}")
    print("=" * 72)

    if not db_path.exists():
        print(f"\n[ERROR] Database file not found at: {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Step 1: Discover all tables
        tables = get_all_tables(conn)
        if not tables:
            print("\n[INFO] No user tables found in database. Nothing to clean.")
            return True

        # Step 2: Get initial counts
        initial_counts = get_table_counts(conn, tables)

        # Step 3: Check auth_users table and target user
        user_row = None
        if "auth_users" in tables:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM auth_users WHERE username = ?", (keep_user,))
            user_row = cursor.fetchone()
            if user_row:
                user_role = user_row["role"] if "role" in user_row.keys() else "N/A"
                user_email = user_row["email"] if "email" in user_row.keys() else "N/A"
                print(f"\n[OK] Found target user '{keep_user}' in auth_users:")
                print(f"     - Role  : {user_role}")
                print(f"     - Email : {user_email}")
            else:
                print(f"\n[WARNING] User '{keep_user}' was NOT found in 'auth_users'!")
                print(f"          If you proceed, 'auth_users' will be left with 0 rows.")
                if not force and not dry_run:
                    response = input("Proceed anyway? [y/N]: ").strip().lower()
                    if response not in ("y", "yes"):
                        print("[ABORTED] Operation cancelled by user.")
                        return False
        else:
            print(f"\n[WARNING] 'auth_users' table does not exist in {db_path.name}!")

        # Display initial row counts
        total_initial_rows = sum(initial_counts.values())
        print(f"\nFound {len(tables)} tables with {total_initial_rows} total records:")
        for tbl in tables:
            print(f"  - {tbl.ljust(35)}: {initial_counts[tbl]:>6} rows")

        # Discover disk-based chat session files
        chat_files = list(chat_sessions_dir.glob("*.json")) if chat_sessions_dir.exists() else []
        print(f"\nDisk chat sessions ({chat_sessions_dir.name}/): {len(chat_files)} files found")

        if dry_run:
            print("\n" + "-" * 72)
            print("[DRY RUN SUMMARY] The following actions WOULD be taken:")
            for tbl in tables:
                if tbl == "auth_users":
                    target_count = 1 if user_row else 0
                    to_remove = max(0, initial_counts[tbl] - target_count)
                    print(f"  - {tbl.ljust(35)}: remove {to_remove} rows (keep '{keep_user}')")
                else:
                    print(f"  - {tbl.ljust(35)}: remove all {initial_counts[tbl]} rows")
            if clear_chat_logs:
                print(f"  - Chat session logs: remove {len(chat_files)} .json file(s)")
            print("-" * 72)
            print("[DRY RUN COMPLETE] No records or files were deleted.")
            return True

        # Confirmation prompt if not forced
        if not force:
            print("\n" + "!" * 72)
            print(" WARNING: This will permanently delete records from data.db!")
            print(f" All records will be removed, preserving ONLY '{keep_user}' in auth_users.")
            if clear_chat_logs and chat_files:
                print(f" Also removes {len(chat_files)} chat session JSON file(s) from {chat_sessions_dir.name}/.")
            print(" No tables will be dropped or modified in schema.")
            print("!" * 72)
            try:
                confirmation = input("Are you sure you want to proceed? Type 'yes' to confirm: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n[ABORTED] Operation cancelled.")
                return False

            if confirmation != "yes":
                print("[ABORTED] Confirmation not received. No records were deleted.")
                return False

        # Step 4: Create backup if requested
        step_idx = 1
        total_steps = 4 if not clear_chat_logs else 5

        if backup:
            print(f"\n[Step {step_idx}/{total_steps}] Creating atomic backup...")
            backup_file = create_atomic_backup(conn, db_path)
            print(f"  [OK] Backup successfully created at: {backup_file.name}")
        else:
            print(f"\n[Step {step_idx}/{total_steps}] Skipping backup (--no-backup specified).")
        step_idx += 1

        # Step 5: Execute record removal inside transaction
        print(f"\n[Step {step_idx}/{total_steps}] Truncating records from tables...")
        step_idx += 1
        cursor = conn.cursor()

        # Temporarily disable foreign keys to avoid order dependency while deleting records
        cursor.execute("PRAGMA foreign_keys = OFF;")

        deleted_stats = {}
        for tbl in tables:
            if tbl == "auth_users":
                cursor.execute('DELETE FROM "auth_users" WHERE username != ?', (keep_user,))
                deleted_rows = cursor.rowcount
                deleted_stats[tbl] = deleted_rows
                print(f"  [OK] 'auth_users': deleted {deleted_rows} record(s), preserved '{keep_user}'")
            else:
                cursor.execute(f'DELETE FROM "{tbl}"')
                deleted_rows = cursor.rowcount
                deleted_stats[tbl] = deleted_rows
                print(f"  [OK] '{tbl}': deleted {deleted_rows} record(s)")

        # Reset SQLite autoincrement sequences for cleared tables if sqlite_sequence exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';"
        )
        if cursor.fetchone():
            for tbl in tables:
                if tbl != "auth_users":
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tbl,))

        # Commit all deletions
        conn.commit()

        # Re-enable foreign keys and verify integrity
        cursor.execute("PRAGMA foreign_keys = ON;")
        fk_check = cursor.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_check:
            print(f"  [WARNING] PRAGMA foreign_key_check reported violations: {fk_check}")
        else:
            print("  [OK] Foreign key check passed: 0 violations.")

        # Step 6: Delete disk-based chat session logs if enabled
        if clear_chat_logs:
            print(f"\n[Step {step_idx}/{total_steps}] Cleaning disk-based chat session logs...")
            step_idx += 1
            deleted_files = 0
            for cf in chat_files:
                try:
                    cf.unlink()
                    deleted_files += 1
                except Exception as ex:
                    print(f"  [WARNING] Could not delete {cf.name}: {ex}")
            print(f"  [OK] Deleted {deleted_files} chat session JSON file(s) from {chat_sessions_dir.name}/.")

        # Step 7: Vacuum database to reclaim unused disk space
        if not skip_vacuum:
            print(f"\n[Step {step_idx}/{total_steps}] Vacuuming database to reclaim disk space...")
            step_idx += 1
            conn.isolation_level = None  # Autocommit mode required for VACUUM in sqlite3
            cursor.execute("VACUUM;")
            conn.isolation_level = ""    # Reset default transaction behavior
            print("  [OK] VACUUM completed.")
        else:
            print(f"\n[Step {step_idx}/{total_steps}] Skipping VACUUM (--skip-vacuum specified).")
            step_idx += 1

        # Step 8: Verify final counts and table existence
        print(f"\n[Step {step_idx}/{total_steps}] Verifying database integrity and final row counts...")
        final_tables = get_all_tables(conn)
        final_counts = get_table_counts(conn, final_tables)

        # Check that no tables were dropped
        missing_tables = set(tables) - set(final_tables)
        if missing_tables:
            print(f"  [ERROR] The following tables are unexpectedly missing: {missing_tables}")
            return False
        print(f"  [OK] All {len(final_tables)} tables are intact (0 tables dropped).")

        # Print final verification table
        print("\n" + "=" * 72)
        print(f"{'Table Name':<35} | {'Initial':>8} | {'Final':>8} | {'Removed':>8}")
        print("-" * 72)
        total_removed = 0
        for tbl in final_tables:
            init_c = initial_counts.get(tbl, 0)
            fin_c = final_counts.get(tbl, 0)
            rem_c = init_c - fin_c
            total_removed += rem_c
            print(f"{tbl:<35} | {init_c:>8} | {fin_c:>8} | {rem_c:>8}")
        print("=" * 72)
        print(f"{'TOTAL':<35} | {total_initial_rows:>8} | {sum(final_counts.values()):>8} | {total_removed:>8}")
        print("=" * 72)

        # Confirm preserved user in auth_users
        if "auth_users" in final_tables:
            cursor = conn.cursor()
            cursor.execute("SELECT username, role, email FROM auth_users;")
            remaining_users = cursor.fetchall()
            print(f"\nRemaining user(s) in auth_users: {len(remaining_users)}")
            for u in remaining_users:
                print(f"  - username: {u['username']} | role: {u['role']} | email: {u['email']}")

        print("\n[SUCCESS] All records have been cleared from data.db while keeping all tables intact.")
        print(f"          Only user '{keep_user}' is retained in 'auth_users'.")
        if clear_chat_logs:
            print(f"          Disk-based chat logs in {chat_sessions_dir.name}/ have been cleared.")
        return True

    except Exception as e:
        print(f"\n[ERROR] An exception occurred during cleanup: {e}")
        try:
            conn.rollback()
            print("[INFO] Transaction rolled back.")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Remove all records from data.db without dropping any tables, "
            "preserving only user 'amc_admin' in auth_users, and clearing recent chat history."
        )
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to data.db file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--chat-sessions-dir",
        type=Path,
        default=DEFAULT_CHAT_SESSIONS_DIR,
        help=f"Path to chat sessions directory (default: {DEFAULT_CHAT_SESSIONS_DIR})",
    )
    parser.add_argument(
        "--keep-user",
        type=str,
        default=DEFAULT_KEEP_USER,
        help=f"Username to preserve in auth_users (default: '{DEFAULT_KEEP_USER}')",
    )
    parser.add_argument(
        "--keep-chat-logs",
        action="store_true",
        help="Do not delete disk-based chat session JSON files in logs/chat_sessions/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the cleanup and report what records/files would be deleted without modifying anything",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped backup of data.db before deleting records",
    )
    parser.add_argument(
        "--skip-vacuum",
        action="store_true",
        help="Skip the VACUUM operation after deletion",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bypass the interactive confirmation prompt",
    )

    args = parser.parse_args()

    success = clean_database(
        db_path=args.db_path,
        chat_sessions_dir=args.chat_sessions_dir,
        keep_user=args.keep_user,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        clear_chat_logs=not args.keep_chat_logs,
        skip_vacuum=args.skip_vacuum,
        force=args.yes,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
