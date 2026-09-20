# Offline Jev scoring

This source-only research directory is outside `distribution_owned`. It is not
installed into Hermes and has no API, admission, cognition, learner or native action
connection. GHP-005 owns the experiment; GL-AI-10 remains native trade outcome truth.

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
