#!/usr/bin/env python3
"""
MyCarReferral v1 — Day 1 schema migration.
Additive only. No renames, no drops. Idempotent (safe to re-run).
"""
import sqlite3
import sys
import re

DB_PATH = '/home/eddie/carsinstock/instance/carsinstock.db'
PINE_BELT_DEALERSHIP_ID = 1
PINE_BELT_BRAND_PREFIX = 'pbu'


def column_exists(conn, table, column):
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def generate_slug(name, existing):
    """First name + last initial, lowercase, alphanumeric only. Collision -> numeric suffix."""
    if not name or not name.strip():
        base = 'birddog'
    else:
        parts = name.lower().strip().split()
        base = (parts[0] + parts[-1][0]) if len(parts) >= 2 else parts[0]
        base = re.sub(r'[^a-z0-9]', '', base) or 'birddog'
    slug = base
    n = 2
    while slug in existing:
        slug = f"{base}{n}"
        n += 1
    return slug


def main():
    print("MyCarReferral v1 — Day 1 Schema Migration")
    print("=" * 50)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Stage 1: column additions
        print("\n[Stage 1] Column additions")
        additions = [
            ('birddogs', 'dealership_id', 'INTEGER DEFAULT 1'),
            ('birddogs', 'slug', 'VARCHAR(100)'),
            ('birddogs', 'opt_out', 'BOOLEAN DEFAULT 0'),
            ('birddog_referrals', 'dealership_id', 'INTEGER DEFAULT 1'),
            ('birddog_referrals', 'attribution_source', 'VARCHAR(50)'),
            ('birddog_referrals', 'buyer_email', 'VARCHAR(255)'),
        ]
        for table, col, definition in additions:
            if column_exists(conn, table, col):
                print(f"  skip  {table}.{col} (already exists)")
            else:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                print(f"  ok    {table}.{col} added")

        conn.execute("UPDATE birddogs SET dealership_id=1 WHERE dealership_id IS NULL")
        conn.execute("UPDATE birddogs SET opt_out=0 WHERE opt_out IS NULL")
        conn.execute("UPDATE birddog_referrals SET dealership_id=1 WHERE dealership_id IS NULL")
        print("  ok    backfilled NULLs in dealership_id and opt_out")

        # Stage 2: slug population
        print("\n[Stage 2] Slug population for existing birddogs")
        birddogs = conn.execute("SELECT id, name, slug FROM birddogs ORDER BY id").fetchall()
        existing_slugs = {b['slug'] for b in birddogs if b['slug']}
        added = 0
        for b in birddogs:
            if b['slug']:
                print(f"  skip  #{b['id']} {b['name']!r} already has slug {b['slug']!r}")
                continue
            new_slug = generate_slug(b['name'], existing_slugs)
            existing_slugs.add(new_slug)
            conn.execute("UPDATE birddogs SET slug=? WHERE id=?", (new_slug, b['id']))
            print(f"  ok    #{b['id']} {b['name']!r} -> slug {new_slug!r}")
            added += 1
        print(f"  Slugs added to {added} birddogs")

        # Stage 3: new tables
        print("\n[Stage 3] New tables")
        if table_exists(conn, 'referral_programs'):
            print("  skip  referral_programs (already exists)")
        else:
            conn.execute("""
                CREATE TABLE referral_programs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dealership_id INTEGER NOT NULL,
                    brand_prefix VARCHAR(10) UNIQUE NOT NULL,
                    program_name VARCHAR(200),
                    referrer_reward_amount DECIMAL(10,2),
                    referee_offer TEXT,
                    attribution_window_days INTEGER DEFAULT 90,
                    click_behavior VARCHAR(20) DEFAULT 'form_first',
                    active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dealership_id) REFERENCES dealerships(id)
                )
            """)
            print("  ok    referral_programs created")

        if table_exists(conn, 'referral_payouts'):
            print("  skip  referral_payouts (already exists)")
        else:
            conn.execute("""
                CREATE TABLE referral_payouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_id INTEGER NOT NULL,
                    referrer_id INTEGER NOT NULL,
                    amount DECIMAL(10,2),
                    method VARCHAR(20),
                    marked_sent_at DATETIME,
                    marked_sent_by_user_id INTEGER,
                    dealer_notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referral_id) REFERENCES birddog_referrals(id),
                    FOREIGN KEY (referrer_id) REFERENCES birddogs(id),
                    FOREIGN KEY (marked_sent_by_user_id) REFERENCES users(id)
                )
            """)
            print("  ok    referral_payouts created")

        # Stage 4: seed Pine Belt program
        print("\n[Stage 4] Seed Pine Belt program")
        existing = conn.execute(
            "SELECT id, brand_prefix FROM referral_programs WHERE dealership_id=?",
            (PINE_BELT_DEALERSHIP_ID,)
        ).fetchone()
        if existing:
            print(f"  skip  Pine Belt program already exists (id={existing['id']}, prefix={existing['brand_prefix']!r})")
        else:
            conn.execute("""
                INSERT INTO referral_programs
                (dealership_id, brand_prefix, program_name, attribution_window_days, click_behavior, active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (PINE_BELT_DEALERSHIP_ID, PINE_BELT_BRAND_PREFIX,
                  'Pine Belt Used Cars Thank-You Gift Program', 90, 'form_first', 1))
            print(f"  ok    Pine Belt program created (brand_prefix={PINE_BELT_BRAND_PREFIX!r})")

        conn.commit()
        print("\n[Transaction committed]")

        # Stage 5: verification
        print("\n[Stage 5] Verification")
        print("  Pine Belt birddogs post-migration:")
        for b in conn.execute("SELECT id, name, slug, dealership_id, opt_out FROM birddogs ORDER BY id"):
            print(f"    #{b['id']:3d}  name={b['name']!r:30s}  slug={b['slug']!r:15s}  dealership_id={b['dealership_id']}  opt_out={b['opt_out']}")

        cnt = conn.execute("SELECT COUNT(*) AS n FROM birddog_referrals").fetchone()['n']
        nulls = conn.execute("SELECT COUNT(*) AS n FROM birddog_referrals WHERE dealership_id IS NULL").fetchone()['n']
        print(f"\n  birddog_referrals: {cnt} total rows, {nulls} with NULL dealership_id (expected 0)")

        print("\n  referral_programs:")
        for p in conn.execute("SELECT * FROM referral_programs"):
            for k in p.keys():
                print(f"    {k}: {p[k]}")

        po_cnt = conn.execute("SELECT COUNT(*) AS n FROM referral_payouts").fetchone()['n']
        print(f"\n  referral_payouts: {po_cnt} rows (expected 0)")

        print("\n=== Migration complete ===")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        print("[ROLLBACK] No changes committed.")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
