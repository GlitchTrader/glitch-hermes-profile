# Glitch Hermes Profile v0.0.2.87

This repository distributes the cognition, skills, deterministic workers, and control plugin used by the **Experimental** Glitch AI edition.

v0.0.2.87 matches management freshness checks to the held-instrument payload, preserves compatible outcome-backed advisory guidance across parser-only releases, and clarifies fill-shifted stop survival and uncertain HOLD-versus-EXIT comparisons. Full-market scans, learner admission, exact release attribution, lesson promotion, native execution, models and cadence remain unchanged. See [the bounded management repair](docs/ledger/2026-09-14-management-continuity.md). The [v0.0.2.86 format repair](docs/ledger/2026-09-14-trigger-field-recovery.md) is retained.

v0.0.2.85 preserves Windows CRLF line-ending compatibility in the selection parser introduced by v84. Root/scope checks, accepted contract suffixes and all cognitive/numeric rules are unchanged.

v0.0.2.84 accepts native contract suffixes in the selection ledger, collapses uniquely owned identical wake copies, and restores omitted management action/reason mirrors only from agreeing explicit choices. Geometry validation recognizes the selected candidate's adjacent execution-uncertainty clause without dropping any required dimension. Management wording separates choosing an exit from claiming its execution, and requires a concrete comparison when defending negative terminal HOLD value. No execution, replication, protection, probability, risk or cadence rule changes. See [the daily maintenance review](docs/ledger/2026-09-11-maintenance-format-and-management.md).

v0.0.2.83 clarifies forecast expiry versus reusable market structure: an earlier target touch completes the old forecast but does not permanently retire that price level. Fresh return-to-level or extension hypotheses use current geometry and new probabilities; no old order or forecast is revived. This is a wording-only follow-up to a live v82 review, with no validation, execution, schedule or risk change.

v0.0.2.82 chooses the meaningful auction move before constructing the entry bracket, explicitly checks fill-shifted geometry at both range edges, and supplies native-dollar/ATR conversions for existing market reference levels. No fixed stop floor, reward/risk gate, instrument preference, or new market signal is added. Narrow output recovery preserves unambiguously authored management fields and identical audit siblings; conflicting values and ambiguous ownership still fail. Native execution, replication, configured risk, model, schedules and learning remain unchanged.

v0.0.2.80 narrows a false setup-deferral text match, supplies book-scoped native-leg serialization examples for management actions, and names the exact required verdict in existing management arithmetic repairs. Trading doctrine, probability checks, native execution, protection validation, models, and schedules are unchanged. See [the maintenance output review](docs/ledger/2026-09-10-maintenance-output-contract.md).

Glitch/NinjaTrader remains the market, account, configured-policy, execution, bracket, replication, and journal authority. Hermes proposes structured intent for the master accounts selected by the user in Glitch. The profile does not distinguish paper from live accounts and makes no profitability, unattended-operation, or live-readiness claim.

The profile is intelligence-first. It supplies evidence vocabulary, time-sequence context, strict output construction, and attributable learning. It does not encode a fixed trading strategy, daily profit target, account-size recipe, preferred setup, geometric template, or hidden action gate. Capacity and supported actions come from the current Glitch packet and user configuration.

Local cognitive lessons require independent cross-session discovery, later completed master-trade confirmation, exact overlay attribution, contradiction review, and periodic revalidation before they can influence Hermes. Initial influence is a short-lived local experiment. Renewal requires a matching frozen, cost-adjusted deterministic evaluation; product promotion additionally requires verified all-in costs, several frozen weeks, calibrated forecasts that beat climatology, positive net results versus staying flat, and positive results across multiple observed regime strata. Lessons expire when those gates are not met. A locally promoted lesson creates only a human-review distribution candidate; it never installs itself into the product or changes Glitch execution.

## Requirements

- Windows with NinjaTrader 8 and the matching Glitch AI AddOn exported from the current Glitch main source.
- Hermes `0.18.2` or newer.
- An OpenAI Codex OAuth account authorized by the user.

## Install

```powershell
hermes profile install github.com/GlitchTrader/glitch-hermes-profile --alias
hermes -p glitch auth add openai-codex --type oauth
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch\setup.ps1"
```

