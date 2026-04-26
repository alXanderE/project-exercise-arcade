export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    const cookieName = process.env.SESSION_COOKIE_NAME || "exercise_arcade_session";
    const cookieParts = [
        `${cookieName}=`,
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        "Max-Age=0",
    ];

    if (
        process.env.NODE_ENV === "production" ||
        String(process.env.VERCEL || "").toLowerCase() === "1"
    ) {
        cookieParts.push("Secure");
    }

    res.setHeader("Set-Cookie", cookieParts.join("; "));
    return res.status(200).json({ message: "Logged out." });
}
