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
