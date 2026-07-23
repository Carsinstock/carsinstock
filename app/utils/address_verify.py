"""
app/utils/address_verify.py  --  Smarty deliverability gate (Stage 1)

WHY THIS FILE EXISTS
    Roughly 1,000 letters came back undeliverable and the pilot dealer paid
    the postage.  Nothing in the codebase verified an address before it
    became mail.  This module is the gate: no address becomes a letter
    unless USPS confirms it is a live delivery point.

THREE OUTCOMES, NEVER TWO
    DELIVERABLE       -> letter, printed with Smarty's standardized address
    UNDELIVERABLE     -> dropped, counted, reported with a reason
    COULD_NOT_VERIFY  -> HALT.  Nothing generated, nothing sent.
    "I checked and it is bad" and "I could not check" must never collapse
    into each other.  That collapse is the bug family this whole project
    has been fighting.

FREEFORM, ON PURPOSE
    The raw joined address string is sent as `street` with no city/state/
    zip.  Smarty parses it.  We do NOT parse addresses ourselves: a survey
    of 922 stored addresses found six distinct formats, including strings
    with no state, strings with no delimiters at all, and "NJ" appearing
    inside street names ("41 NJ Route 36").  A homegrown parser would be
    new untested code sitting in the middle of the gate.

    Freeform forces STRICT matching, so responses are SPARSE.  An input_id
    with no row means Smarty looked and could not match it -> UNDELIVERABLE.
    Verified by test 2026-07-19: freeform + match=invalid returns 1 row for
    3 inputs.  match=invalid does NOT survive freeform.

ZERO-ROW SAFEGUARD
    Per-address, "no row" is a legitimate rejection.  But if a whole batch
    comes back with ZERO rows, that is COULD_NOT_VERIFY, not fifteen bad
    addresses.  A batch matching nothing is far more likely a bad seed, a
    malformed payload, or a service fault.

WHAT THIS GATE CANNOT DO
    It cannot catch "right street, wrong town."  If a seed geocodes forty
    miles away, the resulting houses are real and DPV will pass them.  See
    the seed-confirmation item on the board.
"""

from __future__ import annotations

import json
import os
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

# --------------------------------------------------------------- verdicts
DELIVERABLE = "DELIVERABLE"
UNDELIVERABLE = "UNDELIVERABLE"
COULD_NOT_VERIFY = "COULD_NOT_VERIFY"

# --------------------------------------------------------------- settings
_log = logging.getLogger(__name__)

_ENDPOINT = "https://us-street.api.smarty.com/street-address"
# TRIAL-SPECIFIC.  "us-core-cloud" is the Core Edition / Cloud License string
# for the 42-day trial.  ON THE AUG 29 PURCHASE CHECKLIST: confirm the PAID
# plan uses the same license string.  If it differs and this is not updated,
# every request fails and the gate halts letter generation on day one of
# paying -- a self-inflicted outage at the worst possible moment.
_LICENSE = "us-core-cloud"
_TIMEOUT_SECS = 30
_MAX_BATCH = 100                    # Smarty's per-request ceiling

DROP_COMMERCIAL = True              # config flag; see handoff Stage 1

_USAGE_PATH = os.environ.get(
    "SMARTY_USAGE_PATH",
    "/home/eddie/carsinstock/instance/smarty_usage.json",
)
TRIAL_LIMIT = 1000
TRIAL_EXPIRES = "2026-08-29"


# --------------------------------------------------------------- results
@dataclass
class AddressResult:
    raw: str
    verdict: str
    standardized: Optional[str] = None   # what we PRINT on the letter
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    rdi: Optional[str] = None


@dataclass
class BatchResult:
    ok: bool                              # False => HALT, generate nothing
    halt_reason: Optional[str] = None     # TECHNICAL -- log this, never print it
    halt_code: Optional[str] = None       # what the REP should do about it
    results: List[AddressResult] = field(default_factory=list)
    seed_location: Optional[str] = None   # printed on the summary page

    @property
    def deliverable(self) -> List[AddressResult]:
        return [r for r in self.results if r.verdict == DELIVERABLE]

    @property
    def dropped(self) -> List[AddressResult]:
        return [r for r in self.results if r.verdict == UNDELIVERABLE]

    def drop_summary(self) -> str:
        """Human sentence for page 1.  Commercial is its own line so reps
        learn which seeds produce bad batches."""
        if not self.dropped:
            return ""
        counts = {}
        for r in self.dropped:
            counts[r.reason] = counts.get(r.reason, 0) + 1
        parts = ["%d %s" % (n, why) for why, n in
                 sorted(counts.items(), key=lambda kv: -kv[1])]
        return "; ".join(parts)


