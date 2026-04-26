from sqlalchemy import inspect, text

from .extensions import db


SQLITE_COLUMN_UPDATES = {
    "user": [
        ("session_token", "ALTER TABLE user ADD COLUMN session_token VARCHAR(128)"),
        (
            "session_expires_at",
            "ALTER TABLE user ADD COLUMN session_expires_at DATETIME",
        ),
        ("points", "ALTER TABLE user ADD COLUMN points INTEGER NOT NULL DEFAULT 0"),
        ("level", "ALTER TABLE user ADD COLUMN level INTEGER NOT NULL DEFAULT 1"),
    ],
    "habit": [
        ("difficulty", "ALTER TABLE habit ADD COLUMN difficulty VARCHAR(20)"),
        ("frequency", "ALTER TABLE habit ADD COLUMN frequency VARCHAR(20)"),
        (
            "target_per_week",
            "ALTER TABLE habit ADD COLUMN target_per_week INTEGER NOT NULL DEFAULT 3",
        ),
        (
            "points_reward",
            "ALTER TABLE habit ADD COLUMN points_reward INTEGER NOT NULL DEFAULT 10",
        ),
        (
            "streak_count",
            "ALTER TABLE habit ADD COLUMN streak_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "is_active",
            "ALTER TABLE habit ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
        ),
        ("last_completed_on", "ALTER TABLE habit ADD COLUMN last_completed_on DATE"),
    ],
    "fitness_log": [
        ("source", "ALTER TABLE fitness_log ADD COLUMN source VARCHAR(30)"),
        (
            "workout_minutes",
            "ALTER TABLE fitness_log ADD COLUMN workout_minutes INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "active_calories",
            "ALTER TABLE fitness_log ADD COLUMN active_calories INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "distance_miles",
            "ALTER TABLE fitness_log ADD COLUMN distance_miles FLOAT NOT NULL DEFAULT 0",
        ),
        (
            "points_awarded",
            "ALTER TABLE fitness_log ADD COLUMN points_awarded INTEGER NOT NULL DEFAULT 0",
        ),
        ("notes", "ALTER TABLE fitness_log ADD COLUMN notes VARCHAR(255)"),
    ],
}


def ensure_sqlite_schema():
    engine = db.engine
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, updates in SQLITE_COLUMN_UPDATES.items():
        if table_name not in existing_tables:
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, statement in updates:
            if column_name in existing_columns:
                continue

            db.session.execute(text(statement))

    db.session.commit()
