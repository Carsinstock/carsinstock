"""
Day 1 smoke tests — these prove the harness itself works:
  * the app builds against a disposable test DB
  * ORM tables exist (db.create_all ran)
  * raw tables exist (birddogs/birddog_referrals/dealership_team created)
  * the seed fixture produces a consistent dataset
  * production DB is NOT the one under test

No chain logic is tested here yet — that arrives Day 2+. This file exists so
`pytest -v` runs green with the harness in place (Day 1 ping criterion).
"""
import sqlite3


def test_app_uses_disposable_db_not_production(app):
    """The app under test must point at a temp file, never instance/carsinstock.db."""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "cis_test_" in uri
    assert "instance/carsinstock.db" not in uri
    assert app.config["TESTING"] is True


def test_orm_tables_exist(db_path):
    """db.create_all() should have built the core ORM tables."""
    conn = sqlite3.connect(db_path)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    for t in ("salespeople", "leads", "attributions", "vehicles", "dealers", "users"):
        assert t in names, f"missing ORM table: {t}"


def test_raw_tables_exist(db_path):
    """The model-less tables the birddog chain needs must be created by the fixture."""
    conn = sqlite3.connect(db_path)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    for t in ("birddogs", "birddog_referrals", "dealership_team"):
        assert t in names, f"missing raw table: {t}"


def test_seed_produces_consistent_dataset(seed, db_path):
    """The seed fixture should create one rep, one vehicle, one birddog, all linked."""
    assert seed["salesperson_id"] > 0
    assert seed["vehicle_id"] > 0
    assert seed["birddog_id"] > 0
    assert seed["rep_slug"] == "testrep"

    conn = sqlite3.connect(db_path)
    try:
        bd = conn.execute(
            "SELECT name, team_member_id FROM birddogs WHERE id = ?",
            (seed["birddog_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert bd is not None
    assert bd[0] == "Test Birddog"
    assert bd[1] == seed["team_member_id"]


def test_client_can_hit_a_route(client):
    """The test client should be able to make a request (proves app wiring works)."""
    resp = client.get("/")
    # Homepage may 200, or redirect — we only assert the app responds, not a code.
    assert resp.status_code in (200, 301, 302, 308)
