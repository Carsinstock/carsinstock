from app import create_app, db
from app.models import Salesperson, Vehicle


def reset_and_seed():
    app = create_app()

    with app.app_context():
        # Drop and recreate all tables
        db.drop_all()
        db.create_all()

        # --- Eddie ---
        eddie = Salesperson(
            slug="eddie",
            name="Eddie Castillo",
            dealership="Pine Belt Pre-Owned Vehicles",
            city="Toms River",
            state="NJ",
            phone="732-555-1234",
            email="eddie@example.com",
            tagline="TOP RATED STRAIGHT ANSWERS, NO GAMES.",
            bio=(
                "I help people in Ocean & Monmouth County find the right car "
                "with straightforward numbers and no surprises."
            ),
        )

        # --- Vehicles (attach them directly to Eddie) ---
        v1 = Vehicle(
            salesperson=eddie,
            year=2021,
            make="Honda",
            model="CR-V",
            trim="EX",
            miles=28430,
            price=24995,
        )

        v2 = Vehicle(
            salesperson=eddie,
            year=2020,
            make="Chevrolet",
            model="Equinox",
            trim="LT",
            miles=34100,
            price=19995,
        )

        v3 = Vehicle(
            salesperson=eddie,
            year=2019,
            make="Toyota",
            model="Camry",
            trim="SE",
            miles=41250,
            price=18495,
        )

        # Save everything
        db.session.add_all([eddie, v1, v2, v3])
        db.session.commit()

        print("Database reset. Eddie + 3 vehicles added.")


if __name__ == "__main__":
    reset_and_seed()
