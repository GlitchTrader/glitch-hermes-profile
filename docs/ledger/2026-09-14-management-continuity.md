# Management continuity - v0.0.2.87

## Warranted changes

- An open-position pass already receives only its held instruments. Its freshness check now requires those same instruments, present exactly once and natively fresh in every frame, plus fresh held-instrument timestamps. An unrelated stale instrument cannot suppress that management pass. Packet continuity, native session, AI and live feed checks remain mandatory. Full scans, mixed books, explicit entry reassessments and learner calls keep full-universe admission. Before any model invocation or repair, current packet scope and native position transitions are rechecked.
- Compacted management coverage counts describe the instruments actually supplied, not the original unfiltered market.
- Outcome-backed advisory guidance has a separate cognition fingerprint covering SOUL, injected skills, market/native-risk sources and model-facing prompt assembly, templates and input contracts. Parser/transport-only changes do not discard compatible advice. Exact source-version attribution remains on every artifact; decisions, frozen evaluations, plans and cognitive-overlay promotion still use the full release identity. Legacy guidance without the new fingerprint stays exact-version-only. This release changes cognition, so prior guidance is not relabeled as compatible: the learner must produce new guidance. No history is erased and no lesson is automatically promoted.
- Cognition checks the actual shifted stop against its selected failure boundary at both entry-range edges. Equal dollar risk does not establish stop survival through a still-valid pullback. Adjust authored offsets or the executable zone without inventing a different thesis; no native translation change or new numeric gate.
- STRADDLES remains uncertainty, not negative expected value or proof that EXIT wins. Repeated fresh-entry confidence tests must not replace comparison against the existing entry plan. Insignificant sampled MFE is not material earned profit. Exits before original invalidation remain permitted for specific deterioration, expiry or binding constraints; HOLD is not compulsory. Numeric probability bounds remain required, even when unchanged.

## Protected behavior

No NinjaTrader source, execution, replication, protection, Flatten All, account,
risk setting, model, cadence or strategy-rule change. Existing serialization
repairs and strict intent validation remain. Advisory prose stays excluded from
flat entry selection; current native facts outrank it during management.

## Verification and release boundary

Isolated tests cover every frame, absent/duplicate/stale held data, unrelated
staleness, mixed/current scope, position changes, AI/session/feed gates, compact
payload truthfulness, advice compatibility and unchanged overlay provenance.
Prompt contract tests preserve action flexibility and non-deterministic trading.
Captured packets are replayed offline without model calls or orders. Full suite,
publication, installation parity and fresh runtime evidence are verified
separately. Tests establish the implemented contract, not profitability.

Rollback is a scoped source revert and supported profile update with verified
runtime-learning checkpoints and prior AI/job states preserved. No reset or
NinjaTrader restart is required.
