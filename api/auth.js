const { OAuth2Client } = require("google-auth-library");

const googleClientId = process.env.GOOGLE_CLIENT_ID;
const client = googleClientId ? new OAuth2Client(googleClientId) : null;

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
        return res.status(405).json({ success: false, message: "Method not allowed" });
    }

    if (!googleClientId || !client) {
        return res.status(500).json({
            success: false,
            message: "Google sign-in is not configured.",
        });
    }

    const { token } = req.body || {};

    if (!token) {
        return res.status(400).json({
            success: false,
            message: "Token is missing",
        });
    }

    try {
        const ticket = await client.verifyIdToken({
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

        return res.status(200).json({
            success: true,
            user: {
                id: payload.sub,
                email: payload.email,
                name: payload.name || payload.email,
                picture: payload.picture || null,
            },
        });
    } catch (error) {
        console.error("Verification error:", error);
        return res.status(401).json({
            success: false,
            message: "Invalid or expired token",
        });
    }
}
