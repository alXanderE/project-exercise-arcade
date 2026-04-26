const {
    apiError,
    applyPointDelta,
    calculateFitnessPoints,
    fitnessRewardSettings,
    getFitnessLogsCollection,
    parseBody,
    requireUser,
    serializeFitnessLog,
    serializeUser,
} = require("../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const body = parseBody(req);
        const loggedOn = String(body.loggedOn || "").trim();
        const stepsToAdd = Number.parseInt(body.steps || 0, 10);
        const notes = String(body.notes || "").trim();

        if (!/^\d{4}-\d{2}-\d{2}$/.test(loggedOn)) {
            throw apiError(400, "loggedOn must use YYYY-MM-DD format.");
        }
        if (!Number.isFinite(stepsToAdd)) {
            throw apiError(400, "steps must be a whole number.");
        }
        if (stepsToAdd < 0) {
            throw apiError(400, "steps cannot be negative.");
        }

        const logsCollection = await getFitnessLogsCollection();
        const existing = await logsCollection.findOne({
            user_key: user.email,
            logged_on: loggedOn,
        });
        const created = !existing;
        const previousSteps = Number.parseInt(existing?.steps || 0, 10) || 0;
        const previousPoints = Number.parseInt(existing?.points_awarded || 0, 10) || 0;
        const totalSteps = previousSteps + stepsToAdd;
        const pointsAwarded = calculateFitnessPoints(totalSteps);
        const pointsDelta = pointsAwarded - previousPoints;
        const timestamp = new Date();

        if (existing) {
            await logsCollection.updateOne(
                { _id: existing._id },
                {
                    $set: {
                        steps: totalSteps,
                        source: "manual",
                        points_awarded: pointsAwarded,
                        notes,
                        updated_at: timestamp,
                    },
                }
            );
        } else {
            await logsCollection.insertOne({
                user_key: user.email,
                logged_on: loggedOn,
                steps: totalSteps,
                source: "manual",
                points_awarded: pointsAwarded,
                notes,
                created_at: timestamp,
                updated_at: timestamp,
            });
        }

        await applyPointDelta(user, pointsDelta);
        const log = await logsCollection.findOne({
            user_key: user.email,
            logged_on: loggedOn,
        });

        return res.status(created ? 201 : 200).json({
            message: "Fitness steps logged.",
            created,
            pointsDelta: pointsDelta,
            log: serializeFitnessLog(log),
            rewardSettings: fitnessRewardSettings(),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not save the fitness steps.",
        });
    }
}
