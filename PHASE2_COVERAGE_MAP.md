# Phase 2 Coverage Map & Engineer 16 Handoff

**Status:** Phase 2 COMPLETE. This document records what is tested, what is
deferred, the real bugs/data issues found during testing (flagged, not fixed --
per the all-or-none rule), and the locked next steps.

**Last commit at handoff:** `d6cb2b7` (error-log watcher). Monitoring live.

---

## 1. What Phase 2 delivered

| Item | Status | Commit |
|------|--------|--------|
| Testability refactor | done | `bef30e6` |
| Day-1 harness + 5 smoke tests | done | `dd690d9` |
| Chain 1 -- birddog signup (13 tests) | done | `214b0fc` |
| Chain 3 -- lead routing (7 tests) | done | `5fe8fc6` |
| Chain 2 -- backdrop segment (13 tests) | done | `d6f08d1` |
| Chain 4 -- blast filters (9 tests) | done | `22245d0` |
| NeverBounce customer-DB cleanup | done | `33c7d16` |
| Monitoring: daily health digest | done | `d8c5643` |
| Monitoring: error-log watcher | done | `d6cb2b7` |
| Coverage map (this doc) | done | (this commit) |

**Total: 47 tests green across 4 chains.** Run with `pytest -v` from repo root
(venv active).

---

## 2. Test coverage -- what IS tested

### Chain 1 -- `tests/test_birddog_chain.py` (13)
`create_birddog` + slug helpers. Idempotency on phone+rep verified. (Seed
fixture uses phone `5552223331/2` to avoid colliding with the `5550001111`
seed.)

### Chain 2 -- `tests/test_backdrop.py` (13)
Pure `backdrop_segment()`. Shadow mode includes `e_dropshadow`; reflect mode
(showroom only) omits it. 9 presets covered. Empty/invalid/None all return `''`.
URL-quoting verified.

### Chain 3 -- `tests/test_lead_routing.py` (7)
Lead model + routing. Lead inherits the vehicle's `salesperson_id`;
`referred_by` only set on a valid referrer; `salesperson_id` is NOT NULL.

### Chain 4 -- `tests/test_blast_filters.py` (9)
The REAL customer-blast filter in `app/cron.py` (`run_onboarding_blast` ~line
111, `run_weekly_blast` ~line 178). Originally written against
`cron_saturday.py` (a ~4-email rep reminder) -- **repointed** to the real
customer filter when that mismatch was caught. Tests document CURRENT behavior,
including two known gaps (see F-3).

---

## 3. Deferred / NOT tested (for future phases)

### F-1 / F-2 -- DB Access Refactor -> **Phase 2.5**
~90 hardcoded `sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')`
calls bypass SQLAlchemy across the app. `app/cron.py` uses `get_db()` but with a
hardcoded path. This pattern is why `attribute_lead_to_birddog()` could not be
cleanly unit-tested in isolation (deferred). Phase 2.5 should centralize DB
access so it's mockable and path-independent.

### F-3 -- Email Blast Guardrails -> **Phase 2.6**
Three documented gaps in the current blast filter (tests in Chain 4 capture
current behavior; the FIX is Phase 2.6):
1. **Whitespace-only email** (`"   "`) passes the filter -- `email != ""` misses
   it. Needs a `.strip()` chck.
2. **`cyberleads_quarantine` source is INCLUDED** -- there is no source filter.
   This is the exact gap behind the April SendGrid crisis. Phase 2.6 adds a
   source-based exclusion.
3. (Good behavior, keep) NULL unsubscribe -> EXCLUDED via SQLite NULL semantics,
   which protects the 161 NULL-unsubscribe rows.

**Phase 2.6 build scope (CEO-approved):** hard 500-cap + halt + CEO-alert,
dry-run mode, source-based filter (excludes `cyberleads_quarantine`), F-3
whitespace fix. Then write Chain 4 guardrail tests. Can run parallel to 2.5.
**Both 2.5 and 2.6 must complete before ANY prod blast cron is re-enabled.**

---

## 4. Real data issues found (flagged, NOT actioned)

### 4a. 12 available vehicles assigned to inactive/missing reps
Found by the new monitor. Breakdown:
- **Peter Franco (id=1):** departed rep, deactivated this session
  (`is_active=0`). 4 available vehicles still assigned to him (1 team-pick + 3
  not).
- **Phantom `pick_user_id=6`:** 8 available vehicles assigned to a team member
  id that **does not exist in `dealership_team` at all** (table has only ids 1,
  2, 8, 9). 3 of these are marked `is_team_pick=1`. Cars: 2024 Mustang, 2020
  ILX, 2023 Terrain, 2023 Sentra, 2017 Elantra (+3 more).

**Left untouched deliberately** -- crons are dark, nothing is blasting these, so
no risk. CEO to eyeball the actual cars (on-lot or not?) and decide
retire-vs-reassign with real eyes on inventory. The monitor now flags this count
daily until resolved.

