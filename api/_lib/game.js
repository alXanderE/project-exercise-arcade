const crypto = require("crypto");
const { MongoClient } = require("mongodb");

const mongoUri = (process.env.MONGODB_URI || "").trim();
const mongoDbName = (process.env.MONGODB_DB || "exercise_arcade").trim();
const usersCollectionName = (
    process.env.MONGODB_USERS_COLLECTION || "users"
).trim();
const sessionCookieName = (
    process.env.SESSION_COOKIE_NAME || "exercise_arcade_session"
).trim();

const FITNESS_STEPS_PER_POINT = Number.parseInt(
    process.env.FITNESS_STEPS_PER_POINT || "1000",
    10
);
const FITNESS_DAILY_STEP_CAP = Number.parseInt(
    process.env.FITNESS_DAILY_STEP_CAP || "10000",
    10
);
const FITNESS_DAILY_GOAL_STEPS = Number.parseInt(
    process.env.FITNESS_DAILY_GOAL_STEPS || "10000",
    10
);
const FITNESS_DAILY_GOAL_BONUS = Number.parseInt(
    process.env.FITNESS_DAILY_GOAL_BONUS || "5",
    10
);
const PRIZE_WHEEL_SPIN_COST = Number.parseInt(
    process.env.PRIZE_WHEEL_SPIN_COST || "20",
    10
);

const DAILY_TASKS = [
    {
        id: "warmup-walk",
        title: "10 Minute Walk",
        category: "Warmup",
        description: "Loosen up, get outside, and pick up momentum before the heavier work.",
        coin_reward: 5,
        difficulty: "easy",
        frequency: "daily",
    },
    {
        id: "strength-circuit",
        title: "Bodyweight Circuit",
        category: "Strength",
        description: "Finish 3 rounds of squats, push-ups, and lunges with steady pacing.",
        coin_reward: 12,
        difficulty: "medium",
        frequency: "daily",
    },
    {
        id: "mobility-flow",
        title: "Mobility Flow",
        category: "Recovery",
        description: "Spend 12 minutes opening hips, shoulders, and hamstrings.",
        coin_reward: 8,
        difficulty: "easy",
        frequency: "daily",
    },
];

const POSITIONAL_WHEEL_RULES = [
    { label: "Red", description: "Get the full spin cost back.", color: "#ff001c", rewardType: "spin_multiplier", rewardValue: 100 },
    { label: "Orange", description: "Get half the spin cost back.", color: "#ffae00", rewardType: "spin_multiplier", rewardValue: 50 },
    { label: "Yellow", description: "Get 10% of the spin cost back.", color: "#fffb00", rewardType: "spin_multiplier", rewardValue: 10 },
    { label: "Green", description: "No coins back.", color: "#00f932", rewardType: "spin_multiplier", rewardValue: 0 },
    { label: "Light Blue", description: "Get twice the spin cost back.", color: "#4fd8ff", rewardType: "spin_multiplier", rewardValue: 200 },
    { label: "Dark Blue", description: "Get 20% of the spin cost back.", color: "#006dff", rewardType: "spin_multiplier", rewardValue: 20 },
    { label: "Dark Purple", description: "Lose the spin cost and the same amount again.", color: "#4c1d95", rewardType: "spin_multiplier", rewardValue: -100 },
    { label: "Pink", description: "Get three times the spin cost back.", color: "#fb00ff", rewardType: "spin_multiplier", rewardValue: 300 },
];

const CARD_SUITS = ["S", "H", "D", "C"];
const CARD_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

let cachedMongoClient = null;

function nowUtc() {
    return new Date();
}

function todayIso() {
    return nowUtc().toISOString().slice(0, 10);
}

function calculateLevel(points) {
    return Math.max(1, Math.floor((Number(points) || 0) / 100) + 1);
}

function fitnessRewardSettings() {
    return {
        stepsPerPoint: FITNESS_STEPS_PER_POINT,
        dailyStepCap: FITNESS_DAILY_STEP_CAP,
        dailyGoalSteps: FITNESS_DAILY_GOAL_STEPS,
        dailyGoalBonus: FITNESS_DAILY_GOAL_BONUS,
    };
}

