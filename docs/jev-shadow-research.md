# Level 0 Jev research observer — GHP-005

Version 0.0.2.93 adds a separate recorder and optional typed forecasting process. **Default OFF. No effect on trading.** It neither imports nor invokes Hermes, a learner, an intent sender, or a native action. There is no activation in setup, cron, SOUL or the control plugin. Turning AI Auto on does not start this observer; pausing AI does not stop an independently started recorder. Its own STOP file controls it.

The operator approved this scope on September 19, 2026 after the research at `D:/ab/artifacts/glitch-jev-research/2026-09-19/ARCHITECTURE-DECISION.md`. That local directory retains the native trade reconstruction, both original frozen question bundles, provider comparison, raw predictions, chronological splits, numerical baselines and fitted research artifacts. Those model artifacts are not packaged or loaded here.

## Evidence and authority

The local audit reconciled 83 displayed groups to 80 independent master round trips, with account copies. Their mixture of 14 cognition hashes does not identify an exclusive causal percentage of entry, geometry and management losses. The historical corpus contains 2,653,292 instrument-minute rows over 2024–2026; it contains no comparable full subminute order-flow history. All frozen minute flip probes lost after costs. Longer-horizon raw-Jev probes at 15/30/60 minutes were positive after declared costs, but selected only shorts and had uncertainty intervals crossing zero. Raw Jev probability scores lost to simple controls; adding Jev did not improve the matched numerical model's probability scores. There is no production edge or direct exit justification.

GHP-001 remains deterministic perception. GHP-005 owns this explicitly separate probabilistic research path. GHP-003's no-hidden-strategy boundary and GHP-004's no-trading-authority evaluator boundary remain intact. GL-AI-10/11 own eventual normalized outcome and native receipt semantics. Levels 1–5 (wakes, packet evidence, management proposals, exits, entries/reversals) do not exist in this implementation. Existing five-minute flat scans, positioned-minute management, price wakes, protection, replication and reconciliation are unchanged.

## Data and inference contracts

`AnalyticsBridgeCache.json` → independent recorder → local append-only evidence → optional single TypeSafe process → research predictions. The cache is publication-driven with a minimum five-second persistence interval; neither a five-second delivery guarantee nor a historical tape is implied. Record only distinct cache bytes. Poll metadata at most once/second, with three bounded reads for replace/sharing races. The producer provides no generation counter: missed generations are **unknown**, not estimated as observations.

The `glitch.fast_observation.v1` record retains exact base64 cache bytes, SHA-256, process epoch/sequence, read times, mtime/size and per-contract/timeframe facts. Mtime and `UtcTime` are not proof of a native market event. The rich bridge's native bar timestamp and ingest's last completed-bar boundary establish native freshness; ingest's current-bar UTC can instead be publication time. NinjaTrader bar end timestamps may be up to one minute ahead of wall time. Source times must not regress; replay is recorded but cannot be inferred on. Restarts preserve the source high-water marks. Rewritten identical bytes do not create new observations or repeated calls.

`glitch.jev.observation.v1`, input epoch `live-partial-cache-v1`, contains allowlisted numeric fields, explicit missingness, raw heuristic projections marked as having no strategy/probability semantics, code-computed ATR relations, native economics, bounded same-contract prior observations and compact cross-market references. Strings such as account names, free-text hints, order IDs and credentials are never copied into state. Ingest-only fields are masked to its actual producer coverage: a default zero does not manufacture CCI, DMI, MACD, flow or oscillator observations. Partial and unknown frames remain labelled; this representation is **not** the completed-bar historical training distribution.

Inference requires an operator-selected **exact primary contract**, all four frames, known publishers, matching embedded identities/economics, positive price/economics/ATR15, primary reading and descriptive age at most 15s, and native boundary freshness. Higher-frame publication ages may be up to their interval plus 5s. Unknown publisher, warming/missing core data, stale or mixed contracts remain recorded but ineligible. Legacy descriptive source is retained as evidence, never silently upgraded to publisher identity. The inspected weekend cache lacks Publisher; forward cache acceptance may expose a running-build/provenance gap that must be resolved separately, without inventing identity.

The initial shadow cadence is at most one request per 60s for the explicitly selected contract, with one global in-flight process in this recorder and the latest cache as the single replaceable pending input. No instrument ranking or automatic rotation is performed. A separate output directory permits a separate research run; the operator must run only one SHADOW observer for a given feed/budget. Same-output concurrent processes are rejected by an OS lock. Budget counters persist across restart in that output directory.

`live-long-v1` asks seven independent Choice questions in one request: 5/15/30/60m endpoint UP/DOWN/FLAT; first symmetric barrier touched in 60m; current path; move maturity. Current-path wording now explicitly respects partial/unknown frames, so this is a **new frozen question epoch**, not an unchanged historical bundle. Full questions and their hash are stored at epoch start. Endpoint neutral band is `max(4 ticks, .25 * ATR15 * sqrt(horizon / 15))`; the symmetric barrier is `max(4 ticks, ATR15)`. These are research label definitions, not stop/target instructions or strategy gates. Future barrier labels must censor missing data and same-bar ordering ambiguity. No future outcomes enter model state.

Provider is fixed to direct TypeSafe `jev-1.13.0`, `POST https://api.typesafe.ai/v1/systemone`. No alias, alternate provider, automatic retry or fallback exists. The authenticated research compared OpenRouter's exact dated route separately; its latency advantage did not justify mixing calibration epochs. Official contracts: [HTTP API](https://docs.typesafe.ai/api), [Choice](https://docs.typesafe.ai/primitives/choice), [models](https://docs.typesafe.ai/models). Customer data does not fine-tune Jev; any future learning is a separately frozen downstream research model.

