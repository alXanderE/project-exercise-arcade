import base64
import json
import os
import struct

from flask import Flask, Response, abort, render_template, send_from_directory

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


GYM_EQUIPMENT_FILES = {
    "bench": "bench.pixil",
    "cablemachine": "cablemachine.pixil",
    "dumbbells": "dumbbells.pixil",
    "machine": "machine.pixil",
    "treadmill": "treadmill.pixil",
}


def pixil_png_response(path):
    with open(path, "r", encoding="utf-8") as pixil_file:
        document = json.load(pixil_file)

    data_uris = [document.get("preview", "")]
    for frame in document.get("frames") or []:
        data_uris.append(frame.get("preview", ""))
        for layer in frame.get("layers") or []:
            data_uris.append(layer.get("src", ""))

    for data_uri in data_uris:
        if "base64," not in data_uri:
            continue
        encoded = data_uri.split("base64,", 1)[1]
        try:
            image_bytes = base64.b64decode(encoded)
        except Exception:
            continue
        if not image_bytes.startswith(b"\x89PNG") or len(image_bytes) < 24:
            continue
        width, height = struct.unpack(">II", image_bytes[16:24])
        if 1 <= width <= 2048 and 1 <= height <= 2048:
            return Response(image_bytes, mimetype="image/png")

    abort(404)


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
        os.getenv("FITNESS_STEPS_PER_POINT", "250")
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
    app.config["FITNESS_WORKOUT_MINUTE_POINTS"] = int(
        os.getenv("FITNESS_WORKOUT_MINUTE_POINTS", "2")
    )
    app.config["FITNESS_ACTIVE_CALORIES_PER_POINT"] = int(
        os.getenv("FITNESS_ACTIVE_CALORIES_PER_POINT", "25")
    )
    app.config["FITNESS_DISTANCE_MILES_PER_POINT"] = float(
        os.getenv("FITNESS_DISTANCE_MILES_PER_POINT", "1")
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

    @app.get("/assets/wheel-spin.mp3")
    def wheel_spin_audio_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "wheep_spin.mp3",
        )

    @app.get("/assets/winsound.m4a")
    def win_sound_audio_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "winsound.m4a",
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

    @app.get("/assets/gym-background.png")
    def gym_background_asset():
        return send_from_directory(
            os.path.abspath(os.path.join(app.root_path, "..")),
            "gym_background.png",
        )

    @app.get("/assets/gym-equipment/<equipment_id>.png")
    def gym_equipment_asset(equipment_id):
        filename = GYM_EQUIPMENT_FILES.get(equipment_id)
        if not filename:
            abort(404)

        return pixil_png_response(
            os.path.abspath(
                os.path.join(app.root_path, "..", "gym-equipment", filename)
            )
        )

    return app
