const {
    fitnessRewardSettings,
    getFitnessLogsCollection,
    requireUser,
    serializeFitnessLog,
} = require("../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const logsCollection = await getFitnessLogsCollection();
        const logs = await logsCollection
            .find({ user_key: user.email })
            .sort({ logged_on: -1, created_at: -1 })
            .limit(30)
            .toArray();

        return res.status(200).json({
            logs: logs.map(serializeFitnessLog),
            rewardSettings: fitnessRewardSettings(),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not load the fitness history.",
        });
    }
}
