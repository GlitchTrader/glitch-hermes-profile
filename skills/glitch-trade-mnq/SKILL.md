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

## Use the session story

`market_structure_observations` in execution_scope is your artificial session
memory: deterministic measurements accumulated across the whole session, because
you remember nothing between cycles. When present, trust its counts and read it
before the five frames; when absent or warming up, it is neutral evidence.

- **Location first.** `position_in_range`, `at_range_edge`, `breakout_state`,
  and `key_levels` with touch counts tell you where the auction is. Mid-range
  in rotation with low ADX is the prime NOTHING zone; edges, accepted breaks,
  and swept-then-reclaimed levels are where asymmetry lives.
- **Acceptance versus sweep.** `accepted_above/below` means consecutive closes
  beyond the box; `failed_break_*` means the level swept and price came back.
  Trade continuation on acceptance, reversal hypotheses on failed breaks —
  never a breakout entry on the first poke alone.
- **Respect your own history.** `own_recent_attempts` lists your last completed
  trades and losses near the current price. Re-entering an idea that just
  stopped, at nearly the same level, requires materially changed evidence —
  a reclaimed level, a fresh sweep, a regime flip — not hope.
- **Structure counts.** `swings_1m` and `structure_bias` carry the HH/HL/LH/LL
  story: an LH after an HH sequence is an exhaustion hypothesis; an LL after
  HLs is a micro break of structure. One label is never a trend change by
  itself; `mixed` means honest ambiguity, and forcing a count is worse.
- **Noise floor.** Compare stop distance to `atr_1m` and the range width. A
  stop inside one ATR of ordinary noise is a donation, not protection. Compare
  room to your invalidation against room to the next key level before reward.

Labels can be wrong. They organize attention; they never select the action.
Consult `glitch-market-structure` for the fuller playbook vocabulary.

## Classify before choosing geometry

Choose the best-supported current regime:

- **Directional impulse:** displacement, acceptance, aligned structure/order
  flow, and meaningful room toward the next liquidity objective.
- **Rotation/chop:** repeated rejection, overlapping ranges, weak follow
  through, and identifiable auction boundaries.
- **Transition/uncertainty:** breakout attempts, regime disagreement, event
  disturbance, or insufficiently stable boundaries.

These labels organize judgment; they are not entry gates. Evaluate long, short,
and flat symmetrically. State the likely path, contrary case, invalidation, and
what would materially change the decision.

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

Calibrate every distance to current volatility before liking it: with 1m ATR
near 10 points, a 10-point move is nothing and 20 points is ordinary noise on
today's Nasdaq — protection or targets inside that band are donations. A
roughly 40-point structural stop, defended once to about 50 only when the
original invalidation proves to sit inside the sweep zone and the thesis is
intact, is a current calibration example — never serial widening to avoid
taking a loss.

In transition, reduce exposure, stage it, wait for better location, or remain
flat according to evidence. Never force a directional or mean-reversion
geometry onto an unclear auction.

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

Averaging in and out within one thesis is available on capacity-rich masters.
Staging a planned second tranche at a better price is rational when the thesis
and the original invalidation are unchanged: for example, long 3 contracts,
add 3 more roughly 20 points lower, one structural stop beyond the sweep zone
covering both. Scale out into favorable movement instead of exiting
all-or-nothing: shed contracts progressively — some at +20, more at +40, the
remainder ladders through +60/+80/+100 and beyond as the move matures. Both
directions are calibration examples conditioned on a still-valid thesis, never
a mechanical program, and every tranche keeps independent native protection.

## Manage the thesis, not every tick

The positioned worker reviews every minute, but a review need not cause an
amendment. Hold through noise already allowed by the thesis. Compare current
acceptance/rejection, pivots, order flow, excursion, rollback, remaining
opportunity, and the prior `change_condition`. Use exact-leg `MOVE_STOP` or
`MOVE_TP`, same-direction protected additions, or full `EXIT` when evidence
changes. Do not trail into ordinary noise or repeatedly re-enter the same idea
at nearly the same level without a material change.

Be a ruthless profit-taker. If the thesis is weakening, exit — do not
negotiate with it. When price has traveled half or more of the way to a
target and momentum stalls, taking profit aggressively beats hoping: a mature
winner that round-trips into its stop, or gets babysat to a breakeven exit
after hours in the trade, is a worse error than a slightly early exit. Bank
the money; leave nothing on the table waiting for a perfect exit.

The 0.4%-2% daily objective evaluates the system across repeated outcomes. It
never justifies forcing a trade, oversized exposure, or treating a daily target
as guaranteed.
