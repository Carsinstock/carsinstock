#!/usr/bin/env python3
"""
CarsInStock error-log watcher.

Runs every 15 minutes (cron). Scans the Apache error log for NEW critical
errors since the last run (tracked via a byte-offset state file so it never
re-alerts on the same error or floods on a burst). Emails the CarsInStock ops
addresses ONLY if new critical errors are found -- silent otherwise.

Sends FROM noreply@carsinstock.com TO the ops addresses only (hardcoded list,
never a DB query). Independent of all blast crons. Own lockfile.

Rate-limit: caps the number of error lines per email so one bad deploy can't
send a giant message; reports the overflow count instead.
"""
import sys
import os
import fcntl

sys.path.insert(0, "/home/eddie/carsinstock")
os.chdir("/home/eddie/carsinstock")
from dotenv import load_dotenv
load_dotenv("/home/eddie/carsinstock/.env")

from datetime import datetime

APACHE_ERR = "/var/log/apache2/carsinstock-error.log"
STATE_FILE = "/home/eddie/carsinstock/.monitor_watch_offset"
LOCK_FILE = "/tmp/carsinstock_monitor_watch.lock"
OPS_RECIPIENTS = ["edward@carsinstock.com", "autoloanagent@gmail.com"]
MAX_LINES_PER_EMAIL = 40

# What counts as "critical" -- substrings (lowercased) we alert on.
CRITICAL_MARKERS = ["[error]", "traceback", "critical", "500 internal",
                    "operationalerror", "integrityerror", "modulenotfound"]


def read_offset():
    try:
        with open(STATE_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_offset(n):
    with open(STATE_FILE, "w") as f:
        f.write(str(n))


def scan_new_errors():
    """Return (critical_lines, new_offset, overflowed_count)."""
    if not os.path.exists(APACHE_ERR):
        return [], read_offset(), 0

    size = os.path.getsize(APACHE_ERR)
    last = read_offset()

    # Log rotated/truncated (file smaller than our offset) -> reset to start
    if size < last:
        last = 0

    new_lines = []
    with open(APACHE_ERR, "r", errors="replace") as f:
        f.seek(last)
        chunk = f.read()
        new_offset = f.tell()

    for line in chunk.splitlines():
        low = line.lower()
        if any(m in low for m in CRITICAL_MARKERS):
            new_lines.append(line)

    overflow = 0
    if len(new_lines) > MAX_LINES_PER_EMAIL:
        overflow = len(new_lines) - MAX_LINES_PER_EMAIL
        new_lines = new_lines[:MAX_LINES_PER_EMAIL]

    return new_lines, new_offset, overflow


def main():
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("[monitor_watch] already running -- skipping")
        sys.exit(0)

    critical, new_offset, overflow = scan_new_errors()

    # Always advance the offset so we don't re-scan the same bytes
    write_offset(new_offset)

    if not critical:
        print(f"[monitor_watch] clean -- no new critical errors (offset {new_offset})")
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
        return

    count = len(critical)
    overflow_note = (f"\n\n...plus {overflow} more (truncated to protect inbox)."
                     if overflow else "")
    block = "\n".join(critical) + overflow_note

    subject = f"CarsInStock ALERT: {count} new critical error(s)"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#7f1d1d;padding:16px 20px;border-radius:8px 8px 0 0;">
    <span style="color:white;font-weight:700;">CarsInStock ALERT</span>
  </div>
  <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 8px 8px;padding:24px;">
    <h2 style="color:#dc2626;margin:0 0 8px;">{count} new critical error(s) detected</h2>
    <p style="color:#64748B;font-size:13px;margin:0 0 16px;">Detected: {datetime.utcnow()} UTC</p>
    <pre style="font-family:monospace;font-size:12px;color:#1E293B;white-space:pre-wrap;background:#FEF2F2;padding:14px;border-radius:6px;border:1px solid #FECACA;">{block}</pre>
    <p style="color:#94A3B8;font-size:12px;margin-top:16px;">From the Apache error log. CarsInStock internal monitoring.</p>
  </div>
</div>"""

    from app.utils.email import send_email
    sent = 0
    for addr in OPS_RECIPIENTS:
        if send_email(addr, subject, html):
            sent += 1
    print(f"[monitor_watch] ALERT sent ({count} errors) to {sent}/{len(OPS_RECIPIENTS)}")

    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()


if __name__ == "__main__":
    main()
