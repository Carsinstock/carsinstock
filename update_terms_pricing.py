with open('app/templates/terms.html', 'r') as f:
    content = f.read()

content = content.replace(
    'After the trial period, the Platform charges $2.00 per vehicle listed.',
    'After the trial period, the Platform charges a $20.00 monthly subscription fee plus $2.00 per vehicle listed.'
)

content = content.replace(
    'After your 14-day trial ends, each vehicle posted is billed at $2.00. On or around day 11 of your billing cycle, you will receive an invoice via email for any vehicles posted during that cycle.',
    'After your 14-day trial ends, you will be charged a $20.00 monthly platform fee plus $2.00 per vehicle posted. On or around day 11 of your billing cycle, you will receive an invoice via email for your platform fee and any vehicles posted during that cycle.'
)

with open('app/templates/terms.html', 'w') as f:
    f.write(content)

print('Done!')

