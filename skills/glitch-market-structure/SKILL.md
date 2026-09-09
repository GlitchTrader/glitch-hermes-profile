---
name: glitch-market-structure
description: Interpret instrument-neutral structure, regime, location, and microstructure transitions from Glitch observations.
---
# Market Structure

Maintain competing hypotheses rather than a single directional story.

Use the supplied instrument's native tick size, point value, price path, ATR, timeframe bars, highs/lows, VWAP, volume, and order-flow fields. Do not use MNQ-specific point distances or fixed session recipes.

Describe swing structure, displacement, acceptance/rejection, sweep/reclaim, correction, exhaustion, and microstructure breaks in the instrument's own units. Structural invalidation must be beyond genuine noise and supported by the packet.

Leg path efficiency compares pivot displacement with the same endpoints plus intervening closes; intrabar travel is unknown, so this is sampled efficiency, not tick-by-tick smoothness.

Do not use an unverified numeric base rate or historical label as current evidence.
 Do not impose a fixed ATR threshold on every instrument or regime.