# --------------------------------------------------- predicate (pure)
def evaluate(candidate: dict, drop_commercial: bool = DROP_COMMERCIAL):
    """Deterministic.  No thresholds, no tuning knob.

    Every check is `!= expected` rather than `== bad`, so a MISSING field
    is a rejection.  This matters: observed live, three of four failing
    addresses had NO dpv_match_code key at all.  A `!= "N"` test would
    have passed all three straight into the mailer.
    """
    a = candidate.get("analysis") or {}
    m = candidate.get("metadata") or {}
    rt = m.get("record_type")
    fn = a.get("dpv_footnotes") or ""

    if a.get("dpv_match_code") != "Y":
        # refine the reason so the rep gets something actionable
        if "N1" in fn or rt == "H":
            return UNDELIVERABLE, "missing_unit", "need an apartment or unit number"
        if "M3" in fn:
            return UNDELIVERABLE, "bad_number", "house number not on this street"
        if "A1" in fn:
            return UNDELIVERABLE, "not_found", "address not found"
        return UNDELIVERABLE, "no_dpv_match", "not confirmed by USPS"

    if a.get("dpv_no_stat") != "N":
        return UNDELIVERABLE, "no_stat", "not currently receiving mail"
    if a.get("dpv_vacant") != "N":
        return UNDELIVERABLE, "vacant", "vacant property"
    if a.get("active") != "Y":
        return UNDELIVERABLE, "inactive", "address no longer active"

    if rt != "S":
        if rt == "P":
            return UNDELIVERABLE, "po_box", "PO box"
        if rt == "H":
            return UNDELIVERABLE, "multi_unit", "need an apartment or unit number"
        return UNDELIVERABLE, "not_street", "not a street delivery point"

    if a.get("dpv_cmra") != "N":
        return UNDELIVERABLE, "cmra", "commercial mailbox service"

    if drop_commercial and m.get("rdi") == "Commercial":
        return UNDELIVERABLE, "commercial", "business address"

    return DELIVERABLE, None, None


def _standardized(candidate: dict) -> Optional[str]:
    """What gets PRINTED.  Canonical USPS form with ZIP+4 -- this is the
    line that makes 'USPS-verified' true on the page."""
    line1 = candidate.get("delivery_line_1")
    last = candidate.get("last_line")
    if not line1 or not last:
        return None
    return "%s\n%s" % (line1, last)


# ------------------------------------------- offline-testable assembly
def build_results(addresses: List[str], candidates: List[dict],
                  drop_commercial: bool = DROP_COMMERCIAL) -> BatchResult:
    """Pure.  Takes the addresses we sent and the rows Smarty returned,
    produces the batch outcome.  No network -- this is what the fixture
    self-test exercises."""
    if not addresses:
        return BatchResult(ok=False, halt_reason="no addresses supplied",
                           halt_code="transient")

    # Map by input_id.  NEVER by position: the array is sparse, and zipping
    # positionally would attach the wrong verified address to the wrong
    # letter -- a clean run that mails the neighbour's letter next door.
    by_id = {}
    for c in candidates:
        key = c.get("input_id")
        if key is None:
            continue
        # candidates=1, but keep the first if Smarty ever returns more
        by_id.setdefault(key, c)

    # ZERO-MATCH SAFEGUARD.  Counts OUR ids that came back, not merely rows
    # returned.  Checking `candidates` alone is not enough: if Smarty ever
    # returns rows whose input_ids we do not recognise, by_id misses on
    # every address, all N fall through to the "no row" branch, and we hand
    # back ok=True with the whole batch silently marked UNDELIVERABLE --
    # the exact collapse this gate exists to prevent, wearing a success
    # flag.  Per-address "no row" is a legitimate rejection; ZERO addresses
    # matching is an upstream fault (bad seed, malformed payload, service
    # issue), and we halt.
    matched = sum(1 for i in range(len(addresses)) if str(i) in by_id)
    if matched == 0:
        return BatchResult(
            ok=False,
            halt_reason="no addresses could be checked (0 of %d matched)"
                        % len(addresses),
            halt_code="transient",
        )

    out = []
    for i, raw in enumerate(addresses):
        c = by_id.get(str(i))
        if c is None:
            # Sparse response is EXPECTED under freeform/strict.
            # No row = Smarty looked and could not match it.
            out.append(AddressResult(raw=raw, verdict=UNDELIVERABLE,
                                     reason_code="not_found",
                                     reason="address not found"))
            continue
        verdict, code, why = evaluate(c, drop_commercial)
        out.append(AddressResult(
            raw=raw,
            verdict=verdict,
            standardized=_standardized(c) if verdict == DELIVERABLE else None,
            reason_code=code,
            reason=why,
            rdi=(c.get("metadata") or {}).get("rdi"),
        ))
    return BatchResult(ok=True, results=out)


