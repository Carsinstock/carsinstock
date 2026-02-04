from flask import render_template
from app.salesperson import salesperson

@salesperson.route('/profile/setup')
def setup():
    return render_template('salesperson/setup.html')

@salesperson.route('/salesperson/<slug>')
def profile(slug):
    return render_template('salesperson/profile.html', slug=slug)
