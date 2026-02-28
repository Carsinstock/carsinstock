with open('app/salesperson/routes.py', 'r') as f:
    content = f.read()

content = content.replace(
    '- 2 dollars per car, 14-day free trial, no monthly fees',
    '- 14-day free trial, then $20/month plus $2 per vehicle listed - way cheaper than any lead service'
)

with open('app/salesperson/routes.py', 'w') as f:
    f.write(content)

print('Done!')

