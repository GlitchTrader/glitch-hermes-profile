---
name: glitch-build-intent
description: Convert Glitch decisions into one strict group-scoped intent batch with absolute native bracket prices.
---

# Build Intent

Return exactly one JSON object and no Markdown or prose.

- Outer object: `schema_version: "glitch.intent.batch.v1"`, supplied `cycle_id`, and ordered `decisions`, one per supplied book.
- Each decision targets exactly the book's `master_account`, uses its `route_id` as `operator_profile`, MNQ, and the supplied snapshot hash.
- Each decision uses `schema_version: "glitch.intent.v3"` plus UUID `intent_id`, `created_utc`, `instrument`, `account`, `operator_profile`, `action`, `confidence`, `snapshot_hash`, `model_version`, `prompt_version`, `reason`, and the required compact `decision_audit`. `final_choice` appears exactly once inside `decision_audit`, never at the decision root, and equals `action`. Preserve the supplied output template's shape and scoped identity values.
- For `ENTER_LONG` or `ENTER_SHORT`, choose `quantity` only from the book's `valid_entry_quantities`, set `order_type: "MARKET"`, and include absolute tick-rounded `stop_loss` and `take_profit_1` prices. These are structural price levels, never distances.
- Optional leg 2: `take_profit_2`, `quantity_tp1`, and optional `stop_loss_2`. Optional leg 3: `take_profit_3`, `quantity_tp2`, and optional `stop_loss_3`. The remaining quantity runs to the last target. Each leg has independent valid profit-side target and protective-side stop geometry; ordering one leg relative to another is not required. These native entry legs are the current scale-out mechanism; the action contract has no discretionary partial-reduction action after entry.
- Before increasing exposure, compare one protected tranche, multiple native target legs, reserving capacity for later evidence, a later independently protected same-direction addition, and leaving exposure unchanged. A favorable or adverse price is context, not an automatic trigger; never encode a grid, martingale, recovery, or fixed-quantity rule.
- For `MOVE_STOP`, include only `protection_updates` beyond the core fields. Each update is `{leg_id,stop_loss}` using an exposed active Glitch leg ID; unspecified legs remain unchanged.
- For `MOVE_TP`, include only `protection_updates` beyond the core fields. Each update is `{leg_id,take_profit}` with optional `stop_loss`; unspecified legs remain unchanged and every target stays on the live profit side.
- A stop amendment may tighten or move farther away. Hermes owns that management choice; Glitch validates current protective side, complete native coverage, authoritative Apex state, and total liquidation-buffer downside before any widening mutation.
- For `HOLD`, `EXIT`, and `NOTHING`, omit every entry and management field.
- Never target followers, exceed valid quantities, reverse through an entry, include a limit price, or emit incomplete JSON.

Glitch performs final freshness, policy, compliance, geometry, capacity, replication, and execution validation.
