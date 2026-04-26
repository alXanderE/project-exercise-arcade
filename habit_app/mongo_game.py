import secrets
from datetime import datetime, timezone

from .daily_tasks import find_daily_task
from .mongo_auth import get_mongo_client, mongo_auth_enabled


def mongo_game_enabled():
    return mongo_auth_enabled()


def game_database_name():
    from flask import current_app

    return current_app.config["MONGODB_DB"]


def game_db():
    return get_mongo_client()[game_database_name()]


def users_collection():
    from flask import current_app

    return game_db()[current_app.config["MONGODB_USERS_COLLECTION"]]


def fitness_logs_collection():
    return game_db()["fitness_logs"]


def daily_task_completions_collection():
    return game_db()["daily_task_completions"]


def prize_wheel_spins_collection():
    return game_db()["prize_wheel_spins"]


def custom_tasks_collection():
    return game_db()["custom_tasks"]


def now_utc():
    return datetime.now(timezone.utc)


def user_key(user):
    return str(user.email).strip().lower()


def ensure_mongo_game_indexes():
    if not mongo_game_enabled():
        return

    fitness_logs_collection().create_index(
        [("user_key", 1), ("logged_on", 1)],
        unique=True,
    )
    daily_task_completions_collection().create_index(
        [("user_key", 1), ("task_id", 1), ("completed_on", 1)],
        unique=True,
    )
    prize_wheel_spins_collection().create_index([("user_key", 1), ("created_at", -1)])
    custom_tasks_collection().create_index([("user_key", 1), ("created_at", -1)])


def get_user_account_state(user):
    document = users_collection().find_one({"email": user_key(user)}) or {}
    points = int(document.get("points") or 0)
    level = int(document.get("level") or 1)
    return {"points": max(0, points), "level": max(1, level)}


def sync_sql_user_points(user):
    state = get_user_account_state(user)
    user.points = state["points"]
    user.level = state["level"]
    return user


def update_user_account_state(user, *, points=None, level=None):
    update_fields = {"updated_at": now_utc()}
    if points is not None:
      update_fields["points"] = max(0, int(points))
    if level is not None:
      update_fields["level"] = max(1, int(level))

    users_collection().update_one(
        {"email": user_key(user)},
        {"$set": update_fields},
    )
    if points is not None:
        user.points = update_fields["points"]
    if level is not None:
        user.level = update_fields["level"]
    return user


def serialize_mongo_fitness_log(log):
    return {
        "id": str(log["_id"]),
        "loggedOn": log["logged_on"],
        "steps": int(log["steps"]),
        "source": log.get("source", "manual"),
        "pointsAwarded": int(log.get("points_awarded", 0)),
        "notes": log.get("notes"),
        "createdAt": log["created_at"].isoformat(),
        "updatedAt": log["updated_at"].isoformat(),
    }


def serialize_mongo_daily_task_completion(completion):
    return {
        "id": str(completion["_id"]),
        "taskId": completion["task_id"],
        "completedOn": completion["completed_on"],
        "pointsAwarded": int(completion.get("points_awarded", 0)),
        "createdAt": completion["created_at"].isoformat(),
    }


def serialize_mongo_prize_wheel_spin(spin):
    return {
        "id": str(spin["_id"]),
        "sliceId": spin["slice_id"],
        "pointsSpent": int(spin["points_spent"]),
        "rewardType": spin["reward_type"],
        "rewardValue": int(spin["reward_value"]),
        "prizeLabel": spin["prize_label"],
        "createdAt": spin["created_at"].isoformat(),
    }


def serialize_mongo_custom_task(task):
    return {
        "id": task["task_id"],
        "title": task["title"],
        "category": task["category"],
        "description": task["description"],
        "coin_reward": int(task["coin_reward"]),
        "difficulty": "custom",
        "frequency": "daily",
        "is_custom": True,
    }


def list_custom_tasks(user):
    tasks = (
        custom_tasks_collection()
        .find({"user_key": user_key(user)})
        .sort("created_at", 1)
    )
    return [serialize_mongo_custom_task(task) for task in tasks]


