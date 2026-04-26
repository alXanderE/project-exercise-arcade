import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_
try:
    from pymongo.errors import DuplicateKeyError
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    class DuplicateKeyError(Exception):
        pass

from .auth import build_session, hash_password, verify_password
from .daily_tasks import all_daily_tasks, find_daily_task
from .extensions import db
from .mongo_auth import (
    clear_auth_session,
    create_auth_user,
    find_auth_user_by_display_name,
    find_auth_user_by_email,
    find_auth_user_by_identifier,
    find_auth_user_by_session_token,
    mongo_auth_enabled,
    mongo_auth_unavailable_reason,
    normalize_sql_user_id,
    set_auth_session,
    update_auth_user,
)
from .mongo_game import (
    complete_daily_task as complete_daily_task_mongo,
    create_custom_task,
    fitness_history as fitness_history_mongo,
    fitness_summary as fitness_summary_mongo,
    get_daily_task_completions,
    list_custom_tasks,
    mongo_game_enabled,
    prize_wheel_history as prize_wheel_history_mongo,
    record_prize_wheel_spin,
    save_fitness_steps as save_fitness_steps_mongo,
    sync_sql_user_points,
    update_user_account_state,
)
from .models import (
    FitnessLog,
    Habit,
    HabitLog,
    DailyTaskCompletion,
    PrizeWheelSlice,
    PrizeWheelSpin,
    User,
    UserPrize,
)


api = Blueprint("api", __name__)

POSITIONAL_WHEEL_RULES = [
    {
        "label": "Red",
        "description": "Get the full spin cost back.",
        "color": "#ff001c",
        "reward_type": "spin_multiplier",
        "reward_value": 100,
    },
    {
        "label": "Orange",
        "description": "Get half the spin cost back.",
        "color": "#ffae00",
        "reward_type": "spin_multiplier",
        "reward_value": 50,
    },
    {
        "label": "Yellow",
        "description": "Get 10% of the spin cost back.",
        "color": "#fffb00",
        "reward_type": "spin_multiplier",
        "reward_value": 10,
    },
    {
        "label": "Green",
        "description": "No coins back.",
        "color": "#00f932",
        "reward_type": "spin_multiplier",
        "reward_value": 0,
    },
    {
        "label": "Light Blue",
        "description": "Get twice the spin cost back.",
        "color": "#4fd8ff",
        "reward_type": "spin_multiplier",
        "reward_value": 200,
    },
    {
        "label": "Dark Blue",
        "description": "Get 20% of the spin cost back.",
        "color": "#006dff",
        "reward_type": "spin_multiplier",
        "reward_value": 20,
    },
    {
        "label": "Dark Purple",
        "description": "Lose the spin cost and the same amount again.",
        "color": "#4c1d95",
        "reward_type": "spin_multiplier",
        "reward_value": -100,
    },
    {
        "label": "Pink",
        "description": "Get three times the spin cost back.",
        "color": "#fb00ff",
        "reward_type": "spin_multiplier",
        "reward_value": 300,
    },
]

DEFAULT_PRIZE_WHEEL_SLICES = [
    {
        **POSITIONAL_WHEEL_RULES[display_order % len(POSITIONAL_WHEEL_RULES)],
        "weight": 1,
        "display_order": display_order,
    }
    for display_order in range(16)
]

CARD_SUITS = ["S", "H", "D", "C"]
CARD_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
BLACKJACK_HANDS = {}
GYM_EQUIPMENT_COST = 100
GYM_EQUIPMENT_IDS = {"bench", "cablemachine", "dumbbells", "machine", "treadmill"}


def wheel_rule_for_display_order(display_order):
    if display_order is None:
        return POSITIONAL_WHEEL_RULES[0]
    return POSITIONAL_WHEEL_RULES[int(display_order) % len(POSITIONAL_WHEEL_RULES)]


def calculate_spin_reward(points_spent, reward_type, reward_value):
    if reward_type == "spin_multiplier":
        return int(points_spent * reward_value // 100)

    if reward_type == "points":
        return reward_value

    return 0


def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "points": user.points,
        "level": user.level,
    }


def placeholder_password_hash():
    return hash_password(secrets.token_urlsafe(32))


def display_name_exists(display_name, *, exclude_email=None):
    normalized_display_name = (display_name or "").strip().lower()
    normalized_email = (exclude_email or "").strip().lower()
    if not normalized_display_name:
        return False

    if mongo_auth_enabled():
        auth_user = find_auth_user_by_display_name(display_name)
        if auth_user and auth_user["email"] != normalized_email:
            return True

    existing_display_name = User.query.filter(
        func.lower(User.display_name) == normalized_display_name
    ).first()
    return bool(existing_display_name and existing_display_name.email != normalized_email)


def unique_display_name(candidate, email):
    base_name = (candidate or "").strip() or email.split("@")[0]
    base_name = base_name[:120].strip() or "Player"
    if len(base_name) > 120:
        base_name = base_name[:120]

    if not display_name_exists(base_name, exclude_email=email):
        return base_name

    suffix_source = email.split("@")[0].strip() or "player"
    suffix_source = "".join(char for char in suffix_source if char.isalnum()) or "player"
    fallback_base = base_name[: max(1, 120 - len(suffix_source) - 1)].rstrip()
    candidate_name = f"{fallback_base}-{suffix_source}".strip("-")
    candidate_name = candidate_name[:120]
    if not display_name_exists(candidate_name, exclude_email=email):
        return candidate_name

    counter = 2
    while True:
        suffix = f"-{counter}"
        trimmed_base = base_name[: max(1, 120 - len(suffix))].rstrip()
        candidate_name = f"{trimmed_base}{suffix}"
        if not display_name_exists(candidate_name, exclude_email=email):
            return candidate_name
        counter += 1


