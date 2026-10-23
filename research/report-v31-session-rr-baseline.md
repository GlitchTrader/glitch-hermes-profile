# v31 + session extremes rehydrate (2026-10-23)

## Data bug (pre-prompt)
`SessionTracker` in `GlitchAiMarketIngest` / `GlitchAnalyticsBridge` was incremental-only. After NT recompile ~18:12Z, session high/low reset to the live window and `previous_*` went null — Luna saw MES room ~3.5 pts instead of ~18.

**Fix:** rebuild current + previous session extremes from loaded 1m bars (up to 2000). Snapshot `session.extremes_status` = `complete` | `partial_no_previous`.

**Requires:** NT recompile of Indicator (ingest + bridge + MarketSnapshotJson).

## evidence_quality
`ready` now hard-gates on contiguous history + previous-session extremes. Truncated reload → `partial` with `missing` including `previous_session_extremes` / `contiguous_bar_history`.

## Prompt v31 (`direct-v31-rr-baseline`)
- Removed pooled NOTHING 0.45 vs ENTER 0.23 priors (R:R mixture).
- Baseline = `risk/(risk+reward)`; Luna states signed edge only.
- NOTHING must author numeric entry/stop/target (`selection_ev_nothing_geometry_required`).
- Delivery-survivable range expansion from v30 kept.

## Still outside this freeze
- Scorer without neither-censoring; barrier table by ATR×R:R; paired Luna-vs-baseline edge.