`profile install` performs no model call and creates no cron job. `setup.ps1` verifies the distribution, enables the deterministic plugin, installs the supervised profile gateway, and creates the minute operator plus a 30-minute learning job offset to minutes 02 and 32. The minute dispatcher calls Luna on completed five-minute boundaries while flat, on one bounded price-cross wake review between those boundaries, and—when that review says the frozen path is still `HELD` but chooses `NOTHING`—on exactly one fresh full scan at the next completed minute. It also calls Luna on each newest completed minute while positioned. Before a scheduled scan or position-management call launched late in the minute, it waits briefly for the next native packet while preserving the due reason; pending delivery, direct reassessment, and unscheduled wake checks are never delayed. A trigger review consumes only the fired condition; unrelated frozen instrument paths remain armed until a successful full flat scan other than that one-shot follow-up replaces the set. Its one next-minute follow-up does not replace or rearm that set, and a failed flat scan also leaves the prior set intact. Each one-minute snapshot keeps its live current bar partial and separately publishes NinjaTrader's prior fully closed candle. Cognition may call a transition completed or accepted only when that fully closed candle supports it; a live partial crossing remains anticipatory evidence and price-only delivery revalidation cannot upgrade it. Every admitted decision call receives a bounded instrument-neutral causal market map plus at most one standardized chart built from those same native facts. They organize completed price sequence, levels, range, VWAP, order-flow response, and geometry as observation only; the numerical packet remains authoritative, missing evidence stays neutral, rendering failure is fail-open, and no extra model call is created. Every flat scan and condition-change review receives bounded recent factual decisions, executions, and outcomes; native master stop, target, and managed-exit fills remain in that ledger as immediate completed results until the learner's enriched outcome catches up. A same-side re-entry after a recent exit must reconcile what materially changed without imposing a cooldown. Every full flat scan also receives one canonical prior market ledger and must reconcile prior paths before advancing or replacing them. Entry cognition treats acceptance and retests as probability evidence rather than cumulative prerequisites, and independently derives the nearest setup-specific noise-surviving invalidation and probabilistic objective. Target-first probability must debit already-traveled displacement, opposing structure, exhaustion, evidence quality, and source age; one- and five-minute noise inform stop survival without becoming a fixed ATR gate. Noise is assessed from instrument, intended horizon, structure and costs, not a dollar-stop or reward/risk presumption. Position management explicitly classifies the original thesis as `HELD` or `FAILED`, then compares continuation and exit without a PnL-sign gate. Original native fill/protection receipts supply immutable initial risk; current-to-stop giveback and sampled excursions are labeled separately. On a trigger review it separates the inherited broader-path invalidation from the immediate setup invalidation, using the broader stop only when no nearer structure both falsifies the entry and survives ordinary horizon noise. It prices plausible delivery drift once and leaves stale-price rejection to deterministic latest-price revalidation; when a still-valid entry moves outside its stale delivery range, exactly one fresh flat scan re-compares all candidates without replaying or amending the old intent. Known decisions-boundary JSON delimiter defects, misplaced decision-level wake triggers, and escaped ledger separators are normalized without changing cognitive values. Contract-only output repair is compact and preserves authored geometry and probabilities. It cannot invent a new entry. Probability ranges and EV labels must agree arithmetically; a positive unchanged-bracket forecast may still lose to a specifically justified WAIT. The immediate path forecast is separate from the original target-before-stop event. Hourly learning independently reconstructs opportunity geometry instead of inheriting a rejected decision's remote invalidation or confirmation requirement, and records named missed-opportunity, disciplined-abstention, and uncertain episode IDs. The learner launcher publishes started/running state immediately. If a live decision preempts a learner model call, the same detached scheduled worker yields, preserves its freshly derived evidence, and retries for a bounded window; an AI pause ends retries so profile deployment remains safe. AI resume publishes a bounded waiting state, so operator priority or a deployment pause cannot leave false stale health behind. Every cognitive loop uses the configured Hermes model route and rechecks AI, market and freshness admission after obtaining its shared model lock. Explicit provider usage exhaustion holds both loops until operator `/trade` resume; transient failures do not latch this hold. Job control is scoped to this installed profile. On a fresh installation both jobs are paused.

Both scheduled loops share the same final model-call admission rail. A call may start only while AI Auto and its persisted scope are valid, Glitch's native account-session verdict says the market session is open, all five packet frames and every packaged instrument are fresh and contiguous, and the current native feed self-check is fresh. The same admission is rechecked before a transport retry or contract repair. Closed, maintenance, weekend, stale, partial, or paused conditions consume no model call; a deferred learner waits for a later cron instead of polling.

