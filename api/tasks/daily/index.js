const { DAILY_TASKS } = require("../../_lib/game");

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    return res.status(200).json({ tasks: DAILY_TASKS });
}
