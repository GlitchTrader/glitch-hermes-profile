---
name: glitch-build-intent
description: Serialize a fully compared multi-instrument Glitch judgment into the supported intent schema.
---
# Build the Intent

During a normal flat scan, serialization begins only after every eligible instrument has a complete `INSTRUMENT_COMPARISON_V1` ledger. During a condition-change wake, serialize the compact `TRIGGER_REVIEW_V1` record supplied by the operator. When positioned, serialize the compact `POSITION_MANAGEMENT_V1` record for the active native instrument. Do not reinterpret the market during serialization or default to the first instrument.

Return exactly one `glitch.intent.batch.v1` object with one decision per ordered master book. When the operator instructions state that all ordered master books are flat and share one market decision, return exactly one decision object; the runtime deterministically binds that identical decision to every ordered master book. Preserve supplied cycle ID, account, route, snapshot hash, model version, prompt version, and supported top-level shape. Use only supported actions. Copy the selected instrument exactly from the candidate packet; never default to MNQ.

Preserve the exact required `decision_audit` keys and make `final_choice` appear once and equal `action`. When flat, put the complete symmetric comparison in `decision_audit.decisive_evidence` using:

```text
INSTRUMENT_COMPARISON_V1
INSTRUMENT MNQ:
REGIME_LOCATION=...
CURRENT_AUCTION=...
BULLISH_PATH=...
BEARISH_PATH=...
NEXT_TRANSITION=...
PRIOR_TRIGGER_REVIEW=NOT_APPLICABLE
FIVE_TO_TEN_BAR_FORECAST=...
DELTA_PRICE_RESPONSE=...
OBJECTIVE_INVALIDATION=...
ENTRY_RANGE=...
NOISE_AND_GEOMETRY=...
DATA_QUALITY=...
EXECUTION_UNCERTAINTY=...
ASYMMETRY=...
RANK_STATUS_REJECTION=...
...
RANKING=...
SELECTION_INSTRUMENT=...
SELECTION_ACTION=...
SELECTION_REASON=...
```

Use one block for every supplied candidate, including candidates rejected for entry. `NOTHING` is allowed only after all blocks are complete. `SELECTION_INSTRUMENT` must equal the intent instrument even when `SELECTION_ACTION=NOTHING`; it identifies the top/reference candidate, not an order.

For a condition-change wake, use the supplied compact `TRIGGER_REVIEW_V1` template instead. Evaluate each frozen fired trigger against its source-cycle path before creating a new trigger. `PRIOR_TRIGGER_REVIEW` starts with `HELD`, `FAILED`, or `EXPIRED`; a reclaim alone stays `HELD` while invalidation remains intact, and `FAILED` names the reached invalidation or specific structural contradiction. A fired trigger is not an automatic order, but it cannot be replaced by the same confirmation at a newer extreme without first recording new disconfirmation or loss of remaining target-before-stop value. Separate path validity from entry quality and debit the displacement used as directional evidence from remaining room. WAIT is better only before the primary target and only when a concrete improvement in entry location, invalidation cost, or target-before-stop probability outweighs lost room; it never requires perfect confirmation or a retest. Derive the current objective, invalidation, and executable zone from packet evidence; never defer because those interpretations were not explicitly supplied. If the fired path fails or expires, the compact review may select a newly derived current setup or an overtaking candidate without waiting for a full scan. `SELECTION_INSTRUMENT` and `SELECTION_ACTION` must equal the serialized intent.

For a flat scan or trigger review, serialize `decision_audit` first and the final executable fields after it. Complete the existing geometry/range-edge check before emitting binding prices. Apply any correction you discover to those numeric fields; a prose-only exception does not amend the range and latest-price revalidation cannot repair its geometry. This changes output order, not required fields or the native execution contract. For `ENTER_LONG` or `ENTER_SHORT`, the entry fields are:

```json
{
  "action": "ENTER_LONG",
  "quantity": 1,
  "order_type": "MARKET",
  "stop_loss": 0.0,
  "take_profit_1": 0.0,
  "entry_range_low": 0.0,
  "entry_range_high": 0.0,
  "forecast": {
    "event": "STOP_BEFORE_PRIMARY_TARGET",
    "probability": 0.0,
    "method": "original target/stop first-touch from entry now; unchanged bracket",
    "confidence": 0.0
  }
}
```

The entry range must contain the current decision price and remain strictly between the structural stop and primary target. It is the complete bounded zone where the setup retains positive expected value, not a one-tick quote or a limit order. Price plausible decision-to-delivery drift once; use supplied observed decision timing as context, not a guarantee or a required range width. Do not require the range to absorb ordinary movement across multiple future one-minute packets: deterministic latest-price revalidation skips an entry after price leaves the stated zone. In the current mode's entry-range audit field explain what actually fails at each edge after fill-relative bracket translation. If adjacent prices preserve the same path, genuine invalidation and positive value, include them in the initial range rather than centering an arbitrary narrow band on the quote. If no non-fragile execution zone fits, choose `NOTHING`; never widen an issued range to defeat revalidation. An expired order does not expire an intact thesis: a fresh review derives its own current zone and economics, including at a better price, without reviving or modifying the old order. `probability` is the ex-ante chance that the native stop occurs before the primary target; it is calibration metadata, not a deterministic gate. Optional scale fields remain `take_profit_2`, `stop_loss_2`, `quantity_tp1`, `take_profit_3`, `stop_loss_3`, and `quantity_tp2`. Never emit `stop_price`, `target_price`, `entry_price`, an orders array, or `protection_updates` on a new entry.