Configure the desired master/group in Glitch, turn on Replication if followers should copy the master, then activate the complete operator and learning loop with Glitch **AI Auto** or:

```text
/trade
```

`/trade_mode paper|live` remains only as a deprecated compatibility alias. Its argument does not select accounts or change authority.

## Update

v0.0.2.79 assesses a surviving path with current supported geometry rather than
only an inherited remote stop and consumed destination. Reaching a previously
preferred entry zone does not reset permission to a new extreme; waiting needs
a specific advantage over acting now or rejecting the setup. Continuation beyond
the highest supplied reference remains an uncertain hypothesis, not forbidden
room. Entry ranges describe their actual validity boundaries under fill-relative
bracket translation, with one completed prior call's duration supplied as context,
not a latency guarantee or width rule. Short-window coverage survives market-map
compaction. Noise-surviving invalidation, probabilities, revalidation, model,
cadence, management, learning and native order handling are unchanged.

v0.0.2.78 distinguishes a routine retest that leaves a thesis intact from the
boundary that actually invalidates it. It explains the existing native contract:
initial stops and targets retain their distance from the decision reference and
shift with the actual fill. Hermes evaluates that geometry across its entry range
without a fixed dollar, ATR or reward/risk floor or a mandatory confirmation wait.
Scheduled decisions receive an explicitly empty per-process toolset: supplied
data, chart, preloaded skills and deterministic arithmetic handling remain, while
blocked calculator detours cannot add another tool/continuation round. Learner
and interactive tools, model, cadence, admission, native orders and replication
are unchanged. This is a bounded reasoning/latency correction, not evidence of
profitability or proof of a time-dependent degradation mechanism.
The learner's evidence collector now indexes minute-frame files once, skips
already-recorded intents before rebuilding packets, and looks up prior cognition
only when constructing a new eligible episode. This removes redundant work that
grew with accumulated history, without changing evidence, learning rules or calls.
The distribution owns its nine named Glitch skill directories, not the shared
skills folder; unrelated skills and usage metadata survive supported updates.

v0.0.2.77 accepts a single management EV verdict followed by a parenthetical
explanation without rewriting the authored audit. Ambiguous verdicts and
arithmetic contradictions remain invalid. Probability, action, native protection,
freshness, correction limits and trading doctrine are unchanged.
It also avoids new decision calls when a fresh native snapshot proves every
selected master is already locked by its configured daily capture and all enabled
group members are flat with no working orders. Unknown or stale state, eligible
masters, active exposure and explicit operator instructions retain the normal
path. Existing delivery and learner calls are unaffected; no local latch, target,
threshold, or trading strategy is introduced.

v0.0.2.76 computes a contradictory bare terminal EV label for an already-authored
NOTHING from its unchanged levels, costs and probability range, without another
model call. Entry and management contradictions retain strict validation and
bounded correction. Complete audit tails with an identical repeated final choice
are relocated verbatim; format repairs receive the required ledger mode and book
count. The base HOLD/NOTHING template no longer contradicts required action-specific
entry/protection fields. Missing or invalid protection payloads await a fresh
full-state review without a futile correction that cannot preserve that payload.
Trading doctrine, geometry, execution and learning are unchanged.

v0.0.2.75 corrects completed-leg path efficiency to use the same pivot endpoints
for displacement and sampled travel. Intervening closes preserve observed
reversals; travel inside each bar remains unknown. Other geometry, chart data,
swing confirmation, execution and v74 decision rules are unchanged.

v0.0.2.74 restores known inline ledger separators and a complete misplaced audit
tail without inventing evidence. Stops and targets are checked against native
tick size before delivery. In the existing single correction pass, Hermes may
choose only the adjacent executable ticks for an off-tick entry price; direction,
size, probability, entry range and already-valid prices cannot change. Native
preflight and latest-price rejection remain intact. A fresh review may derive a
new valid zone after an old order expires, without reviving that order. Optional
VWAP/flow absence is not a blanket veto on a supported price/structure thesis.

v0.0.2.73 preserves observed chart context and already-confirmed swing references
within the existing bounded lookback when a minute is missing. Gaps remain visible;
local movement, flow and imbalance calculations still use consecutive observations.
Contract repair cannot change a positioned book's action, protection or probabilities.
An obsolete management repair yields to the next fresh packet instead of starting
another model call. Entry guidance distinguishes the acceptable fill range from
stop survival; neither ATR nor a preferred reward/risk ratio becomes an action gate.

