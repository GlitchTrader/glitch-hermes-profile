# Decision delivery integrity — 2026-09-09

Baseline: profile `786e66c` / v0.0.2.73; native `18d3624`.

## Evidence and authorized scope

The operator requested the best evidence-supported coupled system for the next
24 hours, with minimal warranted repairs and end-to-end verification. This is not
permission to invent a strategy, force trades, reset learning, or restart NT.

- Cycle `20260909T0214Z` failed after a JSON correction retained every named
  trigger-review field but serialized them inline. The validator interpreted
  separators as missing cognition. Its first response also contained a complete
  disconfirming-evidence value at the terminal end of the wrong string.
- MES entry decisions `0153Z` and `0154Z` used stop 7685.375 and targets
  7680.6098/7680.6237 on a 0.25 tick instrument. Native preflight now prevents
  unprotected execution, but the upstream contract did not establish executable
  prices. No native rounding or removal of native preflight is authorized.
- Those entries expired outside a two-tick range. Later fresh reviews repeatedly
  treated the expired range as a continuing prohibition, even at better short
  prices. The old order must remain expired; a fresh judgment must derive its own
  current valid zone without changing the old decision.
- Current reviews repeatedly reject M2K for missing optional VWAP/order flow.
  The scan skill calls flow a requirement despite the existing uncertainty rule.
  Correct that contradiction without treating missing evidence as confirmation.

## Bounded change

Only the direct worker's serialization/native-price preparation and relevant
scan/setup/intent wording, focused tests, and distribution metadata. Preserve
every authored action/probability through representation-only normalization.
If a native price is not representable, only Hermes may select an executable
representation; code must not silently move protection or substitute a trade.

Protected: AddOn/indicator, replication, controls, native safety, user policy,
model/provider/cadence, latest-price/position checks, mathematical EV meaning,
learning history/promotion, chart calculations, account state and configuration.
No new strategy, dollar/ATR/RR gate, quota, or automatic account intervention.

## Proof before release

Baseline: all 362 profile tests pass; 61 native/control tests pass, including
production gateway/host/reducer harnesses and complete AddOn compilation.
Windows tests use short isolated workspace temp paths; default temp permissions
and overlong test paths were test-environment failures, not production defects.

Require witnessed failures before fixes, focused and full regression tests,
offline replay of preserved responses/packets, complete diff review, a verified
learning checkpoint, published/installed parity and a fresh natural runtime
decision. No live test order or flatten. Forward profitability remains unproven.

Rollback: reinstall the checkpointed v73 distribution without resetting evidence.

## Implementation and offline proof

- v74 changes the direct worker, scan/intent wording and distribution metadata;
  no AddOn, indicator, market-map, management doctrine or cadence change.
- The inline ledger repair changes separators only; complete misplaced audit
  tails are relocated verbatim. Partial or ambiguous tails remain rejected.
- Native price validation reports neighboring executable ticks. The existing
  single repair pass lets Hermes choose within that representational boundary,
  preserving direction, size, probabilities, range and all already-valid prices.
  It cannot silently round, enlarge risk beyond those ticks or originate a trade.
- Both actual failed responses in sessions `20260908_231426_7b57eb` and
  `20260908_231509_506299` now extract and validate offline, preserving MNQ NOTHING
  and exact audit keys, with zero model calls. Existing WAIT comparison warnings
  remain observations; this repair does not convert a negative-value abstention
  into an entry or claim the model's comparisons were optimal.
- Focused regression: 190 tests passed, including unchanged adjacent audit-tail
  rejection, missing evidence rejection, six entry price fields, management
  prices, floating-point representation, one bounded repair, shared master
  routing and forbidden recalibration, including after demotion to NOTHING.
  Full profile suite: 396 passed; native/control baseline: 61 passed. Deployment
  and fresh-runtime proof follow; test success alone is not live acceptance.
