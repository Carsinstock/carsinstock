#!/usr/bin/env python3
"""Daily onboarding blast — runs via crontab at 8AM EST. Lockfile prevents double-fire."""
import sys, os, fcntl
sys.path.insert(0, '/home/eddie/carsinstock')
os.chdir('/home/eddie/carsinstock')
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

LOCK_FILE = '/tmp/carsinstock_onboarding.lock'
lock = open(LOCK_FILE, 'w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print('[onboarding] Already running — skipping')
    sys.exit(0)

from app import create_app
from app.cron import run_onboarding_blast
app = create_app()
print(f'[onboarding] Starting blast')
run_onboarding_blast(app)
print(f'[onboarding] Done')
fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
