# Feed identity and geometry repair — 2026-09-16

Authorization: user approved fixing the concrete defects found in the read-only September 16 loss audit. No claim that repairing these defects proves profitability.

## Causes and narrow changes

- Native feeds were keyed by root and last writer: the light ingest overwrote chart VWAP/delta, and M2K September/December prices alternated. The paired AddOn now owns a fresh root with one publisher/contract, prefers the rich chart publisher, clears derived timeframe/session state on a legitimate switch, and applies the same arbitration to persisted/legacy imports. Fallback resumes after the publisher freshness interval, not a strategy gate.
- Management resolved a market snapshot expiry instead of the actual held native contract. The paired AddOn resolves EXIT/MOVE_STOP/MOVE_TP from current nonflat native positions. Missing or ambiguous native identity is explicit; a serialized no-op produces a terminal failure receipt rather than permanent pending. Native protection, flatten, replication and cancellation-race behavior are unchanged.
- Hermes stored root-only chart history. State schema v3 rebuilds only the replaceable market-perception cache from retained causal frames, selecting the packet's contract and rejecting mixed native candle identity. Raw frames, decisions, trades and learning are preserved.
- MES cycle 20260916T0858Z authored 7668.25 stop / 7678.25 target against a 7673 packet reference, but prose claimed 3.75 risk / 6.25 reward. Correct primary-leg distances are 4.75 / 5.25. At the stated 0.25-point friction the hurdle is 0.50, not 0.4167. Instrument-qualified direction and range prose no longer bypass reconstruction. The existing canonicalizer uses submitted numeric fields and packet reference, preserving action, quantity, authored bracket, forecast and probability. Opposite authored direction is still rejected by the existing validator, not silently repaired.
- Learner arithmetic shares this geometry reconstruction instead of trusting declared distances. A probability interval wholly above break-even is labeled above, without an invented one-percentage-point margin. This changes evidence, not a trading rule.

## Protected behavior / non-goals

No SOUL/skill wording, model, cadence, sizing, fixed dollar stop, risk/reward minimum, threshold recalibration, account configuration, epoch reset, Windows/NT restart, or learning deletion. Unrelated dirty web/release work is excluded. No new LLM call is added.

## Proof and rollout

Incident fixtures cover competing feeds, fallback/recovery, import parity, native contract ambiguity, unscheduled management, expiry-specific causal backfill, inconsistent candle identity, native-reference arithmetic and exact probability-range classification. Run the complete profile test suite plus AddOn source compile, native safety and state-machine harnesses. Checkpoint runtime learning before supported profile update; deploy the complete AddOn plus affected indicators. Native compile/loading and fresh runtime evidence remain separate from copied-file parity. Preserve prior AI/cron state only after runtime checks.

Rollback: restore the scoped source commits through the same supported install/copy workflow while paused. Retain the evidence checkpoint. Never reset unrelated work or erase raw learning.