def create_custom_task(user, title, category, description, coin_reward):
    document = {
        "task_id": f"custom-{secrets.token_hex(8)}",
        "user_key": user_key(user),
        "title": title,
        "category": category,
        "description": description,
        "coin_reward": int(coin_reward),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    custom_tasks_collection().insert_one(document)
    return serialize_mongo_custom_task(document)


def find_custom_task(user, task_id):
    task = custom_tasks_collection().find_one(
        {"user_key": user_key(user), "task_id": task_id}
    )
    return serialize_mongo_custom_task(task) if task else None


def get_daily_task_completions(user, completed_on):
    completions = list(
        daily_task_completions_collection().find(
            {"user_key": user_key(user), "completed_on": completed_on}
        )
    )
    return {
        "completedTaskIds": [completion["task_id"] for completion in completions],
        "completions": [
            serialize_mongo_daily_task_completion(completion)
            for completion in completions
        ],
    }


def complete_daily_task(user, task_id, completed_on, calculate_level_fn):
    task = find_daily_task(task_id)
    if not task:
        task = find_custom_task(user, task_id)
    if not task:
        return None, "Daily task not found.", 404

    resolved_task_id = task["id"] if isinstance(task, dict) else task.id
    resolved_points = int(task["coin_reward"] if isinstance(task, dict) else task.coin_reward)

    existing = daily_task_completions_collection().find_one(
        {
            "user_key": user_key(user),
            "task_id": resolved_task_id,
            "completed_on": completed_on,
        }
    )
    if existing:
        return (
            {
                "message": "Daily task already completed today.",
                "completion": serialize_mongo_daily_task_completion(existing),
            },
            None,
            400,
        )

    completion = {
        "user_key": user_key(user),
        "task_id": resolved_task_id,
        "completed_on": completed_on,
        "points_awarded": resolved_points,
        "created_at": now_utc(),
    }
    daily_task_completions_collection().insert_one(completion)
    next_points = user.points + resolved_points
    next_level = calculate_level_fn(next_points)
    update_user_account_state(user, points=next_points, level=next_level)
    return (
        {
            "message": "Daily task completed.",
            "completion": serialize_mongo_daily_task_completion(completion),
        },
        None,
        201,
    )


def save_fitness_steps(
    user,
    *,
    logged_on,
    steps_to_add,
    notes,
    calculate_points_fn,
    calculate_level_fn,
):
    existing = fitness_logs_collection().find_one(
        {"user_key": user_key(user), "logged_on": logged_on}
    )
    created = existing is None

    previous_steps = int(existing.get("steps", 0)) if existing else 0
    previous_points = int(existing.get("points_awarded", 0)) if existing else 0
    total_steps = previous_steps + int(steps_to_add)
    points_awarded = int(calculate_points_fn(total_steps))
    points_delta = points_awarded - previous_points
    timestamp = now_utc()

    if created:
        log = {
            "user_key": user_key(user),
            "logged_on": logged_on,
            "steps": total_steps,
            "source": "manual",
            "points_awarded": points_awarded,
            "notes": notes,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        fitness_logs_collection().insert_one(log)
    else:
        fitness_logs_collection().update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "steps": total_steps,
                    "source": "manual",
                    "points_awarded": points_awarded,
                    "notes": notes,
                    "updated_at": timestamp,
                }
            },
        )
        log = {
            **existing,
            "steps": total_steps,
            "source": "manual",
            "points_awarded": points_awarded,
            "notes": notes,
            "updated_at": timestamp,
        }

    next_points = max(0, user.points + points_delta)
    next_level = calculate_level_fn(next_points)
    update_user_account_state(user, points=next_points, level=next_level)

    return {
        "created": created,
        "pointsDelta": points_delta,
        "log": serialize_mongo_fitness_log(log),
    }


def fitness_history(user, limit=30):
    logs = (
        fitness_logs_collection()
        .find({"user_key": user_key(user)})
        .sort([("logged_on", -1), ("created_at", -1)])
        .limit(limit)
    )
    return {"logs": [serialize_mongo_fitness_log(log) for log in logs]}


def fitness_summary(user, daily_goal_steps):
    logs = list(fitness_logs_collection().find({"user_key": user_key(user)}))
    today_key = datetime.now().date().isoformat()
    today_log = next((log for log in logs if log["logged_on"] == today_key), None)
    return {
        "today": serialize_mongo_fitness_log(today_log) if today_log else None,
        "stats": {
            "totalLogs": len(logs),
            "totalSteps": sum(int(log.get("steps", 0)) for log in logs),
            "totalPointsAwarded": sum(
                int(log.get("points_awarded", 0)) for log in logs
            ),
            "bestDaySteps": max((int(log.get("steps", 0)) for log in logs), default=0),
            "goalDays": sum(
                1 for log in logs if int(log.get("steps", 0)) >= daily_goal_steps
            ),
        },
    }


def record_prize_wheel_spin(
    user,
    *,
    slice_id,
    prize_label,
    reward_type,
    reward_value,
    points_spent,
    reward_delta,
    calculate_level_fn,
):
    spin = {
        "user_key": user_key(user),
        "slice_id": int(slice_id),
        "points_spent": int(points_spent),
        "reward_type": reward_type,
        "reward_value": int(reward_value),
        "prize_label": prize_label,
        "created_at": now_utc(),
    }
    prize_wheel_spins_collection().insert_one(spin)
    next_points = max(0, user.points - int(points_spent) + int(reward_delta))
    next_level = calculate_level_fn(next_points)
    update_user_account_state(user, points=next_points, level=next_level)
    return {"spin": serialize_mongo_prize_wheel_spin(spin)}


def prize_wheel_history(user, limit=20):
    spins = (
        prize_wheel_spins_collection()
        .find({"user_key": user_key(user)})
        .sort("created_at", -1)
        .limit(limit)
    )
    return {"spins": [serialize_mongo_prize_wheel_spin(spin) for spin in spins], "prizes": []}