# --------------------------------------------------------------- usage
def _read_usage() -> dict:
    try:
        with open(_USAGE_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {"used": 0, "updated": None}


def record_usage(n: int) -> dict:
    """Local counter -- Smarty does not return remaining quota, so this is
    an ESTIMATE and should be cross-checked against the dashboard.  It can
    drift if a request is billed but dies in transit.

    A write failure must NOT be swallowed.  instance/ is owned by
    www-data; if this file stops being writable the counter freezes, the
    quota monitor goes blind, and the first symptom is a surprise 402
    mid-batch.  So: log loudly, and mark the result so usage_status() can
    report the counter as untrustworthy rather than merely low.
    """
    u = _read_usage()
    u["used"] = int(u.get("used", 0)) + int(n)
    u["updated"] = datetime.now(timezone.utc).isoformat()
    u["write_ok"] = True
    try:
        tmp = _USAGE_PATH + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(u, fh)
        os.replace(tmp, _USAGE_PATH)
    except Exception as exc:
        # Bookkeeping must never break letter generation -- but it must
        # never fail quietly either.
        u["write_ok"] = False
        _log.error("SMARTY QUOTA COUNTER WRITE FAILED (%s): %s -- counter is "
                   "now stale, quota monitor is blind, check ownership of %s",
                   type(exc).__name__, exc, _USAGE_PATH)
    return u


def usage_status() -> dict:
    """Read-only view for the quota monitor.

    `counter_healthy` is False when the file is missing or unwritable --
    the monitor must alarm on that as loudly as on a high count, because a
    frozen counter reads as LOW usage, which is indistinguishable from
    everything being fine right up until the 402.
    """
    u = _read_usage()
    used = int(u.get("used", 0))
    days = (datetime.strptime(TRIAL_EXPIRES, "%Y-%m-%d").date()
            - datetime.now(timezone.utc).date()).days
    writable = os.access(os.path.dirname(_USAGE_PATH) or ".", os.W_OK)
    if os.path.exists(_USAGE_PATH):
        writable = writable and os.access(_USAGE_PATH, os.W_OK)
    return {
        "used": used,
        "limit": TRIAL_LIMIT,
        "remaining": max(TRIAL_LIMIT - used, 0),
        "pct": (used / TRIAL_LIMIT) * 100 if TRIAL_LIMIT else 0,
        "days_left": days,
        "expires": TRIAL_EXPIRES,
        "updated": u.get("updated"),
        "counter_healthy": bool(writable) and u.get("write_ok", True),
    }


# What the REP sees on the halt page.  The technical halt_reason is logged,
# never printed -- "not authorised" or "batch too large" would alarm a rep
# who can do nothing about either.  Two codes, because they call for
# different actions: "try again" is a lie when the allowance is gone.
REP_HALT_MESSAGE = {
    "transient": ("We could not check these addresses just now.\n"
                  "No letters were generated and nothing was sent.\n"
                  "Please try again in a few minutes."),
    "blocked":   ("Address checking is unavailable right now.\n"
                  "No letters were generated and nothing was sent.\n"
                  "Please let your manager know."),
}
_DEFAULT_HALT = REP_HALT_MESSAGE["transient"]


def rep_halt_message(batch: "BatchResult") -> str:
    """Rep-facing text for the halt PDF.  Logs the technical detail."""
    _log.error("NEIGHBOR BATCH HALTED [%s]: %s",
               batch.halt_code, batch.halt_reason)
    return REP_HALT_MESSAGE.get(batch.halt_code or "", _DEFAULT_HALT)


def seed_location(batch: "BatchResult") -> Optional[str]:
    """Derived from the VERIFIED results, not from the seed input.

    Better than echoing the seed: it reports where the letters are actually
    going.  If a seed geocodes forty miles away, every verified address
    carries the wrong town, and the rep reads "Mays Landing, NJ 08330" on
    page 1 before printing.  Also needs no frontend change, since the
    generate route never receives the seed.
    """
    lines = [r.standardized.split("\n")[-1]
             for r in batch.deliverable if r.standardized]
    if not lines:
        return None
    counts = {}
    for ln in lines:
        counts[ln] = counts.get(ln, 0) + 1
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    # "Toms River NJ 08753-3733" -> "Toms River NJ 08753"
    return best.rsplit("-", 1)[0] if "-" in best.split()[-1] else best


# --------------------------------------------------------------- network
def verify_batch(addresses: List[str],
                 drop_commercial: bool = DROP_COMMERCIAL) -> BatchResult:
    """THE GATE.  Returns a BatchResult; ok=False means generate nothing."""
    if not addresses:
        return BatchResult(ok=False, halt_reason="no addresses supplied",
                           halt_code="transient")
    if len(addresses) > _MAX_BATCH:
        return BatchResult(
            ok=False,
            halt_reason="batch too large (%d, max %d)"
                        % (len(addresses), _MAX_BATCH),
            halt_code="transient")

    auth_id = os.environ.get("SMARTY_AUTH_ID")
    auth_token = os.environ.get("SMARTY_AUTH_TOKEN")
    if not auth_id or not auth_token:
        # Crons load their own env -- a missing key here means the caller
        # forgot load_dotenv.  Halt loudly rather than mail unverified.
        return BatchResult(ok=False,
                           halt_reason="SMARTY_AUTH_ID/TOKEN missing from env",
                           halt_code="blocked")

    payload = [{"input_id": str(i), "street": a, "candidates": 1}
               for i, a in enumerate(addresses)]
    url = "%s?auth-id=%s&auth-token=%s&license=%s" % (
        _ENDPOINT,
        urllib.parse.quote(auth_id),
        urllib.parse.quote(auth_token),
        _LICENSE,
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECS) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        if status == 402:
            return BatchResult(
                ok=False,
                halt_reason="HTTP 402 - Smarty lookup allowance depleted",
                halt_code="blocked")
        if status in (401, 403):
            return BatchResult(
                ok=False,
                halt_reason="HTTP %s - Smarty auth rejected" % status,
                halt_code="blocked")
        if status == 429:
            return BatchResult(
                ok=False,
                halt_reason="HTTP 429 - rate limited",
                halt_code="transient")
        return BatchResult(ok=False,
                           halt_reason="HTTP %s from Smarty" % status,
                           halt_code="transient")
    except Exception as exc:
        return BatchResult(ok=False,
                           halt_reason="network error: %s" % type(exc).__name__,
                           halt_code="transient")

    if status != 200:
        return BatchResult(ok=False,
                           halt_reason="HTTP %s from Smarty" % status,
                           halt_code="transient")

    # Billed per address submitted, whether or not it matched.
    record_usage(len(addresses))

    try:
        data = json.loads(body)
    except Exception:
        return BatchResult(
            ok=False,
            halt_reason="unparseable JSON from Smarty", halt_code="transient")
    if not isinstance(data, list):
        return BatchResult(
            ok=False,
            halt_reason="unexpected JSON shape from Smarty",
            halt_code="transient")

    return build_results(addresses, data, drop_commercial)


# --------------------------------------------------------------- self-test
if __name__ == "__main__":
    import glob
    import sys

    fixtures = sorted(glob.glob("/home/eddie/smarty_fixture_*.json"))
    if not fixtures:
        print("no fixture found; run the capture step first")
        sys.exit(1)
    blob = json.load(open(fixtures[-1]))
    sent, got = blob["sent"], blob["got"]

    print("=== predicate vs saved fixture (%d rows, 0 lookups) ===" % len(got))
    print("%-5s %-26s %-14s %s" % ("id", "input", "verdict", "reason"))
    for c in got:
        v, code, why = evaluate(c)
        src = next((s["street"] for s in sent
                    if s["input_id"] == c.get("input_id")), "?")
        print("%-5s %-26s %-14s %s" % (c.get("input_id"), src[:26], v,
                                       why or _standardized(c) or ""))

    print()
    print("=== assembly incl. sparse + zero-row safeguard ===")
    addrs = ["852 Tudor Ct, Toms River, NJ 08753",
             "1339 Hooper Ave, Toms River, NJ 08753"]
    fake = [dict(json.loads(json.dumps(
        next(c for c in got if c.get("input_id") == "f11"))), input_id="0")]
    br = build_results(addrs, fake)
    print("ok=%s  deliverable=%d  dropped=%d" %
          (br.ok, len(br.deliverable), len(br.dropped)))
    print("summary:", br.drop_summary())
    for r in br.results:
        print("   ", r.verdict, "|", (r.standardized or r.reason))

    empty = build_results(addrs, [])
    print()
    print("zero-row batch -> ok=%s  halt=%r" % (empty.ok, empty.halt_reason))
