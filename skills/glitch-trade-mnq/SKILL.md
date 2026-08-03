---
name: glitch-trade-mnq
description: Reason about MNQ regime, liquidity, structure, geometry, exposure, and active management from the current Glitch packet.
---

# Trade MNQ

## Read the sequence

Use the latest five one-minute frames as a path, not five isolated snapshots.
Read 1m in detail for timing, drift, microstructure, and noise; 5m for the local
auction and pivots; 15m/60m for regime, location, and remaining opportunity.
Higher-timeframe rows are live observations unless explicitly marked closed.
Missing evidence is uncertainty, not bullish or bearish evidence.

Combine price/volume, ATR and expansion, trend strength, VWAP and deviation,
cumulative delta and delta change, session and prior-session levels, Mag7
weighted movement, news sentiment, and event context. No single score chooses
direction. External equity/news context corroborates or contradicts MNQ; it
does not replace MNQ price and order-flow truth.

## Classify before choosing geometry

Choose the best-supported current regime:

- **Directional impulse:** displacement or developing displacement, aligned
  structure/order flow, and meaningful room toward the next liquidity objective.
- **Rotation/chop:** repeated rejection, overlapping ranges, weak follow
  through, and identifiable auction boundaries.
- **Transition/uncertainty:** breakout attempts, regime disagreement, event
  disturbance, or insufficiently stable boundaries.

These labels organize judgment; they are not entry gates. Evaluate long, short,
and flat symmetrically. State the likely next 5–15 minute path, contrary case,
invalidation, and what would materially change the decision. Full confirmation,
consecutive closes, a completed retest, and full multi-timeframe agreement are
not prerequisites for entry.

## Liquidity and structure

Treat swing highs/lows, equal highs/lows, session extremes, prior pivots,
unfilled displacement, rejection/acceptance, and stop runs as likely liquidity
locations—not magic levels. A sweep through an obvious level followed by
rejection can improve a reversal thesis; acceptance and continued displacement
can support continuation. Use order flow and subsequent price behavior to
distinguish them. Nasdaq commonly retraces and probes liquidity during a valid
move, so a one-bar wiggle or ordinary sweep is not structural invalidation.

## Select robust geometry

Define thesis invalidation first, then place the stop beyond the relevant
structure and expected sweep/noise zone. Account for observed 1m volatility,
the packet's age, ordinary one-minute snapshot-to-fill drift, and slippage.
Glitch preserves the chosen stop/target offsets from the model reference at
the actual fill, so choose distances that remain meaningful after execution.
Do not place protection inside ordinary noise or compress it to make the
reward/risk display attractive.

For a directional impulse, seek meaningful expansion rather than repeated
10-20-point oscillations. A roughly 40-point structural stop with objectives
around +60, +120, and +160 points is a useful MNQ calibration example when the
regime and pivots support it. It is not a minimum, maximum, ratio, or template.

For a clear rotational auction, a nearer objective and wider structural
invalidation can be rational because ordinary noise is more likely to visit the
target before escaping the range. Roughly 20 points of target with 40 points of
stop room is a calibration example, not a formula. A cosmetic 1:1 scalp inside
noise has no edge merely because both numbers are equal.

In transition, reduce initial exposure, define invalidation beyond the current
noise floor, and anticipate the most likely next move when the geometry is
bounded. Remain flat when the market is only overlapping mid-range noise, there
is no room to the next objective, or neither direction has a credible path.
Never use full confirmation as the entry requirement.

An anticipatory entry still needs meaningful location, room beyond ordinary
noise toward a credible objective, and invalidation beyond the noise or sweep
zone. If one is missing, prefer NOTHING. If recent own attempts show a loss or
nearby churn in the same zone, require materially new evidence such as a
reclaim, deeper sweep, or regime change before re-entry.

## Build exposure

Apply the operator capacity mandate to total open plus proposed MNQ master
exposure:

- 25k master: at most 1 contract.
- 250k master: at most 10 contracts.

Quantity remains adaptive within that ceiling. Compare one protected tranche,
TP1/TP2/TP3 scale-out, reserved capacity, a later independently protected
same-direction addition, and unchanged exposure. Examples include 3+3+3 or
2+2+2 distributions, with total exposure never above the mandate. Add only
when current evidence still supports the thesis and every new tranche receives
native protection. Never grid, martingale, average mechanically, or add merely
to recover a loss.

## Manage the thesis, not every tick

The positioned worker reviews every minute, but a review need not cause an
amendment. Hold through noise already allowed by the thesis. Compare current
acceptance/rejection, pivots, order flow, excursion, rollback, remaining
opportunity, and the prior `change_condition`. Use exact-leg `MOVE_STOP` or
`MOVE_TP`, same-direction protected additions, or full `EXIT` when evidence
changes. Do not trail into ordinary noise or repeatedly re-enter the same idea
at nearly the same level without a material change.

The 0.4%-2% daily objective evaluates the system across repeated outcomes. It
never justifies forcing a trade, oversized exposure, or treating a daily target
as guaranteed.
