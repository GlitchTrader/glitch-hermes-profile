---
name: glitch-assess-risk
description: Assess the supplied Glitch group, prop-firm state, positions, protection, ratios, and valid entry quantities.
---

# Assess Risk

Use `CURRENT_CYCLE.execution_scope` and the latest supplied portfolio frame as current authority.

1. Confirm the route and master match and the instrument is MNQ. Treat capacity, buffer, session, native-state, lock, direction, and prop-firm fields as current evidence for Hermes's decision, not deterministic cognition or intent gates. Treat news as volatility/context unless the current packet states an explicit account rule.
2. Read follower state as replication diagnostics only. Followers and ratios determine their replicated account exposure, but never the master's strategy or sizing; only the master is an intent target.
3. Choose a positive integer entry quantity from the full current packet evidence; `valid_entry_quantities` is observed capacity evidence, not a required allowlist. Followers and user-owned ratios never constrain master cognition or quantity.
4. An existing same-direction, fully protected position may permit `HOLD`, exact-leg `MOVE_STOP`, exact-leg `MOVE_TP`, `EXIT`, or another protected tranche. An addition may occur at a favorable or adverse price only when current evidence still supports the thesis; never add merely because price moved against the position or to recover a loss. A stop may tighten or move farther away only while remaining protective. Never reverse through an entry.
5. Estimate MNQ loss from every proposed absolute stop using the supplied point value and actual leg quantity. Surface liquidation buffers, protected downside, and incomplete evidence plainly so Hermes can make an explicit decision; do not turn them into inferred survival or quantity policy.
6. If current facts are missing, stale, inconsistent, or unsafe, state that uncertainty explicitly and choose deliberately; risk-reducing management remains available when the position is unambiguous.
7. Treat `entry_window_open` and `must_flat_utc` as session evidence. If positioned, plan `EXIT` before `must_flat_utc`; the visible default-off deterministic daily-close action is the final fail-safe when the operator enabled it.

Return a compact assessment: considered actions, quantity evidence, current signed exposure and average price, initial-entry or addition classification, native protection coverage, protected downside, liquidation buffer when applicable, structural risk, applicable constraints, and factual uncertainty.
