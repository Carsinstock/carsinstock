from app import create_app, db
from app.models import Salesperson, Vehicle


def seed_data():
    # --- Create app context ---
    app = create_app()
    with app.app_context():
        # Start fresh
        db.drop_all()
        db.create_all()

        # --- Demo salespeople ---

        eddie = Salesperson(
            slug="eddie",
            name="Eddie Castillo",
            dealership="Pine Belt Pre-Owned Vehicles",
            city="Toms River",
            state="NJ",
            phone="732-555-1234",
            email="eddie@example.com",
            tagline="TOP RATED STRAIGHT ANSWERS, NO GAMES.",
            bio="I help people in Ocean & Monmouth County find the right car with straightforward numbers and no surprises.",
            google_rating=5.0,
            google_review_count=124,
            review_highlight="Hands down the easiest car deal I’ve ever done.",
        )

        kim = Salesperson(
            slug="kim",
            name="Kim Chan",
            dealership="Pine Belt Toyota",
            city="Lakewood",
            state="NJ",
            phone="732-555-5678",
            email="kim@example.com",
            tagline="Top rated Toyota specialist.",
            bio="I help busy families find reliable Toyotas that fit their payment and their lifestyle.",
            google_rating=4.9,
            google_review_count=89,
            review_highlight="Kim made everything simple and stress-free.",
        )

        db.session.add_all([eddie, kim])
        db.session.commit()

        # --- Demo inventory for Eddie ---

        eddie_crv = Vehicle(
            salesperson_id=eddie.id,
            year=2021,
            make="Honda",
            model="CR-V EX",
            trim="AWD · One owner",
            miles=28430,
            price="$24,995",
            body_style="SUV",
            drivetrain="AWD",
            transmission="Automatic",
        )

        eddie_equinox = Vehicle(
            salesperson_id=eddie.id,
            year=2020,
            make="Chevrolet",
            model="Equinox LT",
            trim="FWD · Remote start",
            miles=34100,
            price="$19,995",
            body_style="SUV",
            drivetrain="FWD",
            transmission="Automatic",
        )

        eddie_camry = Vehicle(
            salesperson_id=eddie.id,
            year=2019,
            make="Toyota",
            model="Camry SE",
            trim="Sport · Backup camera",
            miles=41250,
            price="$18,495",
            body_style="Sedan",
            drivetrain="FWD",
            transmission="Automatic",
        )

        # --- Demo inventory for Kim ---

        kim_rav4 = Vehicle(
            salesperson_id=kim.id,
            year=2022,
            make="Toyota",
            model="RAV4 XLE",
            trim="AWD · Moonroof",
            miles=28800,
            price="$27,995",
            body_style="SUV",
            drivetrain="AWD",
            transmission="Automatic",
        )

        kim_corolla = Vehicle(
            salesperson_id=kim.id,
            year=2021,
            make="Toyota",
            model="Corolla LE",
            trim="Great on gas",
            miles=22150,
            price="$18,250",
            body_style="Sedan",
            drivetrain="FWD",
            transmission="Automatic",
        )

        db.session.add_all(
            [eddie_crv, eddie_equinox, eddie_camry, kim_rav4, kim_corolla]
        )
        db.session.commit()

        print("✅ Database created and demo salespeople + vehicles added.")


if __name__ == "__main__":
    seed_data()
