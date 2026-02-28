#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "/home/eddie/carsinstock/instance/carsinstock.db"

DEMO_VEHICLES_DAYS = {
    "honda accord": 7,
    "toyota rav4": 6,
    "ford f-150": 7,
    "chevrolet equinox": 5,
    "hyundai tucson": 4,
    "bmw 330i": 7,
    "jeep grand cherokee": 6,
    "nissan altima": 5,
    "mazda cx-5": 7,
    "kia telluride": 4,
}

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT salesperson_id, display_name FROM salespeople WHERE profile_url_slug = 'jsmith'")
    sp = cur.fetchone()
    if not sp:
        print("Demo salesperson jsmith not found!")
        conn.close()
        return

    print(f"Found: {sp['display_name']} (ID {sp['salesperson_id']})")

    cur.execute("SELECT id, year, make, model, expires_at FROM vehicles WHERE salesperson_id = ? ORDER BY id", (sp['salesperson_id'],))
    vehicles = cur.fetchall()
    print(f"Found {len(vehicles)} demo vehicles\n")

    now = datetime.utcnow()
    updated = 0

    for v in vehicles:
        vehicle_str = f"{v['make']} {v['model']}".lower()
        days = 7
        for key, d in DEMO_VEHICLES_DAYS.items():
            if key in vehicle_str:
                days = d
                break

        new_expiry = (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE vehicles SET expires_at = ? WHERE id = ?", (new_expiry, v['id']))
        print(f"  {v['year']} {v['make']} {v['model']}: {days} days -> {new_expiry}")
        updated += 1

    conn.commit()
    conn.close()
    print(f"\nUpdated {updated} vehicles.")
    print("Check: https://carsinstock.com/demo")

if __name__ == "__main__":
    main()

