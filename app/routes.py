from flask import Blueprint, render_template

main = Blueprint('main', __name__)

@main.route('/')
def home():
    return render_template('index.html')

@main.route('/salespeople')
def salespeople():
    return render_template('salespeople.html')

@main.route('/customers')
def customers():
    return render_template('customers.html')

@main.route('/search-cars')
def search_cars():
    return render_template('search_cars.html')


@main.route('/<slug>')
def public_profile(slug):
    from app.models.salesperson import Salesperson
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp:
        return render_template('index.html')
    return render_template('salesperson/public_profile.html', sp=sp)
