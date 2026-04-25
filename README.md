# Exercise Arcade Python Server Template

This repo now contains a basic Flask starter for an exercise habit gamification app.

## What is included

- Flask app factory setup
- SQLite database via Flask-SQLAlchemy
- Cookie-based session auth
- User signup, login, logout, and session routes
- Habit creation and completion logging
- Points, levels, streak tracking, and a dashboard summary

## Quick start

1. Create a virtual environment and install dependencies.
2. Copy `.env.example` to `.env` if you want to override defaults.
3. Run the server:

```bash
python app.py
```

The database is created automatically on first start using `sqlite:///exercise_arcade.db`.

## API routes

- `GET /`
- `GET /api/health`
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `GET /api/habits`
- `POST /api/habits`
- `POST /api/habits/<habit_id>/log`
- `GET /api/dashboard`

## Example payloads

Create an account:

```json
{
  "email": "player@example.com",
  "displayName": "Player One",
  "password": "secret123"
}
```

Create a habit:

```json
{
  "name": "Morning Run",
  "description": "Run for at least 20 minutes",
  "difficulty": "medium",
  "frequency": "daily",
  "targetPerWeek": 4,
  "pointsReward": 15
}
```

Log a completion:

```json
{
  "completedOn": "2026-04-25",
  "durationMinutes": 25,
  "notes": "Felt strong today"
}
```
