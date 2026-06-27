"""
Chain 1 ? Birddog signup chain.

COVERAGE (Phase 2):
  [TESTED] create_birddog()        ? fully unit-tested here (takes a conn param, so we
                               pass the disposable-DB connection)
  [TESTED] _slugify()              ? pure helper, fully tested
  [TESTED] _unique_slug()          ? dedup-within-dealership, fully tested
  [DEFERRED] attribute_lead_to_birddog() ? NOT unit-tested. It hardcodes the production
                               DB path (sqlite3.connect('/home/eddie/.../carsinstock.db')),
                               so it cannot be pointed at the disposable test DB.
                               Status: covered by LIVE verification (Mike Cash ->
                               Joe Viverito attribution), unit test DEFERRED to
                               Phase 2.5 (Database Access Refactor). See finding F-1.

These tests verify the parts of the birddog signup chain that the referral and
salesperson blueprints both rely on: a birddog is created with a valid slug and
token, the operation is idempotent on phone+team_member_id, slugs are unique
within a dealership, and multi-tenant dealership_id is respected.
"""
import sqlite3

from app.utils.birddog import create_birddog, _slugify, _unique_slug


# --- helper: a Row-enabled connection to the test DB (matches how the app uses it) ---
def _conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


# =========================================================================
# _slugify() ? pure helper
# =========================================================================
def test_slugify_basic():
    assert _slugify("John Smith") == "johnsmith"


def test_slugify_strips_non_alphanumeric():
    assert _slugify("O'Brien-Jones Jr.") == "obrienjonesjr"


def test_slugify_lowercases():
    assert _slugify("LOUD NAME") == "loudname"


def test_slugify_empty_falls_back():
    assert _slugify("") == "birddog"
    assert _slugify(None) == "birddog"
    assert _slugify("!!!") == "birddog"


# =========================================================================
# _unique_slug() ? dedup within a dealership
# =========================================================================
def test_unique_slug_first_is_base(seed, db_path):
    conn = _conn(db_path)
    try:
        # 'test-birddog' is seeded; a fresh base should be returned unchanged
        assert _unique_slug(conn, "brandnew", dealership_id=1) == "brandnew"
    finally:
        conn.close()


def test_unique_slug_dedups_within_dealership(seed, db_path):
    conn = _conn(db_path)
    try:
        # insert a birddog with slug 'dupe', then ask for the same base
        conn.execute(
            "INSERT INTO birddogs (team_member_id, name, token, slug, dealership_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (seed["team_member_id"], "Dupe One", "tok-dupe-1", "dupe", 1),
        )
        conn.commit()
        assert _unique_slug(conn, "dupe", dealership_id=1) == "dupe2"
    finally:
        conn.close()


def test_unique_slug_isolated_per_dealership(seed, db_path):
    conn = _conn(db_path)
    try:
        # 'shared' taken in dealership 1 should NOT collide in dealership 2
        conn.execute(
            "INSERT INTO birddogs (team_member_id, name, token, slug, dealership_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (seed["team_member_id"], "Shared D1", "tok-shared-1", "shared", 1),
        )
        conn.commit()
        assert _unique_slug(conn, "shared", dealership_id=2) == "shared"
        assert _unique_slug(conn, "shared", dealership_id=1) == "shared2"
    finally:
        conn.close()


# =========================================================================
# create_birddog() ? the core of Chain 1
# =========================================================================
def test_create_birddog_makes_valid_row(seed, db_path):
    conn = _conn(db_path)
    try:
        r = create_birddog(
            conn, team_member_id=seed["team_member_id"],
            name="Jane Doe", phone="5551230000",
        )
    finally:
        conn.close()
    assert r["existing"] is False
    assert r["slug"] == "janedoe"
    assert r["id"] > 0
    assert len(r["token"]) >= 16          # secrets.token_urlsafe(16)
    assert r["team_member_id"] == seed["team_member_id"]
    assert r["dealership_id"] == 1


def test_create_birddog_persists_to_db(seed, db_path):
    conn = _conn(db_path)
    try:
        r = create_birddog(
            conn, team_member_id=seed["team_member_id"],
            name="Persist Me", phone="5559990000",
        )
        row = conn.execute(
            "SELECT name, slug, token, team_member_id FROM birddogs WHERE id = ?",
            (r["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["name"] == "Persist Me"
    assert row["slug"] == r["slug"]
    assert row["token"] == r["token"]


def test_create_birddog_is_idempotent_on_phone_and_rep(seed, db_path):
    conn = _conn(db_path)
    try:
        first = create_birddog(
            conn, team_member_id=seed["team_member_id"],
            name="Repeat Caller", phone="5551112222",
        )
        second = create_birddog(
            conn, team_member_id=seed["team_member_id"],
            name="Repeat Caller", phone="5551112222",
        )
    finally:
        conn.close()
    assert first["existing"] is False
    assert second["existing"] is True
    assert first["id"] == second["id"]      # same row, not a duplicate


def test_create_birddog_same_phone_different_rep_is_distinct(seed, db_path):
    """Same phone under a DIFFERENT rep is a different birddog (idempotency key is phone+rep)."""
    conn = _conn(db_path)
    try:
        # add a second dealership_team rep to attribute under
        cur = conn.execute(
            "INSERT INTO dealership_team (dealership_id, name, slug, is_active) "
            "VALUES (1, ?, ?, 1)",
            ("Second Rep", "secondrep"),
        )
        rep2 = cur.lastrowid
        conn.commit()

        a = create_birddog(conn, team_member_id=seed["team_member_id"],
                            name="Mobile Sharer", phone="5557778888")
        b = create_birddog(conn, team_member_id=rep2,
                            name="Mobile Sharer", phone="5557778888")
    finally:
        conn.close()
    assert a["id"] != b["id"]
    assert b["existing"] is False


def test_create_birddog_dedups_slug_for_distinct_people(seed, db_path):
    """Two different people with the same name get distinct slugs (johnsmith, johnsmith2)."""
    conn = _conn(db_path)
    try:
        a = create_birddog(conn, team_member_id=seed["team_member_id"],
                            name="John Smith", phone="5552223331")
        b = create_birddog(conn, team_member_id=seed["team_member_id"],
                            name="John Smith", phone="5552223332")
    finally:
        conn.close()
    assert a["slug"] == "johnsmith"
    assert b["slug"] == "johnsmith2"
    assert a["id"] != b["id"]


def test_create_birddog_stores_email_when_given(seed, db_path):
    conn = _conn(db_path)
    try:
        r = create_birddog(
            conn, team_member_id=seed["team_member_id"],
            name="With Email", phone="5554443333", email="bird@example.com",
        )
        row = conn.execute(
            "SELECT email FROM birddogs WHERE id = ?", (r["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert r["email"] == "bird@example.com"
    assert row["email"] == "bird@example.com"
