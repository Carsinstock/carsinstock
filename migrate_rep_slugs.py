"""
Migration: Set slugs for dealership_team members + add bio column
"""
import sqlite3

DB = 'instance/carsinstock.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Add bio column to dealership_team if missing
print("Adding bio to dealership_team...")
try:
    cur.execute("ALTER TABLE dealership_team ADD COLUMN bio TEXT")
    print("  OK bio added")
except sqlite3.OperationalError as e:
    print(f"  Skipped: {e}")

# Set slugs for Pine Belt reps
slugs = {
    1: 'peterfranco',
    2: 'joeviverito',
    3: 'robertcamp',
    4: 'mattkilmurray',
}
print("Setting slugs...")
for member_id, slug in slugs.items():
    cur.execute("UPDATE dealership_team SET slug=? WHERE id=?", (slug, member_id))
    print(f"  OK id={member_id} -> {slug}")

conn.commit()
conn.close()
print("Migration complete.")
