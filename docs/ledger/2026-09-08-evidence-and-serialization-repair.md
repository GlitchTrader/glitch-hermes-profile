# Evidence and serialization repair — 2026-09-08

## Authority and protected baseline

Alan requested completion of the incident repair, using the transcript and
pre-incident system rather than redesign. Source baseline is Friday's v0.0.2.70
(`4b44b0e`, documented by `bd987ea`). SOUL, trading skills, worker prompts,
probability/geometry validation, final price-range checks, learning, cadence,
model, replication, risk and account configuration are not changed here.
The separate native repair is NT `91ea467`, following `a098b40`.

## Two demonstrated defects; two bounded source changes

1. `market_structure.py` treated retained Friday and Tuesday observations as
   consecutive minutes. Local swings, ranges, imbalances and flow comparisons
   could span an unobserved weekend. Derive local sequences and their chart from
   the latest contiguous native-minute segment. Keep stored history and native
   previous-session levels; retain existing arithmetic and missing-data semantics.
   Coverage is evidence, never an entry gate. No new indicator or strategy.
2. In cycle `20260908T1522Z`, the original MES ENTER_SHORT lacked both `reason`
   and its duplicate SELECTION_REASON, but already supplied `decisive_reason`
   inside SELECTION_EV. The extra format-repair model call rewrote unrelated
   geometry evidence and failed validation. Reuse that exact authored clause
   only when unambiguous; preserve existing canonical reasons. Do not create a
   judgment or relax validation. Ambiguous/missing explanations remain invalid.

## Proof and limits

- Both new regressions fail against unchanged v70 before the fixes.
- Continuity tests cover 1-, 60- and 5,390-minute gaps, 1/2/25/65 new bars, all
  three instruments, non-mutated history, and identical chart/text scope.
- Real-data replay uses the verified September 4 state checkpoint and the first
  25 retained September 8 frames. Old context reported 420 bars; corrected local
  coverage is 25. Cross-gap MES/MNQ imbalances disappear; genuine current ones
  remain. No live state is written.
- On continuous fixture data, the numeric map is identical except for its
  continuity label; PNG bytes are identical.
- The original failed MES response now passes the unchanged candidate-comparison
  validator, with action, entry range, stop, target, confidence and probability
  unchanged. No repair model call or order submission was used in this replay.
- Focused source tests: 205 passed. Full profile/distribution suite: 345 passed,
  including manifest integrity and consistent release numbering. Publication,
  installation and fresh-runtime checks are separate release steps.

Rollback is the checkpointed v70 distribution through the supported updater,
not deletion of history. That baseline retains both defects. This repair does
not establish profitability or prove all possible native execution interleavings.

## Installed and resumed

- Published runtime source: `60da0474b8401411a5b250db734b3cf48fc74d43` on
  configured profile `main`. The separate native source is `91ea467`.
- With Alan's explicit approval, AI alone was paused for the update. The active
  learner finished successfully before installation; its hourly record was
  retained. NinjaTrader and replication were not stopped.
- Verified checkpoint: `D:/ab/checkpoints/glitch/20260908-pre71-b086de15`,
  465 files with SHA-256 manifest, including the v70 distribution, memories,
  supervisor learning/market records, epoch and native configuration/history.
  No database, epoch, account or history reset was performed by this deployment.
- Supported `hermes profile update glitch --yes` installed v0.0.2.71 at
  `2026-09-08T18:56:43Z`; installed `setup.ps1` completed successfully. Existing
  Startup-folder gateway supervision was retained; no UAC approval was needed.
- All 29 manifest-owned profile files and all 95 native AddOn source files match
  their canonical sources. Credentials, environment, configuration, memories,
  epoch, account groups/overrides, risk locks and runtime policy are hash-unchanged.
  Existing operator/learner job identities, schedules and enabled states remain.
- AI was restored ON at `18:58:31Z`, matching its pre-update state. Replication
  remained ON. Before resumption, all seven native accounts were flat with zero
  working orders and native state available.
- Natural cycle `20260908T1858Z` ran the new bundle `a407ed8e3b5f`, attached the
  three-instrument chart, and completed in 40.63 seconds with zero output repairs
  and zero transport retries. Its NOTHING response supplied no executable bracket;
  the existing observational audit therefore flagged nonnumeric selection EV.
  This is not a malformed-JSON failure, a trade, or proof of profitable cognition.
- Follow-up `20260908T1859Z` also completed and delivered its NOTHING response,
  in 65.95 seconds without output repair or transport retry. Both complete native
  delivery receipts report `no_native_action_requested`. After the documentation
  update, all 12 release/manifest/ledger contract tests pass.

The historical invalid-price, stuck-flatten and omitted-instrument cases are
covered by regression tests, not by deliberately recreating dangerous live orders.

## v72: final live check exposed a comparison defect

The later `20260908T1901Z` attempt failed. Its raw original and repair both put
MNQ in the duplicate wire field while their authoritative selection ledger chose
MES. Existing normalization correctly synchronized the wire field to MES. The
repair guard then compared raw original MNQ with normalized repaired MES, falsely
reporting `selection_ev_repair_evidence_changed:0:instrument`. Conversely, that
representation mismatch could miss a genuine MES-to-MNQ selection change.

The bounded v72 fix retains the original prepared/canonical batch for the repair
comparison. The normalizer, repair prompt, model, action, price/probability checks,
and evidence-change guard are unchanged. Raw output is still preserved for the
repair prompt; the comparison snapshot cannot be overwritten by preparing the
repair. No new strategy, gate, relaxation or market reassessment is introduced.

Six regression cases first fail on v71: unchanged canonical selection with stale
or contract-suffixed wire names, and actual selection changes, for one and two
master books. All 147 direct-cycle contract tests pass with the fix, including
the existing no-new-entry, quantity, direction, probability and geometry guards.
AI was paused again under Alan's standing deployment authorization. Publication,
installation and resumed v72 evidence are recorded separately below.

The full v72 profile suite passes all 351 tests. A read-only replay of the exact
original and correction from Hermes sessions `20260908_160103_be39ec` and
`20260908_160202_a63088`, against their original packet and unchanged validators,
now accepts the same MES NOTHING with one recorded correction and no live model
call or order submission. Pre-v72 checkpoint
`D:/ab/checkpoints/glitch/20260908-pre72-724a0f` verifies 464 files, preserving the
installed v71 payload and current learner/epoch/configuration/native evidence.
