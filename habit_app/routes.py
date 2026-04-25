import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from .auth import build_session, hash_password, verify_password
from .daily_tasks import all_daily_tasks
from .extensions import db
from .models import (
    FitnessLog,
    Habit,
    HabitLog,
    PrizeWheelSlice,
    PrizeWheelSpin,
    User,
    UserPrize,
)


api = Blueprint("api", __name__)

DEFAULT_PRIZE_WHEEL_SLICES = [
    {
        "label": "+5 points",
        "description": "A small boost for the next round.",
        "color": "#14b8a6",
        "weight": 28,
        "reward_type": "points",
        "reward_value": 5,
        "display_order": 0,
    },
    {
        "label": "+15 points",
        "description": "A solid arcade payout.",
        "color": "#22c55e",
        "weight": 22,
        "reward_type": "points",
        "reward_value": 15,
        "display_order": 1,
    },
    {
        "label": "Spin refund",
        "description": "Wins back the cost of this spin.",
        "color": "#f59e0b",
        "weight": 14,
        "reward_type": "points",
        "reward_value": 25,
        "display_order": 2,
    },
    {
        "label": "+50 points",
        "description": "A rare points jackpot.",
        "color": "#ef4444",
        "weight": 6,
        "reward_type": "points",
        "reward_value": 50,
        "display_order": 3,
    },
    {
        "label": "Arcade badge",
        "description": "A collectible prize for the profile.",
        "color": "#8b5cf6",
        "weight": 10,
        "reward_type": "badge",
        "reward_value": 1,
        "display_order": 4,
    },
    {
        "label": "Try again",
        "description": "No prize this time.",
        "color": "#64748b",
        "weight": 20,
        "reward_type": "nothing",
        "reward_value": 0,
        "display_order": 5,
    },
]


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
        "lastCompletedOn": (
            habit.last_completed_on.isoformat() if habit.last_completed_on else None
        ),
    }


def serialize_fitness_log(log):
    return {
        "id": log.id,
        "loggedOn": log.logged_on.isoformat(),
        "steps": log.steps,
        "source": log.source,
        "pointsAwarded": log.points_awarded,
        "notes": log.notes,
        "createdAt": log.created_at.isoformat(),
        "updatedAt": log.updated_at.isoformat(),
    }


def serialize_prize_wheel_slice(slice_):
    return {
        "id": slice_.id,
        "label": slice_.label,
        "description": slice_.description,
        "color": slice_.color,
        "weight": slice_.weight,
        "rewardType": slice_.reward_type,
        "rewardValue": slice_.reward_value,
        "isActive": slice_.is_active,
        "displayOrder": slice_.display_order,
    }


def serialize_prize_wheel_spin(spin):
    return {
        "id": spin.id,
        "sliceId": spin.slice_id,
        "pointsSpent": spin.points_spent,
        "rewardType": spin.reward_type,
        "rewardValue": spin.reward_value,
        "prizeLabel": spin.prize_label,
        "createdAt": spin.created_at.isoformat(),
    }


def serialize_user_prize(prize):
    return {
        "id": prize.id,
        "spinId": prize.spin_id,
        "prizeType": prize.prize_type,
        "label": prize.label,
        "isRedeemed": prize.is_redeemed,
        "createdAt": prize.created_at.isoformat(),
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


def calculate_fitness_points(steps):
    capped_steps = min(steps, current_app.config["FITNESS_DAILY_STEP_CAP"])
    points = capped_steps // current_app.config["FITNESS_STEPS_PER_POINT"]

    if steps >= current_app.config["FITNESS_DAILY_GOAL_STEPS"]:
        points += current_app.config["FITNESS_DAILY_GOAL_BONUS"]

    return points


def fitness_reward_settings():
    return {
        "stepsPerPoint": current_app.config["FITNESS_STEPS_PER_POINT"],
        "dailyStepCap": current_app.config["FITNESS_DAILY_STEP_CAP"],
        "dailyGoalSteps": current_app.config["FITNESS_DAILY_GOAL_STEPS"],
        "dailyGoalBonus": current_app.config["FITNESS_DAILY_GOAL_BONUS"],
    }


def ensure_default_prize_wheel_slices():
    has_slices = PrizeWheelSlice.query.first() is not None
    if has_slices:
        return

    for prize_slice in DEFAULT_PRIZE_WHEEL_SLICES:
        db.session.add(PrizeWheelSlice(**prize_slice))
    db.session.commit()


def active_prize_wheel_slices():
    ensure_default_prize_wheel_slices()
    return (
        PrizeWheelSlice.query.filter_by(is_active=True)
        .order_by(PrizeWheelSlice.display_order.asc(), PrizeWheelSlice.id.asc())
        .all()
    )


def choose_weighted_slice(slices):
    total_weight = sum(max(slice_.weight, 0) for slice_ in slices)
    if total_weight <= 0:
        return None

    winning_number = secrets.SystemRandom().randint(1, total_weight)
    current_weight = 0
    for slice_ in slices:
        current_weight += max(slice_.weight, 0)
        if winning_number <= current_weight:
            return slice_

    return slices[-1]


def apply_prize_wheel_reward(user, spin):
    if spin.reward_type == "points":
        user.points += spin.reward_value
        user.level = calculate_level(user.points)
        return None

    if spin.reward_type in {"badge", "coupon", "mystery"}:
        prize = UserPrize(
            user_id=user.id,
            spin_id=spin.id,
            prize_type=spin.reward_type,
            label=spin.prize_label,
        )
        db.session.add(prize)
        return prize

    return None


@api.get("/health")
def health():
    return jsonify({"ok": True, "service": "exercise-arcade"})


@api.get("/tasks/daily")
def daily_tasks():
    return jsonify({"tasks": all_daily_tasks()})


@api.post("/fitness/steps")
@require_auth
def log_fitness_steps(user):
    payload = request.get_json(silent=True) or {}

    try:
        logged_on = normalize_date(payload.get("loggedOn"))
    except ValueError:
        return jsonify({"message": "loggedOn must use YYYY-MM-DD format."}), 400

    try:
        steps = int(payload.get("steps"))
    except (TypeError, ValueError):
        return jsonify({"message": "steps must be a whole number."}), 400

    if steps < 0:
        return jsonify({"message": "steps cannot be negative."}), 400

    points_awarded = calculate_fitness_points(steps)
    notes = (payload.get("notes") or "").strip() or None

    log = FitnessLog.query.filter_by(user_id=user.id, logged_on=logged_on).first()
    created = log is None

    if created:
        log = FitnessLog(
            user_id=user.id,
            logged_on=logged_on,
            steps=steps,
            source="manual",
            points_awarded=points_awarded,
            notes=notes,
        )
        db.session.add(log)
        points_delta = points_awarded
    else:
        points_delta = points_awarded - log.points_awarded
        log.steps = steps
        log.source = "manual"
        log.points_awarded = points_awarded
        log.notes = notes

    user.points = max(0, user.points + points_delta)
    user.level = calculate_level(user.points)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Fitness steps logged.",
                "created": created,
                "pointsDelta": points_delta,
                "log": serialize_fitness_log(log),
                "rewardSettings": fitness_reward_settings(),
                "user": serialize_user(user),
            }
        ),
        201 if created else 200,
    )


