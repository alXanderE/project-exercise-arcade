const { MongoClient } = require("mongodb");

const mongoUri = (process.env.MONGODB_URI || "").trim();
const mongoDbName = (process.env.MONGODB_DB || "exercise_arcade").trim();
const usersCollectionName = (
    process.env.MONGODB_USERS_COLLECTION || "users"
).trim();
const sessionCookieName = (
    process.env.SESSION_COOKIE_NAME || "exercise_arcade_session"
).trim();

let cachedMongoClient = null;

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

function parseCookies(cookieHeader) {
    return String(cookieHeader || "")
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean)
        .reduce((cookies, part) => {
            const separatorIndex = part.indexOf("=");
            if (separatorIndex === -1) {
                return cookies;
            }
            const key = part.slice(0, separatorIndex).trim();
            const value = part.slice(separatorIndex + 1).trim();
            cookies[key] = decodeURIComponent(value);
            return cookies;
        }, {});
}

function normalizeSqlUserId(value) {
    if (typeof value === "number" && Number.isInteger(value) && value > 0) {
        return value;
    }

    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized || normalized === "null" || normalized === "none" || normalized === "undefined") {
        return null;
    }

    const parsed = Number.parseInt(normalized, 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function serializeUser(user) {
    const sqlUserId = normalizeSqlUserId(user.sql_user_id);
    return {
        id: sqlUserId || user.email,
        email: user.email,
        displayName: user.display_name,
        points: Number.parseInt(user.points || 0, 10) || 0,
        level: Number.parseInt(user.level || 1, 10) || 1,
    };
}

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({
            message: "Method not allowed.",
        });
    }

    try {
        const cookies = parseCookies(req.headers.cookie);
        const sessionToken = cookies[sessionCookieName];

        if (!sessionToken) {
            return res.status(401).json({
                message: "Authentication required.",
            });
        }

        const users = await getUsersCollection();
        const user = await users.findOne({
            session_token: sessionToken,
            session_expires_at: { $gt: new Date() },
        });

        if (!user) {
            return res.status(401).json({
                message: "Authentication required.",
            });
        }

        return res.status(200).json({
            user: serializeUser(user),
        });
    } catch (error) {
        console.error("Session lookup error:", error);
        return res.status(500).json({
            message: "Could not load the account session.",
        });
    }
}
