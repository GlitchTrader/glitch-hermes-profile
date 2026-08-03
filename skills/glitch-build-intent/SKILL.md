---
name: glitch-build-intent
description: Encode a chosen Glitch decision into the strict protected intent contract without adding strategy.
---

# Build Intent

Return one JSON object and no Markdown or prose.

- Preserve the supplied `glitch.intent.batch.v1` template, `cycle_id`, ordered
  books, route/account identities, MNQ snapshot hash, and exact audit shape.
- Each `glitch.intent.v3` decision uses only the supplied action contract.
  `final_choice` appears once inside `decision_audit` and equals `action`.
- `ENTER_LONG` and `ENTER_SHORT` use `MARKET`, a positive integer master
  quantity, and absolute tick-rounded `stop_loss` and `take_profit_1` prices.
- Optional leg 2 uses `take_profit_2`, `quantity_tp1`, and optional
  `stop_loss_2`. Optional leg 3 uses `take_profit_3`, `quantity_tp2`, and
  optional `stop_loss_3`. Remaining quantity runs to the last target. Every
  leg receives independent native OCO protection.
- `MOVE_STOP` contains only core fields plus non-empty
  `protection_updates` entries shaped `{leg_id,stop_loss}`.
- `MOVE_TP` contains only core fields plus non-empty `protection_updates`
  entries shaped `{leg_id,take_profit}` with optional `stop_loss`.
- `HOLD`, `EXIT`, and `NOTHING` omit entry and management fields.
- Never target followers, reverse through entry, emit limit prices, invent leg
  IDs, or return incomplete JSON.

Glitch applies final fixed-identity, user-configured constraint, protection,
replication, reconciliation, and native execution checks. It must not replace
the selected direction, quantity, or geometry with an unrelated strategy.
