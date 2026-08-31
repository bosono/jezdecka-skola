import hmac
import os
from datetime import date, timedelta
from functools import wraps

from flask import Flask, abort, jsonify, request, send_file, session

import db
import supersaas


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

    @app.get("/api/state")
    @login_required
    def get_state():
        return jsonify(db.get_state())

    @app.put("/api/state")
    @login_required
    def put_state():
        body = request.get_json(silent=True) or {}
        data = body.get("data")
        version = body.get("version")
        if not isinstance(data, dict) or not isinstance(version, int):
            abort(400)
        new_version = db.put_state(data, version)
        if new_version is None:
            return jsonify({**db.get_state(), "conflict": True}), 409
        return jsonify({"version": new_version})

    @app.get("/")
    def index():
        return send_file("index.html")

    @app.get("/api/supersaas/status")
    @login_required
    def supersaas_status():
        return jsonify({
            "configured": supersaas.is_configured(),
            "schedule_id": os.environ.get("SUPERSAAS_SCHEDULE_ID"),
            "slot_minutes": supersaas.slot_minutes_from_env(),
        })

    @app.post("/api/supersaas/push")
    @login_required
    def supersaas_push():
        body = request.get_json(silent=True) or {}
        try:
            week_start = date.fromisoformat(str(body.get("week_start", "")))
        except ValueError:
            abort(400)
        days = body.get("days")
        dry_run = bool(body.get("dry_run"))
        state = db.get_state().get("data") or {"horses": [], "riders": [], "slots": [], "assignments": []}
        minutes = supersaas.slot_minutes_from_env()
        bookings = supersaas.week_bookings(state, week_start, days=days, slot_minutes=minutes)
        if dry_run or not supersaas.is_configured():
            return jsonify({"configured": supersaas.is_configured(), "dry_run": True,
                            "count": len(bookings), "bookings": bookings})
        from_dt, to_dt = supersaas.week_range(week_start, days)
        result = supersaas.client_from_env().replace(bookings, from_dt, to_dt)
        return jsonify({"configured": True, "dry_run": False, "count": len(bookings), **result})

    return app


app = create_app() if os.environ.get("SECRET_KEY") else None
