# Glitch Hermes Profile v0.0.2.68

This repository distributes the cognition, skills, deterministic workers, and control plugin used by the **Experimental** Glitch AI edition.

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

`profile install` performs no model call and creates no cron job. `setup.ps1` verifies the distribution, enables the deterministic plugin, installs the supervised profile gateway, and creates the minute operator plus a 30-minute learning job offset to minutes 02 and 32. The minute dispatcher calls Luna on completed five-minute boundaries while flat, on one bounded price-cross wake review between those boundaries, and—when that review says the frozen path is still `HELD` but chooses `NOTHING`—on exactly one fresh full scan at the next completed minute. It also calls Luna on each newest completed minute while positioned. Before a scheduled scan or position-management call launched late in the minute, it waits briefly for the next native packet while preserving the due reason; pending delivery, direct reassessment, and unscheduled wake checks are never delayed. A trigger review consumes only the fired condition; unrelated frozen instrument paths remain armed until a successful full flat scan other than that one-shot follow-up replaces the set. Its one next-minute follow-up does not replace or rearm that set, and a failed flat scan also leaves the prior set intact. Each one-minute snapshot keeps its live current bar partial and separately publishes NinjaTrader's prior fully closed candle. Cognition may call a transition completed or accepted only when that fully closed candle supports it; a live partial crossing remains anticipatory evidence and price-only delivery revalidation cannot upgrade it. Every admitted decision call receives a bounded instrument-neutral causal market map plus at most one standardized chart built from those same native facts. They organize completed price sequence, levels, range, VWAP, order-flow response, and geometry as observation only; the numerical packet remains authoritative, missing evidence stays neutral, rendering failure is fail-open, and no extra model call is created. Every flat scan and condition-change review receives bounded recent factual decisions, executions, and outcomes; native master stop, target, and managed-exit fills remain in that ledger as immediate completed results until the learner's enriched outcome catches up. A same-side re-entry after a recent exit must reconcile what materially changed without imposing a cooldown. Every full flat scan also receives one canonical prior market ledger and must reconcile prior paths before advancing or replacing them. Entry cognition treats acceptance and retests as probability evidence rather than cumulative prerequisites, and independently derives the nearest setup-specific noise-surviving invalidation and probabilistic objective. Target-first probability must debit already-traveled displacement, opposing structure, exhaustion, evidence quality, and source age; one- and five-minute noise inform stop survival without becoming a fixed ATR gate. On a trigger review it separates the inherited broader-path invalidation from the immediate setup invalidation, using the broader stop only when no nearer structure both falsifies the entry and survives ordinary horizon noise. It prices plausible delivery drift once and leaves stale-price rejection to deterministic latest-price revalidation; when a still-valid entry moves outside its stale delivery range, exactly one fresh flat scan re-compares all candidates without replaying or amending the old intent. Known decisions-boundary JSON delimiter defects, misplaced decision-level wake triggers, and escaped ledger separators are normalized without changing cognitive values. Contract-only output repair is compact and preserves the original judgment while supplying required EV or protection fields. Hourly learning independently reconstructs opportunity geometry instead of inheriting a rejected decision's remote invalidation or confirmation requirement, and records named missed-opportunity, disciplined-abstention, and uncertain episode IDs. The learner launcher publishes started/running state immediately. If a live decision preempts a learner model call, the same detached scheduled worker yields, preserves its freshly derived evidence, and retries for a bounded window; an AI pause ends retries so profile deployment remains safe. AI resume publishes a bounded waiting state, so operator priority or a deployment pause cannot leave false stale health behind. Every cognitive loop uses the configured Hermes model route. On a fresh installation both jobs are paused.

Both scheduled loops share the same final model-call admission rail. A call may start only while AI Auto and its persisted scope are valid, Glitch's native account-session verdict says the market session is open, all five packet frames and every packaged instrument are fresh and contiguous, and the current native feed self-check is fresh. The same admission is rechecked before a transport retry or contract repair. Closed, maintenance, weekend, stale, partial, or paused conditions consume no model call; a deferred learner waits for a later cron instead of polling.

Configure the desired master/group in Glitch, turn on Replication if followers should copy the master, then activate the complete operator and learning loop with Glitch **AI Auto** or:

```text
/trade
```

`/trade_mode paper|live` remains only as a deprecated compatibility alias. Its argument does not select accounts or change authority.

## Update

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
