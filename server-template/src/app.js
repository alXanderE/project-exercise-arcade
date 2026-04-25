import express from "express";
import morgan from "morgan";
import path from "path";
import { fileURLToPath } from "url";
import { User } from "./models/User.js";
import {
  buildSession,
  clearSession,
  generateSessionToken,
  getSessionCookieName,
  getSessionMaxAgeSeconds,
  hashPassword,
  parseCookies,
  serializeClearedSessionCookie,
  serializeSessionCookie,
  verifyPassword
} from "./auth.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.join(__dirname, "..", "public");

export function createApp() {
  const app = express();

  function sanitizeUser(user) {
    return {
      id: user._id.toString(),
      email: user.email,
      displayName: user.displayName
    };
  }

  async function getAuthenticatedUserFromRequest(req) {
    const cookies = parseCookies(req.headers.cookie);
    const sessionToken = cookies[getSessionCookieName()];

    if (!sessionToken) {
      return null;
    }

    return User.findOne({
      sessionToken,
      sessionExpiresAt: { $gt: new Date() }
    });
  }

  async function attachCurrentUser(req, _res, next) {
    try {
      req.currentUser = await getAuthenticatedUserFromRequest(req);
      next();
    } catch (error) {
      next(error);
    }
  }

  function requireAuth(req, res, next) {
    if (!req.currentUser) {
      return res.status(401).json({ message: "Authentication required." });
    }

    next();
  }

  app.use(morgan("dev"));
  app.use(express.json());
  app.use(express.static(publicDir));
  app.use(attachCurrentUser);

  app.get("/api/health", (_req, res) => {
    res.json({ ok: true });
  });

  app.get("/api/auth/session", (req, res) => {
    if (!req.currentUser) {
      return res.status(401).json({ message: "Not authenticated." });
    }

    res.json({ user: sanitizeUser(req.currentUser) });
  });

  app.post("/api/auth/signup", async (req, res, next) => {
    try {
      const { email = "", displayName = "", password = "" } = req.body;

      if (!email.trim() || !displayName.trim() || password.length < 6) {
        return res.status(400).json({
          message: "Email, display name, and a password with at least 6 characters are required."
        });
      }

      const normalizedEmail = email.trim().toLowerCase();
      const existingUser = await User.findOne({ email: normalizedEmail });

      if (existingUser) {
        return res.status(400).json({ message: "An account with that email already exists." });
      }

      const sessionToken = generateSessionToken();
      const session = buildSession(sessionToken);

      const user = await User.create({
        email: normalizedEmail,
        displayName: displayName.trim(),
        passwordHash: hashPassword(password),
        ...session
      });

      res.setHeader("Set-Cookie", serializeSessionCookie(sessionToken, getSessionMaxAgeSeconds()));
      res.status(201).json({ message: "Account created.", user: sanitizeUser(user) });
    } catch (error) {
      next(error);
    }
  });

  app.post("/api/auth/login", async (req, res, next) => {
    try {
      const { email = "", password = "" } = req.body;
      const user = await User.findOne({ email: email.trim().toLowerCase() });

      if (!user || !verifyPassword(password, user.passwordHash)) {
        return res.status(401).json({ message: "Invalid email or password." });
      }

      const sessionToken = generateSessionToken();
      const session = buildSession(sessionToken);
      user.sessionToken = session.sessionToken;
      user.sessionExpiresAt = session.sessionExpiresAt;
      await user.save();

      res.setHeader("Set-Cookie", serializeSessionCookie(sessionToken, getSessionMaxAgeSeconds()));
      res.json({ message: "Logged in.", user: sanitizeUser(user) });
    } catch (error) {
      next(error);
    }
  });

  app.post("/api/auth/logout", async (req, res, next) => {
    try {
      if (req.currentUser) {
        clearSession(req.currentUser);
        await req.currentUser.save();
      }

      res.setHeader("Set-Cookie", serializeClearedSessionCookie());
      res.status(204).send();
    } catch (error) {
      next(error);
    }
  });

  app.get("/api/protected", requireAuth, (req, res) => {
    res.json({
      message: "You reached a protected route.",
      user: sanitizeUser(req.currentUser)
    });
  });

  app.use((err, _req, res, _next) => {
    console.error(err);
    res.status(500).json({
      message: "Something went wrong.",
      detail: err.message
    });
  });

  app.get("*", (_req, res) => {
    res.sendFile(path.join(publicDir, "index.html"));
  });

  return app;
}
