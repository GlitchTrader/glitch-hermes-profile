# GHP-005 — Closed-market development results

The operator approved this pass after asking what useful work remained before the
market reopened. The result supports **RECORD_ONLY and no authority expansion**.
Neither new semantic representation adds predictive value to its matched numerical
model. The publisher gap remains a runtime identity gate. A giveback probe has a
small, uncertain conditional benefit and material damage on winning trades.

Local reproducible evidence is in
`D:/ab/artifacts/glitch-jev-research/2026-09-19/closed-market-v1/`.
The original research, opened tests, installed v0.0.2.93 payload and native source
remain unchanged. New source is limited to `research/jev/`, its tests and this Rail
record. The research directory is outside the installed profile ownership manifest.

## Publisher diagnosis

The current cache contains 12 readings and **zero Publisher keys**. Publisher is the
only public property in the on-disk `GlitchIndicatorReading` type missing from the
cache. The property has a public getter and no serialization-ignore attribute. The
same .NET serializer preserves both null and populated Publisher values in isolated
controls. Current native source clones/persists the property and both producers set it.

The on-disk Custom assembly has MVID
`4684a20b-cfec-4166-aa0f-4d9dd1c628ff` and SHA256
`022c17185e55487952aef136729ec5d7e7112ed706c86e9df1a4c05a7c1a8004`.
NinjaTrader started September 15; this DLL was written September 17; the cache was
written September 18. An older in-memory AddOn/DTO is a plausible explanation, not
an independently verified loaded-assembly identity. No source omission has been
established that warrants another native patch. The bounded trace search found no
matching assembly-load/compile proof. No debugger injection, native source edit,
compile or restart occurred. Unknown publisher remains ineligible for inference.

## Frozen development study

`PROTOCOL.md` was written and hashed before calls. SHA256:
`4aa49dcf6b1a5e2584b46b1724613a68154eebb051f6d3900f92de45d226b472`.
Only the original training period was used: 600 selected fit observations in 2024
and 300 development observations in January–June 2025, balanced by instrument.
The split has a two-day gap around January 1, exceeding every forward horizon.
Previously opened validation/test intervals were not used for prompt development
or model scoring. This is a new development comparison within old training data,
not an untouched final holdout. There was one question round, no subsequent tuning.

The semantic bundle measures current directional coherence, upward/downward price
acceptance, maturity, location extension, horizon tension, auction character and
evidence consistency. It does not ask for orders or pretend OHLC history contains
order flow. Both representations answer identical questions: the full normalized
state and a compact bucketed state derived from the same deterministic observations.
Numerical models use the original 96 features. Models and hyperparameters were fixed.

1,960 calls completed with exact **jev-1.13.0**, estimated input cost **$0.220593**.
Latency: median **550ms**, p95 **751ms**, p99 **1,128ms**. All returned HTTP 200;
11 had named-choice/maximum-probability disagreements. The main diagnostic reads
well-formed probabilities by label and retains these flags. A secondary strict
rerun excludes them and preserves the same conclusion. Runtime continues to reject
such responses. There were no retries, fallbacks, model aliases or trading effects.

Mean multiclass Brier across four horizons; lower is better:

| Model | Main development | Strict valid-call subset |
|---|---:|---:|
| Training class frequencies | 0.66768 | 0.66778 |
| Numerical logistic | 0.69971 | 0.69984 |
| Numerical depth-3 tree | 0.71945 | 0.71937 |
| Jev normalized semantic features | 0.68193 | 0.68059 |
| Jev bucketed semantic features | 0.68100 | 0.68207 |
| Numerical + Jev normalized | 0.71561 | 0.71560 |
| Numerical + Jev bucketed | 0.72120 | 0.72109 |

| Horizon | Usable development observations | Numerical | + normalized Jev | + bucketed Jev |
|---|---:|---:|---:|---:|
| 5m | 299 | 0.67141 | 0.68446 | 0.68984 |
| 15m | 296 | 0.67080 | 0.69756 | 0.70099 |
| 30m | 291 | 0.71307 | 0.73420 | 0.74303 |
| 60m | 270 | 0.74359 | 0.74624 | 0.75094 |

Censoring accounts for horizon-dependent counts. All combined-model differences
are unfavorable. At 15m/30m their descriptive day-cluster intervals exclude zero;
5m/60m intervals include zero. These are exploratory comparisons without multiplicity
correction. The smaller numerical fit also loses to the frequency baseline on average:
this study does not establish the numerical forecaster as deployable either.
Full log loss, ECE/calibration curves, coverage and instrument breakdowns are retained
in `evaluation.json` and `evaluation-strict.json`. Independent verification recomputed
8,092 row-level Brier values and all 28 model/horizon means from persisted probabilities.

## Bias diagnosis

