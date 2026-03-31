import sqlite3
DB = 'instance/carsinstock.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("Creating referrals table if not exists...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        salesperson_id INTEGER,
        referrer_name VARCHAR(200),
        referrer_phone VARCHAR(50),
        referrer_email VARCHAR(200),
        friend_name VARCHAR(200),
        friend_phone VARCHAR(50),
        message TEXT,
        paid INTEGER DEFAULT 0,
        submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
print("  OK referrals table ready")

conn.commit()
conn.close()
print("Done.")
