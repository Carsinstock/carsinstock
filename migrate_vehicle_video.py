import sqlite3
DB = 'instance/carsinstock.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Check if column exists
cols = [r[1] for r in cur.execute("PRAGMA table_info(vehicles)").fetchall()]
if 'video_url' not in cols:
    cur.execute("ALTER TABLE vehicles ADD COLUMN video_url VARCHAR(500)")
    print("✅ Added video_url column to vehicles")
else:
    print("✅ video_url already exists")

conn.commit()
conn.close()
print("Done.")
