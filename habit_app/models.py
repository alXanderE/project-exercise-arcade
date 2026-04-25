from datetime import datetime, timezone

from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
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

    habits = db.relationship("Habit", backref="user", lazy=True, cascade="all, delete-orphan")
    habit_logs = db.relationship("HabitLog", backref="user", lazy=True, cascade="all, delete-orphan")


class Habit(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    difficulty = db.Column(db.String(20), nullable=False, default="medium")
    frequency = db.Column(db.String(20), nullable=False, default="daily")
    target_per_week = db.Column(db.Integer, nullable=False, default=3)
    points_reward = db.Column(db.Integer, nullable=False, default=10)
    streak_count = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_completed_on = db.Column(db.Date, nullable=True)

    logs = db.relationship("HabitLog", backref="habit", lazy=True, cascade="all, delete-orphan")


class HabitLog(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habit.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    completed_on = db.Column(db.Date, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    points_awarded = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("habit_id", "completed_on", name="uq_habit_completed_on"),)
