import os
import stripe
from flask import request, redirect, url_for, session, render_template, flash, current_app
from app.billing import billing_bp
from app.models import db
from app.models.user import User
from app.models.salesperson import Salesperson
from app.models.vehicle import Vehicle
from functools import wraps

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def get_or_create_price_id():
    """Get price ID from env, or create the product+price in Stripe and save it."""
    price_id = os.environ.get('STRIPE_PRICE_ID')
    if price_id:
        return price_id
    # Create product
    product = stripe.Product.create(name='CarsInStock Monthly Subscription')
    price = stripe.Price.create(
        product=product.id,
        unit_amount=2000,  # $20.00 base
        currency='usd',
        recurring={'interval': 'month'},
    )
    # Persist to .env file for future runs
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    try:
        with open(env_path, 'a') as f:
            f.write(f'\nSTRIPE_PRICE_ID={price.id}\n')
    except Exception:
        pass
    os.environ['STRIPE_PRICE_ID'] = price.id
    return price.id


@billing_bp.route('/checkout')
@login_required
def checkout():
    user = User.query.get(session['user_id'])
    sp = Salesperson.query.filter_by(user_id=user.id).first()

    # Create or retrieve Stripe customer
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=sp.display_name if sp else user.email,
            metadata={'user_id': user.id}
        )
        user.stripe_customer_id = customer.id
        db.session.commit()

    # Count active vehicles for metered add-on (informational — base price only in checkout)
    active_vehicles = 0
    if sp:
        active_vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).filter(
            Vehicle.expires_at > db.func.now()
        ).count() if hasattr(Vehicle, 'expires_at') else 0

    price_id = get_or_create_price_id()

    checkout_session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': 1}],
        mode='subscription',
        success_url=url_for('billing.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('salesperson.dashboard', _external=True),
        metadata={'user_id': user.id},
        subscription_data={'metadata': {'user_id': user.id}},
    )
    return redirect(checkout_session.url, code=303)


@billing_bp.route('/success')
@login_required
def success():
    session_id = request.args.get('session_id')
    if session_id:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            user = User.query.get(session['user_id'])
            if checkout_session.subscription:
                user.stripe_subscription_id = checkout_session.subscription
                user.subscription_status = 'active'
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f'Stripe success error: {e}')
    flash('Subscription activated! Welcome to CarsInStock.', 'success')
    return redirect(url_for('salesperson.dashboard'))


@billing_bp.route('/portal')
@login_required
def portal():
    user = User.query.get(session['user_id'])
    if not user.stripe_customer_id:
        flash('No billing account found.', 'error')
        return redirect(url_for('salesperson.dashboard'))
    portal_session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=url_for('salesperson.dashboard', _external=True),
    )
    return redirect(portal_session.url, code=303)


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(request.get_json(), stripe.api_key)
    except Exception as e:
        current_app.logger.error(f'Webhook error: {e}')
        return '', 400

    etype = event['type']
    data = event['data']['object']

    if etype == 'customer.subscription.created' or etype == 'invoice.payment_succeeded':
        customer_id = data.get('customer')
        sub_id = data.get('id') if etype == 'customer.subscription.created' else data.get('subscription')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.subscription_status = 'active'
            if sub_id:
                user.stripe_subscription_id = sub_id
            db.session.commit()

    elif etype == 'customer.subscription.deleted':
        customer_id = data.get('customer')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.subscription_status = 'cancelled'
            user.stripe_subscription_id = None
            db.session.commit()

    elif etype == 'invoice.payment_failed':
        customer_id = data.get('customer')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.subscription_status = 'past_due'
            db.session.commit()

    return '', 200