**For Phase 2.5 investigation:** HOW did 8 vehicles get assigned to a
nonexistent rep id=6? That's a data-integrity bug that could recur -- worth
finding the write path that allowed it.

### 4b. Active `dealership_team` members (reference)
- id 2 -- Joe Viverito (joeviverito)
- id 8 -- Michael Limongello (michaellimongello)
- id 9 -- Ryan Lictro (ryanlictro)
- id 1 -- Peter Franco (peterfranco) -- **NOW is_active=0** (departed)

---

## 5. Monitoring (Day 5) -- how it works

Two scripts, both independent of blast crons, both with own lockfiles, both
emailing ONLY the hardcoded ops list (`edward@carsinstock.com`,
`autoloanagent@gmail.com`) from `noreply@carsinstock.com`. Never a DB query for
recipients, so neither can become a customer-email path.

### `monitor_digest.py` -- daily 7AM heartbeat
Cron: `0 7 * * *`. Checks active reps, available vehicles, vehicles assigned to
inactive/missing reps, 48h expiry, leads, customer count, Flask load, Apache
error-log tail. **Weekly (Sundays):** live Cloudinary smoke test (~1 credit/wk).
**Every run:** confirms the weekly blast stays locked off (alerts if any
`blast_schedule.is_active=1` ever appears). Always emails (heartbeat).

### `monitor_watch.py` -- error watcher every 15 min
Cron: `*/15 * * * *`. Scans the Apache error log for NEW critical lines since
last run (byte-offset state file `.monitor_watch_offset`). Emails ONLY on new
criticals; silent otherwise. Rate-limited to 40 lines/email. Alerts once per
error (offset advances), never spams. Markers: `[error]`, `traceback`,
`critical`, `500 internal`, `operationalerror`, `integrityerror`,
`modulenotfound`.

Both proven live this session: digest emailed 2/2 (SendGrid 202), Cloudinary
smoke OK (HTTP 200); watcher detected an injected synthetic error and the alert
landed in the inbox, then went silent on re-run.

**Housekeeping TODO (Phase 2.5):** add a logrotate entry for
`/home/eddie/carsinstock/monitor.log` -- the watcher writes ~96 "clean" lines/day,
so it grows unbounded over months.

---

## 6. Blast safety state (DOUBLE-LOCKED)

The weekly customer blast cannot fire by accident. Two independent locks:
1. **Primary (data):** `blast_schedule` has 1 row (salesperson_id=1) with
   `is_active=0`. `run_weekly_blast` only sends if active schedules exist.
2. **Secondary (cron):** the `cron_weekly` crontab line is commented out with a
   dated Phase 2.6 reason.

**Re-enable order (ONLY after Phase 2.6 guardrails ship):** ship 2.6 -> set
`is_active=1` -> uncomment the cron line. Never before, never out of order.

Active crons remaining (all safe, non-blast): `cron_expiration_warning` (8AM),
`cron_saturday` (1PM Sat), `cron_google_reviews` (6AM), plus the two monitoring
crons. `cron_onboarding.py` dormant.

---

## 7. Locked roadmap (CEO-confirmed)

1. **Phase 2** -- COMPLETE (this handoff).
2. **Phase 2.5** -- DB Access Refactor (F-1/F-2, ~90-call pattern). Also:
   investigate the id=6 ghost write-path; add monitor.log logrotate.
3. **Phase 2.6** -- Email Blast Guardrails (F-3 + 500-cap/dry-run/source-filter),
   then Chain 4 guardrail tests. Parallel to 2.5.
4. **Phase 3a** -- Master Dashboard -> **3b** Stripe -> **3c** Training videos.
5. **Phase 4** -- Sales mode.

**Discipline rules in force:** CEO approves scope before test code; real bugs
found while testing are FLAGGED not fixed mid-phase (all-or-none); flag when
scope doesn't match reality.

---

## 8. Operational reminders for Engineer 16

- Always `cd /home/eddie/carsinstock && source venv/bin/activate` before work.
  Use `python3`, not `python`.
- No Apache restarts before 9PM (live reps). `sudo systemctl reload apache2` is
  graceful anytime if needed.
- Schema-check before any DB write script. Prod DB: `instance/carsinstock.db`.
- Env vars: `export $(grep -v '^#' .env | xargs)`.
- **Console paste lesson:** long base64 blobs corrupt in the DigitalOcean web
  console (heredoc terminators get eaten). Working method: split base64 into
  ~2KB chunks, `printf '%s' '<chunk>' >> /tmp/file.b64` (first `>`, rest `>>`),
  md5 the assembled base64 TEXT before decoding. All transferred files must be
  pure ASCII (em-dashes corrupt; use `--`).
- PII: `exports/` and `*.csv` are gitignored; customer data never enters the
  repo.
