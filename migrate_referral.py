import sqlite3

DB = 'instance/carsinstock.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("Adding referred_by to leads...")
try:
    cur.execute("ALTER TABLE leads ADD COLUMN referred_by VARCHAR(100)")
    print("  OK referred_by added")
except sqlite3.OperationalError as e:
    print(f"  Skipped: {e}")

conn.commit()
conn.close()
print("Migration complete.")
