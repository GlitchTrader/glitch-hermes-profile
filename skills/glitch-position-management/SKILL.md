---
name: glitch-position-management
description: Manage native positions through setup transitions, excursion, rollback, protection, and remaining asymmetry.
---
# Position Management

For each positioned native book reconstruct the chosen wager, horizon, allowed pullback and invalidation from `entry_plans.geometry_context`, entry reason and disconfirmation. Compare these with current structure, native protection, excursion, rollback and remaining objective. A local review level is not automatically failure of a parent wager. Resolve contradictory entry notes explicitly against the selected geometry and current evidence; never silently shorten its horizon or widen native risk.

Compare `HOLD`, `MOVE_STOP`, `MOVE_TP`, and `EXIT` by remaining expected value. Use fill, current price, working stop and target, initial native risk, current noise, favorable and adverse excursion, rollback, accepted response, delta-price agreement, remaining objective, and giveback risk. Classify `CURRENT_SETUP` as `HELD:` or `FAILED:`. `FAILED` requires the authored invalidation to be materially satisfied or a specific accepted post-entry structural contradiction; a negative mark, one adverse bar, absent immediate follow-through, a trigger recross, or ordinary noise is not failure.

Use original intent-bound native fill/protection receipts for initial risk, never current-to-stop giveback or a modified stop. Missing initial risk stays unknown. Portfolio excursions are sampled, not tick-exact; chart history before entry is not post-entry MFE. If size changed, do not compare current excursion with original total risk as though quantity were unchanged.

Before material favorable excursion, the accepted initial risk buys room to genuine invalidation. Do not EXIT merely because of a red mark or ordinary noise. Early EXIT needs named changed evidence, deteriorated continuation value, thesis expiry or a binding time/risk constraint. `HELD` describes the original thesis; it does not force HOLD regardless of alternatives. Exit promptly when actual failure makes continuation inferior, even if the hard stop has not printed. After material favorable excursion, rebase the comparison on current evidence rather than the original entry thesis. An unbroken original invalidation or still-reachable target does not itself make `HOLD` superior after earned optionality exists.

Favorable excursion is earned optionality. Once it is material relative to initial risk and current noise, `HOLD` bears the burden of proof. Protect at a supported level that can survive current noise. If no such level exists and continuation value no longer compensates for giveback, use `EXIT`. Ordinary-noise reasoning may reject one proposed stop level but cannot by itself reject `MOVE_TP` or `EXIT`. A profit-protecting stop is at or above entry for a long and at or below entry for a short.

Evaluate proposed `EXIT` at current native price after costs; a missing receipt prevents claiming execution, not choosing the action. `STRADDLES` is uncertainty, not negative value or proof that EXIT wins. Do not reapply the fresh-entry confidence hurdle each minute. Name what changed from the entry plan; ordinary movement already allowed by it is not new deterioration, and small sampled MFE is not material earned profit. If unchanged-bracket `HOLD` value is negative, justify any superior managed alternative from current evidence and available actions, not merely an intact thesis or unspecified future management. This comparison does not make a red mark or one adverse bar an exit rule.

Use only supplied native leg IDs:

```json
{"action":"MOVE_STOP","protection_updates":[{"leg_id":"COPY_NATIVE_LEG_ID","stop_loss":3055.2}]}
```

```json
{"action":"MOVE_TP","protection_updates":[{"leg_id":"COPY_NATIVE_LEG_ID","take_profit":3059.1,"stop_loss":3055.2}]}
```

Extend a working target only when current evidence already supports the farther destination, before the old target fills, with a supported non-loosening stop in the same `MOVE_TP` update. Do not wait for price to trade beyond a target that will already close the position. For `HOLD` and `EXIT`, omit `protection_updates`. Reconcile recent requested updates, their `latest_execution_result`, and each leg's current native working orders, including failed or partial results. Missing/pending results do not confirm a change; a failure does not prove every leg is unchanged. Reassess a valid supported update versus EXIT or HOLD at current prices, without blindly retrying an invalid price or forgetting why protection was needed. Never invent a leg ID or claim an unconfirmed change.

Distinguish ordinary adverse excursion, thesis deterioration, and thesis invalidation. Carry the entry-authored disconfirming evidence and change condition through the trade as its causal review baseline. They are not automatic exit gates: decide from post-entry completed or accepted evidence whether a condition is materially satisfied. When it is, re-estimate the remaining path and compare `EXIT`; do not preserve `HOLD` solely because the hard stop is intact, the target is larger, or arithmetic break-even is low. An unsustained touch or ordinary adverse excursion is not enough. Do not widen stops, move mechanically to breakeven, or exit solely because a percentage cue was reached. Preserve earned asymmetry when reversal or setup-transition evidence rises.
