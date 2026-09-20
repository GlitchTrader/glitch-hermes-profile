# Offline Jev research

This source-only research directory is outside `distribution_owned`. It is not
installed into Hermes and has no admission, cognition, learner or native action
connection. GHP-005 owns the experiment; GL-AI-10 remains native trade outcome truth.
The scoring and learning modules are local only. The explicitly invoked batch runner
can call a pinned research provider client against prepared jobs, subject to operator
authorization for the external data transfer; it is never started by Hermes or setup.

## Bounded feature development and thesis replay

`learning.py` supplies expanding chronological folds, forward-window purging, fixed
numerical comparators, candidate retention and development-only error feedback. Noul
answers remain separate yes probabilities. The bounded experiment can propose four
questions, test them on matched earlier/later folds, retain only measured improvement,
then use those errors for one further four-question round. A final frozen bundle
receives one later chronological confirmation; repeated development is never called
an untouched holdout. No fitted model is exported to or loaded by runtime.

`thesis.py` builds explicitly allowlisted state from native same-contract marks and
the original authored entry reason/invalidation. It excludes future marks, terminal
outcomes, current/later Hermes rationale, account and order identities. Paired arms
differ only in whether authored text is present. Mixed embedded contracts are rejected;
absent descriptive/flow data remains absent. The conditional exit probe waits for a
source price after inference completion and before native closure. Missing publications
or invalid results break the two-observation persistence probe. This is retrospective
measurement, not executable subminute replay or a native action contract.

`run_batch.mjs` verifies job/protocol/provider hashes before any request, locks a study
directory, journals and flushes each reservation before dispatch, and never retries an
uncertain ID. It limits concurrency to four, uses the research client's ten-second
timeout, and stops at the declared call/cost cap or model mismatch. A process crash
leaves `RUNNING.lock`; inspect the process and dispatch journal before explicitly
clearing that research-only guard. Completed journal entries are preserved. Default
invocation without explicit inputs performs no inference. The provider client's local
credential handling and response validation remain pinned by its file hash.

The current epoch's protocol, proposal, separate labels, data builders and evaluation
driver are retained at `D:/ab/artifacts/glitch-jev-research/2026-09-19/learning-loop-v1`.
Its scientific dependencies live in the pre-existing isolated `.research-libs` sibling
directory; none is a Hermes dependency. The TypeSafe [feature-discovery cookbook](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)
informs the propose/evaluate/retain loop; its random-fold example is not used for this
time series. [Current source and evidence status](../../docs/ledger/2026-09-20-jev-learning-loop.md).

## Prospective observation scoring

From the canonical profile checkout:

```powershell
python research/jev/score_recorder.py --evidence "C:/Users/alan/Documents/NinjaTrader 8/GlitchData/jev-shadow" --report "D:/ab/artifacts/jev-prospective-report.json"
```

Use a new report path for each evaluation. The command refuses to overwrite an
existing report or write into GlitchData/the input directory. `--as-of` accepts an
explicit Unix timestamp for reproducible visibility cuts. Input files are read only;
complete-byte hashes and unfinished tails are reported. There is no scheduled job.

The scorer reconstructs each observation from its exact raw native bytes and evaluates
freshness at capture time. Unknown publisher, source regression, invalid contracts or
economics exclude the observation. Requests and predictions must join by observation,
raw hash, state hash, exact pinned model and question hash. Expired, superseded,
malformed, stale or duplicate results cannot become extra forecast samples.

Labels cover 5/15/30/60-minute endpoints with the previously declared neutral bands.
Completed native minute bars provide OHLC paths only when every interval is present
and wholly after the anchor. A bar straddling the anchor cannot contribute a pre-anchor
high or low. Both barriers in one bar remain UNRESOLVED. Missing minutes or sparse
price marks leave first-touch order unresolved and excursions as observed lower bounds.
No minute data is interpolated into subminute observations.

NinjaTrader minute bars carry end timestamps ([native timestamp contract](https://ninjatrader.com/support/helpguides/nt8/how_bars_are_built.htm)).
Both current producers serialize `last_completed_bar.utc_time` from `Times[bip][1]`
and `closed_utc` from `Times[bip][0]`. The latter is the next bar timestamp, so the
offline reader uses `utc_time` as the completed bar end and subtracts one minute for
its start. Capture time remains the independent availability boundary. This avoids
shifting the prior OHLC into the next interval; no native field is rewritten.

An endpoint may use the first fresh mark within 15 seconds after the target. Its delay
is explicit; exact endpoints receive a separate metric series. Forecasts are grouped
by provider, returned model, question hash, input epoch and horizon. Outputs include
Brier, log loss, calibration curve/ECE, balanced accuracy and high-confidence coverage.
The hypothetical long/short probes each wait for a price mark whose native source time
is after inference completion. They charge declared commission/spread/slippage and are
not native fills, a policy, portfolio PnL or a reversal simulation.

Before a prospective experiment, freeze the questions, provider/model, representation,
cadence, sample/exclusion rules and comparator population. Preserve session/day/instrument
identities for blocked uncertainty estimates. A new model or prompt starts a new epoch.
Historical numerical models cannot be silently applied to partial live observations:
their completed-bar feature coverage must first match. Current Hermes probabilities
refer to different authored bracket events, so endpoint probabilities are not a matched
comparison. Record native Hermes event definitions before scoring that comparison.

There is no wake/exit policy in this tool. Detection lead, missed favorable excursion,
premature-exit damage and opportunity cost require a separately frozen causal policy
and observable future path. They remain unmeasured when those inputs are absent.

Closed-market development results: [canonical ledger report](../../docs/ledger/2026-09-19-jev-closed-market.md).
