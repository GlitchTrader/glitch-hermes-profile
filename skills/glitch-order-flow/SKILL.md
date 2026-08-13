---
name: glitch-order-flow
description: Relate delta and aggression to price response for each candidate setup.
---
# Order-Flow Winner

Use only supplied flow fields and label unavailable fields as unknown. For each instrument and each relevant bullish/bearish path, compare effort with result:

- positive delta with efficient upward progress supports buyer acceptance;
- positive delta with little upward progress can indicate absorption or trapped buyers;
- negative delta with efficient decline supports seller acceptance;
- negative delta while price holds or rises can indicate absorption or trapped sellers;
- weakening delta during extension raises exhaustion risk;
- a delta flip after a sweep, reclaim, failed acceptance, or microstructure break can transition the current setup.

State:

1. who is currently winning the auction;
2. whether price is accepting that effort;
3. whether the flow supports continuation, contradicts it, or is too incomplete to judge;
4. what evidence would flip the winner;
5. how the flow changes the bullish setup, bearish setup, current setup, and next setup.

Do not turn delta, imbalance, a single candle, or a high directional score into an automatic entry. Conversely, when effort, price response, favorable location, genuine pivot-based invalidation, and practical room for the instrument's current behavior and execution delay agree, order flow may materially support an anticipatory entry without perfect or completed-candle confirmation. A missing flow field is a limitation, not directional evidence; price its effect on practical room and asymmetry rather than treating it as an automatic veto. Do not compare a flow-rich candidate against a flow-poor candidate as if evidence quality were equal.
