---
name: glitch-position-management
description: Manage native positions through setup transitions, excursion, rollback, protection, and remaining asymmetry.
---
# Position Management

For each positioned native book reconstruct the entry setup, current setup, next setup, current structure, native protection, peak favorable excursion, trough, rollback, movement through breakeven, and remaining objective.

Compare `HOLD`, `MOVE_STOP`, `MOVE_TP`, and `EXIT` by remaining expected value. Use fill, current price, working stop and target, initial native risk, current noise, favorable and adverse excursion, rollback, accepted response, delta-price agreement, remaining objective, and giveback risk. Classify `CURRENT_SETUP` as `HELD:` or `FAILED:`. `FAILED` requires the authored invalidation to be materially satisfied or a specific accepted post-entry structural contradiction; a negative mark, one adverse bar, absent immediate follow-through, a trigger recross, or ordinary noise is not failure.

Before material favorable excursion, the accepted initial risk buys room to genuine invalidation. While `CURRENT_SETUP` is `HELD`, do not choose `EXIT` at or below breakeven; preserve `HOLD` behind the native stop. Exit promptly when the thesis is actually `FAILED`, even if the hard stop has not printed. After material favorable excursion, rebase the comparison on current evidence rather than the original entry thesis. An unbroken original invalidation or still-reachable target does not itself make `HOLD` superior after earned optionality exists.

Favorable excursion is earned optionality. Once it is material relative to initial risk and current noise, `HOLD` bears the burden of proof. Protect at a supported level that can survive current noise. If no such level exists and continuation value no longer compensates for giveback, use `EXIT`. Ordinary-noise reasoning may reject one proposed stop level but cannot by itself reject `MOVE_TP` or `EXIT`. A profit-protecting stop is at or above entry for a long and at or below entry for a short.

Use only supplied native leg IDs:

```json
{"action":"MOVE_STOP","protection_updates":[{"leg_id":"COPY_NATIVE_LEG_ID","stop_loss":3055.2}]}
```

```json
{"action":"MOVE_TP","protection_updates":[{"leg_id":"COPY_NATIVE_LEG_ID","take_profit":3059.1,"stop_loss":3055.2}]}
```

Extend a target only after price accepts beyond the prior objective, and only while ratcheting the stop in the same `MOVE_TP` update. For `HOLD` and `EXIT`, omit `protection_updates`. Never invent a leg ID or claim a native change without its receipt.

Distinguish ordinary adverse excursion, thesis deterioration, and thesis invalidation. Carry the entry-authored disconfirming evidence and change condition through the trade as its causal review baseline. They are not automatic exit gates: decide from post-entry completed or accepted evidence whether a condition is materially satisfied. When it is, re-estimate the remaining path and compare `EXIT`; do not preserve `HOLD` solely because the hard stop is intact, the target is larger, or arithmetic break-even is low. An unsustained touch or ordinary adverse excursion is not enough. Do not widen stops, move mechanically to breakeven, or exit solely because a percentage cue was reached. Preserve earned asymmetry when reversal or setup-transition evidence rises.
