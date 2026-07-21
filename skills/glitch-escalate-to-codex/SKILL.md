---
name: glitch-escalate-to-codex
description: Turn a Hermes supervisor finding into a bounded, approval-gated Codex build request.
---

# Escalate to Codex

Use only from Hermes chat when analysis shows a source-controlled change is
needed.

1. Record the finding in the Hermes supervisor observations stream.
2. Append one `glitch.supervisor.build_request.v1` record with status `proposed`.
3. State the exact files/scope, acceptance criteria, evidence, and rollback.
4. Wait for explicit user approval before changing status to `approved`.

An approved request is available to a separately invoked builder. It does not
schedule Codex, run trading cycles, poll market data, or imply approval from a
recommendation. Hermes trading remains independent while a request is pending
or being built.
