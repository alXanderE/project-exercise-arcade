from datetime import datetime, timezone

from .extensions import db


class TimestampMixin:
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class User(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    session_token = db.Column(db.String(128), unique=True, nullable=True, index=True)
    session_expires_at = db.Column(db.DateTime, nullable=True)
    points = db.Column(db.Integer, nullable=False, default=0)
    level = db.Column(db.Integer, nullable=False, default=1)

    habits = db.relationship(
        "Habit", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    habit_logs = db.relationship(
        "HabitLog", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    fitness_logs = db.relationship(
        "FitnessLog", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    daily_task_completions = db.relationship(
        "DailyTaskCompletion", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    prize_wheel_spins = db.relationship(
        "PrizeWheelSpin", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    prizes = db.relationship(
        "UserPrize", backref="user", lazy=True, cascade="all, delete-orphan"
    )


class Habit(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    difficulty = db.Column(db.String(20), nullable=False, default="medium")
    frequency = db.Column(db.String(20), nullable=False, default="daily")
    target_per_week = db.Column(db.Integer, nullable=False, default=3)
    points_reward = db.Column(db.Integer, nullable=False, default=10)
    streak_count = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_completed_on = db.Column(db.Date, nullable=True)

    logs = db.relationship(
        "HabitLog", backref="habit", lazy=True, cascade="all, delete-orphan"
    )


class HabitLog(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(
        db.Integer, db.ForeignKey("habit.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    completed_on = db.Column(db.Date, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    points_awarded = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("habit_id", "completed_on", name="uq_habit_completed_on"),
    )


class FitnessLog(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    logged_on = db.Column(db.Date, nullable=False, index=True)
    steps = db.Column(db.Integer, nullable=False)
    workout_minutes = db.Column(db.Integer, nullable=False, default=0)
    active_calories = db.Column(db.Integer, nullable=False, default=0)
    distance_miles = db.Column(db.Float, nullable=False, default=0.0)
    source = db.Column(db.String(30), nullable=False, default="manual")
    points_awarded = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "logged_on", name="uq_user_fitness_logged_on"),
    )


class DailyTaskCompletion(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    task_id = db.Column(db.String(80), nullable=False, index=True)
    completed_on = db.Column(db.Date, nullable=False, index=True)
    points_awarded = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "task_id",
            "completed_on",
            name="uq_user_daily_task_completed_on",
        ),
    )


class PrizeWheelSlice(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    color = db.Column(db.String(20), nullable=False, default="#22c55e")
    weight = db.Column(db.Integer, nullable=False, default=1)
    reward_type = db.Column(db.String(30), nullable=False, default="points")
    reward_value = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    spins = db.relationship("PrizeWheelSpin", backref="slice", lazy=True)


class PrizeWheelSpin(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    slice_id = db.Column(
        db.Integer,
        db.ForeignKey("prize_wheel_slice.id"),
        nullable=False,
        index=True,
    )
    points_spent = db.Column(db.Integer, nullable=False, default=0)
    reward_type = db.Column(db.String(30), nullable=False)
    reward_value = db.Column(db.Integer, nullable=False, default=0)
    prize_label = db.Column(db.String(120), nullable=False)


class UserPrize(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    spin_id = db.Column(
        db.Integer,
        db.ForeignKey("prize_wheel_spin.id"),
        nullable=True,
        index=True,
    )
    prize_type = db.Column(db.String(30), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    is_redeemed = db.Column(db.Boolean, nullable=False, default=False)

    spin = db.relationship("PrizeWheelSpin", backref="user_prizes", lazy=True)
