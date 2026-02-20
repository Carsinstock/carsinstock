from flask import Blueprint, render_template, request, redirect, flash, session

main = Blueprint('main', __name__)

@main.route('/')
def home():
    return render_template('index.html')

@main.route('/salespeople')
def salespeople():
    return render_template('salespeople.html')

@main.route('/customers')
def customers():
    from flask import session
    if session.get('user_id'):
        return redirect('/customers/list')
    return render_template('customers.html')

@main.route('/search-cars')
def search_cars():
    return render_template('search_cars.html')



@main.route('/how-to')
def howto():
    return render_template('howto.html')

@main.route('/<slug>')
def public_profile(slug):
    from app.models.salesperson import Salesperson
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp:
        return render_template('index.html')
    from app.models.vehicle import Vehicle
    from datetime import datetime
    vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').all()
    # Filter out expired
    vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]
    is_owner = (session.get('user_id') == sp.user_id)
    return render_template('salesperson/public_profile.html', sp=sp, vehicles=vehicles, is_owner=is_owner)


@main.route("/lead/submit", methods=["POST"])
def submit_lead():
    from app.models import db
    from app.models.lead import Lead
    from app.models.vehicle import Vehicle
    from app.models.salesperson import Salesperson
    from app.utils.email import send_email

    vehicle_id = request.form.get("vehicle_id")
    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()
    customer_phone = request.form.get("customer_phone", "").strip()
    message = request.form.get("message", "").strip()

    if not customer_name or not customer_email:
        flash("Name and email are required.", "error")
        return redirect(request.referrer or "/")

    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        flash("Vehicle not found.", "error")
        return redirect(request.referrer or "/")

    sp = Salesperson.query.get(vehicle.salesperson_id)

    lead = Lead(
        vehicle_id=vehicle.id,
        salesperson_id=vehicle.salesperson_id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        message=message,
        source="storefront",
        status="new"
    )

    try:
        db.session.add(lead)
        db.session.commit()

        # Send email notification to salesperson
        if sp and sp.email:
            html = f"""
            <h2>🚗 New Lead on CarsInStock!</h2>
            <p><strong>Vehicle:</strong> {vehicle.year} {vehicle.make} {vehicle.model}</p>
            <p><strong>Price:</strong> ${vehicle.price:,.0f}</p>
            <hr>
            <p><strong>Customer Name:</strong> {customer_name}</p>
            <p><strong>Email:</strong> {customer_email}</p>
            <p><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
            <p><strong>Message:</strong> {message or 'No message'}</p>
            <hr>
            <p>Log in to <a href="https://carsinstock.com">CarsInStock</a> to manage your leads.</p>
            """
            try:
                send_email(sp.email, f"New Lead: {vehicle.year} {vehicle.make} {vehicle.model}", html)
            except Exception as e:
                print(f"Lead email error: {e}")

        flash("Thanks! The salesperson will be in touch soon.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "error")
        print(f"Lead submit error: {e}")

    return redirect(request.referrer or "/")

@main.route('/debug-session')
def debug_session():
    from flask import session, jsonify
    from app.models.salesperson import Salesperson
    sp = Salesperson.query.first()
    return jsonify({
        'session_user_id': session.get('user_id'),
        'session_user_id_type': str(type(session.get('user_id'))),
        'sp_user_id': sp.user_id,
        'sp_user_id_type': str(type(sp.user_id)),
        'match': session.get('user_id') == sp.user_id
    })
