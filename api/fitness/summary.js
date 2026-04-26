const {
    fitnessRewardSettings,
    getFitnessLogsCollection,
    requireUser,
    serializeFitnessLog,
    serializeUser,
    todayIso,
} = require("../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const logsCollection = await getFitnessLogsCollection();
        const logs = await logsCollection.find({ user_key: user.email }).toArray();
        const todayLog = logs.find((log) => log.logged_on === todayIso()) || null;

        return res.status(200).json({
            today: todayLog ? serializeFitnessLog(todayLog) : null,
            stats: {
                totalLogs: logs.length,
                totalSteps: logs.reduce((sum, log) => sum + (Number.parseInt(log.steps || 0, 10) || 0), 0),
                totalPointsAwarded: logs.reduce((sum, log) => sum + (Number.parseInt(log.points_awarded || 0, 10) || 0), 0),
                bestDaySteps: logs.reduce((max, log) => Math.max(max, Number.parseInt(log.steps || 0, 10) || 0), 0),
                goalDays: logs.filter((log) => (Number.parseInt(log.steps || 0, 10) || 0) >= fitnessRewardSettings().dailyGoalSteps).length,
            },
            rewardSettings: fitnessRewardSettings(),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not load the fitness summary.",
        });
    }
}
