const crypto = require("crypto");
const { OAuth2Client } = require("google-auth-library");
const { MongoClient } = require("mongodb");

const googleClientId = (process.env.GOOGLE_CLIENT_ID || "").trim();
const mongoUri = (process.env.MONGODB_URI || "").trim();
const mongoDbName = (process.env.MONGODB_DB || "exercise_arcade").trim();
const usersCollectionName = (
    process.env.MONGODB_USERS_COLLECTION || "users"
).trim();
const sessionCookieName = (
    process.env.SESSION_COOKIE_NAME || "exercise_arcade_session"
).trim();
const sessionDays = Number.parseInt(process.env.SESSION_DAYS || "30", 10);

const googleClient = googleClientId ? new OAuth2Client(googleClientId) : null;

let cachedMongoClient = null;

function nowUtc() {
    return new Date();
}

function maxAgeSeconds() {
    return Math.max(1, sessionDays) * 24 * 60 * 60;
}

async function getUsersCollection() {
    if (!mongoUri) {
        throw new Error("MONGODB_URI is not configured.");
    }

    if (!cachedMongoClient) {
        cachedMongoClient = new MongoClient(mongoUri);
        await cachedMongoClient.connect();
    }

    return cachedMongoClient.db(mongoDbName).collection(usersCollectionName);
}

function normalizeEmail(email) {
    return String(email || "").trim().toLowerCase();
}

function baseDisplayName(name, email) {
    const candidate = String(name || "").trim() || normalizeEmail(email).split("@")[0];
    return candidate.slice(0, 120) || "Player";
}

async function uniqueDisplayName(users, name, email) {
    const baseName = baseDisplayName(name, email);
    const normalizedEmail = normalizeEmail(email);

    const existingBase = await users.findOne({
        display_name_lower: baseName.toLowerCase(),
        email: { $ne: normalizedEmail },
    });
    if (!existingBase) {
        return baseName;
    }

    let counter = 2;
    while (true) {
        const suffix = `-${counter}`;
        const candidate = `${baseName.slice(0, Math.max(1, 120 - suffix.length))}${suffix}`;
        const existing = await users.findOne({
            display_name_lower: candidate.toLowerCase(),
            email: { $ne: normalizedEmail },
        });
        if (!existing) {
            return candidate;
        }
        counter += 1;
    }
}

function placeholderPasswordHash(googleSub) {
    return `google-oauth:${googleSub}`;
}

function buildSession() {
    const sessionToken = crypto.randomBytes(32).toString("hex");
    const expiresAt = new Date(Date.now() + maxAgeSeconds() * 1000);
    return { sessionToken, expiresAt };
}

function setSessionCookie(res, sessionToken) {
    const cookieParts = [
        `${sessionCookieName}=${sessionToken}`,
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        `Max-Age=${maxAgeSeconds()}`,
    ];

    if (
        process.env.NODE_ENV === "production" ||
        String(process.env.VERCEL || "").toLowerCase() === "1"
    ) {
        cookieParts.push("Secure");
    }

    res.setHeader("Set-Cookie", cookieParts.join("; "));
}

function serializeUser(user) {
    return {
        id: user.sql_user_id || user.email,
        email: user.email,
        displayName: user.display_name,
        points: Number.parseInt(user.points || 0, 10) || 0,
        level: Number.parseInt(user.level || 1, 10) || 1,
    };
}

async function upsertGoogleUser(payload) {
    const users = await getUsersCollection();
    const email = normalizeEmail(payload.email);
    const timestamp = nowUtc();
    const existingUser = await users.findOne({ email });
    const { sessionToken, expiresAt } = buildSession();

    if (existingUser) {
        const nextDisplayName =
            existingUser.display_name ||
            (await uniqueDisplayName(users, payload.name, email));

        await users.updateOne(
            { email },
            {
                $set: {
                    display_name: nextDisplayName,
                    display_name_lower: nextDisplayName.toLowerCase(),
                    session_token: sessionToken,
                    session_expires_at: expiresAt,
                    updated_at: timestamp,
                    auth_provider: "google",
                    google_sub: payload.sub,
                    picture: payload.picture || null,
                },
                $setOnInsert: {
                    created_at: timestamp,
                },
            }
        );

        const updatedUser = await users.findOne({ email });
        return { user: updatedUser, sessionToken };
    }

    const displayName = await uniqueDisplayName(users, payload.name, email);
    const user = {
        email,
        display_name: displayName,
        display_name_lower: displayName.toLowerCase(),
        password_hash: placeholderPasswordHash(payload.sub),
        sql_user_id: null,
        points: 0,
        level: 1,
        created_at: timestamp,
        updated_at: timestamp,
        session_token: sessionToken,
        session_expires_at: expiresAt,
        auth_provider: "google",
        google_sub: payload.sub,
        picture: payload.picture || null,
    };

    await users.insertOne(user);
    return { user, sessionToken };
}

export default async function handler(req, res) {
    if (req.method === "GET") {
        if (!googleClientId) {
            return res.status(500).json({
                success: false,
                message: "GOOGLE_CLIENT_ID is not configured.",
            });
        }

        return res.status(200).json({
            success: true,
            clientId: googleClientId,
        });
    }

    if (req.method !== "POST") {
        return res.status(405).json({
            success: false,
            message: "Method not allowed",
        });
    }

    if (!googleClientId || !googleClient) {
        return res.status(500).json({
            success: false,
            message: "Google sign-in is not configured.",
        });
    }

    if (!mongoUri) {
        return res.status(500).json({
            success: false,
            message: "MONGODB_URI is not configured.",
        });
    }

    const { token } = req.body || {};
    if (!token) {
        return res.status(400).json({
            success: false,
            message: "Token is missing.",
        });
    }

    try {
        const ticket = await googleClient.verifyIdToken({
            idToken: token,
            audience: googleClientId,
        });
        const payload = ticket.getPayload();

        if (!payload || !payload.sub || !payload.email) {
            return res.status(401).json({
                success: false,
                message: "Google account data was incomplete.",
            });
        }

        const { user, sessionToken } = await upsertGoogleUser(payload);
        setSessionCookie(res, sessionToken);

        return res.status(200).json({
            success: true,
            message: "Logged in with Google.",
            user: serializeUser(user),
        });
    } catch (error) {
        console.error("Google auth error:", error);
        return res.status(401).json({
            success: false,
            message: "Invalid or expired token.",
        });
    }
}
