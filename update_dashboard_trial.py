# 1. Update the route to pass trial info
with open('app/salesperson/routes.py', 'r') as f:
    content = f.read()

old_render = '''return render_template("salesperson/dashboard.html", sp=sp,
            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,
            leads=leads, chats=chats, customers=customers, blast_count=blast_count)'''

new_render = '''# Trial calculation
        from app.models.user import User
        user = User.query.get(session["user_id"])
        from datetime import timedelta
        trial_end = user.created_at + timedelta(days=14)
        now = datetime.utcnow()
        trial_days_left = max(0, (trial_end - now).days)
        trial_active = trial_days_left > 0

        return render_template("salesperson/dashboard.html", sp=sp,
            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,
            leads=leads, chats=chats, customers=customers, blast_count=blast_count,
            trial_days_left=trial_days_left, trial_active=trial_active)'''

content = content.replace(old_render, new_render)

with open('app/salesperson/routes.py', 'w') as f:
    f.write(content)

# 2. Update the template to show trial banner
with open('app/templates/salesperson/dashboard.html', 'r') as f:
    content = f.read()

old_h1 = '<h1>Dashboard</h1>'

new_h1 = '''<h1>Dashboard</h1>
    {% if trial_active %}
    <div style="background:linear-gradient(90deg,#1E293B 0%,#334155 100%);color:white;border-radius:10px;padding:16px 20px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
            <p style="margin:0;font-size:15px;font-weight:600;">Free Trial — <span style="color:#00C851;">{{ trial_days_left }} day{{ 's' if trial_days_left != 1 }} remaining</span></p>
            <p style="margin:4px 0 0 0;font-size:13px;color:#94a3b8;">After your trial, listings are $2 per vehicle.</p>
        </div>
    </div>
    {% else %}
    <div style="background-color:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:16px 20px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
            <p style="margin:0;font-size:15px;font-weight:600;color:#991b1b;">Your free trial has ended</p>
            <p style="margin:4px 0 0 0;font-size:13px;color:#6b7280;">Add a payment method to keep your listings active. Just $2 per vehicle.</p>
        </div>
    </div>
    {% endif %}'''

content = content.replace(old_h1, new_h1)

with open('app/templates/salesperson/dashboard.html', 'w') as f:
    f.write(content)

print('Done!')

