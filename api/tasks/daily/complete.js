const {
    DAILY_TASKS,
    applyPointDelta,
    getTaskCompletionsCollection,
    parseBody,
    requireUser,
    serializeTaskCompletion,
    serializeUser,
    todayIso,
} = require("../../_lib/game");

function findTask(user, taskId) {
    const task = DAILY_TASKS.find((item) => item.id === taskId);
    if (task) {
        return task;
    }

    const customTasks = Array.isArray(user.custom_tasks) ? user.custom_tasks : [];
    const customTask = customTasks.find((item) => item.task_id === taskId);
    if (!customTask) {
        return null;
    }

    return {
        id: customTask.task_id,
        coin_reward: Number.parseInt(customTask.coin_reward || 0, 10) || 0,
    };
}

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const body = parseBody(req);
        const taskId = String(body.taskId || "").trim();
        const task = findTask(user, taskId);

        if (!task) {
            return res.status(404).json({ message: "Daily task not found." });
        }

        const completedOn = todayIso();
        const completionsCollection = await getTaskCompletionsCollection();
        const existing = await completionsCollection.findOne({
            user_key: user.email,
            task_id: task.id,
            completed_on: completedOn,
        });
        if (existing) {
            return res.status(400).json({
                message: "Daily task already completed today.",
                completion: serializeTaskCompletion(existing),
                user: serializeUser(user),
            });
        }

        const completion = {
            user_key: user.email,
            task_id: task.id,
            completed_on: completedOn,
            points_awarded: Number.parseInt(task.coin_reward || 0, 10) || 0,
            created_at: new Date(),
        };
        await completionsCollection.insertOne(completion);
        await applyPointDelta(user, completion.points_awarded);

        return res.status(201).json({
            message: "Daily task completed.",
            completion: serializeTaskCompletion(completion),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not complete the task.",
        });
    }
}
