# 1. Homepage - hero section
with open('app/templates/index.html', 'r') as f:
    content = f.read()
content = content.replace(
    '14-day free trial. $2 per car afterward.',
    '14-day free trial. $20/month + $2 per vehicle after that.'
)
content = content.replace(
    '14-day free trial. $2 per vehicle after that.',
    '14-day free trial. $20/month + $2 per vehicle after that.'
)
with open('app/templates/index.html', 'w') as f:
    f.write(content)
print('1. Homepage updated')

# 2. Public profile page
with open('app/templates/salesperson/public_profile.html', 'r') as f:
    content = f.read()
content = content.replace(
    '14-day free trial. No monthly fees.<br>Just $2 per car you post. That\'s it.',
    '14-day free trial. $20/month + $2 per vehicle listed.<br>Cancel anytime.'
)
with open('app/templates/salesperson/public_profile.html', 'w') as f:
    f.write(content)
print('2. Public profile updated')

print('Done!')

