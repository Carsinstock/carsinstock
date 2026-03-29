import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To
from itsdangerous import URLSafeSerializer


def get_unsubscribe_serializer():
    secret = os.environ.get('SECRET_KEY', 'carsinstock-fallback-secret')
    return URLSafeSerializer(secret, salt='unsubscribe')


def generate_unsubscribe_token(customer_id):
    s = get_unsubscribe_serializer()
    return s.dumps(customer_id)


def verify_unsubscribe_token(token):
    s = get_unsubscribe_serializer()
    try:
        customer_id = s.loads(token)
        return customer_id
    except Exception:
        return None


def send_email(to_email, subject, html_content):
    try:
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        from_email = Email(
            email=os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@carsinstock.com'),
            name=os.environ.get('SENDGRID_FROM_NAME', 'CarsInStock')
        )
        message = Mail(
            from_email=from_email,
            to_emails=To(to_email),
            subject=subject,
            html_content=html_content
        )
        response = sg.send(message)
        print(f"Email sent to {to_email}, status: {response.status_code}")
        return response.status_code in [200, 201, 202]
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False


def send_welcome_email(to_email):
    subject = "Welcome to CarsInStock!"
    html_content = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #00C851;">
            <h1 style="color: #00C851; margin: 0; font-size: 28px;">CarsInStock</h1>
            <p style="color: #666; margin: 5px 0 0 0; font-size: 14px;">Real Salespeople. Real Inventory. Real Fresh.</p>
        </div>
        <div style="padding: 30px 0;">
            <h2 style="color: #333; margin-top: 0;">Welcome aboard!</h2>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">
                Your CarsInStock account has been created. You are one step closer to having your own
                public storefront where customers can browse your real, in-stock inventory.
            </p>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">
                <strong>What to do next:</strong>
            </p>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">
                1. Log in and set up your salesperson profile<br>
                2. Upload your vehicles with real photos<br>
                3. Share your personal storefront link with customers
            </p>
            <div style="text-align: center; padding: 20px 0;">
                <a href="https://carsinstock.com/login"
                   style="background-color: #00C851; color: white; padding: 14px 32px;
                          text-decoration: none; border-radius: 6px; font-size: 16px;
                          font-weight: bold; display: inline-block;">
                    Log In Now
                </a>
            </div>
            
                <div style="background:#F0FDF4;border-radius:8px;padding:20px;margin-bottom:20px;">
                <h3 style="color:#1E293B;margin-top:0;font-size:18px;">🎉 Your 14-Day Free Trial Has Started!</h3>
                <p style="color:#555;font-size:15px;line-height:1.6;margin:0;">
                    Post unlimited vehicles at no charge for 14 days. After your trial, it&#39;s just $39/month — unlimited cars, cancel anytime.
                </p>
            </div>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">
                Every listing on CarsInStock expires after 7 days so customers always see
                what is actually on your lot. No ghost cars. No stale inventory.
            </p>
        </div>
        <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
            <p style="color: #999; font-size: 12px; margin: 0;">
                Fresh Cars. Real People. | CarsInStock.com<br>
                Questions? Reply to sales@carsinstock.com
            </p>
        </div>
    </div>
    """
    return send_email(to_email, subject, html_content)


def _build_unsubscribe_footer(customer_id=None, salesperson_name=None, dealership_name=None):
    """Build email footer with unsubscribe link and legal disclaimer"""
    unsub_html = ""
    if customer_id:
        token = generate_unsubscribe_token(customer_id)
        unsub_url = f"https://carsinstock.com/unsubscribe/{token}"
        unsub_html = f'<a href="{unsub_url}" style="color:#94A3B8;font-size:11px;text-decoration:underline;">Unsubscribe</a>'
    disclaimer_html = '<a href="https://carsinstock.com/disclaimer" style="color:#94A3B8;font-size:11px;text-decoration:underline;">Legal Disclaimer</a>'
    separator = " &middot; " if unsub_html else ""
    return (
        f'<div style="border-top:1px solid #e2e8f0;padding:12px 0;text-align:center;">'
        f'<p style="color:#94A3B8;font-size:11px;margin:0 0 6px;line-height:1.5;">You are receiving this because you opted in to receive updates from the salesperson or dealership.</p>'
        f'{unsub_html}{separator}{disclaimer_html}'
        f'</div>'
    )

def send_vehicle_email(to_emails, vehicle, salesperson, personal_message="", customer_map=None):
    """Send vehicle listing to multiple email addresses.
    
    customer_map: dict mapping email -> customer_id for unsubscribe links.
    If None, no unsubscribe links are included (for non-customer recipients).
    """
    storefront_url = f"https://carsinstock.com/{salesperson.profile_url_slug}"
    subject = f"Check out this {vehicle.year} {vehicle.make} {vehicle.model}!"

    img_html = ""
    if vehicle.image_url:
        img_html = f'<img src="{vehicle.image_url}" style="width:100%; max-width:560px; border-radius:10px; margin-bottom:15px;">'

    msg_html = ""
    if personal_message:
        msg_html = f'<p style="color:#555; font-size:16px; line-height:1.6; font-style:italic; border-left:3px solid #00C851; padding-left:12px;">&ldquo;{personal_message}&rdquo;</p>'

    price_str = f"${vehicle.price:,.0f}" if vehicle.price else "Contact for price"
    mileage_str = f"{vehicle.mileage:,} miles" if vehicle.mileage else ""

    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    from_email = Email(
        email=os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@carsinstock.com'),
        name=salesperson.display_name + " via CarsInStock"
    )

    sent = 0
    errors = 0
    if customer_map is None:
        customer_map = {}

    for email_addr in to_emails:
        email_addr = email_addr.strip()
        if not email_addr:
            continue

        # Build per-recipient footer with their unsubscribe link
        cust_id = customer_map.get(email_addr)
        footer_html = _build_unsubscribe_footer(customer_id=cust_id, salesperson_name=salesperson.display_name, dealership_name=getattr(salesperson, "dealership_name", None))
        # Personalize {{first_name}} if we have a customer record
        from app.models.customer import Customer
        cust = Customer.query.filter_by(id=cust_id).first() if cust_id else None
        first_name = cust.first_name if cust and cust.first_name else ""

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #00C851;">
                <h1 style="color: #00C851; margin: 0; font-size: 28px;">CarsInStock</h1>
            </div>
            <div style="padding: 20px;">
                {msg_html}
                {img_html}
                <h2 style="color: #333; margin: 10px 0 5px;">{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''}</h2>
                <p style="color: #00C851; font-size: 24px; font-weight: bold; margin: 5px 0;">{price_str}</p>
                <p style="color: #666; font-size: 15px; margin: 5px 0;">{mileage_str}</p>
                <p style="color: #666; font-size: 15px; margin: 5px 0;">{vehicle.exterior_color or ''} {vehicle.transmission or ''}</p>
                <p style="color: #666; font-size: 15px; margin: 5px 0;">VIN: {vehicle.vin or 'N/A'}</p>
                <div style="text-align: center; padding: 20px 0;">
                    <a href="{storefront_url}"
                       style="background-color: #00C851; color: white; padding: 14px 32px;
                              text-decoration: none; border-radius: 6px; font-size: 16px;
                              font-weight: bold; display: inline-block;">
                        View on My Storefront
                    </a>
                </div>
                <p style="color: #999; font-size: 13px; text-align: center;">
                    Sent by {salesperson.display_name} via CarsInStock
                </p>
            </div>
            {footer_html}
        </div>
        """

        try:
            message = Mail(
                from_email=from_email,
                to_emails=email_addr,
                subject=subject,
                html_content=html_content
            )
            sg.send(message)
            sent += 1
        except Exception as e:
            print(f"Email send error to {email_addr}: {e}")
            errors += 1

    return sent, errors
