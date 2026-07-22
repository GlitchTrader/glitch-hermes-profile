---
name: glitch-review-outcomes
description: Review attributable Glitch-journaled Hermes outcomes and produce candidate lessons without changing active policy or archetypes.
---

# Review Outcomes

Use only the active local Glitch epoch under
`%USERPROFILE%\Documents\NinjaTrader 8\GlitchData`:

- `intents\hermes-trade-outcomes.jsonl` is the completed-outcome source.
- `intents\executions.jsonl` supplies firewall/execution lifecycle evidence.
- `hermes\exchange\hermes\outbox` and `hermes\exchange\hermes\receipts`
  bind the decision to delivery.
- `hermes\exchange\hermes\supervisor\lessons.jsonl` is the only destination
  for candidate lessons.

Do not read the retired Docker path `/opt/glitch-data/journal`, archived reset
epochs, or pre-reset cron output as current evidence.

1. Read only the journal whose filename matches this profile. Separate records by provenance: `hermes` outcomes may evaluate this operator; legacy or unattributed records are context only and must not be attributed to Hermes.
2. Reconstruct each decision from its immutable `cycle_id` packet, pre-trade snapshot hash, selected and available quantities, pre-entry exposure and protection, initial-entry or addition classification, complete target-leg and stop geometry, per-leg and total planned risk, firewall verdict, fills, commissions, per-contract and planned-risk-normalized MAE/MFE and PnL, management decisions, duration, and actual exit. Exclude ambiguous or incomplete records.
3. Compare expected versus observed behavior by regime, action, archetype or discretionary candidate, rejection reason, and churn.
4. Distinguish valid losses from process errors. Never reward hindsight-only changes.
5. Compare the pre-trade `decision_audit` with the observed result. Track whether the losing case contained the evidence that eventually mattered, without treating a valid probabilistic loss as proof the thesis was wrong.
6. Produce candidate lessons only. Append an evidence-linked lesson to
   `supervisor\lessons.jsonl` only when a completed attributable outcome exists.
   Never edit installed skills, prompts, `USER.md`, `SOUL.md`, active archetypes,
   policy, prop rules, operator identity, routes, or execution settings in place.
   The learning loop may propose or evaluate one versioned Hermes cognitive
   overlay for prompt, SOUL, or skill behavior. A proposal has no trading
   influence. A later independent supervisory decision may activate it only from
   later comparable evidence after contradiction review, with an expected
   effect, evaluation metric, and rollback; the overlay never changes Glitch
   execution authority.

Hermes starts with zero attributable trades. An empty journal is valid.
