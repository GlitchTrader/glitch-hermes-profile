# Glitch Hermes Profile v0.0.2.1 Candidate

This repository distributes the cognition, skills, deterministic workers, and control plugin used by the **Experimental** Glitch AI edition.

Glitch/NinjaTrader remains the market, account, risk, execution, bracket, replication, and journal authority. Hermes proposes decisions for the master accounts in the groups configured by the user in Glitch. The profile does not distinguish paper from live accounts and makes no profitability, unattended-operation, or live-readiness claim.

## Requirements

- Windows with NinjaTrader 8 and a matching Glitch AI `v0.0.2.1` candidate installed.
- Hermes `0.18.2` or newer.
- An OpenAI Codex OAuth account authorized by the user.

## Install

```powershell
hermes profile install github.com/GlitchTrader/glitch-hermes-profile --alias
hermes -p glitch auth add openai-codex --type oauth
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch\setup.ps1"
```

`profile install` performs no model call and creates no cron job. `setup.ps1` verifies the distribution, enables the deterministic plugin, installs the supervised profile gateway, and creates the minute operator and 15-minute learning jobs. On a fresh installation both jobs are paused.

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

Updates replace distribution-owned cognition, skills, plugin, and worker scripts. Hermes preserves authentication, `config.yaml` overrides, sessions, memories, ledgers, and cron enabled/paused state. Re-running setup reconciles job definitions without changing whether an existing job was enabled or paused.

## Controls

- `/trade` — turn AI trading and learning on for the Glitch-configured scope.
- `/pause_trading` — turn both scheduled loops off.
- `/flatten_all` — pause both loops and ask Glitch to flatten its configured accounts.
- `/glitch_status` — show control, policy, replication, gateway, and job state.
- `/long`, `/short` — one-cycle operator-directed experiment; Glitch still validates geometry, capacity, and execution.
- `/bias_long`, `/bias_short`, `/bias_neutral` — advisory direction only.

The `SHA256SUMS` file covers distribution-owned cognition, skills, plugin, workers, setup, and documentation, and is verified before setup changes are made. It excludes itself, user-preserved `config.yaml`, and the install-stamped `distribution.yaml`.
