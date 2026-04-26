const {
    requireUser,
    getTaskCompletionsCollection,
    serializeTaskCompletion,
    serializeUser,
    todayIso,
} = require("../../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const completionsCollection = await getTaskCompletionsCollection();
        const completedOn = todayIso();
        const completions = await completionsCollection
            .find({ user_key: user.email, completed_on: completedOn })
            .toArray();

        return res.status(200).json({
            completedTaskIds: completions.map((completion) => completion.task_id),
            completions: completions.map(serializeTaskCompletion),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not load task completions.",
        });
    }
}
