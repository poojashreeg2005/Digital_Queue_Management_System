
import os

from flask import Flask, render_template
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from config import Config
from models import db, User

from routes.auth import auth_bp
from routes.student import student_bp
from routes.admin import admin_bp

app = Flask(__name__)

# Load application configuration
app.config.from_object(Config)

# Connect SQLAlchemy
db.init_app(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.student_login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Register authentication routes
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(admin_bp)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return {
        "status": "running",
        "application": "QueueFlow AI"
    }


@app.errorhandler(403)
def forbidden(error):
    return "Access denied: You do not have permission to view this page.", 403


@app.errorhandler(404)
def not_found(error):
    return "Page not found.", 404


def create_admin():
    """Create the first admin account if it does not exist."""

    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env"
        )

    existing_admin = User.query.filter_by(email=email.lower()).first()

    if existing_admin:
        if existing_admin.role != "admin":
            raise RuntimeError(
                "Configured admin email already belongs to a non-admin user."
            )
        print("Admin account already exists.")
        return

    admin = User(
        name="QueueFlow Administrator",
        email=email.lower(),
        password_hash=generate_password_hash(password),
        role="admin"
    )

    db.session.add(admin)
    db.session.commit()

    print("Initial admin account created.")


if __name__ == "__main__":

    with app.app_context():
        db.create_all()
        create_admin()

    print("QueueFlow AI backend is starting...")

    app.run(debug=True)
