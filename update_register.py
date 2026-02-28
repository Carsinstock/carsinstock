import shutil
shutil.copy('app/templates/auth/register.html', 'app/templates/auth/register.html.bak')

old = '<p class="auth-subtitle">Join CarsInStock — Real Salespeople. Real Inventory.</p>'

new = '''<p class="auth-subtitle">Join CarsInStock — Real Salespeople. Real Inventory.</p>
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin: 0 0 20px 0; text-align: center;">
        <p style="margin: 0; color: #166534; font-size: 15px; font-weight: 600;">Start your <strong>14-day free trial</strong> — no credit card required.</p>
        <p style="margin: 4px 0 0 0; color: #4b5563; font-size: 13px;">After your trial, it is just <strong>$2 per vehicle</strong> you list. Cancel anytime.</p>
    </div>'''

with open('app/templates/auth/register.html', 'r') as f:
    content = f.read()

content = content.replace(old, new)

old2 = '<p class="auth-footer">'
new2 = '<p style="text-align:center;font-size:12px;color:#9ca3af;margin-top:8px;">Your 14-day free trial starts immediately. No payment required.</p>\n    <p class="auth-footer">'

content = content.replace(old2, new2)

with open('app/templates/auth/register.html', 'w') as f:
    f.write(content)

print('Done!')

