"""
Kudos feature for the internal employee portal.

What this file does:
  - Lets a signed-in user pick a colleague, write a short message and send kudos.
  - Shows a public feed of recent kudos on the dashboard.
  - Lets an administrator hide, restore or delete inappropriate kudos.

Built from SPECIFICATION.md. Run with:  python app.py
"""
import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

MAX_MESSAGE_LENGTH = 500   # longest kudos message allowed
PAGE_SIZE = 20             # kudos shown per page of the feed

# The database tables (see "Database Schema" in SPECIFICATION.md)
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL REFERENCES users(id),
    recipient_id INTEGER NOT NULL REFERENCES users(id),
    message TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 500),
    created_at TEXT NOT NULL,
    is_visible INTEGER NOT NULL DEFAULT 1,      -- moderation: 0 means hidden from the feed
    moderated_by INTEGER REFERENCES users(id),  -- admin who hid or restored it
    moderated_at TEXT,
    reason_for_moderation TEXT,
    CHECK (sender_id != recipient_id)
);
CREATE INDEX IF NOT EXISTS idx_kudos_feed ON kudos (is_visible, created_at DESC);
"""

# Sample people so the app can be tried straight away
SEED_USERS = [
    ("Aroha Ngata", "aroha@example.com", 1),
    ("Ben Carter", "ben@example.com", 0),
    ("Mei Lin", "mei@example.com", 0),
    ("Sam Patel", "sam@example.com", 0),
]


def create_app(database_path="kudos.db"):
    app = Flask(__name__)
    # The secret key signs the login cookie. Set SECRET_KEY in production.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["DATABASE"] = database_path

    # ---------- database helpers ----------
    def db():
        """Open one database connection per request and reuse it."""
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    def init_db():
        """Create the tables and add the sample users the first time."""
        db().executescript(SCHEMA)
        if db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db().executemany("INSERT INTO users (name, email, is_admin) VALUES (?, ?, ?)", SEED_USERS)
        db().commit()

    with app.app_context():
        init_db()

    # ---------- who is signed in ----------
    def current_user():
        user_id = session.get("user_id")
        if user_id is None:
            return None
        return db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def login_required(view):
        """Reject the request with 401 if nobody is signed in."""
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                return jsonify(error="Please sign in."), 401
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        """Reject the request with 403 unless the signed-in user is an administrator."""
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="Please sign in."), 401
            if not user["is_admin"]:
                return jsonify(error="Administrators only."), 403
            return view(*args, **kwargs)
        return wrapped

    def kudos_to_dict(row, include_moderation=False):
        """Turn a database row into the JSON shape the frontend expects."""
        item = {
            "id": row["id"],
            "sender": row["sender_name"],
            "recipient": row["recipient_name"],
            "message": row["message"],
            "created_at": row["created_at"],
        }
        if include_moderation:
            item.update(is_visible=bool(row["is_visible"]),
                        moderated_at=row["moderated_at"],
                        reason_for_moderation=row["reason_for_moderation"])
        return item

    FEED_QUERY = """
        SELECT k.*, s.name AS sender_name, r.name AS recipient_name
        FROM kudos k
        JOIN users s ON s.id = k.sender_id
        JOIN users r ON r.id = k.recipient_id
    """

    # ---------- pages ----------
    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", user=current_user(),
                               users=db().execute("SELECT id, name FROM users ORDER BY name").fetchall(),
                               max_length=MAX_MESSAGE_LENGTH)

    @app.post("/login")
    def login():
        """Demo sign-in: pick a user. In the real portal this is replaced by company SSO."""
        user = db().execute("SELECT id FROM users WHERE id = ?", (request.form.get("user_id"),)).fetchone()
        if user is None:
            abort(400)
        session["user_id"] = user["id"]
        return redirect(url_for("dashboard"))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("dashboard"))

    # ---------- API ----------
    @app.get("/api/users")
    @login_required
    def list_users():
        """Colleagues the signed-in user can send kudos to (everyone except themselves)."""
        rows = db().execute("SELECT id, name FROM users WHERE id != ? ORDER BY name",
                            (session["user_id"],)).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.get("/api/kudos")
    def feed():
        """Public feed: visible kudos only, newest first, one page at a time."""
        try:
            page = max(int(request.args.get("page", 1)), 1)
        except ValueError:
            return jsonify(error="page must be a number."), 400
        rows = db().execute(
            FEED_QUERY + " WHERE k.is_visible = 1 ORDER BY k.created_at DESC, k.id DESC LIMIT ? OFFSET ?",
            (PAGE_SIZE + 1, (page - 1) * PAGE_SIZE)).fetchall()
        # We ask for one extra row to know whether there is a next page
        return jsonify(items=[kudos_to_dict(r) for r in rows[:PAGE_SIZE]],
                       page=page, has_more=len(rows) > PAGE_SIZE)

    @app.post("/api/kudos")
    @login_required
    def create_kudos():
        """Validate the input and store a new kudos."""
        data = request.get_json(silent=True) or {}
        message = str(data.get("message", "")).strip()
        recipient_id = data.get("recipient_id")

        if not message:
            return jsonify(error="Please write a message."), 400
        if len(message) > MAX_MESSAGE_LENGTH:
            return jsonify(error=f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer."), 400
        if not isinstance(recipient_id, int):
            return jsonify(error="Please choose a colleague."), 400
        if recipient_id == session["user_id"]:
            return jsonify(error="You cannot give kudos to yourself."), 400
        if db().execute("SELECT 1 FROM users WHERE id = ?", (recipient_id,)).fetchone() is None:
            return jsonify(error="That colleague was not found."), 404

        # Values are passed as parameters, never built into the SQL text (prevents SQL injection)
        cursor = db().execute(
            "INSERT INTO kudos (sender_id, recipient_id, message, created_at) VALUES (?, ?, ?, ?)",
            (session["user_id"], recipient_id, message, datetime.now(timezone.utc).isoformat()))
        db().commit()
        app.logger.info("Kudos %s created by user %s", cursor.lastrowid, session["user_id"])
        return jsonify(id=cursor.lastrowid), 201

    @app.get("/api/admin/kudos")
    @admin_required
    def admin_list():
        """Administrators see every kudos, including hidden ones."""
        rows = db().execute(FEED_QUERY + " ORDER BY k.created_at DESC, k.id DESC LIMIT 200").fetchall()
        return jsonify([kudos_to_dict(r, include_moderation=True) for r in rows])

    @app.patch("/api/admin/kudos/<int:kudos_id>")
    @admin_required
    def moderate(kudos_id):
        """Hide or restore a kudos and record who did it, when and why."""
        data = request.get_json(silent=True) or {}
        if not isinstance(data.get("is_visible"), bool):
            return jsonify(error="is_visible must be true or false."), 400
        reason = str(data.get("reason", "")).strip()[:200] or None
        result = db().execute(
            "UPDATE kudos SET is_visible = ?, moderated_by = ?, moderated_at = ?, reason_for_moderation = ? WHERE id = ?",
            (int(data["is_visible"]), session["user_id"], datetime.now(timezone.utc).isoformat(), reason, kudos_id))
        db().commit()
        if result.rowcount == 0:
            return jsonify(error="Kudos not found."), 404
        app.logger.info("Kudos %s visibility set to %s by admin %s", kudos_id, data["is_visible"], session["user_id"])
        return jsonify(id=kudos_id, is_visible=data["is_visible"])

    @app.delete("/api/admin/kudos/<int:kudos_id>")
    @admin_required
    def delete(kudos_id):
        """Permanently remove a kudos."""
        result = db().execute("DELETE FROM kudos WHERE id = ?", (kudos_id,))
        db().commit()
        if result.rowcount == 0:
            return jsonify(error="Kudos not found."), 404
        app.logger.info("Kudos %s deleted by admin %s", kudos_id, session["user_id"])
        return "", 204

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
