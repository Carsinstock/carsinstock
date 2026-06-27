# CarsInStock — Test Suite

Phase 2 safety net: automated tests for the four critical chains + a disposable
test database that never touches production.

## Running

```bash
cd /home/eddie/carsinstock
source venv/bin/activate
pytest -v
```

## Safety model

- Every test runs against a **fresh temporary SQLite file**, created and
  destroyed per test. The production DB (`instance/carsinstock.db`) is **never**
  opened by the suite.
- This works because `create_app()` accepts an optional `test_config` override
  (commit `bef30e6`). Tests pass a throwaway DB URI; production calls
  `create_app()` with no argument and are unaffected.

## Schema note (important)

The app has a **split data layer**:

- **ORM models** (built by `db.create_all()`): `salespeople`, `leads`,
  `attributions`, `vehicles`, `dealers`, `users`.
- **Raw sqlite tables** (no ORM model — created by hand in `conftest.py`):
  `birddogs`, `birddog_referrals`, `dealership_team`. The birddog chain uses
  raw `conn.execute()` against these, so the fixture creates them explicitly.

If you add a feature that touches a new model-less table, add its `CREATE TABLE`
to `RAW_TABLE_SQL` in `conftest.py` or its tests will fail with "no such table."

## Fixtures (`conftest.py`)

- `app` — Flask app on a disposable DB, full schema built, torn down after.
- `client` — Flask test client.
- `db_path` — raw sqlite path, for tests that use `conn.execute()` like the app.
- `seed` — minimal known dataset: one dealer/user/rep, one `dealership_team`
  row, one available vehicle, one birddog. Returns a dict of ids/slugs.

## Coverage map (filled in as chains land)

| File | Chain | Status |
|---|---|---|
| `test_smoke.py` | Harness self-check | ✅ Day 1 |
| `test_birddog_chain.py` | 1 — birddog signup | ⏳ Day 2-3 |
| `test_lead_routing.py` | 3 — lead routing | ⏳ Day 2-3 |
| `test_backdrop.py` | 2 — backdrop transform | ⏳ Day 4 |
| `test_blast_cron.py` | 4 — blast cron guardrails (incl. 500 cap) | ⏳ Day 4 |

## Discipline

If a test surfaces a **real production bug**, it is PAUSED and FLAGGED to the
CEO — not fixed inside the test work. A test catching a real bug is the test
working; the fix is a separate, approved change.
