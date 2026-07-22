---
name: glitch-self-learning
description: Convert completed, attributable Glitch trading outcomes into append-only episodic and durable Hermes lessons. Use when reviewing fills, exits, rejections, MAE/MFE, decision audits, or conflicting prior lessons, and when updating native memory without treating memory as trading truth.
---

# Glitch Self Learning

Learn only from evidence Glitch can identify and reproduce.

## Authority

- Treat NinjaTrader/Glitch positions, orders, fills, balances, PnL, brackets,
  receipts, and outcomes as facts.
- Treat Hermes reviews, hypotheses, and memory as interpretations.
- Preserve losses, mistakes, rejections, disconnects, contradictions, and
  uncertainty. Never reset a baseline, delete an adverse result, or improve a
  record after the fact.

## Workflow

1. Join a completed outcome by `cycle_id` to its immutable pre-decision packet,
   decision, intent, receipt, fills, protection, exit, and route using stable IDs. If attribution is incomplete,
   append an unresolved observation and do not learn a causal rule from it.
2. Record one append-only episodic lesson with evidence links, observed result,
   decision quality, uncertainty, and plausible alternatives. For entries,
   record stop and target distances in points and volatility/noise units,
   structural invalidation, execution delay/drift, MAE/MFE, regime, quantity,
   whether the intended absolute levels were preserved, selected and available
   quantities, pre-entry exposure and protection, initial-entry versus addition,
   complete per-leg planned risk, realized PnL, and MAE/MFE per contract and
   against planned risk. Assess whether quantity was evidence-based or habitual
   and whether native legs, reserved capacity, or a later protected addition were
   plausible alternatives without inventing hindsight rules.
3. Audit repeated decision language and behavior. Flag stops placed inside
   ordinary noise, distant targets chosen mainly for cosmetic reward/risk, and
   nearby re-entry after a stop without materially changed evidence. These are
   hypotheses until repeated attributable outcomes support them.
4. Promote a compact durable lesson to native memory only when repeated
   completed evidence supports it. Keep a single outcome as an episode or
   hypothesis unless it proves a deterministic process defect.
5. When evidence conflicts with a lesson, append the contradiction and lower,
   revise, or retire its confidence. Never erase the earlier lesson.
6. Keep current positions, balances, eligibility, temporary directives, trade
   quotas, and transient market state out of durable memory.

Write structured learning only to Hermes-owned append-only knowledge, journal,
or supervisor streams and native memory. Never overwrite Glitch-owned files,
change execution policy, alter groups or limits, or convert hindsight into a
mandatory trading gate.

A cognitive overlay starts as a proposal with no trading influence. Only a later
independent supervisory decision may activate it after later comparable evidence
and contradiction review. Later evidence may continue, promote, revise, or roll
it back; Hermes never rewrites installed SOUL, skills, Glitch policy, account
groups, or execution code directly.
