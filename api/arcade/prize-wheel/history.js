const {
    getPrizeWheelSpinsCollection,
    requireUser,
    serializePrizeWheelSpin,
} = require("../../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const spinsCollection = await getPrizeWheelSpinsCollection();
        const spins = await spinsCollection
            .find({ user_key: user.email })
            .sort({ created_at: -1 })
            .limit(20)
            .toArray();

        return res.status(200).json({
            spins: spins.map(serializePrizeWheelSpin),
            prizes: [],
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not load the prize wheel history.",
        });
    }
}
