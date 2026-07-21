---
name: glitch-assess-risk
description: Assess the supplied Glitch group, prop-firm state, positions, protection, ratios, and valid entry quantities.
---

# Assess Risk

Use `CURRENT_CYCLE.execution_scope` and the latest supplied portfolio frame as current authority.

1. Confirm the route and master match, the instrument is MNQ, and Glitch reports no current risk, session-time, direction, or prop-firm restriction on increasing exposure. Treat news as volatility/context unless the current packet states an explicit account rule.
2. Read follower state as replication diagnostics only. Followers and ratios determine their replicated account exposure, but never the master's strategy or sizing; only the master is an intent target.
3. Choose an entry quantity only from that book's `valid_entry_quantities`. Glitch derives this list from the master's authoritative contract ceiling and current account-wide exposure. Followers and user-owned ratios never constrain master cognition or quantity. Never invent fallback capacity.
4. An existing same-direction, fully protected position may permit `HOLD`, `MOVE_STOP`, `MOVE_TP`, `EXIT`, or another protected tranche. `MOVE_TP` may carry a tighter stop but can never loosen it. Never reverse through an entry or exceed supplied capacity.
5. Estimate MNQ loss from the proposed absolute stop using the supplied point value when available. Judge that risk against structure, current portfolio state, drawdown, and prop restrictions; do not impose a separate fixed-dollar cap.
6. If current facts are missing, stale, inconsistent, or unsafe, allow no new exposure. Risk-reducing management remains available when the position is unambiguous.
7. `entry_window_open=false` forbids new exposure. If positioned, plan `EXIT` before `must_flat_utc`; the deterministic harness is only the final fail-safe.

Return a compact assessment: allowed actions, valid quantities, current signed exposure, protection state, structural risk, applicable constraints, and factual blocking reasons.
