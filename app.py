import hmac
import os
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, jsonify, request, send_file, session

import db


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            abort(401)
        return f(*args, **kwargs)

    return wrapper


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ["SECRET_KEY"]
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app_password = os.environ["APP_PASSWORD"]

    db.init_db()

    @app.get("/api/ping")
    def ping():
        return jsonify({"ok": True})

    @app.post("/api/login")
    def login():
        body = request.get_json(silent=True) or {}
        if hmac.compare_digest(str(body.get("password", "")), app_password):
            session["auth"] = True
            session.permanent = True
            return jsonify({"ok": True})
        return jsonify({"ok": False}), 401

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    return app


app = create_app() if os.environ.get("SECRET_KEY") else None
