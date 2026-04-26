const {
    apiError,
    applyPointDelta,
    blackjackHandValue,
    requireUser,
    saveUser,
    serializeBlackjackState,
} = require("../../_lib/game");

function drawCard(state) {
    return state.deck.pop();
}

async function finalizeHand(user, state, outcome, payout, message) {
    state.status = "finished";
    state.outcome = outcome;
    state.payout = payout;
    state.net = payout - state.bet;
    delete user.blackjack_state;
    await applyPointDelta(user, payout);
    return serializeBlackjackState(state, user, true, message);
}

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const state = user.blackjack_state;
        if (!state || state.status !== "playing") {
            throw apiError(400, "Start a blackjack hand first.");
        }

        state.player.push(drawCard(state));
        if (blackjackHandValue(state.player) > 21) {
            return res.status(200).json(await finalizeHand(user, state, "bust", 0, "You busted. Dealer wins this hand."));
        }

        user.blackjack_state = state;
        await saveUser(user);
        return res.status(200).json(serializeBlackjackState(state, user, false, "Card dealt."));
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not deal a blackjack card.",
        });
    }
}
