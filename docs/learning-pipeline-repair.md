# Learning pipeline repair

**Scope:** Glitch NinjaTrader Advanced / Hermes profile

## Root causes

1. Outcome reconciliation used Hermes `outbox/*.json` as its decision source.
   Outbox packets are delivery state and can be consumed or discarded. They
   cannot be the durable attribution ledger. Completed executions therefore
   had no matching intents and `hermes-trade-outcomes.jsonl` remained empty.
2. Direct and learning workers invoked Hermes against the same mutable profile
   state without a shared CLI lock. The profile recorded `WinError 5` while
   replacing `cron/jobs.json`, and failed learning sessions ended before their
   first model/API call.
3. Worker errors retained too little stderr to distinguish a provider failure,
   profile-state failure, or process-launch failure.
4. The AI portfolio-event writer joined the `expires_utc` property directly to
   `portfolio_events`, producing invalid JSON for directive wake payloads.

## Implemented fixes

- `reconcile-hermes-outcomes.py` accepts the append-only
  `GlitchData/intents/decisions.jsonl` decision log.
- `run-direct-glitch-cycle.py` supplies that durable log during every
  reconciliation. The outbox remains available only as supplemental evidence.
- `win_subprocess.py` provides a crash-recoverable per-profile Hermes CLI lock.
  Both direct and learning workers use it around the Hermes child process.
- Direct and learning worker failures now retain stderr and stdout tails with
  the exit code.
- A regression test proves decisions remain discoverable after outbox
  consumption.
- The AI AddOn portfolio-event writer now emits a comma before
  `portfolio_events`, restoring valid directive JSON.

## Non-fixes by design

The `direct-v6-local` decision policy was not loosened. The learner must receive
attributable outcomes before prompt behavior is evaluated or changed. Native
NinjaTrader execution remains the performance authority; Hermes outcomes are
the AI attribution layer.

## Verification contract

- Reconciliation must discover decisions from the durable decision log even
  when the corresponding outbox packet is absent.
- Concurrent direct and learning Hermes calls must serialize per profile.
- A failed worker status must include actionable child-process diagnostics.
- Runtime follow-up belongs to the native cron workers, not Codex monitoring.
