with open('app/auth/routes.py', 'r') as f:
    content = f.read()

old = 'flash("Email verified successfully! You can now log in.", "success")'
new = 'flash("Email verified! Your 14-day free trial is now active. Log in to get started.", "success")'

content = content.replace(old, new)

with open('app/auth/routes.py', 'w') as f:
    f.write(content)

print('Done!')

