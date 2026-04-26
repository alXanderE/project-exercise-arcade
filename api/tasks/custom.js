const {
    apiError,
    parseBody,
    requireUser,
    saveUser,
    serializeCustomTask,
    serializeUser,
} = require("../_lib/game");
const crypto = require("crypto");

export default async function handler(req, res) {
    try {
        const user = await requireUser(req);

        if (req.method === "GET") {
            const tasks = Array.isArray(user.custom_tasks) ? user.custom_tasks : [];
            return res.status(200).json({
                tasks: tasks.map(serializeCustomTask),
                user: serializeUser(user),
            });
        }

        if (req.method !== "POST") {
            return res.status(405).json({ message: "Method not allowed." });
        }

        const body = parseBody(req);
        const title = String(body.title || "").trim();
        const category = String(body.category || "").trim();
        const description = String(body.description || "").trim();
        const coinReward = Math.min(
            20,
            Math.max(1, Number.parseInt(body.coinReward || 1, 10) || 1)
        );

        if (!title || !category || !description) {
            throw apiError(400, "Add a name, category, and description.");
        }

        const task = {
            task_id: `custom-${crypto.randomBytes(8).toString("hex")}`,
            title,
            category,
            description,
            coin_reward: coinReward,
            created_at: new Date(),
            updated_at: new Date(),
        };

        user.custom_tasks = Array.isArray(user.custom_tasks) ? user.custom_tasks : [];
        user.custom_tasks.push(task);
        await saveUser(user);

        return res.status(201).json({
            message: "Custom workout created.",
            task: serializeCustomTask(task),
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not save the custom workout.",
        });
    }
}
