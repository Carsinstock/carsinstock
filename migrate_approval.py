"""
Migration: Task 4 — Vehicle Approval Queue
Run from: /home/eddie/carsinstock
Command:  python3 migrate_approval.py
"""
import sqlite3

DB_PATH = 'instance/carsinstock.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("Adding approval_status to vehicles...")
try:
    cur.execute("ALTER TABLE vehicles ADD COLUMN approval_status VARCHAR(20) DEFAULT 'approved'")
    print("  ✅ approval_status added")
except sqlite3.OperationalError as e:
    print(f"  ⚠️  Skipped: {e}")

print("Adding rejection_reason to vehicles...")
try:
    cur.execute("ALTER TABLE vehicles ADD COLUMN rejection_reason TEXT")
    print("  ✅ rejection_reason added")
except sqlite3.OperationalError as e:
    print(f"  ⚠️  Skipped: {e}")

print("Creating team_notifications table...")
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_member_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            type VARCHAR(20) NOT NULL,
            message TEXT,
            is_dismissed INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✅ team_notifications created")
except sqlite3.OperationalError as e:
    print(f"  ⚠️  Skipped: {e}")

conn.commit()
conn.close()
print("\nMigration complete.")
