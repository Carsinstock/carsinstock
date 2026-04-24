#!/usr/bin/env python3
"""
migrate_toolbox_tables.py
Idempotent — safe to run multiple times.
Creates offer_codes and geocode_cache tables if they do not exist.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'carsinstock.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Table 1: offer_codes
    cur.execute('''
        CREATE TABLE IF NOT EXISTS offer_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_code TEXT UNIQUE NOT NULL,
            offer_type TEXT NOT NULL,
            team_member_id INTEGER NOT NULL,
            dealership_id INTEGER NOT NULL,
            recipient_name TEXT,
            recipient_address TEXT NOT NULL,
            source_customer_id INTEGER,
            amount INTEGER DEFAULT 500,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            redeemed BOOLEAN DEFAULT 0,
            redeemed_at DATETIME,
            redeemed_vehicle_id INTEGER,
            redeemed_sale_amount INTEGER,
            notes TEXT,
            FOREIGN KEY (team_member_id) REFERENCES dealership_team(id),
            FOREIGN KEY (dealership_id) REFERENCES dealerships(id)
        )
    ''')
    print("✅ offer_codes table: ready")

    # Table 2: geocode_cache
    cur.execute('''
        CREATE TABLE IF NOT EXISTS geocode_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_address TEXT UNIQUE NOT NULL,
            latitude REAL,
            longitude REAL,
            formatted_address TEXT,
            neighbor_addresses_json TEXT,
            cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ geocode_cache table: ready")

    conn.commit()
    conn.close()
    print("\n✅ Migration complete. Both tables verified.")

if __name__ == '__main__':
    migrate()
