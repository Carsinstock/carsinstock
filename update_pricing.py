# 1. Registration page - trial banner
with open('app/templates/auth/register.html', 'r') as f:
    content = f.read()
content = content.replace(
    'After your trial, it is just <strong>$2 per vehicle</strong> you list. Cancel anytime.',
    'After your trial, just <strong>$20/month + $2 per vehicle</strong> listed. Cancel anytime.'
)
with open('app/templates/auth/register.html', 'w') as f:
    f.write(content)
print('1. Registration page updated')

# 2. Dashboard - active trial banner
with open('app/templates/salesperson/dashboard.html', 'r') as f:
    content = f.read()
content = content.replace(
    'After your trial, listings are $2 per vehicle.',
    'After your trial, $20/month + $2 per vehicle listed.'
)
content = content.replace(
    'Add a payment method to keep your listings active. Just $2 per vehicle.',
    'Add a payment method to keep your listings active. $20/month + $2 per vehicle listed.'
)
with open('app/templates/salesperson/dashboard.html', 'w') as f:
    f.write(content)
print('2. Dashboard updated')

print('Done! All pricing updated.')

