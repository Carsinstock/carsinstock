"""
Chain 4 -- Blast email recipient filtering (existing behavior).

SCOPE NOTE -- this chain was REPOINTED during Phase 2:
  The original scope named cron_saturday.py, but that is a low-volume
  (~4 email) internal rep reminder, NOT the mass customer blast that caused
  the April 2026 SendGrid crisis. The real customer-blast recipient logic lives
  in app/cron.py (run_onboarding_blast / run_weekly_blast). These tests cover
  the EXISTING recipient-filter behavior of that real query.

COVERAGE (Phase 2):
  [TESTED]  The recipient-selection filter used by both blast functions:
              WHERE salesperson_id=? AND unsubscribed=0
                    AND email IS NOT NULL AND email != ""
            Verified: unsubscribed excluded, subscribed included, NULL-unsub
            excluded (SQLite NULL semantics), empty email excluded.
  [DOCUMENTED-GAP] Two tests below assert CURRENT (imperfect) behavior and act
            as the smoking gun for Phase 2.6 - Email Blast Guardrails:
              * whitespace-only email is INCLUDED (finding F-3)
              * source='cyberleads_quarantine' is INCLUDED (no source filter)
            When Phase 2.6 builds the source filter + email hardening, these
            two tests get UPDATED to assert the corrected behavior.
  [DEFERRED] app/cron.py uses get_db() with the hardcoded prod path (F-2), and
            the 500-cap / dry-run / source-filter guardrails DO NOT EXIST yet
            (Phase 2.6 builds them). Full cron-function coverage deferred.

The filter SQL here is copied verbatim from app/cron.py (lines 111 and 178) so
the test exercises the real query the production blast uses.
"""
import sqlite3
import pytest


# The EXACT recipient filter from app/cron.py (run_onboarding_blast line 111,
# run_weekly_blast line 178). Kept here verbatim so the test documents the real
# query. If Phase 2.6 changes the production query, update this string to match
# and flip the gap-documenting assertions.
BLAST_FILTER_SQL = (
    'SELECT id, email, unsubscribed, source FROM customers '
    'WHERE salesperson_id=? AND unsubscribed=0 '
    'AND email IS NOT NULL AND email != ""'
)


@pytest.fixture()
def cust_db():
    """A tiny disposable customers table mirroring the production columns."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, salesperson_id INT, "
        "email TEXT, unsubscribed BOOLEAN, source TEXT)"
    )
    conn.commit()
    yield conn
    conn.close()
    try:
        os.unlink(path)
    except OSError:
        pass


def _included_emails(conn, sp_id=1):
    rows = conn.execute(BLAST_FILTER_SQL, (sp_id,)).fetchall()
    return {r["email"] for r in rows}


def _add(conn, email, unsubscribed, source="web_signup", sp_id=1):
    conn.execute(
        "INSERT INTO customers (salesperson_id, email, unsubscribed, source) "
        "VALUES (?, ?, ?, ?)",
        (sp_id, email, unsubscribed, source),
    )
    conn.commit()


# =========================================================================
# Core unsubscribe filtering -- the protection that prevents emailing opt-outs
# =========================================================================
def test_subscribed_customer_is_included(cust_db):
    _add(cust_db, "sub@x.com", 0)
    assert "sub@x.com" in _included_emails(cust_db)


def test_unsubscribed_customer_is_excluded(cust_db):
    _add(cust_db, "unsub@x.com", 1)
    assert "unsub@x.com" not in _included_emails(cust_db)


def test_mixed_set_returns_only_subscribed(cust_db):
    _add(cust_db, "yes@x.com", 0)
    _add(cust_db, "no@x.com", 1)
    included = _included_emails(cust_db)
    assert included == {"yes@x.com"}


# =========================================================================
# Edge case: NULL unsubscribe (the 161 CyberLeads records)
# =========================================================================
def test_null_unsubscribe_is_excluded(cust_db):
    """DOCUMENTED BEHAVIOR: a NULL unsubscribed flag is EXCLUDED, because in
    SQLite `unsubscribed=0` evaluates NULL as not-true. Good: the 161 NULL
    CyberLeads records would not be blasted by the current query."""
    _add(cust_db, "nullsub@x.com", None)
    assert "nullsub@x.com" not in _included_emails(cust_db)


# =========================================================================
# Edge case: empty / whitespace email
# =========================================================================
def test_empty_email_is_excluded(cust_db):
    _add(cust_db, "", 0)
    assert "" not in _included_emails(cust_db)


def test_whitespace_only_email_is_currently_INCLUDED(cust_db):
    """FINDING F-3 (gap, smoking gun for Phase 2.6): a whitespace-only email
    PASSES the filter, because `email != ""` does not catch "   ". Such an
    address would be handed to SendGrid and bounce. Phase 2.6 should trim/
    validate; when it does, flip this assertion to `not in`."""
    _add(cust_db, "   ", 0)
    assert "   " in _included_emails(cust_db)   # documents CURRENT (flawed) behavior


# =========================================================================
# Source filter gap -- the smoking gun for Phase 2.6
# =========================================================================
def test_cyberleads_source_is_currently_INCLUDED(cust_db):
    """SMOKING GUN for Phase 2.6: the blast query has NO source filter, so
    source='cyberleads_quarantine' records are fully eligible to be blasted.
    This is the exact gap that drove the April 2026 SendGrid crisis. The
    NeverBounce cleanup deletes most of these rows, but the QUERY still has no
    guard -- a future unverified import would sail through. Phase 2.6 builds a
    source filter; when it does, flip this assertion to `not in`."""
    _add(cust_db, "cyber@x.com", 0, source="cyberleads_quarantine")
    assert "cyber@x.com" in _included_emails(cust_db)   # documents CURRENT behavior


def test_clean_source_is_included(cust_db):
    _add(cust_db, "real@x.com", 0, source="web_signup")
    assert "real@x.com" in _included_emails(cust_db)


# =========================================================================
# Per-salesperson scoping -- a blast only targets that rep's customers
# =========================================================================
def test_filter_is_scoped_to_salesperson(cust_db):
    _add(cust_db, "mine@x.com", 0, sp_id=1)
    _add(cust_db, "theirs@x.com", 0, sp_id=2)
    assert _included_emails(cust_db, sp_id=1) == {"mine@x.com"}
