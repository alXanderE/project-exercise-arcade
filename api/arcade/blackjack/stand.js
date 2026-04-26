const {
    apiError,
    applyPointDelta,
    blackjackHandValue,
    requireUser,
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

        while (blackjackHandValue(state.dealer) < 17) {
            state.dealer.push(drawCard(state));
        }

        const playerTotal = blackjackHandValue(state.player);
        const dealerTotal = blackjackHandValue(state.dealer);
        if (dealerTotal > 21) {
            return res.status(200).json(await finalizeHand(user, state, "dealer_bust", state.bet * 2, "Dealer busted. You win."));
        }
        if (playerTotal > dealerTotal) {
            return res.status(200).json(await finalizeHand(user, state, "win", state.bet * 2, "You beat the dealer."));
        }
        if (playerTotal === dealerTotal) {
            return res.status(200).json(await finalizeHand(user, state, "push", state.bet, "Push. Your bet was returned."));
        }
        return res.status(200).json(await finalizeHand(user, state, "lose", 0, "Dealer wins this hand."));
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not finish the blackjack hand.",
        });
    }
}
