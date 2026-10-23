---
name: glitch-volume-profile
description: Read volume-at-price facts as evidence of where a level is defended, accepted, or has no support.
---
# Volume Profile

Use only supplied `volume_profile_facts`. Absent, warming, truncated, or omitted facts are unknown, never zero or direction. `tick_rule_only` classification makes bid/ask split weaker evidence; say so once. Facts are computed by code from the session profile; you choose which levels matter.

Compare effort with result at each candidate level, for the bullish and bearish path:

- heavy volume near a level with little price progress is contested; heavy volume and progress through it is acceptance;
- repeated probes that close back (`touch_count` with `rejection` outcomes) suggest a defended boundary; `acceptance` outcomes weaken it. A zone is not a line: judge probes against the level's tolerance and current noise, and let a fresh probe change the count's meaning;
- volume far below the level on the far side, or a vacuum (LVN) beyond it, means price moved there fast and little was traded. "No buyers here" is a probability input, not a veto. If price reaches the far side it can travel, and continuation is more plausible than a reversal there;
- POC, value area, and HVN are where trade was accepted and act as magnets or reference; price outside value that stays there shows acceptance of new value, while a quick return inside shows rejection.

Stop location: a vacuum beyond the level is supporting evidence that price passing the level is genuinely a different auction. It does not move the stop by itself. Keep the stop beyond the movement the wager allows, use `nearest_vacuum_beyond` and its dollar distance only as a reference, and price the wider or tighter risk in probability and payoff, not by shaving the stop to the vacuum edge.

Candle facts (engulfing, N-candle run, close versus prior close) are timing facts on the named bar. They carry meaning only together with location, volume at that location, and flow; never enter or exit on one alone. An exit on a bar close is a management judgment, not a stop: the stop fires on touch.

State, once: which level is defended or accepted, what volume says about support beyond it, what would flip that, and how it changes the current setup, next setup, and stop location. No single node, pattern, or count is an automatic entry, and a missing profile is a limitation priced once, not a veto.
