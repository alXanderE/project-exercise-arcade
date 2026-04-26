const {
    apiError,
    applyPointDelta,
    blackjackHandValue,
    buildDeck,
    parseBody,
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
        const body = parseBody(req);
        const bet = Number.parseInt(body.bet || 0, 10);
        if (!Number.isFinite(bet) || bet < 1) {
            throw apiError(400, "Bet must be at least 1 coin.");
        }
        if ((Number.parseInt(user.points || 0, 10) || 0) < bet) {
            throw apiError(400, "Not enough coins for that blackjack bet.");
        }

        await applyPointDelta(user, -bet);
        const state = {
            bet,
            deck: buildDeck(),
            player: [],
            dealer: [],
            status: "playing",
        };
        state.player.push(drawCard(state), drawCard(state));
        state.dealer.push(drawCard(state), drawCard(state));
        user.blackjack_state = state;
        await saveUser(user);

        const playerTotal = blackjackHandValue(state.player);
        const dealerTotal = blackjackHandValue(state.dealer);
        if (playerTotal === 21 || dealerTotal === 21) {
            if (playerTotal === 21 && dealerTotal === 21) {
                return res.status(200).json(await finalizeHand(user, state, "push", bet, "Both hands hit 21. Bet returned."));
            }
            if (playerTotal === 21) {
                return res.status(200).json(await finalizeHand(user, state, "blackjack", bet * 3, "Blackjack! You beat the dealer."));
            }
            return res.status(200).json(await finalizeHand(user, state, "dealer_blackjack", 0, "Dealer has 21."));
        }

        return res.status(200).json(serializeBlackjackState(state, user, false, "Hit or stand."));
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not start blackjack.",
        });
    }
}
