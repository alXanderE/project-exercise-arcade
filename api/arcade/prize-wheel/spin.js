const {
    PRIZE_WHEEL_SPIN_COST,
    apiError,
    applyPointDelta,
    calculateSpinReward,
    getPrizeWheelSpinsCollection,
    requireUser,
    serializePrizeWheelSpin,
    serializeUser,
    wheelSlices,
    randomInt,
} = require("../../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        if ((Number.parseInt(user.points || 0, 10) || 0) < PRIZE_WHEEL_SPIN_COST) {
            throw apiError(400, "Not enough points to spin the prize wheel.");
        }

        const slices = wheelSlices();
        const winningSlice = slices[randomInt(slices.length)];
        const rewardDelta = calculateSpinReward(PRIZE_WHEEL_SPIN_COST, winningSlice);
        const timestamp = new Date();
        const spin = {
            user_key: user.email,
            slice_id: winningSlice.id,
            points_spent: PRIZE_WHEEL_SPIN_COST,
            reward_type: winningSlice.rewardType,
            reward_value: winningSlice.rewardValue,
            prize_label: winningSlice.label,
            created_at: timestamp,
        };

        const spinsCollection = await getPrizeWheelSpinsCollection();
        await spinsCollection.insertOne(spin);
        await applyPointDelta(user, -PRIZE_WHEEL_SPIN_COST + rewardDelta);

        return res.status(200).json({
            message: "Prize wheel spun.",
            spin: serializePrizeWheelSpin(spin),
            winningSlice,
            prize: null,
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not spin the prize wheel.",
        });
    }
}
