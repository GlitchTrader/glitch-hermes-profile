---
name: glitch-assess-risk
description: Assess the supplied Glitch group, prop-firm state, positions, protection, ratios, and valid entry quantities.
---

# Assess Risk

Use `CURRENT_CYCLE.execution_scope` and the latest supplied portfolio frame as current authority.

1. Confirm the route and master match, the instrument is MNQ, and Glitch reports no current risk, session-time, direction, or prop-firm restriction on increasing exposure. Treat news as volatility/context unless the current packet states an explicit account rule.
2. Read follower state as replication diagnostics only. Followers and ratios determine their replicated account exposure, but never the master's strategy or sizing; only the master is an intent target.
3. Choose an entry quantity only from that book's `valid_entry_quantities`. Glitch derives this list from the master's authoritative contract ceiling and current account-wide exposure. Followers and user-owned ratios never constrain master cognition or quantity. Never invent fallback capacity.
4. An existing same-direction, fully protected position may permit `HOLD`, exact-leg `MOVE_STOP`, exact-leg `MOVE_TP`, `EXIT`, or another protected tranche. An addition may occur at a favorable or adverse price only when current evidence still supports the thesis; never add merely because price moved against the position or to recover a loss. A stop may tighten or move farther away only while remaining protective and inside the authoritative Apex liquidation buffer. Never reverse through an entry or exceed supplied capacity.
5. Estimate MNQ loss from every proposed absolute stop using the supplied point value and actual leg quantity. For an Apex Legacy evaluation, treat Glitch's authoritative liquidation buffer and the complete Glitch-owned stop coverage of current exposure as a hard account-survival boundary. Missing or ambiguous coverage, point value, buffer, or account state forbids new exposure. Glitch chooses no preferred quantity and imposes no percentage budget, quantity schedule, or artificial reserve.
6. If current facts are missing, stale, inconsistent, or unsafe, allow no new exposure. Risk-reducing management remains available when the position is unambiguous.
7. `entry_window_open=false` forbids new exposure. If positioned, plan `EXIT` before `must_flat_utc`; the deterministic harness is only the final fail-safe.

Return a compact assessment: allowed actions, valid quantities, current signed exposure and average price, initial-entry or addition classification, native protection coverage, protected downside, liquidation buffer when applicable, structural risk, applicable constraints, and factual blocking reasons.
