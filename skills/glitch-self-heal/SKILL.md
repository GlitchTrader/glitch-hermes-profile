---
name: glitch-self-heal
description: Reconcile Hermes-owned state to authoritative Glitch and NinjaTrader evidence, append an auditable correction, and resume safe operation autonomously. Use for discrepancies, interrupted delivery, stale locks, malformed output, missing derived indexes, memory conflicts, session/job faults, or mismatched Hermes bookkeeping.
---

# Glitch Self Heal

Reconcile truth, record the correction, and resume. Self-healing is not an
escalation path and must not depend on Codex or a human operator.

## Truth order

Use this order whenever records disagree:

1. current NinjaTrader/Glitch positions, working orders, fills, balances, PnL,
   brackets, and signed execution receipts;
2. immutable Glitch packets, decisions, execution events, and journal records;
3. operator-confirmed facts;
4. Hermes outbox, receipts, ledger, journal, knowledge, session, and memory;
5. inference.

Never invent missing facts. Preserve the conflict until stronger evidence
resolves it.

## Reconcile and resume

1. Identify the affected packet, intent, trade, route, account, stream, and
   time range. Capture both sides of the discrepancy.
2. Rebuild only Hermes-owned derived state from authoritative evidence. Retry
   interrupted delivery only with the same validated packet and intent IDs.
   Clear a Hermes lock only after proving no owning process remains.
3. Append a correction to the Hermes health/ledger/journal stream with the old
   claim, authoritative evidence, corrected state, action taken, and UTC time.
   Never rewrite or delete the original record.
4. Use a supported Glitch reconciliation or journal surface when Glitch must
   append its own record. Never edit Glitch-owned trading truth directly.
5. Verify positions, orders, protection, receipts, and derived state agree.
   Resume the affected capability or group when that proof exists. Healthy
   groups continue throughout.

If safety cannot be proven, stop new entries only for the affected group or
capability, preserve existing native protection, append the unresolved fault,
continue diagnosis, and keep all unaffected operation running. A source defect
may be recorded for later building, but self-heal does not wait for that work.

## Forbidden recovery

- Never reset an account, PnL baseline, journal, ledger, session, or memory to
  make records agree.
- Never delete or conceal losses, rejects, disconnects, rule breaches, or
  failed repairs.
- Never fabricate a fill, bracket, outcome, reconciliation, or recovery.
- Never loosen risk, raise limits, change groups, target followers directly,
  bypass Glitch, or place a bookkeeping trade.
- Never mark a fault resolved until current authoritative evidence proves it.
