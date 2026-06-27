"""
Phase 2 test harness — shared fixtures.

SAFETY: Every fixture here runs against a DISPOSABLE temp SQLite database.
The production DB (instance/carsinstock.db) is NEVER opened by the test suite.
create_app() is called WITH a test_config override pointing at a throwaway file,
so production config is never touched.

Schema note: the app uses a SPLIT data layer —
  * SQLAlchemy ORM models  -> built by db.create_all()
      (salespeople, leads, attributions, vehicles, dealers, users)
  * Raw sqlite tables (NO ORM model) -> must be created by hand here
      (birddogs, birddog_referrals, dealership_team)
The birddog chain uses raw conn.execute() against those last three, so the
fixture creates them explicitly. Without this, Chain 1 tests would fail with
"no such table: birddogs".
"""
import os
import tempfile
import sqlite3
from datetime import datetime, timedelta

import pytest

# Compat shim: Flask 2.2.5's test client reads werkzeug.__version__, but the
# installed Werkzeug doesn't expose it. Set it if missing so test_client works.
# Touches only the test process, never the app or its dependencies.
import werkzeug as _wz
if not hasattr(_wz, '__version__'):
    try:
        from importlib.metadata import version as _v
        _wz.__version__ = _v('werkzeug')
    except Exception:
        _wz.__version__ = '0'

from app import create_app
from app.models import db


# --- Raw-sqlite tables that have no ORM model (copied from live .schema) -----
# These mirror production structure exactly so tests exercise the real columns.
RAW_TABLE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS dealership_team (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dealership_id INTEGER NOT NULL DEFAULT 1,
        name VARCHAR(200) NOT NULL,
        phone VARCHAR(50),
        email VARCHAR(200),
        profile_photo VARCHAR(500),
        slug VARCHAR(200),
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        password_hash VARCHAR(255),
        user_id INTEGER,
        bio TEXT,
        backdrop_preset VARCHAR(50)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS birddogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_member_id INTEGER NOT NULL,
        name VARCHAR(200) NOT NULL,
        email VARCHAR(200),
        phone VARCHAR(50),
        token VARCHAR(100) NOT NULL UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        dealership_id INTEGER DEFAULT 1,
        slug VARCHAR(100),
        opt_out BOOLEAN DEFAULT 0,
        is_active BOOLEAN DEFAULT 1,
        FOREIGN KEY (team_member_id) REFERENCES dealership_team(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS birddog_referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        birddog_id INTEGER NOT NULL,
        team_member_id INTEGER NOT NULL,
        buyer_name VARCHAR(200),
        buyer_phone VARCHAR(50),
        lead_id INTEGER,
        status VARCHAR(50) DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        closed_at DATETIME,
        dealership_id INTEGER DEFAULT 1,
        attribution_source VARCHAR(50),
        buyer_email VARCHAR(255),
        FOREIGN KEY (birddog_id) REFERENCES birddogs(id),
        FOREIGN KEY (team_member_id) REFERENCES dealership_team(id),
        FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
    );
    """,
]


def _create_raw_tables(db_path):
    """Create the model-less tables directly in the test sqlite file."""
    conn = sqlite3.connect(db_path)
    try:
        for stmt in RAW_TABLE_SQL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def app():
    """
    A fresh Flask app bound to a brand-new disposable SQLite file.
    Tears the file down after each test. Production DB is never referenced.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="cis_test_")
    os.close(fd)

    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + db_path,
        "WTF_CSRF_ENABLED": False,
    }

    application = create_app(test_config)

    with application.app_context():
        db.create_all()            # ORM tables
        _create_raw_tables(db_path)  # raw tables (birddogs, etc.)

    yield application

    # teardown
    with application.app_context():
        db.session.remove()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture()
def client(app):
    """Flask test client for route-level tests."""
    return app.test_client()


@pytest.fixture()
def db_path(app):
    """The raw sqlite path, for tests that use conn.execute() like the app does."""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    return uri.replace("sqlite:///", "")


@pytest.fixture()
def seed(app):
    """
    Seed a minimal, known dataset the chains can build on:
      * one dealer + user + salesperson (ORM)
      * one matching dealership_team row (raw) — the rep as the app sees it
      * one available vehicle owned by that rep (ORM)
      * one birddog under that rep (raw)
    Returns a dict of the key ids/slugs for assertions.
    """
    from app.models.user import User
    from app.models.dealer import Dealer
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle

    ids = {}
    with app.app_context():
        # --- ORM seed ---
        dealer = Dealer(dealer_name="Test Motors", city="Testville")
        db.session.add(dealer)
        db.session.flush()

        user = User(email="testrep@example.com", password_hash="x")
        db.session.add(user)
        db.session.flush()

        rep = Salesperson(
            user_id=user.id,
            dealer_id=dealer.dealer_id,
            display_name="Test Rep",
            email="testrep@example.com",
            profile_url_slug="testrep",
            dealership_name="Test Motors",
            status="active",
        )
        db.session.add(rep)
        db.session.flush()

        veh = Vehicle(
            salesperson_id=rep.salesperson_id,
            year=2023, make="Toyota", model="RAV4",
            vin="TESTVIN0000000001",
            mileage=10000, price=31995.0,
            status="available",
            expires_at=datetime.utcnow() + timedelta(days=7),
            approval_status="approved",
        )
        db.session.add(veh)
        db.session.commit()

        ids["dealer_id"] = dealer.dealer_id
        ids["user_id"] = user.id
        ids["salesperson_id"] = rep.salesperson_id
        ids["rep_slug"] = rep.profile_url_slug
        ids["vehicle_id"] = veh.id

    # --- raw seed (dealership_team + birddog), mirroring how the app writes ---
    path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            "INSERT INTO dealership_team (dealership_id, name, slug, is_active) "
            "VALUES (1, ?, ?, 1)",
            ("Test Rep", "testrep"),
        )
        team_member_id = cur.lastrowid

        conn.execute(
            "INSERT INTO birddogs (team_member_id, name, email, phone, token, "
            "dealership_id, slug, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, 1)",
            (team_member_id, "Test Birddog", "bird@example.com", "5550001111",
             "testtoken0001", "test-birddog"),
        )
        birddog_id = conn.execute(
            "SELECT id FROM birddogs WHERE token = ?", ("testtoken0001",)
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    ids["team_member_id"] = team_member_id
    ids["birddog_id"] = birddog_id
    ids["birddog_slug"] = "test-birddog"
    return ids
