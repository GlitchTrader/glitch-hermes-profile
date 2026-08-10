---
name: glitch-market-scan
description: Scan every eligible futures instrument and rank supported setups by probability-adjusted asymmetry.
---
# Multi-Instrument Market Scan

For every instrument supplied by the authoritative packet and allowed by policy, build the same candidate view. Never default to MNQ, the first array element, or the instrument with the most familiar history.

Assess regime, session phase, location, volatility/ATR, multi-timeframe structure, price path, order flow, current setup, next setup, setup phase, objective, invalidation, room, execution uncertainty, and account exposure.

For each candidate describe: current setup, next setup, transition trigger, current probabilistic winner, continuation/reversal odds only when supported by supplied fields, target-before-stop estimate only when supportable, and why this candidate outranks or loses to the alternatives.

Rank survival-adjusted opportunity, not raw confidence. A candidate with less room, late setup age, poor invalidation, stale native context, or high execution uncertainty should lose to a cleaner candidate even if its directional score is stronger. If no candidate has bounded positive asymmetry, return NOTHING.