def verify_google_id_token(token):
    google_client_id = current_app.config.get("GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        return None, "Google sign-in is not configured.", 500

    if not token:
        return None, "Token is missing.", 400

    tokeninfo_url = "https://oauth2.googleapis.com/tokeninfo?" + urlencode(
        {"id_token": token}
    )

    try:
        with urlopen(tokeninfo_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        return None, "Invalid or expired Google token.", 401
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None, "Could not verify the Google token right now.", 502

    if payload.get("aud") != google_client_id:
        return None, "Google token audience mismatch.", 401

    if payload.get("email_verified") not in {"true", True}:
        return None, "Google account email is not verified.", 401

    if not payload.get("email") or not payload.get("sub"):
        return None, "Google account data was incomplete.", 401

    return payload, None, 200


def sync_sql_user_from_auth_document(auth_user):
    user = User.query.filter_by(email=auth_user["email"]).first()

    if not user:
        user = User(
            email=auth_user["email"],
            display_name=auth_user["display_name"],
            password_hash=auth_user["password_hash"],
            points=int(auth_user.get("points") or 0),
            level=int(auth_user.get("level") or 1),
        )
        db.session.add(user)
        db.session.commit()
    else:
        user.email = auth_user["email"]
        user.display_name = auth_user["display_name"]
        user.password_hash = auth_user["password_hash"]
        user.points = int(auth_user.get("points") or user.points or 0)
        user.level = int(auth_user.get("level") or user.level or 1)
        db.session.commit()

    return user


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
        "workoutMinutes": getattr(log, "workout_minutes", 0) or 0,
        "activeCalories": getattr(log, "active_calories", 0) or 0,
        "distanceMiles": getattr(log, "distance_miles", 0) or 0,
        "source": log.source,
        "pointsAwarded": log.points_awarded,
        "notes": log.notes,
        "createdAt": log.created_at.isoformat(),
        "updatedAt": log.updated_at.isoformat(),
    }


def serialize_prize_wheel_slice(slice_):
    rule = wheel_rule_for_display_order(slice_.display_order)
    return {
        "id": slice_.id,
        "label": rule["label"],
        "description": rule["description"],
        "color": rule["color"],
        "weight": 1,
        "rewardType": rule["reward_type"],
        "rewardValue": rule["reward_value"],
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


def serialize_daily_task_completion(completion):
    return {
        "id": completion.id,
        "taskId": completion.task_id,
        "completedOn": completion.completed_on.isoformat(),
        "pointsAwarded": completion.points_awarded,
        "createdAt": completion.created_at.isoformat(),
    }


def current_utc():
    return datetime.now(timezone.utc)


def get_current_user():
    session_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if not session_token:
        return None

    if mongo_auth_enabled():
        auth_user = find_auth_user_by_session_token(session_token)
        if not auth_user:
            return None
        return sync_sql_user_from_auth_document(auth_user)

    return User.query.filter(
        User.session_token == session_token,
        User.session_expires_at.isnot(None),
        User.session_expires_at > current_utc(),
    ).first()


def login_user(response, user):
    session_token, expires_at = build_session(current_app.config["SESSION_DAYS"])
    if mongo_auth_enabled():
        set_auth_session(user.email, session_token, expires_at)
        max_age = current_app.config["SESSION_DAYS"] * 24 * 60 * 60
        response.set_cookie(
            current_app.config["SESSION_COOKIE_NAME"],
            session_token,
            httponly=True,
            samesite="Lax",
            max_age=max_age,
        )
        return

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
    if mongo_auth_enabled():
        clear_auth_session(user.email if user else None)
        response.set_cookie(
            current_app.config["SESSION_COOKIE_NAME"],
            "",
            httponly=True,
            samesite="Lax",
            max_age=0,
        )
        return

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


def requested_local_date():
    payload = request.get_json(silent=True) or {}
    local_date = payload.get("localDate") or request.args.get("localDate")
    try:
        return normalize_date(local_date)
    except ValueError:
        return None


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


def calculate_fitness_points(steps, workout_minutes=0, active_calories=0, distance_miles=0):
    capped_steps = min(steps, current_app.config["FITNESS_DAILY_STEP_CAP"])
    points = capped_steps // current_app.config["FITNESS_STEPS_PER_POINT"]

    if steps >= current_app.config["FITNESS_DAILY_GOAL_STEPS"]:
        points += current_app.config["FITNESS_DAILY_GOAL_BONUS"]

    points += max(0, int(workout_minutes)) * current_app.config["FITNESS_WORKOUT_MINUTE_POINTS"]
    active_calories_per_point = current_app.config["FITNESS_ACTIVE_CALORIES_PER_POINT"]
    if active_calories_per_point > 0:
        points += max(0, int(active_calories)) // active_calories_per_point

    distance_miles_per_point = current_app.config["FITNESS_DISTANCE_MILES_PER_POINT"]
    if distance_miles_per_point > 0:
        points += int(max(0, float(distance_miles)) // distance_miles_per_point)

    return points


def fitness_reward_settings():
    return {
        "stepsPerPoint": current_app.config["FITNESS_STEPS_PER_POINT"],
        "dailyStepCap": current_app.config["FITNESS_DAILY_STEP_CAP"],
        "dailyGoalSteps": current_app.config["FITNESS_DAILY_GOAL_STEPS"],
        "dailyGoalBonus": current_app.config["FITNESS_DAILY_GOAL_BONUS"],
        "workoutMinutePoints": current_app.config["FITNESS_WORKOUT_MINUTE_POINTS"],
        "activeCaloriesPerPoint": current_app.config["FITNESS_ACTIVE_CALORIES_PER_POINT"],
        "distanceMilesPerPoint": current_app.config["FITNESS_DISTANCE_MILES_PER_POINT"],
    }


def parse_nonnegative_int(value, field_name, default=0):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return parsed


def parse_nonnegative_float(value, field_name, default=0):
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return parsed


def ensure_default_prize_wheel_slices():
    default_display_orders = [
        prize_slice["display_order"]
        for prize_slice in DEFAULT_PRIZE_WHEEL_SLICES
    ]
    existing_slices = {
        slice_.display_order: slice_
        for slice_ in PrizeWheelSlice.query.filter(
            PrizeWheelSlice.display_order.in_(default_display_orders)
        )
    }

    for prize_slice in DEFAULT_PRIZE_WHEEL_SLICES:
        existing_slice = existing_slices.get(prize_slice["display_order"])
        if existing_slice:
            for key, value in prize_slice.items():
                setattr(existing_slice, key, value)
        else:
            db.session.add(PrizeWheelSlice(**prize_slice))

    for slice_ in PrizeWheelSlice.query.filter(
        ~PrizeWheelSlice.display_order.in_(default_display_orders)
    ):
        slice_.is_active = False

    db.session.commit()


def active_prize_wheel_slices():
    ensure_default_prize_wheel_slices()
    return (
        PrizeWheelSlice.query.filter_by(is_active=True)
        .order_by(PrizeWheelSlice.display_order.asc(), PrizeWheelSlice.id.asc())
        .all()
    )


def choose_weighted_slice(slices):
    if not slices:
        return None

    winning_index = secrets.SystemRandom().randrange(len(slices))
    return slices[winning_index]


def parse_positive_int(value, field_name, *, minimum=1, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.")

    if number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")

    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} must be no more than {maximum}.")

    return number


def set_user_points(user, points):
    user.points = max(0, int(points))
    user.level = calculate_level(user.points)

    if mongo_game_enabled():
        update_user_account_state(user, points=user.points, level=user.level)
    else:
        db.session.commit()


def apply_point_delta(user, points_delta):
    set_user_points(user, user.points + int(points_delta))
    return user


def build_deck():
    deck = [
        {"rank": rank, "suit": suit}
        for suit in CARD_SUITS
        for rank in CARD_RANKS
    ]
    secrets.SystemRandom().shuffle(deck)
    return deck


def blackjack_card_value(card):
    rank = card["rank"]
    if rank == "A":
        return 11
    if rank in {"J", "Q", "K"}:
        return 10
    return int(rank)


def blackjack_hand_value(hand):
    total = sum(blackjack_card_value(card) for card in hand)
    aces = sum(1 for card in hand if card["rank"] == "A")

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total


def serialize_blackjack_card(card):
    suit_symbols = {"S": "spades", "H": "hearts", "D": "diamonds", "C": "clubs"}
    return {
        "rank": card["rank"],
        "suit": card["suit"],
        "label": f"{card['rank']} of {suit_symbols.get(card['suit'], card['suit'])}",
    }


def serialize_blackjack_state(state, user, *, reveal_dealer=False, message=None):
    dealer_cards = state["dealer"]
    visible_dealer = dealer_cards if reveal_dealer else dealer_cards[:1]
    dealer_total = blackjack_hand_value(dealer_cards) if reveal_dealer else None
    player_total = blackjack_hand_value(state["player"])

    return {
        "bet": state["bet"],
        "playerCards": [serialize_blackjack_card(card) for card in state["player"]],
        "dealerCards": [serialize_blackjack_card(card) for card in visible_dealer],
        "dealerHiddenCount": max(0, len(dealer_cards) - len(visible_dealer)),
        "playerTotal": player_total,
        "dealerTotal": dealer_total,
        "status": state["status"],
        "outcome": state.get("outcome"),
        "payout": state.get("payout", 0),
        "net": state.get("net", -state["bet"]),
        "message": message or state.get("message", ""),
        "user": serialize_user(user),
    }


def blackjack_user_key(user):
    return str(user.email or user.id).strip().lower()


def save_blackjack_state(user, state):
    BLACKJACK_HANDS[blackjack_user_key(user)] = state


def clear_blackjack_state(user):
    BLACKJACK_HANDS.pop(blackjack_user_key(user), None)


def finalize_blackjack_hand(user, state, outcome, payout, message):
    state["status"] = "finished"
    state["outcome"] = outcome
    state["payout"] = payout
    state["net"] = payout - state["bet"]
    state["message"] = message
    apply_point_delta(user, payout)
    clear_blackjack_state(user)
    return serialize_blackjack_state(state, user, reveal_dealer=True, message=message)


def active_blackjack_state(user):
    state = BLACKJACK_HANDS.get(blackjack_user_key(user))
    if not state or state.get("status") != "playing":
        return None
    return state


def draw_blackjack_card(state):
    if not state["deck"]:
        state["deck"] = build_deck()
    return state["deck"].pop()


def generated_workout_reward(difficulty):
    rewards = {
        "easy": 8,
        "medium": 14,
        "hard": 22,
    }
    return rewards.get(str(difficulty or "").strip().lower(), rewards["medium"])


def dice_reward_for_bet(kind, amount):
    if kind == "parity":
        return int(amount) // 4
    if kind in {"die_one", "die_two"}:
        return int(amount) // 2
    if kind == "total":
        return int(amount)
    return 0


def apply_prize_wheel_reward(user, spin):
    if spin.reward_type == "spin_multiplier":
        user.points = max(
            0,
            user.points + calculate_spin_reward(
                spin.points_spent, spin.reward_type, spin.reward_value
            ),
        )
        user.level = calculate_level(user.points)
        return None

    if spin.reward_type == "points":
        user.points = max(0, user.points + spin.reward_value)
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


@api.get("/tasks/daily/completions")
@require_auth
def daily_task_completions(user):
    local_date = requested_local_date()
    if local_date is None:
        return jsonify({"message": "localDate must use YYYY-MM-DD format."}), 400

    if mongo_game_enabled():
        sync_sql_user_points(user)
        result = get_daily_task_completions(user, local_date.isoformat())
        generated_completions = DailyTaskCompletion.query.filter(
            DailyTaskCompletion.user_id == user.id,
            DailyTaskCompletion.completed_on == local_date,
            DailyTaskCompletion.task_id.like("generated-%"),
        ).all()
        result["completedTaskIds"] = list(
            dict.fromkeys(
                result.get("completedTaskIds", []) +
                [completion.task_id for completion in generated_completions]
            )
        )
        result["completions"] = result.get("completions", []) + [
            serialize_daily_task_completion(completion)
            for completion in generated_completions
        ]
        result["user"] = serialize_user(user)
        return jsonify(result)

    completions = DailyTaskCompletion.query.filter_by(
        user_id=user.id,
        completed_on=local_date,
    ).all()

    return jsonify(
        {
            "completedTaskIds": [completion.task_id for completion in completions],
            "completions": [
                serialize_daily_task_completion(completion)
                for completion in completions
            ],
            "user": serialize_user(user),
        }
    )


@api.post("/tasks/daily/complete")
@api.post("/tasks/daily/<task_id>/complete")
@require_auth
def complete_daily_task(user, task_id=None):
    payload = request.get_json(silent=True) or {}
    resolved_task_id = task_id or (payload.get("taskId") or "").strip()
    if not resolved_task_id:
        return jsonify({"message": "taskId is required."}), 400

    local_date = requested_local_date()
    if local_date is None:
        return jsonify({"message": "localDate must use YYYY-MM-DD format."}), 400

    generated_workout = payload.get("generatedWorkout") or {}
    is_generated_workout = (
        resolved_task_id.startswith("generated-") and
        isinstance(generated_workout, dict)
    )

    if is_generated_workout:
        if mongo_game_enabled():
            sync_sql_user_points(user)
        reward = generated_workout_reward(generated_workout.get("difficulty"))
        existing_completion = DailyTaskCompletion.query.filter_by(
            user_id=user.id,
            task_id=resolved_task_id,
            completed_on=local_date,
        ).first()
        if existing_completion:
            return (
                jsonify(
                    {
                        "message": "Daily task already completed today.",
                        "completion": serialize_daily_task_completion(existing_completion),
                        "user": serialize_user(user),
                    }
                ),
                400,
            )

        completion = DailyTaskCompletion(
            user_id=user.id,
            task_id=resolved_task_id,
            completed_on=local_date,
            points_awarded=reward,
        )
        user.points += reward
        user.level = calculate_level(user.points)
        db.session.add(completion)
        if mongo_game_enabled():
            update_user_account_state(user, points=user.points, level=user.level)
        db.session.commit()

        return (
            jsonify(
                {
                    "message": "Generated workout completed.",
                    "completion": serialize_daily_task_completion(completion),
                    "user": serialize_user(user),
                }
            ),
            201,
        )

    if mongo_game_enabled():
        try:
            sync_sql_user_points(user)
            payload, error_message, status_code = complete_daily_task_mongo(
                user,
                resolved_task_id,
                local_date.isoformat(),
                calculate_level,
            )
        except Exception:
            return jsonify({"message": "Daily task progress could not be saved right now."}), 500
        if error_message:
            return jsonify({"message": error_message}), status_code
        payload["user"] = serialize_user(user)
        return jsonify(payload), status_code

    task = find_daily_task(resolved_task_id)
    if not task:
        return jsonify({"message": "Daily task not found."}), 404

    existing_completion = DailyTaskCompletion.query.filter_by(
        user_id=user.id,
        task_id=resolved_task_id,
        completed_on=local_date,
    ).first()
    if existing_completion:
        return (
            jsonify(
                {
                    "message": "Daily task already completed today.",
                    "completion": serialize_daily_task_completion(existing_completion),
                    "user": serialize_user(user),
                }
            ),
            400,
        )

    completion = DailyTaskCompletion(
        user_id=user.id,
        task_id=resolved_task_id,
        completed_on=local_date,
        points_awarded=task.coin_reward,
    )
    user.points += task.coin_reward
    user.level = calculate_level(user.points)

    db.session.add(completion)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Daily task completed.",
                "completion": serialize_daily_task_completion(completion),
                "user": serialize_user(user),
            }
        ),
        201,
    )


