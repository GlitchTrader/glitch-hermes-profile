---
name: glitch-market-scan
description: Build a mandatory symmetric setup ledger for every eligible instrument before ranking.
---
# Multi-Instrument Market Scan

The scan is a comparison process, not a directional vote. Enumerate every instrument in the authoritative packet that is allowed by policy and scope. Never default to MNQ, the first array element, the strongest raw score, or the most familiar history.

For each instrument, complete the same record in this order. Every instrument always has a current auction/path, even when the path is low-quality, late, conflicted, or not tradeable; do not use "no setup" as a substitute for describing the active auction.

1. **Market context:** regime, session phase, volatility/ATR if supplied, location, structure, price path, room, invalidation quality, execution uncertainty, and exposure/correlation.
2. **Current setup:** the active auction/path now, setup phase, evidence, objective, invalidation, and whether it is early, active, mature, exhausted, failed, or undefined.
3. **Bullish setup/path:** the specific evidence-supported path toward higher prices, trigger/transition, objective, invalidation, order-flow requirement, and status. It can be absent or conditional.
4. **Bearish setup/path:** the specific evidence-supported path toward lower prices, trigger/transition, objective, invalidation, order-flow requirement, and status. It can be absent or conditional.
5. **Next setup:** the next plausible state, the exact transition evidence that would promote it, and what would invalidate it.
6. **Prior trigger review:** `NOT_APPLICABLE` during a normal scan; on a condition-change review, classify the frozen prior trigger before replacing it.
7. **Auction winner:** buyer/seller/balanced/unknown, whether effort is accepted, and the evidence that would flip the winner.
8. **Asymmetry:** use coarse evidence-grounded continuation, reversal, and target-before-stop probability ranges; record `UNKNOWN` only when the supplied evidence is unusable. Include room, invalidation cost, setup maturity, risk geometry, data quality, execution uncertainty, exposure/correlation, and survival-adjusted opportunity.

A trend is context, not automatically a setup. Describe the actual location, path, trigger, invalidation, and remaining room. At a session extreme or stated first objective, distinguish continuation through the level from reversal at it. Do not count a farther hypothetical level as current room until price accepts through the nearer objective or transition. Late continuation, incomplete flow, or an in-progress candle reduces confidence and practical room; it is not an automatic veto while location, genuine invalidation, room beyond current noise, and effort/price response still support positive expected value.

After every instrument record is complete, rank all candidates by probability-adjusted asymmetry. Compare both directions within each instrument and then compare instruments. The winner must retain positive expected value after room, invalidation, maturity, order-flow agreement, costs, latency, entry-range uncertainty, exposure, and survival are considered. If no candidate retains practical edge, choose global `NOTHING` and state why every candidate lost.

The final `decision_audit.decisive_evidence` must use the exact `INSTRUMENT_COMPARISON_V1` format supplied by the operator. Every instrument block must be present; every placeholder must be replaced; ranking and selection must include all candidates.
