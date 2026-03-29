#!/usr/bin/env python3
"""Sunday weekly blast — runs via crontab at 9AM EST. Lockfile prevents double-fire."""
import sys, os, fcntl
sys.path.insert(0, '/home/eddie/carsinstock')
os.chdir('/home/eddie/carsinstock')
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

LOCK_FILE = '/tmp/carsinstock_weekly.lock'
lock = open(LOCK_FILE, 'w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print('[weekly] Already running — skipping')
    sys.exit(0)

from app import create_app
from app.cron import run_weekly_blast
app = create_app()
print(f'[weekly] Starting blast')
run_weekly_blast(app)
print(f'[weekly] Done')
fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
