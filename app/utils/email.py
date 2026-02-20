import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To


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
        <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #6C2BD9;">
            <h1 style="color: #6C2BD9; margin: 0; font-size: 28px;">CarsInStock</h1>
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
                   style="background-color: #6C2BD9; color: white; padding: 14px 32px;
                          text-decoration: none; border-radius: 6px; font-size: 16px;
                          font-weight: bold; display: inline-block;">
                    Log In Now
                </a>
            </div>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">
                Every listing on CarsInStock expires after 7 days so customers always see
                what is actually on your lot. No ghost cars. No stale inventory.
            </p>
        </div>
        <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
            <p style="color: #999; font-size: 12px; margin: 0;">
                CarsInStock | 76 RT 37 East, Toms River, NJ 08753<br>
                Questions? Reply to sales@carsinstock.com
            </p>
        </div>
    </div>
    """
    return send_email(to_email, subject, html_content)


def send_vehicle_email(to_emails, vehicle, salesperson, personal_message="", customer_id=None):
    """Send vehicle listing to multiple email addresses"""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To
    import os

    storefront_url = f"https://carsinstock.com/{salesperson.profile_url_slug}"
    
    subject = f"Check out this {vehicle.year} {vehicle.make} {vehicle.model}!"
    
    img_html = ""
    if vehicle.image_url:
        img_html = f'<img src="{vehicle.image_url}" style="width:100%; max-width:560px; border-radius:10px; margin-bottom:15px;">'
    
    msg_html = ""
    if personal_message:
        msg_html = f'<p style="color:#555; font-size:16px; line-height:1.6; font-style:italic; border-left:3px solid #6C2BD9; padding-left:12px;">"{personal_message}"</p>'

    price_str = f"${vehicle.price:,.0f}" if vehicle.price else "Contact for price"
    mileage_str = f"{vehicle.mileage:,} miles" if vehicle.mileage else ""
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #6C2BD9;">
            <h1 style="color: #6C2BD9; margin: 0; font-size: 28px;">CarsInStock</h1>
        </div>
        <div style="padding: 20px;">
            {msg_html}
            {img_html}
            <h2 style="color: #333; margin: 10px 0 5px;">{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim or ''}</h2>
            <p style="color: #6C2BD9; font-size: 24px; font-weight: bold; margin: 5px 0;">{price_str}</p>
            <p style="color: #666; font-size: 15px; margin: 5px 0;">{mileage_str}</p>
            <p style="color: #666; font-size: 15px; margin: 5px 0;">{vehicle.exterior_color or ''} {vehicle.transmission or ''}</p>
            <p style="color: #666; font-size: 15px; margin: 5px 0;">VIN: {vehicle.vin or 'N/A'}</p>
            <div style="text-align: center; padding: 20px 0;">
                <a href="{storefront_url}"
                   style="background-color: #6C2BD9; color: white; padding: 14px 32px;
                          text-decoration: none; border-radius: 6px; font-size: 16px;
                          font-weight: bold; display: inline-block;">
                    View on My Storefront
                </a>
            </div>
            <p style="color: #999; font-size: 13px; text-align: center;">
                Sent by {salesperson.display_name} via CarsInStock
            </p>
        </div>
        <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
            <p style="color: #999; font-size: 12px; margin: 0;">
                CarsInStock | 76 RT 37 East, Toms River, NJ 08753
            </p>   """ + (f'<p style="color: #999; font-size: 11px; margin: 10px 0 0 0;"><a href="https://carsinstock.com/unsubscribe/{customer_id}" style="color: #999;">Unsubscribe</a></p>' if customer_id else '') + """
```
        </div>
    </div>
    """

    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    from_email = Email(
        email=os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@carsinstock.com'),
        name=salesperson.display_name + " via CarsInStock"
    )
    
    sent = 0
    errors = 0
    for email_addr in to_emails:
        email_addr = email_addr.strip()
        if not email_addr:
            continue
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