function calculateFitnessPoints(steps) {
    const safeSteps = Math.max(0, Number.parseInt(steps || 0, 10) || 0);
    const cappedSteps = Math.min(safeSteps, FITNESS_DAILY_STEP_CAP);
    let points = Math.floor(cappedSteps / FITNESS_STEPS_PER_POINT);
    if (safeSteps >= FITNESS_DAILY_GOAL_STEPS) {
        points += FITNESS_DAILY_GOAL_BONUS;
    }
    return points;
}

async function getMongoClient() {
    if (!mongoUri) {
        throw new Error("MONGODB_URI is not configured.");
    }
    if (!cachedMongoClient) {
        cachedMongoClient = new MongoClient(mongoUri);
        await cachedMongoClient.connect();
    }
    return cachedMongoClient;
}

async function getDb() {
    const client = await getMongoClient();
    return client.db(mongoDbName);
}

async function getUsersCollection() {
    const db = await getDb();
    return db.collection(usersCollectionName);
}

async function getFitnessLogsCollection() {
    const db = await getDb();
    return db.collection("fitness_logs");
}

async function getTaskCompletionsCollection() {
    const db = await getDb();
    return db.collection("daily_task_completions");
}

async function getPrizeWheelSpinsCollection() {
    const db = await getDb();
    return db.collection("prize_wheel_spins");
}

function parseCookies(cookieHeader) {
    return String(cookieHeader || "")
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean)
        .reduce((cookies, part) => {
            const separatorIndex = part.indexOf("=");
            if (separatorIndex === -1) {
                return cookies;
            }
            const key = part.slice(0, separatorIndex).trim();
            const value = part.slice(separatorIndex + 1).trim();
            cookies[key] = decodeURIComponent(value);
            return cookies;
        }, {});
}

function normalizeEmail(email) {
    return String(email || "").trim().toLowerCase();
}

function serializeUser(user) {
    return {
        id: user.sql_user_id || user.email,
        email: user.email,
        displayName: user.display_name,
        points: Number.parseInt(user.points || 0, 10) || 0,
        level: Number.parseInt(user.level || 1, 10) || 1,
    };
}

function serializeFitnessLog(log) {
    return {
        id: String(log._id || `${log.user_key}-${log.logged_on}`),
        loggedOn: log.logged_on,
        steps: Number.parseInt(log.steps || 0, 10) || 0,
        source: log.source || "manual",
        pointsAwarded: Number.parseInt(log.points_awarded || 0, 10) || 0,
        notes: log.notes || "",
        createdAt: new Date(log.created_at || nowUtc()).toISOString(),
        updatedAt: new Date(log.updated_at || nowUtc()).toISOString(),
    };
}

function serializeTaskCompletion(completion) {
    return {
        id: String(completion._id || `${completion.user_key}-${completion.task_id}-${completion.completed_on}`),
        taskId: completion.task_id,
        completedOn: completion.completed_on,
        pointsAwarded: Number.parseInt(completion.points_awarded || 0, 10) || 0,
        createdAt: new Date(completion.created_at || nowUtc()).toISOString(),
    };
}

function serializeCustomTask(task) {
    return {
        id: task.task_id,
        title: task.title,
        category: task.category,
        description: task.description,
        coin_reward: Number.parseInt(task.coin_reward || 0, 10) || 0,
        difficulty: "custom",
        frequency: "daily",
        is_custom: true,
    };
}

function serializePrizeWheelSpin(spin) {
    return {
        id: String(spin._id || `${spin.user_key}-${spin.created_at}`),
        sliceId: Number.parseInt(spin.slice_id || 0, 10) || 0,
        pointsSpent: Number.parseInt(spin.points_spent || 0, 10) || 0,
        rewardType: spin.reward_type,
        rewardValue: Number.parseInt(spin.reward_value || 0, 10) || 0,
        prizeLabel: spin.prize_label,
        createdAt: new Date(spin.created_at || nowUtc()).toISOString(),
    };
}

function wheelSlices() {
    return Array.from({ length: 16 }, (_, displayOrder) => {
        const rule = POSITIONAL_WHEEL_RULES[displayOrder % POSITIONAL_WHEEL_RULES.length];
        return {
            id: displayOrder + 1,
            label: rule.label,
            description: rule.description,
            color: rule.color,
            weight: 1,
            rewardType: rule.rewardType,
            rewardValue: rule.rewardValue,
            isActive: true,
            displayOrder,
        };
    });
}

