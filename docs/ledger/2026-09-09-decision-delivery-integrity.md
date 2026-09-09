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

## Live-input finding after v74 activation

The natural `0254Z` review used the new bundle successfully (31.6 seconds,
zero repair/retry). Inspecting its input revealed MES completed-leg
`path_efficiency=1.666667`: `_legs` divided swing-extreme displacement by a
different close-to-close path. This is a deterministic measurement defect, not a
reason to retune trading. A bounded v75 follow-up will use identical pivot
endpoints for numerator and denominator, with intervening observed closes and
explicit unknown intrabar travel. Preserve swing confirmation, points/ticks/ATR,
completed/current identity, chart, all other calculations and v74 cognition.

The fix is three calculation lines plus a comment; the existing structure skill
defines sampled versus unknown intrabar travel once, avoiding repetitive map
metadata and preserving the existing text budget. Eighteen new mirrored,
instrument-neutral cases fail on v74 and pass after correction. The focused
suite passes 236 tests. Replay of actual packet `20260909T0254Z` changes only
completed-leg efficiencies: MES 1.666667 becomes 1.0; another MNQ leg had 4.875
and becomes 1.0. Intervening reversals still reduce efficiency. Every other
measurement, retained state and rendered PNG byte is unchanged. Replay images:
`D:/ab/t/g75-replay-ff596c`. No model call or runtime evidence mutation was used.
The complete v75 profile suite passes 414 tests. The native/control suite remains
61 passing tests; native production files have not changed in either release.

v74 publication/install proof: main `31c1f83`, bundle `863839d9200e`, all 29
distribution hashes matched; 33 protected configuration/native-ledger/learning
files stayed byte-identical during update. Verified 65-file checkpoint:
`D:/ab/checkpoints/glitch-v74-before-20260909T0252Z`. AI restored at 02:54:12Z,
both original cron IDs/schedules enabled, replication unchanged, NT PID 19808
unchanged. Fresh `0254Z` and `0255Z` cycles attached charts and completed with
zero output repairs or transport retries. This proves operation, not an edge.

## Final v75 deployment verification

- Published implementation: `26ef5b8799b66a11420bc17f8b0a5626e7224b5a`,
  verified against remote `main`; v75 bundle `3682d1f88485` matches source and
  installed profile. Supported `hermes profile update glitch --yes` and the
  installed setup completed successfully.
- Verified 65-file v74 rollback checkpoint:
  `D:/ab/checkpoints/glitch-v75-before-20260909T0311Z`. The existing learner was
  allowed to finish local processing and defer its model call while AI was
  paused; neither worker was killed and no learner/epoch evidence was reset.
- All 29 distribution-owned files and the checksum manifest match source.
  All 33 protected configuration, native-ledger and learning files stayed
  byte-identical across this installation. Native source/live remain 95/95
  matching files; NT PID 19808 and its start time are unchanged.
- Original AI ON state restored at `2026-09-09T03:13:03Z` through native control.
  Policy valid, execution enabled, replication enabled and effective. Both
  original cron IDs/schedules remain enabled. All seven native accounts were
  flat with zero working orders before resumption; no test trade was sent.
- Post-install regression rerun: 414 profile tests and 61 native/control tests
  passed. No additional model invocation was initiated for testing.
- Natural scheduled scan `20260909T0315Z` completed in 50.6 seconds using bundle
  `3682d1f88485`, with its chart attached, zero output repairs, zero transport
  retries and a complete native receipt. It chose NOTHING: the prior MNQ target
  was consumed, the remaining nearby support was too close relative to supplied
  noise, and no supported new extension target was established. Missing M2K
  flow/VWAP were described as neutral limitations rather than directional facts.
  The observational `selection_ev_numeric_invalid` flag remains visible because
  this abstention supplied `target=NONE_SUPPLIED` and no numeric target-first
  forecast; this is not a failed delivery or evidence of calibrated probability.
- Read-only reconstruction from the exact `0315Z` retained state confirms all
  eight MES/MNQ completed-leg efficiencies lie in [0,1]. M2K has three contiguous
  completed bars, no completed leg, and unavailable VWAP/order flow; no missing
  bar or indicator was fabricated. The rail at `03:16:57Z` reports health ON,
  no reason codes, three fresh instruments and a completed decision worker.

## Acceptance boundary

The witnessed defects are repaired and the tested distribution is live. These
checks do not establish profitable expectancy, calibrated target-first
probabilities, or every possible broker/order lifecycle. There was no naturally
originated v75 trade during this deployment check, so no new fill/protection
claim is made. Preserve this version for forward evidence rather than adding
strategy gates, increasing risk, forcing entries or retuning from this one
abstention. Known missing market evidence remains explicit.
