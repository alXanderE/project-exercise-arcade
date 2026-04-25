# Exercise Arcade Python Server Template

This repo now contains a basic Flask starter for an exercise habit gamification app.

## What is included

- Front page with exercise tasks, custom workout cards, account auth, step logging, a prize wheel, and a live point counter
- Server-side daily task definitions in `habit_app/daily_tasks.py`
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
Open `http://127.0.0.1:5000` to see the front end page.

To add shared daily task cards, edit `habit_app/daily_tasks.py` and add another
`DailyTask(...)` entry to `TASK_LIBRARY`. Players can also add personal custom
workouts from the front end; those are saved in their browser.

## API routes

- `GET /`
- `GET /api/health`
- `GET /api/tasks/daily`
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `GET /api/habits`
- `POST /api/habits`
- `POST /api/habits/<habit_id>/log`
- `GET /api/dashboard`
- `POST /api/fitness/steps`
- `GET /api/fitness/summary`
- `GET /api/fitness/history`
- `GET /api/arcade/prize-wheel`
- `POST /api/arcade/prize-wheel/spin`
- `GET /api/arcade/prize-wheel/history`

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

Log daily steps:

```json
{
  "loggedOn": "2026-04-25",
  "steps": 8500,
  "notes": "Walked to class and back"
}
```

Manual fitness logging awards points that can be spent in the arcade. By default,
users earn 1 point per 1,000 steps, up to 20,000 rewarded steps per day, plus a
5 point bonus for reaching 10,000 steps.

Spin the prize wheel:

```http
POST /api/arcade/prize-wheel/spin
```

The server charges the configured spin cost, chooses a weighted prize slice, records the spin, applies the reward, and returns the winning slice so the client can animate the wheel toward the server-authoritative result. The front end uses `pixilart-drawing.png` for the wheel artwork.

Configure the spin cost with:

```bash
PRIZE_WHEEL_SPIN_COST=20
FITNESS_STEPS_PER_POINT=1000
FITNESS_DAILY_STEP_CAP=20000
FITNESS_DAILY_GOAL_STEPS=10000
FITNESS_DAILY_GOAL_BONUS=5
```
