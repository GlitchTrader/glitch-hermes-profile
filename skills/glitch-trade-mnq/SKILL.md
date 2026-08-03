---
name: glitch-trade-mnq
description: Compare MNQ hypotheses and produce case-specific judgment from the current Glitch evidence without encoding a strategy.
---

# Reason About MNQ

## Read evidence as a sequence

Treat recent one-minute frames as a path rather than isolated snapshots. Use
higher-timeframe observations for context, while respecting whether each value
is live, closed, stale, missing, or provisional. Missing evidence is uncertainty,
not positive or negative evidence.

Synthesize price and volume, volatility, trend and rotation measurements, VWAP
context, order flow, session and prior-session references, external equity
context, news, event context, account state, current exposure, and native data
quality. No single feature, composite score, pattern name, or historical label
chooses the result.

`market_structure_observations` is deterministic session memory. Its counts and
labels organize evidence across otherwise stateless cycles; they do not select
an action. When the block is absent, warming, stale, or contradicted by current
facts, represent that uncertainty explicitly.

## Compare competing hypotheses

Evaluate continuation, reversal, rotation, transition, and deliberate inaction
as competing explanations. For each material direction, identify:

- the most likely near-term path;
- evidence supporting and contradicting it;
- the state or observation that would invalidate it;
- remaining opportunity and execution uncertainty;
- why another supported action is currently weaker or equally plausible.

Anticipation and confirmation are both valid forms of judgment. Location,
acceptance, rejection, sweeps, structure labels, imbalance, volatility, recent
attempts, and external context are evidence whose relevance changes by case.
None is a mandatory setup, preferred playbook, re-entry veto, or confirmation
checklist.

## Use only supplied authority

Read scope, account identity, supported actions, capacity, protection fields,
and configured constraints from the current packet. Do not infer rules or limits
from account size, firm name, examples, memory, or generic prop-firm lore.

Choose any supported structured intent only when it expresses the selected
hypothesis faithfully. Quantity and geometry must remain within supplied
capacity and contract fields, but no fixed point distance, ATR multiple,
reward/risk ratio, target count, tranche split, scaling ladder, or averaging
formula is preferred.

## Manage current exposure from current evidence

When exposure exists, reassess the original thesis against current native facts,
new evidence, remaining opportunity, protection state, execution uncertainty,
and alternatives. Continuing unchanged, amending, adding supported protected
exposure, reducing, exiting, or doing nothing are all case-specific choices.
Unrealized profit, rollback, normal noise, prior attempts, elapsed time, and a
recent loss can inform judgment but never issue an automatic command.

## Be explicit and falsifiable

A high-quality decision is not necessarily active. It is internally consistent,
uses the current packet, names uncertainty and counterevidence, respects the
supplied contract, and states what would materially change the conclusion.
Do not optimize for action frequency, a daily monetary objective, a preferred
style, or a particular geometric template.
