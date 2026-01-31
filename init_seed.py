from app import create_app, db
from app.models import Dealership, User, Site

app = create_app()
app.app_context().push()

# 1. Dealership
dealer = Dealership(
    name="Pine Belt Pre-Owned Vehicles",
    city="Toms River",
    state="NJ",
    main_phone="(732) 555-1234",
)
db.session.add(dealer)
db.session.commit()

# 2. Salesperson
user = User(
    dealership_id=dealer.id,
    first_name="Eddie",
    last_name="Castillo",
    email="eddie@carsinstock.com",
    phone="(732) 555-9999",
)
user.set_password("test1234")
db.session.add(user)
db.session.commit()

# 3. Site
site = Site(
    dealership_id=dealer.id,
    user_id=user.id,
    slug="eddie",
    display_name="Eddie Castillo",
    tagline="Helping real people get real cars.",
    bio="Welcome to my inventory. I’ll help you find the right car.",
)
db.session.add(site)
db.session.commit()

print("Seed complete: dealership, user, site created.")
