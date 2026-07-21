---
name: glitch-submit-intent
description: Explain the supported interactive path for steering the Glitch decision worker without bypassing it.
---

# Submit Glitch Intent

Interactive chat never writes an outbox decision or posts a raw intent.

1. Use `/bias_long`, `/bias_short`, or `/bias_neutral` for a one-cycle advisory.
2. Use `/long` or `/short` only for an operator-directed experiment on the configured Glitch scope. The command writes a bounded directive; the next stateless worker cycle still calculates structure and emits the decision.
3. The installed worker alone validates the batch, writes the outbox, and delivers each intent through Glitch's authenticated receiver.
4. Receipts and Glitch execution events are authoritative. A chat response is never evidence that an order exists.

Never write or replace an outbox file, invoke the worker manually to force a second decision, mutate policy/groups/snapshots, or place an order outside Glitch.
