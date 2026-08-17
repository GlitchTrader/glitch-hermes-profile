# Glitch Hermes Profile v0.0.2.52

This repository distributes the cognition, skills, deterministic workers, and control plugin used by the **Experimental** Glitch AI edition.

Glitch/NinjaTrader remains the market, account, configured-policy, execution, bracket, replication, and journal authority. Hermes proposes structured intent for the master accounts selected by the user in Glitch. The profile does not distinguish paper from live accounts and makes no profitability, unattended-operation, or live-readiness claim.

The profile is intelligence-first. It supplies evidence vocabulary, time-sequence context, strict output construction, and attributable learning. It does not encode a fixed trading strategy, daily profit target, account-size recipe, preferred setup, geometric template, or hidden action gate. Capacity and supported actions come from the current Glitch packet and user configuration.

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

`profile install` performs no model call and creates no cron job. `setup.ps1` verifies the distribution, enables the deterministic plugin, installs the supervised profile gateway, and creates the minute operator plus a 30-minute learning job offset to minutes 02 and 32. The minute dispatcher calls Luna on completed five-minute boundaries while flat, on one bounded price-cross wake review between those boundaries, and—when that review says the frozen path is still `HELD` but chooses `NOTHING`—on exactly one fresh full scan at the next completed minute. It also calls Luna on each newest completed minute while positioned. A consumed wake remains disarmed until the next successful flat scan arms new triggers. Each one-minute snapshot keeps its live current bar partial and separately publishes NinjaTrader's prior fully closed candle. Every flat scan and condition-change review receives bounded recent factual decisions, executions, and outcomes; native master stop, target, and managed-exit fills remain in that ledger as immediate completed results until the learner's enriched outcome catches up. A same-side re-entry after a recent exit must reconcile what materially changed without imposing a cooldown. Every full flat scan also receives one canonical prior market ledger and must reconcile prior paths before advancing or replacing them. Entry cognition does not recursively inject learner verdicts; at a fresh extreme it derives uncertainty-discounted objectives from current evidence rather than requiring the future target to have traded already. Entry cognition prices plausible delivery drift once and leaves stale-price rejection to deterministic latest-price revalidation. Known terminal JSON delimiter defects and misplaced decision-level wake triggers are normalized without changing cognitive values. Hourly learning evaluates the strongest rejected candidate with candidate-specific economics and records named missed-opportunity, disciplined-abstention, and uncertain episode IDs. It launches the separately locked direct worker and returns immediately. Every cognitive loop uses the configured Hermes model route. On a fresh installation both jobs are paused.

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

The reset owns only the Hermes backend. It refuses to run unless AI and both jobs are paused, stops the profile gateway, and permanently clears Hermes memories, sessions, request dumps, cron history, logs, stale jobs, decisions, intents, packets, snapshots, learning artifacts, and overlays. It does not inspect or mutate NinjaTrader accounts, positions, or orders, and it preserves the Glitch Journal, TradeLedger, warnings, locks, peaks, analytics cache, policy, account groups, ratios, licensing, and UI settings. Setup then recreates exactly two paused jobs and a fresh Hermes state database. No archive is created.

When the command completes, reset the intended NinjaTrader accounts and use Glitch **Reset Data** to clear Journal and Summary statistics. Those operator-owned actions are deliberately outside the backend script.

## Controls

- `/trade` — turn AI trading and learning on for the Glitch-configured scope.
- `/pause_trading` — turn both scheduled loops off.
- `/flatten_all` — pause both loops and ask Glitch to flatten its configured accounts.
- `/glitch_status` — show control, policy, replication, gateway, and job state.
- `/long [all|<route>]`, `/short [all|<route>]` — one-cycle operator-directed experiment. Bare form is accepted only when exactly one route is bound; the response names the captured scope.
- `/bias_long`, `/bias_short`, `/bias_neutral` — advisory direction only.

The `SHA256SUMS` file covers distribution-owned cognition, skills, plugin, workers, setup, and documentation, and is verified before setup changes are made. It excludes itself, user-preserved `config.yaml`, and the install-stamped `distribution.yaml`.
