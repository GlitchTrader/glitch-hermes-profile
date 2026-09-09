# Context and management repair boundaries — v0.0.2.73

Baseline: profile `13126e3` / v72. Native `18d3624` remains unchanged.

## Authorized scope and causal changes

- The v71 continuity fix correctly excluded unobserved cross-session motion but
  also hid all earlier chart context after a single missing minute. Preserve
  observed context within the existing 420-minute bound and render missing time
  explicitly. Retain pivots only when they were confirmed wholly inside an
  observed consecutive segment. Local movement, volatility, flow, range and
  three-bar imbalance calculations remain on the latest consecutive segment.
  Report context count separately from consecutive calculation coverage. No
  history is deleted, missing bar invented, or prior-session motion synthesized.
- A management arithmetic repair could replace HOLD with EXIT without new market
  evidence. The repair now preserves action, native protection and probabilities,
  enforced after canonicalization. The original arithmetic validator is unchanged:
  a wrong verdict is still rejected, not made observational. A repair cannot
  produce a different trade decision. A newer packet prevents an obsolete second
  management model call, including after waiting for the shared model lock.
  Replanning belongs to the next normal full-evidence position review. Existing
  native protection remains active; no blanket ban on early or losing exits.
- Setup wording conflated the executable fill range with stop survival across
  multiple time horizons. Clarify that fill range describes acceptable delivery
  prices, whereas stop survival depends on genuine invalidation and adverse
  movement over the intended path. No fixed ATR, dollar or reward/risk threshold.

## Protected behavior and proof

No AddOn, replication, compliance, UI, native protection, policy, account, model,
cadence, entry-range revalidation, probability formula or learner changes.
Focused regressions cover missing minutes, multi-day gaps, retained references,
unmodified local calculations, both directions of forbidden repair action changes,
protection/probability preservation, and stale repair admission before/after lock.
The full profile suite passes 362 tests, including distribution integrity. An
offline replay of immutable packets preserves local calculations and recovers
earlier chart context. The recorded HOLD-to-EXIT repair is rejected while a
fresh authored EXIT still validates. No live model call or order is used in replay.
Live delivery and offline replay are separate evidence, not profitability proof.

Rollback uses the checkpointed v72 distribution through the supported updater;
it reintroduces the known context/repair defects. Never reset learning to roll back.