function calculateSpinReward(pointsSpent, slice) {
    return Math.floor(pointsSpent * (Number(slice.rewardValue || 0) / 100));
}

function randomInt(max) {
    return crypto.randomInt(max);
}

function buildDeck() {
    const deck = [];
    for (const suit of CARD_SUITS) {
        for (const rank of CARD_RANKS) {
            deck.push({ rank, suit });
        }
    }
    for (let index = deck.length - 1; index > 0; index -= 1) {
        const swapIndex = randomInt(index + 1);
        [deck[index], deck[swapIndex]] = [deck[swapIndex], deck[index]];
    }
    return deck;
}

function blackjackCardValue(card) {
    if (card.rank === "A") {
        return 11;
    }
    if (["J", "Q", "K"].includes(card.rank)) {
        return 10;
    }
    return Number.parseInt(card.rank, 10);
}

function blackjackHandValue(hand) {
    let total = hand.reduce((sum, card) => sum + blackjackCardValue(card), 0);
    let aces = hand.filter((card) => card.rank === "A").length;
    while (total > 21 && aces > 0) {
        total -= 10;
        aces -= 1;
    }
    return total;
}

function serializeBlackjackCard(card) {
    return {
        rank: card.rank,
        suit: card.suit,
        label: `${card.rank} of ${card.suit}`,
    };
}

function serializeBlackjackState(state, user, revealDealer = false, message = "") {
    const dealerCards = revealDealer ? state.dealer : state.dealer.slice(0, 1);
    return {
        bet: state.bet,
        playerCards: state.player.map(serializeBlackjackCard),
        dealerCards: dealerCards.map(serializeBlackjackCard),
        dealerHiddenCount: Math.max(0, state.dealer.length - dealerCards.length),
        playerTotal: blackjackHandValue(state.player),
        dealerTotal: revealDealer ? blackjackHandValue(state.dealer) : null,
        status: state.status,
        outcome: state.outcome || null,
        payout: Number.parseInt(state.payout || 0, 10) || 0,
        net: Number.parseInt(state.net || -state.bet, 10) || 0,
        message,
        user: serializeUser(user),
    };
}

function parseBody(req) {
    if (!req.body) {
        return {};
    }
    if (typeof req.body === "object") {
        return req.body;
    }
    try {
        return JSON.parse(req.body);
    } catch {
        return {};
    }
}

function apiError(status, message) {
    const error = new Error(message);
    error.status = status;
    return error;
}

async function requireUser(req) {
    const cookies = parseCookies(req.headers.cookie);
    const sessionToken = cookies[sessionCookieName];
    if (!sessionToken) {
        throw apiError(401, "Authentication required.");
    }

    const users = await getUsersCollection();
    const user = await users.findOne({
        session_token: sessionToken,
        session_expires_at: { $gt: nowUtc() },
    });
    if (!user) {
        throw apiError(401, "Authentication required.");
    }
    return user;
}

async function saveUser(user) {
    const users = await getUsersCollection();
    user.updated_at = nowUtc();
    await users.updateOne(
        { email: normalizeEmail(user.email) },
        { $set: user }
    );
    return user;
}

async function applyPointDelta(user, delta) {
    user.points = Math.max(0, (Number.parseInt(user.points || 0, 10) || 0) + delta);
    user.level = calculateLevel(user.points);
    await saveUser(user);
    return user;
}

module.exports = {
    DAILY_TASKS,
    PRIZE_WHEEL_SPIN_COST,
    apiError,
    applyPointDelta,
    calculateFitnessPoints,
    calculateLevel,
    calculateSpinReward,
    fitnessRewardSettings,
    getFitnessLogsCollection,
    getPrizeWheelSpinsCollection,
    getTaskCompletionsCollection,
    getUsersCollection,
    normalizeEmail,
    nowUtc,
    parseBody,
    requireUser,
    saveUser,
    serializeBlackjackState,
    serializeCustomTask,
    serializeFitnessLog,
    serializePrizeWheelSpin,
    serializeTaskCompletion,
    serializeUser,
    todayIso,
    wheelSlices,
    buildDeck,
    blackjackHandValue,
    randomInt,
};
