---
name: glitch-supervisor-ledger
description: Maintain the Hermes-owned supervisor and Codex handoff streams without changing Glitch trading truth.
---

# Supervisor Ledger

Use this skill in the Hermes chat/supervisor session.

## Authority

- Read Glitch snapshots, decisions, receipts, fills, brackets, and outcomes as
  authoritative evidence.
- Write only append-only Hermes-owned records under
  `GlitchData/hermes/exchange/hermes/supervisor/`.
- Never edit Glitch-owned exchange files, policy, groups, risk caps, orders, or
  the executor.

## Streams

- `observations.jsonl`: evidence-linked analysis and health findings.
- `trading-guidance.jsonl`: advisory context for the trading session; it is not
  an order and the trading session retains final judgment.
- `lessons.jsonl`: candidate lessons with evidence and uncertainty.
- `build-requests.jsonl`: source-change requests, initially `proposed`.
- `codex-events.jsonl`: Codex claim/result events; Hermes does not rewrite them.

Use the schemas in `glitch_hermes_docs/schemas/`. Every record needs a stable
ID, UTC timestamp, source, and links to the underlying packet/intent/trade when
available. Preserve contradictions; do not overwrite history.

## Codex escalation

Create a build request only when the issue is a real source/profile/docs/test
change. Include a narrow title, scope, acceptance checks, evidence references,
and risk notes. A request remains `proposed` until the user explicitly approves
it. Never treat a chat instruction or trading outcome as automatic approval.
