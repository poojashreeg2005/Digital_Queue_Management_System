
from functools import wraps

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, abort
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User

auth_bp = Blueprint("auth", __name__)


def role_required(required_role):
    """Restrict a route to a specific user role."""

    def decorator(view_function):
        @wraps(view_function)
        @login_required
        def wrapped_view(*args, **kwargs):
            if current_user.role != required_role:
                abort(403)

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        logout_user()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("auth.register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.register"))

        student = User(
            name=name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role="student"
        )

        db.session.add(student)
        db.session.commit()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.student_login"))

    return render_template("register.html")


@auth_bp.route("/student/login", methods=["GET", "POST"])
def student_login():

    # If an admin is logged in, log out that session
    # so a student can access the student login page.
    if current_user.is_authenticated:
        if current_user.role == "student":
            return redirect(url_for("student.dashboard"))

        logout_user()

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if (
            user
            and user.role == "student"
            and check_password_hash(user.password_hash, password)
        ):
            login_user(user)
            flash("Welcome to QueueFlow!", "success")
            return redirect(url_for("student.dashboard"))

        flash("Invalid student email or password.", "error")

    return render_template("student_login.html")


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin.dashboard"))

        logout_user()

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if (
            user
            and user.role == "admin"
            and check_password_hash(user.password_hash, password)
        ):
            login_user(user)
            flash("Administrator login successful.", "success")
            return redirect(url_for("admin.dashboard"))

        flash("Invalid administrator email or password.", "error")

    return render_template("admin_login.html")


@auth_bp.route("/logout")
@login_required
def logout():

    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("home"))
