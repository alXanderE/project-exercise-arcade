# Server Template

This is a reusable Express + MongoDB + session-auth starter extracted from Habit Haven.

## Includes

- Express server
- MongoDB connection with Mongoose
- User model
- Cookie-based session auth
- Signup, login, logout, and session routes
- Protected example route

## Setup

1. Install dependencies:

```bash
npm install
```

2. Copy the environment file:

```bash
copy .env.example .env
```

3. Add your MongoDB URI to `.env`

4. Start the server:

```bash
npm run dev
```

## Main files

- `src/server.js`
- `src/app.js`
- `src/db.js`
- `src/auth.js`
- `src/models/User.js`

## Routes

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `GET /api/protected`
