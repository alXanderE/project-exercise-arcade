import os

from flask import Flask, render_template, send_from_directory

from .extensions import db
from .mongo_auth import ensure_mongo_auth_indexes
from .mongo_game import ensure_mongo_game_indexes
from .routes import api
from .schema import ensure_sqlite_schema

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False


def default_database_url():
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured

    if os.getenv("VERCEL"):
        return "sqlite:////tmp/exercise_arcade.db"

    return "sqlite:///exercise_arcade.db"


def create_app():
    load_dotenv()

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["HOST"] = os.getenv("HOST", "0.0.0.0")
    app.config["PORT"] = int(os.getenv("PORT", "5000"))
    app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.config["SQLALCHEMY_DATABASE_URI"] = default_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MONGODB_URI"] = os.getenv("MONGODB_URI", "").strip()
    app.config["MONGODB_DB"] = os.getenv("MONGODB_DB", "exercise_arcade")
    app.config["MONGODB_USERS_COLLECTION"] = os.getenv(
        "MONGODB_USERS_COLLECTION",
        "users",
    )
    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    app.config["SESSION_COOKIE_NAME"] = os.getenv(
        "SESSION_COOKIE_NAME",
        "exercise_arcade_session",
    )
    app.config["SESSION_DAYS"] = int(os.getenv("SESSION_DAYS", "30"))
    app.config["PRIZE_WHEEL_SPIN_COST"] = int(os.getenv("PRIZE_WHEEL_SPIN_COST", "20"))
    app.config["FITNESS_STEPS_PER_POINT"] = int(
        os.getenv("FITNESS_STEPS_PER_POINT", "1000")
    )
    app.config["FITNESS_DAILY_STEP_CAP"] = int(
        os.getenv("FITNESS_DAILY_STEP_CAP", "10000")
    )
    app.config["FITNESS_DAILY_GOAL_STEPS"] = int(
        os.getenv("FITNESS_DAILY_GOAL_STEPS", "10000")
    )
    app.config["FITNESS_DAILY_GOAL_BONUS"] = int(
        os.getenv("FITNESS_DAILY_GOAL_BONUS", "5")
    )

    db.init_app(app)

    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()
        ensure_sqlite_schema()
        ensure_mongo_auth_indexes()
        ensure_mongo_game_indexes()

    app.register_blueprint(api, url_prefix="/api")

    @app.get("/")
    @app.get("/fitness")
    def root():
        return render_template("index.html")

    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.get("/assets/prize-wheel.png")
    def prize_wheel_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "wheel_Of_fitness.png",
        )

    @app.get("/assets/wheel-criteria.png")
    def wheel_criteria_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "wheel_criteria.png",
        )

    @app.get("/assets/cards.png")
    @app.get("/assets/card.png")
    def card_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "cards.png",
        )

    @app.get("/assets/dice.png")
    def dice_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "dice.png",
        )

    return app