```powershell
hermes profile update glitch
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch\setup.ps1"
```

Updates replace distribution-owned cognition, skills, plugin, and worker scripts. Hermes preserves authentication, non-routing `config.yaml` overrides, sessions, memories, ledgers, and cron enabled/paused state. Re-running setup reconciles the supported model route, clears obsolete fallback/model overrides, and reconciles job definitions without changing whether an existing supported job was enabled or paused.

## Clean epoch reset

When the operator explicitly requests a fresh learning epoch, pause AI first and run:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch\scripts\reset-hermes-trading-epoch.ps1" -Apply
```

The reset owns only the Hermes backend. It refuses to run unless AI and both jobs are paused, stops the profile gateway, then creates and SHA-256 verifies a checkpoint under `GlitchData\hermes-checkpoints` before deleting anything. The checkpoint preserves Hermes memories and plans plus the complete supervisor learning ledger, current guidance, current plan, prior epoch identity, and installed distribution record; it deliberately excludes replaceable multi-gigabyte packets and market snapshots. Only after verification does reset permanently clear Hermes sessions, request dumps, cron history, logs, stale jobs, decisions, intents, packets, snapshots, learning artifacts, and overlays. It does not inspect or mutate NinjaTrader accounts, positions, or orders, and it preserves the Glitch Journal, TradeLedger, warnings, locks, peaks, analytics cache, policy, account groups, ratios, licensing, and UI settings. Setup then recreates exactly two paused jobs and a fresh Hermes state database. There is no unbacked apply path.

When the command completes, reset the intended NinjaTrader accounts and use Glitch **Reset Data** to clear Journal and Summary statistics. Those operator-owned actions are deliberately outside the backend script.

## Frozen cognition evaluation

The deterministic evaluator is deliberately unscheduled and outside both the direct operator and the model learner. It cannot create, suppress, amend, or execute an intent. It freezes the exact prompt and cognitive-bundle hash plus the current evidence cursors, then scores only later exact-version decisions and completed master outcomes.

Pause Glitch AI first, then create the prospective checkpoint with the Hermes Python runtime:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  "$env:LOCALAPPDATA\hermes\profiles\glitch\scripts\evaluate-frozen-cognition.py" freeze
```

The default cost policy applies a four-tick round-trip research stress and is explicitly unverified; it may evaluate the local experiment but can never pass the product-distribution gate. To make product evidence eligible, freeze with an explicit all-in round-trip USD cost for every traded instrument and name the verified source:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  "$env:LOCALAPPDATA\hermes\profiles\glitch\scripts\evaluate-frozen-cognition.py" freeze `
  --round-trip-cost-usd MES=5.00 --round-trip-cost-usd MNQ=2.00 `
  --round-trip-cost-usd M2K=2.00 --verified-cost-source "operator verified schedule"
```

The amounts above demonstrate syntax only; they are not fee recommendations. After the frozen observation period, score and publish the report used by the lesson-lifecycle gate:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" `
  "$env:LOCALAPPDATA\hermes\profiles\glitch\scripts\evaluate-frozen-cognition.py" evaluate --publish
```

The report separates gross result, explicit evaluation cost, net result, forecast Brier score versus climatology, independent NOTHING opportunity chronology, execution quality, weekly/instrument/regime-stratified results, and the local versus distribution gates. Counterfactual NOTHING paths are labeled as chronology, never fills or realized PnL. Evaluation executes the checkpointed evaluator and writes one immutable report; publication binds that report, its freeze manifest, and its evaluator hash. The learner accepts only the newest matching verified publication, and an unevaluated active freeze prevents automatic prompt activation.

## Controls

- `/trade` — turn AI trading and learning on for the Glitch-configured scope.
- `/pause_trading` — turn both scheduled loops off.
- `/flatten_all` — pause both loops and ask Glitch to flatten its configured accounts.
- `/glitch_status` — show control, policy, replication, gateway, and job state.
- `/long [all|<route>]`, `/short [all|<route>]` — one-cycle operator-directed experiment. Bare form is accepted only when exactly one route is bound; the response names the captured scope.
- `/bias_long`, `/bias_short`, `/bias_neutral` — advisory direction only.

The `SHA256SUMS` file covers distribution-owned cognition, skills, plugin, workers, setup, and documentation, and is verified before setup changes are made. It excludes itself, user-preserved `config.yaml`, and the install-stamped `distribution.yaml`.
