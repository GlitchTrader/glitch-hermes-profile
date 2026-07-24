---
name: glitch-observe-market
description: Read the supplied direct Glitch decision packet and describe observable MNQ state without issuing a trade.
---

# Observe Market

Use only `CURRENT_CYCLE.decision_packet` for current market facts.

1. Require five complete observed frames, the current MNQ snapshot hash, and the scoped portfolio rows. Read packet continuity and missing-minute metadata as uncertainty evidence, never as an automatic veto. Do not open old policy or current-state files to re-decide this cycle.
2. Treat each timeframe row as a live in-progress observation unless explicitly marked closed. Its UTC value is observation time, not proof of candle close. Confirmation is probabilistic: infer it from the five-frame path and current structure rather than requiring a closed candle.
3. Use the immediate and next one-minute movement as the primary timing object for new exposure; use 1m and 5m for local structure and noise. Use 15m and 60m for regime, location, and opposing-risk context, never as permission that substitutes for locally timely evidence. Higher-timeframe disagreement changes confidence and quantity; it does not automatically veto or force a short-term trade.
4. Describe price location, recent five-frame path, support/resistance, volatility, momentum, trend, and order flow when present. Classify the local move as initiating, progressing, or exhausting and identify whether the current price offers early participation, a favorable retest, or a late entry into opposing structure or a session extreme. Missing order flow is neutral and must not become evidence against a trade. Numeric scores are lossy evidence, not authority over raw price.
5. Never invent missing indicators, future bars, sentiment, news, or a pattern match. Archetypes may inform judgment but are never a whitelist.

Pass a compact observation to risk and thesis: data quality, regime, local path, structure, volatility/noise, supporting evidence, conflicts, and missing evidence. This skill never emits or submits an intent.
