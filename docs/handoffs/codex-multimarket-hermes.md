# Codex Handoff — Multi-Instrument Hermes Bridge

Date: 2026-08-10

## Context

Hermes has been refactored to scan eligible instruments symmetrically and select a supported candidate/setup. The Hermes implementation is instrument-neutral and currently handles MNQ, MES, and M2K from the supplied packet.

Hermes-owned changes are complete in:

- `SOUL.md`
- `operator.json`
- `scripts/run-direct-glitch-cycle.py`
- `scripts/run-hermes-learning-cycle.py`
- `skills/glitch-market-scan/SKILL.md`
- `skills/glitch-setup-state/SKILL.md`
- `skills/glitch-order-flow/SKILL.md`
- `skills/glitch-position-management/SKILL.md`
- generalized compatibility `skills/glitch-trade-mnq/SKILL.md`
- `skills/glitch-build-intent/SKILL.md`
- `skills/glitch-learn/SKILL.md`
- `skills/glitch-market-structure/SKILL.md`

Do not reintroduce MNQ-only filtering in the add-on or replace Hermes candidate selection with a fixed instrument.

## Verified current packet facts

Latest live packet:

- schema: `glitch.hermes.decision_packet.v2`
- instruments: `MNQ`, `MES`, `M2K`
- policy allowlist: `MNQ`, `MES`, `M2K`
- instrument economics are supplied per instrument
- current descriptive flow is nested under `instrument.descriptive_state.descriptive_state.flow`
- current flow includes cumulative delta, delta change, delta velocity, delta acceleration, aggression balance, price-flow divergence, and classified volume
- timeframe bars are supplied for 1m/5m/15m/60m
- latest packet does not contain native positions for the observed accounts
- policy scope is represented by the UI-enabled master books and instrument allowlist; there is no separate manual exploration permission

## Required Codex work

### 1. Validate multi-instrument intent acceptance

Add integration tests and, if required, executor changes proving that a valid intent can select `MES` or `M2K` when those instruments are in the authoritative allowlist.

Verify:

- fixed identity checks remain intact;
- instrument allowlist checks use the selected intent instrument;
- quantity uses the selected instrument's native economics and account limits;
- stop/target tick alignment uses the selected instrument's tick size;
- native protection is created and reconciled for the selected instrument;
- replication does not silently convert the selected instrument to MNQ;
- follower routing remains replication context and never creates Hermes decisions;
- rejection receipts identify the selected instrument and exact failure reason.

### 3. Add explicit candidate/scope metadata

Extend the packet or an Hermes-facing immutable scope object with:

```json
{
  "eligible_instruments": ["MNQ", "MES", "M2K"],
  "ordered_master_books": [
    {"route_id": "glitch", "account": "Sim101", "instruments": ["MNQ", "MES", "M2K"]}
  ],
  "scope_hash": "..."
}
```

This must describe eligibility, not dictate the strategy or selected setup. Hermes ranks candidates; Glitch validates the resulting selection.

### 4. Per-candle and per-timeframe order-flow data

The current packet exposes flow under the current descriptive state, but the timeframe-bar rows do not expose a clean per-bar delta sequence.

If the desired cognition requires candle-by-candle order-flow learning, add optional fields to each timeframe bar, without breaking packets where the data is unavailable:

```json
{
  "order_flow": {
    "cumulative_delta": 0,
    "delta_change": 0,
    "delta_velocity": 0,
    "delta_acceleration": 0,
    "aggression_balance": 0,
    "price_flow_divergence": false,
    "classification_coverage": 1.0,
    "classification_method": "..."
  }
}
```

Required behavior:

- derive from native NinjaTrader data;
- preserve unknown as null/unknown, never zero as a fake value;
- include instrument root and timeframe identity;
- keep current descriptive flow backward compatible;
- add fixture and live serialization tests for MNQ, MES, and M2K.

No new indicator is required if the existing analytics bridge can produce these values accurately. If it cannot, modify the indicator/analytics bridge rather than synthesizing them in Hermes.

### 5. Structured forecast metadata

The current intent contract supports only:

```json
{"event":"STOP_BEFORE_PRIMARY_TARGET", "probability": ..., "confidence": ..., "method":"..."}
```

Hermes currently keeps additional current/next setup and probability reasoning inside required audit strings because unknown intent fields are rejected.

Optionally extend the contract with a backward-compatible forecast collection for:

- continuation probability;
- reversal probability;
- target-before-stop probability;
- next 5–10-candle path probability;
- setup-transition probability;
- regime classification.

This must remain non-gating metadata. Glitch must not execute or reject solely because a forecast is uncertain or missing.

### 6. Exact excursion telemetry

Hermes can use supplied active-trade peak/rollback fields and sampled outcome evidence. Exact intrabar counterfactual management remains limited when only sampled MFE/MAE is available.

If exact management learning is required, add authoritative trade telemetry for:

- native position price path at adequate resolution;
- exact MFE and MAE timestamps;
- movement through breakeven;
- target/stop first-touch ordering;
- native amendment receipt sequence;
- active setup/market snapshot reference at each amendment.

Do not add synthetic counterfactual PnL.

## Acceptance criteria

1. A live packet containing MNQ, MES, and M2K reaches Hermes unchanged.
2. Hermes can select any allowlisted instrument in a valid intent.
3. Glitch accepts and executes a selected MES/M2K intent within the UI-enabled simulated master scope.
4. Glitch rejects an intent for a non-allowlisted instrument with an authoritative receipt.
5. Native protection and quantity validation use the selected instrument's metadata.
6. No follower receives an independent decision.
7. The UI-enabled master scope remains the sole authority for active simulated trade scope; no parallel manual permission gate exists.
8. Per-candle order-flow fields remain null/unknown when unavailable and never become fabricated directional evidence.
9. Existing MNQ behavior and all current contract tests remain valid.
10. Reconciliation records instrument, scope, selected setup metadata where available, and native receipts.

## Handoff boundary

Hermes will not call Codex, modify the add-on, modify indicators, or claim these changes are deployed. Codex should return build/test/deployment handles, changed paths, commit/build identifiers, and verification output to the operator owner.