@api.get("/fitness/history")
@require_auth
def fitness_history(user):
    logs = (
        FitnessLog.query.filter_by(user_id=user.id)
        .order_by(FitnessLog.logged_on.desc(), FitnessLog.created_at.desc())
        .limit(30)
        .all()
    )

    return jsonify(
        {
            "logs": [serialize_fitness_log(log) for log in logs],
            "rewardSettings": fitness_reward_settings(),
        }
    )


@api.get("/fitness/summary")
@require_auth
def fitness_summary(user):
    logs = FitnessLog.query.filter_by(user_id=user.id).all()
    today = date.today()
    today_log = next((log for log in logs if log.logged_on == today), None)

    return jsonify(
        {
            "today": serialize_fitness_log(today_log) if today_log else None,
            "stats": {
                "totalLogs": len(logs),
                "totalSteps": sum(log.steps for log in logs),
                "totalPointsAwarded": sum(log.points_awarded for log in logs),
                "bestDaySteps": max((log.steps for log in logs), default=0),
                "goalDays": sum(
                    1
                    for log in logs
                    if log.steps >= current_app.config["FITNESS_DAILY_GOAL_STEPS"]
                ),
            },
            "rewardSettings": fitness_reward_settings(),
            "user": serialize_user(user),
        }
    )


@api.get("/arcade/prize-wheel")
@require_auth
def get_prize_wheel(user):
    slices = active_prize_wheel_slices()
    return jsonify(
        {
            "spinCost": current_app.config["PRIZE_WHEEL_SPIN_COST"],
            "slices": [serialize_prize_wheel_slice(slice_) for slice_ in slices],
            "user": serialize_user(user),
        }
    )


@api.post("/arcade/prize-wheel/spin")
@require_auth
def spin_prize_wheel(user):
    spin_cost = current_app.config["PRIZE_WHEEL_SPIN_COST"]
    if user.points < spin_cost:
        return (
            jsonify(
                {
                    "message": "Not enough points to spin the prize wheel.",
                    "spinCost": spin_cost,
                    "user": serialize_user(user),
                }
            ),
            400,
        )

    slices = active_prize_wheel_slices()
    winning_slice = choose_weighted_slice(slices)
    if not winning_slice:
        return (
            jsonify({"message": "The prize wheel has no active weighted slices."}),
            503,
        )

    user.points -= spin_cost
    user.level = calculate_level(user.points)

    spin = PrizeWheelSpin(
        user_id=user.id,
        slice_id=winning_slice.id,
        points_spent=spin_cost,
        reward_type=winning_slice.reward_type,
        reward_value=winning_slice.reward_value,
        prize_label=winning_slice.label,
    )
    db.session.add(spin)
    db.session.flush()

    prize = apply_prize_wheel_reward(user, spin)
    user.level = calculate_level(user.points)
    db.session.commit()

    return jsonify(
        {
            "message": "Prize wheel spun.",
            "spin": serialize_prize_wheel_spin(spin),
            "winningSlice": serialize_prize_wheel_slice(winning_slice),
            "prize": serialize_user_prize(prize) if prize else None,
            "user": serialize_user(user),
        }
    )


@api.get("/arcade/prize-wheel/history")
@require_auth
def prize_wheel_history(user):
    spins = (
        PrizeWheelSpin.query.filter_by(user_id=user.id)
        .order_by(PrizeWheelSpin.created_at.desc())
        .limit(20)
        .all()
    )
    prizes = (
        UserPrize.query.filter_by(user_id=user.id)
        .order_by(UserPrize.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        {
            "spins": [serialize_prize_wheel_spin(spin) for spin in spins],
            "prizes": [serialize_user_prize(prize) for prize in prizes],
        }
    )


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
                    "message": (
                        "Email, display name, and a password with at least "
                        "6 characters are required."
                    )
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
    habits = (
        Habit.query.filter_by(user_id=user.id)
        .order_by(Habit.created_at.desc())
        .all()
    )
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

    existing_log = HabitLog.query.filter_by(
        habit_id=habit.id,
        completed_on=completed_on,
    ).first()
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
                "longestStreak": max(
                    (habit.streak_count for habit in habits),
                    default=0,
                ),
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
