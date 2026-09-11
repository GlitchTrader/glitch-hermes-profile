# Reference units and management serialization - v0.0.2.82

## Cause and scope

Native trade/decision reconstruction found successful cheap-stop trades aimed at
meaningful auction destinations alongside recent short-lived entries aimed at
nearby range noise. This does not establish a fixed dollar stop floor, preferred
ratio, or progressive memory decay. Earlier and recent decisions must remain
attributable to their exact bundles and supplied evidence.

The cognition clarification replaces existing wording: select the meaningful
auction move and horizon before the bracket, distinguish incidental management
levels from the primary destination, and show the numeric fill-shifted stop and
target at both entry-range edges. A touch stop cannot rely on sustained acceptance
after it would already execute. Anticipation, valid range rotations, locally cheap
invalidation and probabilistic extension targets remain available.

The worker converts at most six existing same-packet reference levels per current
scoped instrument into native ticks, one-contract dollars and 1m/5m ATR units.
Absent ATR stays unknown; missing native economics is not inferred from a default
contract. No levels, rankings, forecasts, signals or entry gates are generated.
Original packets and the bounded causal market map are not modified.

Two observed serialization failures had explicit, recoverable values: an identical
audit sibling outside its audit, and a missing terminal decision brace followed by
management protection at batch level. Recovery relocates only uniquely owned
single-decision MOVE_STOP/MOVE_TP payloads without changing action, leg or prices.
Identical known audit copies collapse; conflicts, ambiguous multi-book ownership,
foreign/missing legs, invalid prices and unknown fields still fail. Terminal repair
rejects duplicate JSON object keys. The final output instruction now closes a
decision after all action-specific fields instead of prescribing a no-action tail.

## Validation and protected behavior

Focused regressions cover lossless recovery, ambiguity rejection, existing native
validation, unit differences, absent data, source identity, scoped current-frame
placement, bounded context and original-input immutability. The actual failed
responses pass full validation offline with their original scenarios and unchanged
authored action/protection, requiring no additional correction call.

No NinjaTrader source, native offset/replication/protection behavior, account or
risk setting, model, invocation cadence, learner, data-admission check or decision
repair count changes. The private operational review records full-suite results,
checkpoint verification, publication/install parity and natural live-cycle proof
separately. None proves future profitability or zero defects.

Rollback uses a scoped source revert and supported profile update, while retaining
the verified configuration/learning/epoch checkpoint. No account, order or learner
reset belongs to this release.
