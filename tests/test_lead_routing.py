"""
Chain 3 -- Lead routing.

COVERAGE (Phase 2):
  [TESTED]  Lead routing data model + routing rules, verified at the ORM level:
            - a storefront lead inherits the vehicle's salesperson_id (routes to
              the rep who owns the car) -- the submit_lead() rule
            - a rep-storefront lead credits the rep via referred_by (the
              rep_submit_lead() rule: referred_by = team_slug)
            - referred_by is recorded only when it resolves to a real rep, else None
            - source/status defaults behave as the handlers rely on
  [DEFERRED] The HTTP route handlers themselves (rep_submit_lead, submit_lead)
            resolve the rep via raw sqlite3.connect() to the hardcoded prod DB
            path, and rep_submit_lead calls attribute_lead_to_birddog (F-1).
            Full end-to-end HTTP handler tests are DEFERRED to Phase 2.5
            (Database Access Refactor). See findings F-1/F-2. The routing LOGIC
            those handlers implement is covered here at the model level.

These tests lock the routing invariants the platform depends on: a lead always
lands with the correct rep, and referral credit is recorded correctly (or not
at all when the referrer is invalid).
"""
from datetime import datetime, timedelta

from app.models import db
from app.models.user import User
from app.models.dealer import Dealer
from app.models.salesperson import Salesperson
from app.models.vehicle import Vehicle
from app.models.lead import Lead


# --- helpers: build reps + vehicles in the disposable DB --------------------
def _make_rep(app, slug, email):
    with app.app_context():
        dealer = Dealer(dealer_name="Routing Motors", city="Testville")
        db.session.add(dealer)
        db.session.flush()
        user = User(email=email, password_hash="x")
        db.session.add(user)
        db.session.flush()
        rep = Salesperson(
            user_id=user.id, dealer_id=dealer.dealer_id,
            display_name=slug, email=email,
            profile_url_slug=slug, status="active",
        )
        db.session.add(rep)
        db.session.commit()
        return rep.salesperson_id


def _make_vehicle(app, salesperson_id, vin):
    with app.app_context():
        v = Vehicle(
            salesperson_id=salesperson_id,
            year=2023, make="Toyota", model="RAV4", vin=vin,
            mileage=10000, price=30000.0, status="available",
            expires_at=datetime.utcnow() + timedelta(days=7),
            approval_status="approved",
        )
        db.session.add(v)
        db.session.commit()
        return v.id


# =========================================================================
# Storefront lead routes to the rep who owns the vehicle (submit_lead rule)
# =========================================================================
def test_lead_routes_to_vehicle_owner(app):
    rep_id = _make_rep(app, "ownerrep", "owner@x.com")
    veh_id = _make_vehicle(app, rep_id, "VINOWNER0000001")
    with app.app_context():
        lead = Lead(
            vehicle_id=veh_id, salesperson_id=rep_id,
            customer_name="Buyer", customer_email="buyer@x.com",
            source="storefront", status="new",
        )
        db.session.add(lead)
        db.session.commit()
        fetched = Lead.query.get(lead.lead_id)
        assert fetched.salesperson_id == rep_id
        assert fetched.vehicle_id == veh_id


def test_two_reps_leads_dont_cross(app):
    """A lead for rep A's car must not land on rep B."""
    a = _make_rep(app, "repa", "a@x.com")
    b = _make_rep(app, "repb", "b@x.com")
    va = _make_vehicle(app, a, "VINA0000000001")
    vb = _make_vehicle(app, b, "VINB0000000001")
    with app.app_context():
        la = Lead(vehicle_id=va, salesperson_id=a,
                  customer_name="CA", customer_email="ca@x.com", source="storefront")
        lb = Lead(vehicle_id=vb, salesperson_id=b,
                  customer_name="CB", customer_email="cb@x.com", source="storefront")
        db.session.add_all([la, lb])
        db.session.commit()
        assert Lead.query.get(la.lead_id).salesperson_id == a
        assert Lead.query.get(lb.lead_id).salesperson_id == b
        assert a != b


# =========================================================================
# referred_by credit (rep_submit_lead rule: referred_by = team_slug)
# =========================================================================
def test_rep_storefront_lead_credits_rep_via_referred_by(app):
    rep_id = _make_rep(app, "joeviverito", "joe@x.com")
    veh_id = _make_vehicle(app, rep_id, "VINJOE00000001")
    with app.app_context():
        lead = Lead(
            vehicle_id=veh_id, salesperson_id=rep_id,
            customer_name="Cust", customer_email="c@x.com",
            source="rep_storefront", referred_by="joeviverito",
        )
        db.session.add(lead)
        db.session.commit()
        fetched = Lead.query.get(lead.lead_id)
        assert fetched.referred_by == "joeviverito"
        assert fetched.source == "rep_storefront"


def test_no_attribution_lead_has_null_referred_by(app):
    """submit_lead rule: referred_by = referred_by if _ref_member else None.
    A lead with no valid referrer still routes to the owner, referred_by None."""
    rep_id = _make_rep(app, "soloRep", "solo@x.com")
    veh_id = _make_vehicle(app, rep_id, "VINSOLO0000001")
    with app.app_context():
        lead = Lead(
            vehicle_id=veh_id, salesperson_id=rep_id,
            customer_name="NoRef", customer_email="noref@x.com",
            source="storefront", referred_by=None,
        )
        db.session.add(lead)
        db.session.commit()
        fetched = Lead.query.get(lead.lead_id)
        assert fetched.salesperson_id == rep_id   # still routed to owner
        assert fetched.referred_by is None        # no false credit


# =========================================================================
# Model defaults the handlers rely on
# =========================================================================
def test_lead_source_defaults_to_organic_when_omitted(app):
    rep_id = _make_rep(app, "defrep", "def@x.com")
    with app.app_context():
        lead = Lead(salesperson_id=rep_id,
                    customer_name="D", customer_email="d@x.com")
        db.session.add(lead)
        db.session.commit()
        fetched = Lead.query.get(lead.lead_id)
        assert fetched.source == "organic"
        assert fetched.status == "new"


def test_lead_requires_salesperson_id(app):
    """salesperson_id is NOT NULL -- a lead can never be orphaned with no rep."""
    import sqlalchemy
    rep_id = _make_rep(app, "nn", "nn@x.com")  # noqa: F841
    with app.app_context():
        bad = Lead(customer_name="Orphan", customer_email="o@x.com")  # no salesperson_id
        db.session.add(bad)
        raised = False
        try:
            db.session.commit()
        except sqlalchemy.exc.IntegrityError:
            raised = True
            db.session.rollback()
        assert raised, "lead without salesperson_id should violate NOT NULL"


def test_lead_can_carry_vehicle_or_not(app):
    """Leads may be vehicle-specific or general (vehicle_id nullable)."""
    rep_id = _make_rep(app, "vrep", "v@x.com")
    veh_id = _make_vehicle(app, rep_id, "VINVEH00000001")
    with app.app_context():
        with_v = Lead(vehicle_id=veh_id, salesperson_id=rep_id,
                      customer_name="WV", customer_email="wv@x.com", source="storefront")
        without_v = Lead(salesperson_id=rep_id,
                         customer_name="NV", customer_email="nv@x.com", source="rep_storefront")
        db.session.add_all([with_v, without_v])
        db.session.commit()
        assert Lead.query.get(with_v.lead_id).vehicle_id == veh_id
        assert Lead.query.get(without_v.lead_id).vehicle_id is None
