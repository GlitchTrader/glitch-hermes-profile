---
name: glitch-market-structure
description: Consultable market-structure playbook — range and breakout participation, swing structure, liquidity, FVG, fib and ATR framing, and pattern base rates. Reference vocabulary for interpreting market_structure_observations; never a rule set.
---

# Market Structure Playbook

This is reference vocabulary for reading `market_structure_observations`. It is
consulted, not executed: every idea here is a comparable hypothesis for the
thesis, never a checklist, gate, or template. It is not loaded on the trading
hot path; retrieve it when debriefing, learning, or asked.

## Regime decides which playbook applies

- **Range (rotation):** low ADX, box width near ATR, repeated edge rejections.
  Participation logic: fade edges toward mid/other edge, invalidation *outside*
  the box beyond the sweep zone — never inside it. Mid-range entries have the
  worst location on the chart; passing is a position.
- **Directional (trend day):** high ADX, acceptance beyond prior box, HH/HL or
  LL/LH sequence with follow-through. Participation logic: join pullbacks into
  structure (prior break level, HL/LH, unfilled imbalance), stop beyond the
  swing that would break the sequence, targets at the next liquidity objective
  — not at the first 10-point oscillation. Trend days punish fading; repeated
  counter-trend fades against acceptance are how a whole session churns away.
- **Transition:** breakout attempts, disagreeing timeframes, event windows.
  Smaller, staged, later, or flat. Forcing either playbook here is the error.

## Acceptance versus sweep — the one distinction that pays

A level can be *broken* (consecutive closes beyond, holds on retest) or
*swept* (poked, liquidity taken, price reclaimed). The same print means
opposite things: acceptance supports continuation; a sweep-and-reclaim
supports reversal back through the range. The first touch of a breakout is
unproven; the retest that holds is the evidence. Equal highs/lows and obvious
session extremes are liquidity magnets — expect the sweep before the move.

## Swing structure counts

HH-HL-HH-HL is a trend telling you it is healthy. The first LH after an HH run
is exhaustion evidence, not proof. LL after HLs is a micro break of structure
(BOS); the pullback after a BOS toward the broken area is the classic
continuation location. A change of character (CHoCH) needs both the label and
follow-through. `structure_bias: mixed` is honest chop — the count does not owe
you a story every minute.

## Imbalance (FVG) and levels

An unfilled three-bar gap marks where price moved too fast for two-sided
trade. It is a candidate reaction zone: confluence with a key level or a
pullback-in-trend improves a thesis; an FVG alone is not an entry. Mitigation
(partial fill) then rejection is the useful behavior to watch. Fib retraces
of the impulse or range (38.2/50/61.8) and measured moves are *target and
pullback candidates* to compare against structure — never automatic prices.

## ATR framing for geometry

Express stop and target distances in ATR units before liking them. A stop
under 1× ATR(1m) of ordinary noise gets hit by randomness; the sweep zone
beyond a level is usually part of the noise. Compare room-to-invalidation
against room-to-next-objective: if the box is 40 points wide and ATR(60m) is
similar, a 60-point target inside the range needs the range to break first —
say so in the thesis or choose the nearer objective.

## Pattern base rates — weak priors only

Reported intraday base rates (unverified in our market, timeframe, and
execution; treat as folklore-grade priors that never outrank current
structure): inside-bar continuation ~86%; ascending triangle ~83% break-even /
~70% target; descending triangle ~87% / ~50%; initial-balance breakout ~78% in
volatile sessions; symmetrical triangle ~75% / ~58%; opening-candle
continuation ~70%. Use pattern names as context labels in the audit, with the
regime deciding whether continuation or reversal logic applies.

## Re-entry and churn discipline

A stop-out is information: the location failed at that time. Re-entering the
same idea at nearly the same level needs materially new evidence — a reclaim,
a deeper sweep, a regime change — otherwise the second entry is paying twice
for one opinion. Three stops in the same zone in under an hour is the market
saying the read is wrong; the correct trade is usually the opposite one or
none. Surfing the bigger wave means fewer, better-located entries with stops
the wave cannot reach.
