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
