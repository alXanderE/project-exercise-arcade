from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from .auth import build_session, hash_password, verify_password
from .extensions import db
from .models import Habit, HabitLog, User


api = Blueprint("api", __name__)


def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "points": user.points,
        "level": user.level,
    }


def serialize_habit(habit):
    return {
        "id": habit.id,
        "name": habit.name,
        "description": habit.description,
        "difficulty": habit.difficulty,
        "frequency": habit.frequency,
        "targetPerWeek": habit.target_per_week,
        "pointsReward": habit.points_reward,
        "streakCount": habit.streak_count,
        "isActive": habit.is_active,
        "lastCompletedOn": habit.last_completed_on.isoformat() if habit.last_completed_on else None,
    }


def current_utc():
    return datetime.now(timezone.utc)


def get_current_user():
    session_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if not session_token:
        return None

    return User.query.filter(
        User.session_token == session_token,
        User.session_expires_at.isnot(None),
        User.session_expires_at > current_utc(),
    ).first()


def login_user(response, user):
    session_token, expires_at = build_session(current_app.config["SESSION_DAYS"])
    user.session_token = session_token
    user.session_expires_at = expires_at
    db.session.commit()
    max_age = current_app.config["SESSION_DAYS"] * 24 * 60 * 60
    response.set_cookie(
        current_app.config["SESSION_COOKIE_NAME"],
        session_token,
        httponly=True,
        samesite="Lax",
        max_age=max_age,
    )


def logout_user(response, user):
    if user:
        user.session_token = None
        user.session_expires_at = None
        db.session.commit()

    response.set_cookie(
        current_app.config["SESSION_COOKIE_NAME"],
        "",
        httponly=True,
        samesite="Lax",
        max_age=0,
    )


def require_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"message": "Authentication required."}), 401

        return handler(user, *args, **kwargs)

    return wrapped


def calculate_level(points):
    return max(1, (points // 100) + 1)


def normalize_date(value):
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def update_habit_streak(habit, completed_on):
    if habit.last_completed_on is None:
        habit.streak_count = 1
    elif completed_on == habit.last_completed_on:
        return
    elif completed_on - habit.last_completed_on == timedelta(days=1):
        habit.streak_count += 1
    else:
        habit.streak_count = 1

    habit.last_completed_on = completed_on


@api.get("/health")
def health():
    return jsonify({"ok": True, "service": "exercise-arcade"})


@api.post("/auth/signup")
def signup():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    display_name = (payload.get("displayName") or "").strip()
    password = payload.get("password") or ""

    if not email or not display_name or len(password) < 6:
        return (
            jsonify(
                {
                    "message": "Email, display name, and a password with at least 6 characters are required."
                }
            ),
            400,
        )

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"message": "An account with that email already exists."}), 400

    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.session.add(user)
    db.session.commit()

    response = jsonify({"message": "Account created.", "user": serialize_user(user)})
    login_user(response, user)
    return response, 201


@api.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"message": "Invalid email or password."}), 401

    response = jsonify({"message": "Logged in.", "user": serialize_user(user)})
    login_user(response, user)
    return response


@api.post("/auth/logout")
@require_auth
def logout(user):
    response = jsonify({"message": "Logged out."})
    logout_user(response, user)
    return response


@api.get("/auth/session")
@require_auth
def session(user):
    return jsonify({"user": serialize_user(user)})


@api.get("/habits")
@require_auth
def list_habits(user):
    habits = Habit.query.filter_by(user_id=user.id).order_by(Habit.created_at.desc()).all()
    return jsonify({"habits": [serialize_habit(habit) for habit in habits]})


@api.post("/habits")
@require_auth
def create_habit(user):
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()

    if not name:
        return jsonify({"message": "Habit name is required."}), 400

    difficulty = (payload.get("difficulty") or "medium").strip().lower()
    frequency = (payload.get("frequency") or "daily").strip().lower()
    target_per_week = int(payload.get("targetPerWeek") or 3)
    points_reward = int(payload.get("pointsReward") or 10)

    habit = Habit(
        user_id=user.id,
        name=name,
        description=(payload.get("description") or "").strip() or None,
        difficulty=difficulty,
        frequency=frequency,
        target_per_week=target_per_week,
        points_reward=points_reward,
    )
    db.session.add(habit)
    db.session.commit()

    return jsonify({"message": "Habit created.", "habit": serialize_habit(habit)}), 201


@api.post("/habits/<int:habit_id>/log")
@require_auth
def log_habit(user, habit_id):
    habit = Habit.query.filter_by(id=habit_id, user_id=user.id, is_active=True).first()
    if not habit:
        return jsonify({"message": "Habit not found."}), 404

    payload = request.get_json(silent=True) or {}

    try:
        completed_on = normalize_date(payload.get("completedOn"))
    except ValueError:
        return jsonify({"message": "completedOn must use YYYY-MM-DD format."}), 400

    existing_log = HabitLog.query.filter_by(habit_id=habit.id, completed_on=completed_on).first()
    if existing_log:
        return jsonify({"message": "Habit already logged for that date."}), 400

    points_awarded = habit.points_reward
    update_habit_streak(habit, completed_on)

    if habit.streak_count > 0 and habit.streak_count % 7 == 0:
        points_awarded += 20

    log = HabitLog(
        habit_id=habit.id,
        user_id=user.id,
        completed_on=completed_on,
        duration_minutes=payload.get("durationMinutes"),
        notes=(payload.get("notes") or "").strip() or None,
        points_awarded=points_awarded,
    )

    user.points += points_awarded
    user.level = calculate_level(user.points)

    db.session.add(log)
    db.session.commit()

    return jsonify(
        {
            "message": "Habit logged.",
            "habit": serialize_habit(habit),
            "log": {
                "id": log.id,
                "completedOn": log.completed_on.isoformat(),
                "durationMinutes": log.duration_minutes,
                "notes": log.notes,
                "pointsAwarded": log.points_awarded,
            },
            "user": serialize_user(user),
        }
    )


@api.get("/dashboard")
@require_auth
def dashboard(user):
    habits = Habit.query.filter_by(user_id=user.id, is_active=True).all()
    recent_logs = (
        HabitLog.query.filter_by(user_id=user.id)
        .order_by(HabitLog.completed_on.desc(), HabitLog.created_at.desc())
        .limit(10)
        .all()
    )

    return jsonify(
        {
            "user": serialize_user(user),
            "stats": {
                "activeHabits": len(habits),
                "totalPoints": user.points,
                "longestStreak": max((habit.streak_count for habit in habits), default=0),
                "recentCompletions": len(recent_logs),
            },
            "recentLogs": [
                {
                    "habitId": log.habit_id,
                    "completedOn": log.completed_on.isoformat(),
                    "durationMinutes": log.duration_minutes,
                    "pointsAwarded": log.points_awarded,
                    "notes": log.notes,
                }
                for log in recent_logs
            ],
        }
    )
