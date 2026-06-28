#!/usr/bin/env python3
"""
CarsInStock daily monitoring digest.

Runs every morning (cron). Emails a system health heartbeat to the CarsInStock
ops addresses (NOT customer-facing). Once a week (Sundays) it also runs a live
Cloudinary smoke test to confirm the image pipeline is up.

Sends FROM noreply@carsinstock.com (CarsInStock system mail) TO the ops
addresses only -- single hardcoded recipient list, never a DB query, so it can
never become a customer-email path.

Independent of all blast crons. Has its own lockfile.
"""
import sys
import os
import fcntl
import sqlite3
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, "/home/eddie/carsinstock")
os.chdir("/home/eddie/carsinstock")
from dotenv import load_dotenv
load_dotenv("/home/eddie/carsinstock/.env")

DB_PATH = "/home/eddie/carsinstock/instance/carsinstock.db"
APACHE_ERR = "/var/log/apache2/carsinstock-error.log"
CLOUDINARY_SMOKE_URL = (
    "https://res.cloudinary.com/dbpa9qqtb/image/upload/"
    "v1772163049/demo/demo_cover_photo.jpg"
)
# CarsInStock OPS addresses only -- hardcoded, never a customer list.
OPS_RECIPIENTS = ["edward@carsinstock.com", "autoloanagent@gmail.com"]

LOCK_FILE = "/tmp/carsinstock_monitor_digest.lock"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def check_health(conn):
    """Return (lines, problems) -- problems is a count of red flags."""
    lines = []
    problems = 0

    # Active reps
    team = conn.execute(
        "SELECT id, name, email FROM dealership_team WHERE is_active=1"
    ).fetchall()
    lines.append(f"Active reps: {len(team)}")

    # Vehicles per rep + total available
    total_avail = conn.execute(
        "SELECT COUNT(*) c FROM vehicles WHERE status='available'"
    ).fetchone()["c"]
    lines.append(f"Available vehicles: {total_avail}")

    # Vehicles assigned to an inactive or nonexistent rep (data integrity).
    # Catches departed reps (is_active=0) and ghost assignments (pick_user_id
    # not in dealership_team at all, e.g. a deleted rep id).
    orphaned = conn.execute(
        "SELECT COUNT(*) c FROM vehicles v "
        "LEFT JOIN dealership_team dt ON v.pick_user_id = dt.id "
        "WHERE v.status='available' AND v.pick_user_id IS NOT NULL "
        "AND (dt.id IS NULL OR dt.is_active=0)"
    ).fetchone()["c"]
    if orphaned:
        problems += 1
        lines.append(f"WARN: {orphaned} available vehicles assigned to inactive/missing reps")

    # Vehicles expiring in 48h
    now = datetime.utcnow()
    expiring = conn.execute(
        "SELECT COUNT(*) c FROM vehicles WHERE status='available' "
        "AND expires_at <= ? AND expires_at > ?",
        (now + timedelta(hours=48), now),
    ).fetchone()["c"]
    lines.append(f"Vehicles expiring in 48h: {expiring}")

    # Leads
    leads_today = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE created_at >= ?",
        (now.strftime("%Y-%m-%d"),),
    ).fetchone()["c"]
    total_leads = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    lines.append(f"Leads today: {leads_today}  |  total: {total_leads}")

    # Customer list size (post-cleanup sanity)
    cust = conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    lines.append(f"Customers in DB: {cust}")

    # Blast safety state -- confirm the weekly blast is still locked off
    active_sched = conn.execute(
        "SELECT COUNT(*) c FROM blast_schedule WHERE is_active=1"
    ).fetchone()["c"]
    if active_sched:
        problems += 1
        lines.append(f"ALERT: {active_sched} ACTIVE blast schedule(s) -- "
                     f"weekly blast is supposed to be locked off until Phase 2.6!")
    else:
        lines.append("Blast safety: no active schedules (locked off) OK")

    return lines, problems


def check_flask():
    try:
        from app import create_app
        create_app()
        return "Flask app: loads clean OK", 0
    except Exception as e:
        return f"Flask app: FAILED to load -- {e}", 1


def check_apache_errors_recent():
    """Count error-level lines in the apache log from the last 24h (rough)."""
    if not os.path.exists(APACHE_ERR):
        return "Apache error log: not found", 0
    try:
        with open(APACHE_ERR, "r", errors="replace") as f:
            tail = f.readlines()[-500:]
        errs = [l for l in tail if "[error]" in l.lower() or "traceback" in l.lower()]
        if errs:
            return f"Apache errors in recent log tail: {len(errs)} (see watcher for detail)", 1
        return "Apache error log: clean in recent tail OK", 0
    except Exception as e:
        return f"Apache error log: could not read -- {e}", 0


def cloudinary_smoke():
    """Fetch a known Cloudinary image. Returns (line, problem_count)."""
    try:
        req = urllib.request.Request(CLOUDINARY_SMOKE_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.getcode()
            size = len(r.read())
        if code == 200 and size > 1000:
            return f"Cloudinary smoke: OK (HTTP {code}, {size} bytes)", 0
        return f"Cloudinary smoke: SUSPECT (HTTP {code}, {size} bytes)", 1
    except Exception as e:
        return f"Cloudinary smoke: FAILED -- {e}", 1


def build_digest():
    conn = get_conn()
    health_lines, health_problems = check_health(conn)
    conn.close()

    flask_line, flask_problems = check_flask()
    apache_line, apache_problems = check_apache_errors_recent()

    # Cloudinary smoke only on Sundays (weekday()==6) to conserve credits
    is_sunday = datetime.utcnow().weekday() == 6
    if is_sunday:
        cloud_line, cloud_problems = cloudinary_smoke()
    else:
        cloud_line, cloud_problems = "Cloudinary smoke: skipped (weekly, runs Sundays)", 0

    total_problems = (health_problems + flask_problems
                      + apache_problems + cloud_problems)

    status = "ALL CLEAR" if total_problems == 0 else f"{total_problems} ITEM(S) NEED ATTENTION"

    body_lines = health_lines + [flask_line, apache_line, cloud_line]
    text_block = "\n".join(f"  - {l}" for l in body_lines)

    subject = f"CarsInStock Daily Health: {status}"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#1E293B;padding:16px 20px;border-radius:8px 8px 0 0;">
    <span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span>
    <span style="color:#94A3B8;font-size:13px;margin-left:8px;">System Health Digest</span>
  </div>
  <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 8px 8px;padding:24px;">
    <h2 style="color:{'#00C851' if total_problems == 0 else '#dc2626'};margin:0 0 8px;">{status}</h2>
    <p style="color:#64748B;font-size:13px;margin:0 0 16px;">Run: {datetime.utcnow()} UTC</p>
    <pre style="font-family:monospace;font-size:13px;color:#1E293B;white-space:pre-wrap;background:#F8FAFC;padding:14px;border-radius:6px;border:1px solid #E2E8F0;">{text_block}</pre>
    <p style="color:#94A3B8;font-size:12px;margin-top:16px;">CarsInStock internal monitoring. This is system mail, not customer-facing.</p>
  </div>
</div>"""
    return subject, html, total_problems


def main():
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("[monitor_digest] already running -- skipping")
        sys.exit(0)

    subject, html, problems = build_digest()

    from app.utils.email import send_email
    sent = 0
    for addr in OPS_RECIPIENTS:
        if send_email(addr, subject, html):
            sent += 1
    print(f"[monitor_digest] {subject} -- emailed {sent}/{len(OPS_RECIPIENTS)} recipients")

    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()


if __name__ == "__main__":
    main()
