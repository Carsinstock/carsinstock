import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from app import db
from app.models import User


@click.command("create-admin")
@click.option("--email", prompt=True)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
)
@with_appcontext
def create_admin(email, password):
    existing = User.query.filter_by(email=email).first()
    if existing:
        click.echo("❌ User already exists")
        return

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
    )

    db.session.add(user)
    db.session.commit()

    click.echo("✅ Admin user created successfully")


def register_commands(app):
    """Register custom Flask CLI commands."""
    app.cli.add_command(create_admin)