@api.post("/fitness/steps")
@require_auth
def log_fitness_steps(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)
        payload = request.get_json(silent=True) or {}

        try:
            logged_on = normalize_date(payload.get("loggedOn")).isoformat()
        except ValueError:
            return jsonify({"message": "loggedOn must use YYYY-MM-DD format."}), 400

        try:
            steps = parse_nonnegative_int(payload.get("steps"), "steps")
            workout_minutes = parse_nonnegative_int(
                payload.get("workoutMinutes"),
                "workoutMinutes",
            )
            active_calories = parse_nonnegative_int(
                payload.get("activeCalories"),
                "activeCalories",
            )
            distance_miles = parse_nonnegative_float(
                payload.get("distanceMiles"),
                "distanceMiles",
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400

        notes = (payload.get("notes") or "").strip() or None
        source = (payload.get("source") or "manual").strip()[:30] or "manual"
        try:
            result = save_fitness_steps_mongo(
                user,
                logged_on=logged_on,
                steps_to_add=steps,
                workout_minutes_to_add=workout_minutes,
                active_calories_to_add=active_calories,
                distance_miles_to_add=distance_miles,
                source=source,
                notes=notes,
                calculate_points_fn=calculate_fitness_points,
                calculate_level_fn=calculate_level,
            )
        except Exception:
            return jsonify({"message": "Fitness progress could not be saved right now."}), 500
        result["message"] = "Fitness steps logged."
        result["rewardSettings"] = fitness_reward_settings()
        result["user"] = serialize_user(user)
        return jsonify(result), 201 if result["created"] else 200

    payload = request.get_json(silent=True) or {}

    try:
        logged_on = normalize_date(payload.get("loggedOn"))
    except ValueError:
        return jsonify({"message": "loggedOn must use YYYY-MM-DD format."}), 400

    try:
        steps = parse_nonnegative_int(payload.get("steps"), "steps")
        workout_minutes = parse_nonnegative_int(
            payload.get("workoutMinutes"),
            "workoutMinutes",
        )
        active_calories = parse_nonnegative_int(
            payload.get("activeCalories"),
            "activeCalories",
        )
        distance_miles = parse_nonnegative_float(
            payload.get("distanceMiles"),
            "distanceMiles",
        )
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    notes = (payload.get("notes") or "").strip() or None
    source = (payload.get("source") or "manual").strip()[:30] or "manual"

    log = FitnessLog.query.filter_by(user_id=user.id, logged_on=logged_on).first()
    created = log is None

    if created:
        points_awarded = calculate_fitness_points(
            steps,
            workout_minutes=workout_minutes,
            active_calories=active_calories,
            distance_miles=distance_miles,
        )
        log = FitnessLog(
            user_id=user.id,
            logged_on=logged_on,
            steps=steps,
            workout_minutes=workout_minutes,
            active_calories=active_calories,
            distance_miles=distance_miles,
            source=source,
            points_awarded=points_awarded,
            notes=notes,
        )
        db.session.add(log)
        points_delta = points_awarded
    else:
        total_steps = log.steps + steps
        total_workout_minutes = (log.workout_minutes or 0) + workout_minutes
        total_active_calories = (log.active_calories or 0) + active_calories
        total_distance_miles = (log.distance_miles or 0) + distance_miles
        points_awarded = calculate_fitness_points(
            total_steps,
            workout_minutes=total_workout_minutes,
            active_calories=total_active_calories,
            distance_miles=total_distance_miles,
        )
        points_delta = points_awarded - log.points_awarded
        log.steps = total_steps
        log.workout_minutes = total_workout_minutes
        log.active_calories = total_active_calories
        log.distance_miles = total_distance_miles
        log.source = source
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
    if mongo_game_enabled():
        sync_sql_user_points(user)
        result = fitness_history_mongo(user)
        result["rewardSettings"] = fitness_reward_settings()
        return jsonify(result)

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
    if mongo_game_enabled():
        sync_sql_user_points(user)
        result = fitness_summary_mongo(
            user,
            current_app.config["FITNESS_DAILY_GOAL_STEPS"],
        )
        result["rewardSettings"] = fitness_reward_settings()
        result["user"] = serialize_user(user)
        return jsonify(result)

    logs = FitnessLog.query.filter_by(user_id=user.id).all()
    today = date.today()
    today_log = next((log for log in logs if log.logged_on == today), None)

    return jsonify(
        {
            "today": serialize_fitness_log(today_log) if today_log else None,
            "stats": {
                "totalLogs": len(logs),
                "totalSteps": sum(log.steps for log in logs),
                "totalWorkoutMinutes": sum(
                    (log.workout_minutes or 0) for log in logs
                ),
                "totalActiveCalories": sum(
                    (log.active_calories or 0) for log in logs
                ),
                "totalDistanceMiles": sum(
                    (log.distance_miles or 0) for log in logs
                ),
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
    if mongo_game_enabled():
        sync_sql_user_points(user)

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
    if mongo_game_enabled():
        sync_sql_user_points(user)

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

    wheel_rule = wheel_rule_for_display_order(winning_slice.display_order)
    if mongo_game_enabled():
        reward_delta = calculate_spin_reward(
            spin_cost,
            wheel_rule["reward_type"],
            wheel_rule["reward_value"],
        )
        try:
            result = record_prize_wheel_spin(
                user,
                slice_id=winning_slice.id,
                prize_label=wheel_rule["label"],
                reward_type=wheel_rule["reward_type"],
                reward_value=wheel_rule["reward_value"],
                points_spent=spin_cost,
                reward_delta=reward_delta,
                calculate_level_fn=calculate_level,
            )
        except Exception:
            return jsonify({"message": "The prize wheel could not be updated right now."}), 500
        spin = result["spin"]
        prize = None
    else:
        user.points -= spin_cost
        user.level = calculate_level(user.points)

        spin = PrizeWheelSpin(
            user_id=user.id,
            slice_id=winning_slice.id,
            points_spent=spin_cost,
            reward_type=wheel_rule["reward_type"],
            reward_value=wheel_rule["reward_value"],
            prize_label=wheel_rule["label"],
        )
        db.session.add(spin)
        db.session.flush()

        prize = apply_prize_wheel_reward(user, spin)
        user.level = calculate_level(user.points)
        db.session.commit()

    return jsonify(
        {
            "message": "Prize wheel spun.",
            "spin": spin if mongo_game_enabled() else serialize_prize_wheel_spin(spin),
            "winningSlice": serialize_prize_wheel_slice(winning_slice),
            "prize": serialize_user_prize(prize) if prize else None,
            "user": serialize_user(user),
        }
    )


@api.get("/arcade/prize-wheel/history")
@require_auth
def prize_wheel_history(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)
        return jsonify(prize_wheel_history_mongo(user))

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


@api.post("/arcade/blackjack/start")
@require_auth
def start_blackjack(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)

    payload = request.get_json(silent=True) or {}
    try:
        bet = parse_positive_int(payload.get("bet"), "Bet")
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    if user.points < bet:
        return jsonify({"message": "Not enough coins for that blackjack bet.", "user": serialize_user(user)}), 400

    deck = build_deck()
    state = {
        "bet": bet,
        "deck": deck,
        "player": [deck.pop(), deck.pop()],
        "dealer": [deck.pop(), deck.pop()],
        "status": "playing",
        "outcome": None,
        "payout": 0,
        "net": -bet,
    }
    apply_point_delta(user, -bet)

    player_total = blackjack_hand_value(state["player"])
    dealer_total = blackjack_hand_value(state["dealer"])
    if player_total == 21 or dealer_total == 21:
        if player_total == 21 and dealer_total == 21:
            result = finalize_blackjack_hand(
                user,
                state,
                "push",
                bet,
                "Both hands hit 21. Your bet was returned.",
            )
        elif player_total == 21:
            result = finalize_blackjack_hand(
                user,
                state,
                "blackjack",
                bet * 3,
                "Blackjack! You beat the dealer.",
            )
        else:
            result = finalize_blackjack_hand(
                user,
                state,
                "dealer_blackjack",
                0,
                "Dealer has 21.",
            )
        return jsonify(result)

    save_blackjack_state(user, state)
    return jsonify(serialize_blackjack_state(state, user, message="Hit or stand."))


@api.post("/arcade/blackjack/hit")
@require_auth
def hit_blackjack(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)

    state = active_blackjack_state(user)
    if not state:
        return jsonify({"message": "Start a blackjack hand first.", "user": serialize_user(user)}), 400

    state["player"].append(draw_blackjack_card(state))
    player_total = blackjack_hand_value(state["player"])
    if player_total > 21:
        return jsonify(
            finalize_blackjack_hand(
                user,
                state,
                "bust",
                0,
                "You busted. Dealer wins this hand.",
            )
        )

    save_blackjack_state(user, state)
    return jsonify(serialize_blackjack_state(state, user, message="Card dealt."))


@api.post("/arcade/blackjack/stand")
@require_auth
def stand_blackjack(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)

    state = active_blackjack_state(user)
    if not state:
        return jsonify({"message": "Start a blackjack hand first.", "user": serialize_user(user)}), 400

    while blackjack_hand_value(state["dealer"]) < 17:
        state["dealer"].append(draw_blackjack_card(state))

    player_total = blackjack_hand_value(state["player"])
    dealer_total = blackjack_hand_value(state["dealer"])

    if dealer_total > 21:
        outcome = "dealer_bust"
        payout = state["bet"] * 2
        message = "Dealer busted. You win."
    elif player_total > dealer_total:
        outcome = "win"
        payout = state["bet"] * 2
        message = "You beat the dealer."
    elif player_total == dealer_total:
        outcome = "push"
        payout = state["bet"]
        message = "Push. Your bet was returned."
    else:
        outcome = "lose"
        payout = 0
        message = "Dealer wins this hand."

    return jsonify(finalize_blackjack_hand(user, state, outcome, payout, message))


@api.post("/arcade/dice/roll")
@require_auth
def roll_dice_game(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)

    payload = request.get_json(silent=True) or {}
    bets = []

    def add_bet(kind, amount_field, value_field=None, *, minimum=1, maximum=None):
        raw_amount = payload.get(amount_field)
        try:
            amount = int(raw_amount or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{amount_field} must be a whole number.")
        if amount < 0:
            raise ValueError(f"{amount_field} cannot be negative.")
        if amount <= 0:
            return
        value = None
        if value_field:
            value = parse_positive_int(
                payload.get(value_field),
                value_field,
                minimum=minimum,
                maximum=maximum,
            )
        bets.append({"kind": kind, "amount": amount, "value": value})

    try:
        add_bet("die_one", "dieOneBet", "dieOneNumber", minimum=1, maximum=6)
        add_bet("die_two", "dieTwoBet", "dieTwoNumber", minimum=1, maximum=6)
        add_bet("total", "totalBet", "totalNumber", minimum=2, maximum=12)
        try:
            parity_amount = int(payload.get("parityBet") or 0)
        except (TypeError, ValueError):
            raise ValueError("parityBet must be a whole number.")
        if parity_amount < 0:
            raise ValueError("parityBet cannot be negative.")
        if parity_amount > 0:
            parity = str(payload.get("parityChoice") or "").lower()
            if parity not in {"odd", "even"}:
                raise ValueError("Choose odd or even for the total.")
            bets.append({"kind": "parity", "amount": parity_amount, "value": parity})
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    if not bets:
        return jsonify({"message": "Place at least one dice bet."}), 400

    total_wager = sum(bet["amount"] for bet in bets)
    if any(bet["amount"] < 1 for bet in bets):
        return jsonify({"message": "Each dice bet must be at least 1 coin."}), 400

    if user.points < total_wager:
        return jsonify({"message": "Not enough coins for those dice bets.", "user": serialize_user(user)}), 400

    die_one = secrets.SystemRandom().randint(1, 6)
    die_two = secrets.SystemRandom().randint(1, 6)
    total = die_one + die_two
    parity = "even" if total % 2 == 0 else "odd"
    results = []
    winnings = 0

    for bet in bets:
        won = False
        if bet["kind"] == "die_one":
            won = die_one == bet["value"]
        elif bet["kind"] == "die_two":
            won = die_two == bet["value"]
        elif bet["kind"] == "total":
            won = total == bet["value"]
        elif bet["kind"] == "parity":
            won = parity == bet["value"]

        reward = dice_reward_for_bet(bet["kind"], bet["amount"])
        payout = bet["amount"] + reward if won else 0
        winnings += payout
        results.append({**bet, "won": won, "reward": reward, "payout": payout})

    apply_point_delta(user, -total_wager + winnings)

    return jsonify(
        {
            "message": "Dice rolled.",
            "roll": {"dieOne": die_one, "dieTwo": die_two, "total": total, "parity": parity},
            "bets": results,
            "totalWager": total_wager,
            "winnings": winnings,
            "net": winnings - total_wager,
            "user": serialize_user(user),
        }
    )


@api.post("/gym/equipment/purchase")
@require_auth
def purchase_gym_equipment(user):
    if mongo_game_enabled():
        sync_sql_user_points(user)

    payload = request.get_json(silent=True) or {}
    equipment_id = str(payload.get("itemId") or "").strip().lower()
    if equipment_id not in GYM_EQUIPMENT_IDS:
        return jsonify({"message": "Gym equipment item not found."}), 404

    if user.points < GYM_EQUIPMENT_COST:
        return (
            jsonify(
                {
                    "message": "Not enough coins to buy that gym item.",
                    "cost": GYM_EQUIPMENT_COST,
                    "user": serialize_user(user),
                }
            ),
            400,
        )

    apply_point_delta(user, -GYM_EQUIPMENT_COST)
    return jsonify(
        {
            "message": "Gym equipment purchased.",
            "itemId": equipment_id,
            "cost": GYM_EQUIPMENT_COST,
            "user": serialize_user(user),
        }
    )


@api.get("/tasks/custom")
@require_auth
def list_custom_tasks_route(user):
    if not mongo_game_enabled():
        return jsonify({"tasks": []})

    sync_sql_user_points(user)
    return jsonify({"tasks": list_custom_tasks(user), "user": serialize_user(user)})


@api.post("/tasks/custom")
@require_auth
def create_custom_task_route(user):
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    category = (payload.get("category") or "").strip()
    description = (payload.get("description") or "").strip()
    try:
        reward = min(20, max(1, int(payload.get("coinReward") or 1)))
    except (TypeError, ValueError):
        return jsonify({"message": "coinReward must be a whole number."}), 400

    if not title or not category or not description:
        return jsonify({"message": "Add a name, category, and description."}), 400

    if not mongo_game_enabled():
        return jsonify({"message": "MongoDB custom tasks are not enabled."}), 400

    try:
        sync_sql_user_points(user)
        task = create_custom_task(user, title, category, description, reward)
    except Exception:
        return (
            jsonify(
                {
                    "message": (
                        "The workout could not be saved to MongoDB right now."
                    )
                }
            ),
            500,
        )
    return jsonify({"message": "Custom workout created.", "task": task}), 201


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

    if current_app.config.get("MONGODB_URI") and not mongo_auth_enabled():
        return jsonify({"message": mongo_auth_unavailable_reason()}), 500

    if mongo_auth_enabled():
        if find_auth_user_by_email(email):
            return jsonify({"message": "An account with that email already exists."}), 400
        if find_auth_user_by_display_name(display_name):
            return jsonify({"message": "That display name is already taken."}), 400
    else:
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"message": "An account with that email already exists."}), 400

        existing_display_name = User.query.filter(
            func.lower(User.display_name) == display_name.lower()
        ).first()
        if existing_display_name:
            return jsonify({"message": "That display name is already taken."}), 400

    password_hash = hash_password(password)
    user = User(
        email=email,
        display_name=display_name,
        password_hash=password_hash,
    )
    db.session.add(user)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if mongo_auth_enabled():
        try:
            create_auth_user(email, display_name, password_hash, user.id)
        except DuplicateKeyError:
            db.session.delete(user)
            db.session.commit()
            return jsonify({"message": "That account already exists in MongoDB."}), 400
        except Exception:
            db.session.delete(user)
            db.session.commit()
            raise

    response = jsonify({"message": "Account created.", "user": serialize_user(user)})
    login_user(response, user)
    return response, 201


@api.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    identifier = (payload.get("identifier") or payload.get("email") or "").strip()
    password = payload.get("password") or ""

    normalized_identifier = identifier.lower()

    if current_app.config.get("MONGODB_URI") and not mongo_auth_enabled():
        return jsonify({"message": mongo_auth_unavailable_reason()}), 500

    user = None
    auth_user = find_auth_user_by_identifier(normalized_identifier)
    if auth_user:
        if not verify_password(password, auth_user["password_hash"]):
            return jsonify({"message": "Invalid email, display name, or password."}), 401
        user = sync_sql_user_from_auth_document(auth_user)
    else:
        user = User.query.filter(
            or_(
                User.email == normalized_identifier,
                func.lower(User.display_name) == normalized_identifier,
            )
        ).first()
        if not user or not verify_password(password, user.password_hash):
            return jsonify({"message": "Invalid email, display name, or password."}), 401

        if mongo_auth_enabled():
            existing_auth_user = find_auth_user_by_email(user.email)
            if existing_auth_user:
                update_auth_user(
                    user.email,
                    display_name=user.display_name,
                    password_hash=user.password_hash,
                    sql_user_id=user.id,
                )
            else:
                create_auth_user(
                    user.email,
                    user.display_name,
                    user.password_hash,
                    user.id,
                )

    response = jsonify({"message": "Logged in.", "user": serialize_user(user)})
    login_user(response, user)
    return response


@api.post("/auth/google")
def google_login():
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")

    google_payload, error_message, status_code = verify_google_id_token(token)
    if error_message:
        return jsonify({"message": error_message}), status_code

    email = google_payload["email"].strip().lower()

    if current_app.config.get("MONGODB_URI") and not mongo_auth_enabled():
        return jsonify({"message": mongo_auth_unavailable_reason()}), 500

    auth_user = find_auth_user_by_email(email)
    if auth_user:
        if mongo_auth_enabled():
            update_auth_user(
                email,
                auth_provider="google",
                google_sub=google_payload["sub"],
                picture=google_payload.get("picture"),
            )
            auth_user = find_auth_user_by_email(email)
        user = sync_sql_user_from_auth_document(auth_user)
    else:
        user = User.query.filter_by(email=email).first()
        if user:
            if mongo_auth_enabled():
                existing_auth_user = find_auth_user_by_email(user.email)
                if existing_auth_user:
                    update_auth_user(
                        user.email,
                        display_name=user.display_name,
                        password_hash=user.password_hash,
                        sql_user_id=user.id,
                        auth_provider="google",
                        google_sub=google_payload["sub"],
                        picture=google_payload.get("picture"),
                    )
                else:
                    display_name = unique_display_name(user.display_name, user.email)
                    if display_name != user.display_name:
                        user.display_name = display_name
                        db.session.commit()
                    create_auth_user(
                        user.email,
                        display_name,
                        user.password_hash,
                        user.id,
                    )
                    update_auth_user(
                        user.email,
                        auth_provider="google",
                        google_sub=google_payload["sub"],
                        picture=google_payload.get("picture"),
                    )
        else:
            display_name = unique_display_name(
                google_payload.get("name") or google_payload["email"].split("@")[0],
                email,
            )
            password_hash = placeholder_password_hash()
            user = User(
                email=email,
                display_name=display_name,
                password_hash=password_hash,
            )
            db.session.add(user)
            db.session.commit()

            if mongo_auth_enabled():
                create_auth_user(email, display_name, password_hash, user.id)
                update_auth_user(
                    email,
                    auth_provider="google",
                    google_sub=google_payload["sub"],
                    picture=google_payload.get("picture"),
                )

    response = jsonify(
        {
            "message": "Logged in with Google.",
            "user": serialize_user(user),
        }
    )
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
    if mongo_game_enabled():
        sync_sql_user_points(user)
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
