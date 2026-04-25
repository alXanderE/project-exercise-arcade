import os

from flask import Flask, jsonify

from .extensions import db
from .routes import api

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False


def create_app():
    load_dotenv()

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["HOST"] = os.getenv("HOST", "0.0.0.0")
    app.config["PORT"] = int(os.getenv("PORT", "5000"))
    app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///exercise_arcade.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_NAME"] = os.getenv("SESSION_COOKIE_NAME", "exercise_arcade_session")
    app.config["SESSION_DAYS"] = int(os.getenv("SESSION_DAYS", "30"))

    db.init_app(app)

    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()

    app.register_blueprint(api, url_prefix="/api")

    @app.get("/")
    def root():
        return jsonify(
            {
                "name": "Exercise Arcade API",
                "status": "ok",
                "docs": {
                    "health": "/api/health",
                    "signup": "/api/auth/signup",
                    "login": "/api/auth/login",
                    "habits": "/api/habits",
                    "dashboard": "/api/dashboard",
                },
            }
        )

    return app
