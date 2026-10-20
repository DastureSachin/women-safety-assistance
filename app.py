import os
import re
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_ALLOWED_RE = re.compile(r"^[+0-9 ()-]+$")
LOCATION_RE = re.compile(
    r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.environ.get(
            "DATABASE", str(Path(app.root_path) / "women_safety.db")
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        WTF_CSRF_TIME_LIMIT=3600,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "Set the SECRET_KEY environment variable before starting the application."
        )

    CSRFProtect(app)

    def connect_database():
        database_path = Path(app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_database():
        connection = connect_database()
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        relationship TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS incidents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        location TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                    """
                )

                # Upgrade the original plain-text password rows in place so
                # existing accounts remain usable without retaining plaintext.
                users = connection.execute(
                    "SELECT id, password FROM users"
                ).fetchall()
                for user in users:
                    password = user["password"]
                    if not password.startswith(("scrypt:", "pbkdf2:", "argon2:")):
                        connection.execute(
                            "UPDATE users SET password = ? WHERE id = ?",
                            (generate_password_hash(password), user["id"]),
                        )
        finally:
            connection.close()

    @app.before_request
    def load_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            database = get_database()
            g.user = database.execute(
                "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if g.user is None:
                session.clear()

    def get_database():
        if "database" not in g:
            g.database = connect_database()
        return g.database

    @app.teardown_appcontext
    def close_database(_error=None):
        database = g.pop("database", None)
        if database is not None:
            database.close()

    def login_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    @app.errorhandler(CSRFError)
    def handle_csrf_error(_error):
        return (
            render_template(
                "error.html",
                title="Form expired",
                message="This form could not be verified. Please reload the page and try again.",
            ),
            400,
        )

    @app.route("/")
    @login_required
    def dashboard():
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not name or len(name) > 100:
                flash("Enter a name no longer than 100 characters.", "error")
            elif len(email) > 254 or not EMAIL_RE.fullmatch(email):
                flash("Enter a valid email address.", "error")
            elif len(password) < 8 or len(password) > 256:
                flash("Your password must be between 8 and 256 characters.", "error")
            else:
                try:
                    database = get_database()
                    database.execute(
                        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                        (name, email, generate_password_hash(password)),
                    )
                    database.commit()
                except sqlite3.IntegrityError:
                    flash("An account with that email already exists.", "error")
                else:
                    flash("Account created. Please log in.", "success")
                    return redirect(url_for("login"))
            return render_template("register.html", name=name, email=email)

        return render_template("register.html", name="", email="")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = get_database().execute(
                "SELECT id, name, password FROM users WHERE email = ?", (email,)
            ).fetchone()

            if user is None or not check_password_hash(user["password"], password):
                flash("Invalid email or password.", "error")
                return render_template("login.html", email=email)

            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html", email="")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/contacts", methods=["GET", "POST"])
    @login_required
    def contacts():
        database = get_database()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            relationship = request.form.get("relationship", "").strip()
            digits = re.sub(r"\D", "", phone)
            if not name or len(name) > 100:
                flash("Enter a contact name no longer than 100 characters.", "error")
            elif (
                not PHONE_ALLOWED_RE.fullmatch(phone)
                or not 7 <= len(digits) <= 15
            ):
                flash("Enter a valid phone number containing 7 to 15 digits.", "error")
            elif len(relationship) > 60:
                flash("Relationship must be 60 characters or fewer.", "error")
            else:
                database.execute(
                    """
                    INSERT INTO contacts (user_id, name, phone, relationship)
                    VALUES (?, ?, ?, ?)
                    """,
                    (g.user["id"], name, phone, relationship),
                )
                database.commit()
                flash("Emergency contact added.", "success")
                return redirect(url_for("contacts"))

        entries = database.execute(
            """
            SELECT id, name, phone, relationship FROM contacts
            WHERE user_id = ? ORDER BY name COLLATE NOCASE, id
            """,
            (g.user["id"],),
        ).fetchall()
        return render_template("contacts.html", contacts=entries)

    @app.post("/contacts/<int:contact_id>/delete")
    @login_required
    def delete_contact(contact_id):
        database = get_database()
        result = database.execute(
            "DELETE FROM contacts WHERE id = ? AND user_id = ?",
            (contact_id, g.user["id"]),
        )
        database.commit()
        if result.rowcount == 0:
            abort(404)
        flash("Emergency contact deleted.", "success")
        return redirect(url_for("contacts"))

    @app.route("/reports", methods=["GET", "POST"])
    @login_required
    def reports():
        database = get_database()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()
            if not title or len(title) > 120:
                flash("Enter a report title no longer than 120 characters.", "error")
            elif not description or len(description) > 2000:
                flash("Enter a description of up to 2,000 characters.", "error")
            elif len(location) > 80 or (
                location and not valid_location(location)
            ):
                flash("Enter a valid latitude, longitude pair or leave location blank.", "error")
            else:
                database.execute(
                    """
                    INSERT INTO incidents (user_id, title, description, location)
                    VALUES (?, ?, ?, ?)
                    """,
                    (g.user["id"], title, description, location),
                )
                database.commit()
                flash("Incident report saved.", "success")
                return redirect(url_for("reports"))

        entries = database.execute(
            """
            SELECT id, title, description, location, created_at FROM incidents
            WHERE user_id = ? ORDER BY created_at DESC, id DESC
            """,
            (g.user["id"],),
        ).fetchall()
        return render_template("reports.html", reports=entries)

    @app.route("/safety-tips")
    @login_required
    def safety_tips():
        return render_template("tips.html")

    def valid_location(location):
        match = LOCATION_RE.fullmatch(location)
        if not match:
            return False
        latitude, longitude = map(float, match.groups())
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    init_database()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=False)