Every submitted stop and target must be an integer multiple of the supplied native tick size. Analytical VWAP, bands and averaged structural levels are references, not automatically executable prices. Select the supported native tick first, then use that exact stop/target in the intent and SELECTION_EV arithmetic; code must not silently round a bracket for you. Initial native brackets preserve each authored level's offset from the packet decision reference, not its absolute chart price. In the existing entry-range field show the numeric stop/target pairs at the low and high range edges: each level + range edge - decision reference. Check the actual inequality: the shifted long stop stays below the chosen failure boundary, the short stop above it, at both edges. Preserved dollar risk does not prove that. If it fails, correct the authored offset or executable zone; do not keep the contradictory bracket and merely call it robust. Market slippage can exceed the range. Do not promise an unchanged absolute stop. Post-entry native prices and leg IDs remain authoritative.

For every entry, state risk in points, ticks, supplied one-/five-minute ATR or equivalent horizon noise, and one-contract dollars before costs. Use deterministic_geometry_context and `point_value_usd`, never account `max_contracts`, followers or replication. A shallow pivot is not genuine invalidation merely because it creates an attractive ratio. Judge noise and meaningful capture from structure, actual volatility, path duration, costs and delivery delay, not a dollar floor or preferred ratio. Improve location or choose a deeper genuine invalidation when needed; never tighten a stop or invent a target to manufacture a payoff. The separate next-five-to-ten-bar description is immediate path context, not a time limit on the original target/stop forecast. If management closes before either barrier, that terminal event remains unobserved.

Construct the failure boundary and supported fill zone together, then choose the authored stop offset to preserve that boundary at the worst fill edge. A one-tick clearance from the decision quote can leave no room for spread or delivery movement. For a long, check `authored_stop + entry_range_high - decision_reference < failure_boundary`; for a short, check `authored_stop + entry_range_low - decision_reference > failure_boundary`. Equality fails the stated clearance. Evaluate the resulting risk and probability before selecting entry; neither wider ranges nor more risk are automatically better. Buys are checked against ask and sells against bid. Packet quotes are observed history, not guaranteed current fills. Never amend an issued range or bypass revalidation.

Use the existing geometry field for one coherent wager: its horizon, allowed pullback/probes, touch-stop boundary and destination. Keep the entry trigger, acceptance-failure level and hard stop distinct. A stop one tick beyond an acceptance level does not wait for acceptance; use supplied wick/probe extremes and adverse legs to justify clearance beyond all movement this wager allows. Cite those prices, not just ATR and the word non-fragile. A local continuation attempt cannot borrow the parent auction's target-first probability while stopping inside its valid pullback. A nearer stop requires a separately supported local wager; a farther target requires its own traversable path, not merely a printed distant level. Compare the coherent bracket now with a better entry location without making the retest mandatory. Never repair a losing payoff by shaving invalidation, inflating the destination, or assuming management will rescue it. Check the same touch-stop event at both translated range edges; equality with a boundary is not strictly beyond it.

Bind `disconfirming_evidence` to this same selected wager, horizon and allowed pullback, not a discarded tighter attempt. `change_condition` can name an earlier review level; distinguish that review from actual failure. The manager must be able to reconstruct the trade you chose without silently changing its horizon.

Keep SELECTION_EV arithmetic separate from comparative action: an above-hurdle target-first range is POSITIVE even when a specifically justified WAIT wins. A correction must not relabel it UNCERTAIN to preserve NOTHING or back-solve probability to preserve an entry. ENTER still requires positive stated current-zone value; NOTHING must identify the better alternative and missed-move cost.

For positioned decisions use the exact `MOVE_STOP` and `MOVE_TP` examples in the position-management skill. For `NOTHING`, `HOLD`, `EXIT`, `MOVE_STOP`, and `MOVE_TP`, omit every entry and entry-range field. Never invent a leg ID, route, account, price, quantity, probability, or receipt. Never target followers or reverse through an entry.

Preserve every user-configured constraint and Glitch authority. Glitch final checks must not replace the selected direction, instrument, quantity, geometry, or supported action with an unrelated strategy.

For flat and trigger reviews, keep one short factual clause per comparison field and every required instrument. Put the selected wager's full geometry and probability only in their dedicated fields; summarize conclusions elsewhere. Do not repeat calculations, doctrine or the complete instrument comparison in the five case summaries. Complete numeric evidence and valid JSON take precedence over the requested length target.
