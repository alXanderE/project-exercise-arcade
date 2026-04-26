const {
    PRIZE_WHEEL_SPIN_COST,
    requireUser,
    serializeUser,
    wheelSlices,
} = require("../../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        return res.status(200).json({
            spinCost: PRIZE_WHEEL_SPIN_COST,
            slices: wheelSlices(),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not load the prize wheel.",
        });
    }
}
