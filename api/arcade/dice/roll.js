const {
    apiError,
    applyPointDelta,
    parseBody,
    requireUser,
    serializeUser,
    randomInt,
} = require("../../_lib/game");

function parsePositiveInt(value, fieldName, minimum, maximum) {
    const number = Number.parseInt(value, 10);
    if (!Number.isFinite(number)) {
        throw apiError(400, `${fieldName} must be a whole number.`);
    }
    if (number < minimum || (maximum !== undefined && number > maximum)) {
        throw apiError(400, `${fieldName} is out of range.`);
    }
    return number;
}

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ message: "Method not allowed." });
    }

    try {
        const user = await requireUser(req);
        const body = parseBody(req);
        const bets = [];

        const addBet = (kind, amountField, valueField, minimum, maximum) => {
          const amount = Number.parseInt(body[amountField] || 0, 10);
          if (!Number.isFinite(amount)) {
              throw apiError(400, `${amountField} must be a whole number.`);
          }
          if (amount < 0) {
              throw apiError(400, `${amountField} cannot be negative.`);
          }
          if (amount <= 0) {
              return;
          }
          bets.push({
              kind,
              amount,
              value: valueField ? parsePositiveInt(body[valueField], valueField, minimum, maximum) : null,
          });
        };

        addBet("die_one", "dieOneBet", "dieOneNumber", 1, 6);
        addBet("die_two", "dieTwoBet", "dieTwoNumber", 1, 6);
        addBet("total", "totalBet", "totalNumber", 2, 12);

        const parityBet = Number.parseInt(body.parityBet || 0, 10);
        if (Number.isFinite(parityBet) && parityBet > 0) {
            const parityChoice = String(body.parityChoice || "").toLowerCase();
            if (!["odd", "even"].includes(parityChoice)) {
                throw apiError(400, "Choose odd or even for the total.");
            }
            bets.push({ kind: "parity", amount: parityBet, value: parityChoice });
        }

        if (!bets.length) {
            throw apiError(400, "Place at least one dice bet.");
        }

        const totalWager = bets.reduce((sum, bet) => sum + bet.amount, 0);
        if ((Number.parseInt(user.points || 0, 10) || 0) < totalWager) {
            throw apiError(400, "Not enough coins for those dice bets.");
        }

        const dieOne = randomInt(6) + 1;
        const dieTwo = randomInt(6) + 1;
        const total = dieOne + dieTwo;
        const parity = total % 2 === 0 ? "even" : "odd";
        let winnings = 0;

        const results = bets.map((bet) => {
            let won = false;
            let multiplier = 0;
            if (bet.kind === "die_one") {
                won = dieOne === bet.value;
                multiplier = 6;
            } else if (bet.kind === "die_two") {
                won = dieTwo === bet.value;
                multiplier = 6;
            } else if (bet.kind === "total") {
                won = total === bet.value;
                multiplier = 10;
            } else if (bet.kind === "parity") {
                won = parity === bet.value;
                multiplier = 2;
            }
            const payout = won ? bet.amount * multiplier : 0;
            winnings += payout;
            return { ...bet, won, payout };
        });

        await applyPointDelta(user, -totalWager + winnings);

        return res.status(200).json({
            message: "Dice rolled.",
            roll: { dieOne, dieTwo, total, parity },
            bets: results,
            totalWager,
            winnings,
            net: winnings - totalWager,
            user: serializeUser(user),
        });
    } catch (error) {
        return res.status(error.status || 500).json({
            message: error.message || "Could not roll dice.",
        });
    }
}
