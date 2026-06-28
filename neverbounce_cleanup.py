#!/usr/bin/env python3
"""
One-time NeverBounce cleanup for the customers table.

Deletes CyberLeads-sourced records that NeverBounce flagged as not-valid, plus
any unsubscribed (or NULL-unsubscribe) CyberLeads records. Keeps only the clean,
subscribed, valid ones.

LOCKED RULE (CEO-confirmed 2026-06-28):
  KEEP a row only if  email_status == 'valid'  AND  unsubscribed == 0.
  DELETE everything else (invalid/unknown/accept_all_unverifiable/disposable,
  plus unsubscribed==1 OR unsubscribed IS NULL).

SCOPE GUARD (belt-and-suspenders): a row is only ever eligible for deletion if
  (a) its source == 'cyberleads_quarantine'  AND
  (b) its id appears in the NeverBounce verdict CSV.
So web_signup / Pine Belt / recruitment / birddog records can never be touched,
even if an unexpected id appeared in the verdict file.

USAGE:
  Dry run (default, NO changes):   python3 neverbounce_cleanup.py
  Real delete (after CEO go):      python3 neverbounce_cleanup.py --execute

The script ALWAYS writes a full backup of the customers table before any delete.
"""
import csv
import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = "/home/eddie/carsinstock/instance/carsinstock.db"
VERDICT_CSV = "/home/eddie/carsinstock/exports/cyberleads_for_neverbounce_20260627_110606.all.csv"
EXPORT_DIR = "/home/eddie/carsinstock/exports"
SOURCE_TAG = "cyberleads_quarantine"

EXECUTE = "--execute" in sys.argv


def load_verdicts(path):
    """Return {id: email_status} from the NeverBounce CSV, parsed with the csv
    module so quoted commas in names/emails are handled correctly."""
    verdicts = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"id", "email_status", "unsubscribed"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"FATAL: verdict CSV missing columns: {missing}. "
                     f"Found: {reader.fieldnames}")
        for row in reader:
            try:
                rid = int(row["id"])
            except (ValueError, TypeError):
                continue
            verdicts[rid] = (row["email_status"] or "").strip().lower()
    return verdicts


def backup_customers(conn):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPORT_DIR, f"customers_backup_pre_neverbounce_{ts}.csv")
    cur = conn.execute("SELECT * FROM customers ORDER BY id")
    cols = [d[0] for d in cur.description]
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in cur:
            w.writerow(r)
            n += 1
    return path, n


def main():
    if not os.path.exists(VERDICT_CSV):
        sys.exit(f"FATAL: verdict CSV not found at {VERDICT_CSV}")
    if not os.path.exists(DB_PATH):
        sys.exit(f"FATAL: DB not found at {DB_PATH}")

    verdicts = load_verdicts(VERDICT_CSV)
    print(f"Loaded {len(verdicts)} verdicts from NeverBounce CSV")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Pre-state snapshot
    total_before = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    cyber_before = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE source=?", (SOURCE_TAG,)
    ).fetchone()[0]
    other_before = total_before - cyber_before
    print(f"\nCustomers table BEFORE: {total_before} total "
          f"({cyber_before} {SOURCE_TAG}, {other_before} other/keep-always)")

    # Decide keep/delete for every cyberleads row, using the locked rule + scope guard
    rows = conn.execute(
        "SELECT id, email, unsubscribed, source FROM customers WHERE source=?",
        (SOURCE_TAG,),
    ).fetchall()

    to_delete = []
    keep = []
    not_in_verdict = []
    for r in rows:
        rid = r["id"]
        unsub = r["unsubscribed"]   # 0, 1, or None
        status = verdicts.get(rid)
        if status is None:
            # id not in verdict file -> scope guard: do NOT touch it
            not_in_verdict.append(rid)
            keep.append(rid)
            continue
        is_valid = (status == "valid")
        is_subscribed = (unsub == 0)
        if is_valid and is_subscribed:
            keep.append(rid)
        else:
            to_delete.append(rid)

    # Reporting breakdown
    del_invalid_status = sum(
        1 for r in rows
        if verdicts.get(r["id"]) not in (None, "valid")
    )
    del_unsub = sum(
        1 for r in rows
        if verdicts.get(r["id"]) is not None
        and (r["unsubscribed"] == 1 or r["unsubscribed"] is None)
        and r["id"] in to_delete
    )

    print("\n=== CLEANUP PLAN (cyberleads_quarantine only) ===")
    print(f"  KEEP   : {len(keep)}  (valid AND subscribed; "
          f"includes {len(not_in_verdict)} not-in-verdict, untouched by scope guard)")
    print(f"  DELETE : {len(to_delete)}")
    print(f"  (of deletes: {del_invalid_status} non-valid status; "
          f"the rest unsubscribed/NULL)")
    print(f"  other/keep-always rows NEVER considered: {other_before}")

    if not EXECUTE:
        print("\n*** DRY RUN -- no changes made. ***")
        print("Review the counts above. To execute the delete, re-run with --execute")
        conn.close()
        return

    # ---- EXECUTE path ----
    print("\n--execute flag set. Backing up customers table first...")
    backup_path, backup_n = backup_customers(conn)
    print(f"  Backup written: {backup_path} ({backup_n} rows)")
    if backup_n != total_before:
        conn.close()
        sys.exit(f"FATAL: backup row count {backup_n} != table count {total_before}. "
                 f"Aborting before delete.")

    # Delete in one transaction, scoped hard to source + id list
    print(f"\nDeleting {len(to_delete)} rows...")
    cur = conn.cursor()
    deleted = 0
    CHUNK = 500
    for i in range(0, len(to_delete), CHUNK):
        chunk = to_delete[i:i + CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        # source guard repeated in the WHERE clause as final safety
        cur.execute(
            f"DELETE FROM customers WHERE source=? AND id IN ({placeholders})",
            (SOURCE_TAG, *chunk),
        )
        deleted += cur.rowcount
    conn.commit()

    # Post-state verification
    total_after = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    cyber_after = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE source=?", (SOURCE_TAG,)
    ).fetchone()[0]
    other_after = total_after - cyber_after

    print("\n=== POST-DELETE VERIFICATION ===")
    print(f"  Rows deleted (reported by SQLite): {deleted}")
    print(f"  Customers BEFORE: {total_before}  AFTER: {total_after}")
    print(f"  cyberleads BEFORE: {cyber_before}  AFTER: {cyber_after}")
    print(f"  other/keep-always BEFORE: {other_before}  AFTER: {other_after}  "
          f"({'UNCHANGED - good' if other_before == other_after else 'CHANGED - INVESTIGATE'})")
    print(f"  Backup path: {backup_path}")

    print("\n=== 10-row sample of KEPT cyberleads records (spot check) ===")
    sample = conn.execute(
        "SELECT id, email, first_name, last_name, unsubscribed, source "
        "FROM customers WHERE source=? ORDER BY id LIMIT 10", (SOURCE_TAG,)
    ).fetchall()
    for s in sample:
        print(f"  {s['id']:>6} | {s['email']:<35} | "
              f"{s['first_name']} {s['last_name']} | unsub={s['unsubscribed']}")

    print("\n=== confirm KEEP-ALWAYS records untouched ===")
    ws = conn.execute(
        "SELECT id, email, source FROM customers WHERE source!=? ORDER BY id", (SOURCE_TAG,)
    ).fetchall()
    for w in ws:
        print(f"  {w['id']:>6} | {w['email']:<35} | source={w['source']}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