Sixteen real 2024 states and their numeric mirrors were tested with both choice
orders and two endpoint wordings: 128 calls. Eight synthetic paths added 32 calls.
Actual insertion-order wire hashes are retained; the experiment does not confuse
client dictionary sorting with model behavior.

| Diagnostic on real states | Result |
|---|---:|
| Mean probability total variation after option reordering | 0.0559 |
| Top-choice changes after reordering | 10.16% |
| Mean total variation after equivalent endpoint rewording | 0.1953 |
| Mirror-symmetry error after swapping UP/DOWN back | 0.2255 |
| Synthetic current-path recognition | 27/32 |

For the original 60m wording/order, the balanced original-plus-mirrored sample had
mean UP/DOWN/FLAT probabilities **0.0934 / 0.2625 / 0.6441**. Plain wording changed
them to **0.1559 / 0.4188 / 0.4253**. Thus neither the parser nor option ordering
alone explains the short/flat skew. These are state/prompt sensitivity diagnostics,
not a proof that any alternate wording predicts better. No new wording was promoted.

## Management counterfactuals

All **80 master trades / 1,134 management decisions** were considered, using 1,263
fresh exact-contract minute marks. The authored state was HELD on 1,130 decisions
and FAILED on four; these labels cannot independently quantify how often a thesis
had actually deteriorated. There were 45 EXIT decisions and eight MOVE_STOP decisions.

Forty-four first EXIT signals had usable matched pre-model evidence. Native completion
followed the available model decision by a median **0.274s**; none had a later minute
mark before native closure. Replacing those exits with their earlier pre-model marks
would change gross PnL by **-$1.75** in aggregate. That earlier mark precedes knowledge
of the decision, so it is an optimistic latency comparison, not an executable replay.
Three first FAILED signals had matched evidence; their analogous difference was +$2.50.
This does not test whether a separate observer could recognize deterioration sooner.

The predeclared offline foil triggers after sampled MFE reaches 0.5R and half that
sampled profit is given back. It acts only at a subsequent available native price
mark, never the best future price. It is not a selected strategy or proposed live gate.

| Giveback probe | Result |
|---|---:|
| Trades with a trigger | 23/80 |
| Triggered trades with an eligible subsequent mark | 18 |
| Improved / harmed | 10 / 8 |
| Gross benefit / damage | +$173.25 / -$88.50 |
| Gross difference | +$84.75 |
| After declared extra exit-cost penalty | +$53.48 |
| Mean difference per measured intervention | +$2.97 |
| Day-cluster 95% interval for that mean, six days | -$3.01 to +$10.40 |
| Damage on original winners after extra cost | -$102.27 |

Nine declared cost stresses leave +$31.13 to +$77.63 on the same conditional subset.
Five triggered trades lack a subsequent mark before actual closure. Unobserved barrier
touches, changed protection and subminute execution cannot be reconstructed from these
marks. This is neither a complete policy replay nor a Jev result. It supports measuring
both saved losses and damaged winners prospectively; it does not justify direct EXIT.

## Source, validation and reopening gate

The new offline scorer reads exact recorder bytes, checks native identity/freshness
at capture time, and joins requests/predictions by hashes and pinned epochs. It labels
5/15/30/60m endpoints, records endpoint delay, distinguishes sampled excursion bounds
from complete minute paths, censors ambiguous first touches, and charges hypothetical
probe costs only after inference is available. It does not write native outcomes or
create a wake/exit policy. See [its operating contract](../../research/jev/README.md).

The reader also resolves a timestamp naming hazard before forward labeling:
`last_completed_bar.utc_time` is native `Times[bip][1]`, whereas `closed_utc` is
`Times[bip][0]`. NinjaTrader [stamps time bars at their end](https://ninjatrader.com/support/helpguides/nt8/how_bars_are_built.htm).
Therefore the prior bar's `utc_time`, not the following timestamp, anchors its OHLC
interval. This research correction prevents a one-minute label shift without
rewriting native data or changing the installed observer.

**754 profile tests pass**, including 30 new offline tests covering adverse-first green
endpoints, same-bar ambiguity, missing intervals, future revisions/publication,
contract mismatches, post-inference execution timing, costs, duplicate results, stale
responses, hash joins and native source regression. A read-only run over the current
recorder evidence correctly produced **zero forecast outcomes** from the single stale,
publisher-missing weekend observation. That is missing forward evidence, not a score
of zero and not active-session acceptance.

GHP-005 remains in progress. The next admissible evidence is naturally fresh, attributable
SIM input with explicit native publisher identity and measured recording cadence. If
the identity gap persists, resolve the native loaded-instance lifecycle under the
operator's change-control authority before enabling inference. No publisher inference
shortcut or native patch has been selected. Prospective questions and comparators must
be frozen before any SHADOW run. The current five-minute Hermes fallback and all
execution/protection/replication/reconciliation boundaries remain unchanged.
