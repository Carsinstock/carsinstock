import sqlite3
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/home/eddie/carsinstock')

print("=" * 50)
print("CARSINSTOCK SYSTEM HEALTH CHECK")
print(f"Run time: {datetime.utcnow()}")
print("=" * 50)

conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
conn.row_factory = sqlite3.Row

team = conn.execute("SELECT id, name, slug, email FROM dealership_team WHERE is_active=1").fetchall()
print(f"\n✅ ACTIVE REPS: {len(team)}")
for t in team:
    print(f"   - {t['name']} | {t['email']}")

print(f"\n✅ ACTIVE VEHICLES:")
for t in team:
    v = conn.execute("SELECT COUNT(*) as c FROM vehicles WHERE pick_user_id=? AND status='available'", (t['id'],)).fetchone()
    print(f"   - {t['name']}: {v['c']} vehicles")

not_picked = conn.execute("SELECT COUNT(*) as c FROM vehicles WHERE status='available' AND is_team_pick=0 AND pick_user_id IS NOT NULL").fetchone()
print(f"\n{'✅' if not_picked['c'] == 0 else '❌'} VEHICLES MISSING is_team_pick: {not_picked['c']}")

now = datetime.utcnow()
expiring = conn.execute("SELECT COUNT(*) as c FROM vehicles WHERE status='available' AND expires_at <= ? AND expires_at > ?", (now + timedelta(hours=48), now)).fetchone()
print(f"\n{'⚠️' if expiring['c'] > 0 else '✅'} VEHICLES EXPIRING IN 48 HOURS: {expiring['c']}")

leads_today = conn.execute("SELECT COUNT(*) as c FROM leads WHERE created_at >= ?", (now.strftime('%Y-%m-%d'),)).fetchone()
total_leads = conn.execute("SELECT COUNT(*) as c FROM leads").fetchone()
print(f"\n✅ LEADS TODAY: {leads_today['c']}")
print(f"✅ TOTAL LEADS: {total_leads['c']}")
conn.close()

from app import create_app
create_app()
print(f"\n✅ FLASK APP: Loads clean")
print("\n" + "=" * 50)
print("HEALTH CHECK COMPLETE")
print("=" * 50)
