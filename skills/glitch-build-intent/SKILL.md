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

For a condition-change wake, use the supplied compact `TRIGGER_REVIEW_V1` template instead. Evaluate each frozen fired trigger against its source-cycle path before creating a new trigger. `PRIOR_TRIGGER_REVIEW` starts with `HELD`, `FAILED`, or `EXPIRED`. A fired trigger is not an automatic order, but it cannot be replaced by the same confirmation at a newer extreme without first recording new disconfirmation or loss of remaining target-before-stop value. Derive the current objective, invalidation, and executable zone from packet evidence; never defer because those interpretations were not explicitly supplied. If the fired path fails or expires, the compact review may select a newly derived current setup or an overtaking candidate without waiting for a full scan. `SELECTION_INSTRUMENT` and `SELECTION_ACTION` must equal the serialized intent.

For `ENTER_LONG` or `ENTER_SHORT`, use the exact entry contract:

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
    "method": "next five-to-ten one-minute bars from supplied evidence",
    "confidence": 0.0
  }
}
```

The entry range must contain the current decision price and remain strictly between the structural stop and primary target. It is the complete bounded zone where the setup retains positive expected value, not a one-tick quote or a limit order. Make it wide enough to survive ordinary movement during model and transport delay across multiple one-minute packets. Place each edge where location, geometry, or the path actually stops being valid. If no useful execution zone can fit between genuine invalidation and the primary objective, choose `NOTHING`. `probability` is the ex-ante chance that the native stop occurs before the primary target; it is calibration metadata, not a deterministic gate. Optional scale fields remain `take_profit_2`, `stop_loss_2`, `quantity_tp1`, `take_profit_3`, `stop_loss_3`, and `quantity_tp2`. Never emit `stop_price`, `target_price`, `entry_price`, an orders array, or `protection_updates` on a new entry.

For every entry, state the proposed risk in points, ticks, one- and five-minute ATR or equivalent supplied horizon noise, and one-contract dollars before costs. Compute one-contract risk as stop-distance points multiplied by the packet's `point_value_usd`; compute tick value as `tick_size` multiplied by `point_value_usd`. Do not use account `max_contracts`, follower ratios, replication, or the number of ordered books in this calculation. A shallow nearby pivot is not genuine invalidation merely because it creates an attractive ratio. The stop must survive ordinary movement over the intended five-to-ten-bar forecast horizon. When it cannot, improve location, use a deeper evidence-supported invalidation, or choose `NOTHING`; never manufacture a fixed distance or widen risk without structure.

For positioned decisions use the exact `MOVE_STOP` and `MOVE_TP` examples in the position-management skill. For `NOTHING`, `HOLD`, `EXIT`, `MOVE_STOP`, and `MOVE_TP`, omit every entry and entry-range field. Never invent a leg ID, route, account, price, quantity, probability, or receipt. Never target followers or reverse through an entry.

Preserve every user-configured constraint and Glitch authority. Glitch final checks must not replace the selected direction, instrument, quantity, geometry, or supported action with an unrelated strategy.