Requests run in a child process. The parent checks its monotonic deadline every 25ms while active and terminates only that child when two seconds elapse (OS scheduling may delay termination; a result at/after two seconds is always ineligible). DNS, slow body reads and provider hangs cannot accumulate workers or block market publication. Changed cache identity supersedes an in-flight result. Raw completed responses remain available, including malformed/unknown-model responses. A hard-killed request has no returned body and an explicit deadline status. Missing inference never means HOLD or EXIT.

`glitch.jev.prediction.v1` links the request and raw observation, state/question hashes and versions, exact requested/returned model, UTC and monotonic duration, raw sanitized response, usage, estimated cost, status, expiry/supersession and `influenced=false`, downstream IDs null. Request records retain the exact state and durable reservation before starting the side effect. Unknown model, answer type/key mismatch, bad probability ranges, unexplained sums or named-choice/argmax disagreement invalidate the response. Small two-decimal rounding sums may be normalized in a **separate scoring copy** with notes; raw cells are unchanged. Choice confidence is not empirical forecast accuracy.

## Operations, limits and privacy

Use the installed Hermes Python and installed script after supported profile update/setup. No scientific packages or TypeSafe SDK are runtime dependencies.

```powershell
$python = "$env:LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"
$observer = "$env:LOCALAPPDATA/hermes/profiles/glitch/scripts/run-jev-shadow.py"
& $python $observer                                  # OFF: no reads or writes
& $python $observer --mode RECORD_ONLY --duration-seconds 60
```

For an explicitly supervised prospective recording session, omit duration and run the same RECORD_ONLY command in a separate process. A Windows background launch must be hidden (`Start-Process -WindowStyle Hidden`). This release does not install a service, startup task or recurring job. It is restart-safe, not automatically restarted. Default output is `GlitchData/jev-shadow`; absolute output paths must end in `jev-shadow`, be distinct from the input, and have no symlink/junction redirection. Existing unowned directories are refused.

Create `GlitchData/jev-shadow/STOP` to stop the loop within its next check and terminate any child request. A present STOP refuses subsequent startup. Remove it only when intentionally resuming the observer. Normal interrupt or a bounded duration also stops it. OFF is the default for a **new invocation**; it does not signal another process. `health.json` is atomic, refreshes every 5s, includes PID/epoch/mode/status/current source ages and can be stale after a crash. Check its age and process identity before calling the observer running.

After active-session recorder/input acceptance and freezing a prospective evaluation interval, an operator can explicitly select SHADOW:

```powershell
& $python $observer --mode SHADOW --instrument 'MNQ 12-26' --env-file 'D:/private/jev.env'
```

The exact contract and credential path above are examples; neither is auto-selected. Read only `TYPESAFE_API_KEY` and the optional `OPENROUTER_API_KEY` used for redaction from the selected local file or process environment. RECORD_ONLY never reads credentials. Never put the key file in the repository, installed payload or GlitchData. Redirects are refused. Requests carry only allowlisted market state to TypeSafe. Raw error bodies/authorization headers are not logged; completed response text is scrubbed for known keys. TypeSafe's no-training statement is not proof of universal zero retention. No broker credential is read or sent.

Defaults: 512KiB input, depth 24, 64KiB request/response, 2MiB journal record, 4MiB segment, 512MiB total evidence, maximum 500 calls and $1 conservative accounting reserve. Each attempted call reserves $0.03 permanently, including failures/unknown outcomes, before dispatch. This is a conservative estimate at the verified $0.042/million input price, not a provider-enforced billing limit. The fixed byte/call caps remain authoritative if billing changes. Cost estimates use reported usage; do not infer zero cost for timeouts. Higher configured caps are bounded to 4GiB, 10,000 calls and $10 reserve; raising a cap is an explicit new invocation. Limit accounting is local to that evidence directory, not account-wide.

No pruning is automatic. Disk limits stop this observer and preserve evidence. Call limits stop inference while recording continues. Crash recovery checks complete JSON records and raw-byte hashes, reports a torn tail without modifying it, identifies interrupted requests, and starts a new process epoch. The final incomplete line is preserved in its original segment. Storage errors stop the observer; they do not touch native execution, scheduled cognition or protection.

## Validation and remaining gates

Source tests cover exact-byte preservation, native versus publication time, producer field coverage, identity/economics mismatch, stale/future/replayed input, finite values, payload allowlisting, probability semantics, redirects, credentials, provider failure, process deadlines, supersession, deduplication, budgets, OS lock, torn tails and no-influence imports. Run the full profile suite after the focused observer tests and regenerate SHA256SUMS for the selected installed files.

Install through `hermes profile update glitch --yes` and installed `setup.ps1` after checkpointing/preserving profile state. Verify source, remote and installed files independently. No NinjaTrader source modification, compile or restart belongs to this change. Existing AI/cron/replication pause settings and learning data must remain unchanged. Rollback is stopping the independent observer; preserve its evidence.

Weekend stale-cache recording verifies serialization, duplicate suppression, stale refusal and restart, **not** forward SIM freshness, market-event cadence or predictive value. GHP-005 stays in progress until naturally active data proves cadence, full raw fidelity, native source time and producer identity. Prospective SHADOW requires a frozen new live/partial epoch and matched numerical/Hermes controls, chronological purging, declared costs and uncertainty by day/session. The opened historical tests cannot become a tuning set. Later wake or management authority needs its own decision; no automatic promotion exists.
