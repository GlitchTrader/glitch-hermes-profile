"""Unit conversion and lossless output recovery, without model or native calls."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT, valid_batch, position_management_evidence


def management_batch(action="MOVE_STOP"):
    batch, scenario = valid_batch("2026-09-10T22:20:00.0000000Z")
    intent = batch["decisions"][0]
    intent.update(instrument="M2K", action=action, intent_id="11111111-1111-4111-8111-111111111111")
    intent["decision_audit"].update(
        decisive_evidence=position_management_evidence(action, "POSITIVE"), final_choice=action,
    )
    scenario["books"][0]["instrument_contexts"] = {"M2K": {
        "current_signed_quantity": 1,
        "instrument_economics": {"point_value_usd": 5, "tick_size": 0.1},
        "native_protection": {"orders": [{"leg_id": "LEG1"}]},
    }}
    updates = [{"leg_id": "LEG1", "stop_loss": 100.5}]
    if action == "MOVE_TP":
        updates[0]["take_profit"] = 120.0
    batch["protection_updates"] = updates
    return batch, scenario


@pytest.mark.parametrize("action", ["MOVE_STOP", "MOVE_TP"])
def test_missing_decision_brace_and_batch_protection_are_losslessly_recovered(action):
    batch, scenario = management_batch(action)
    intent = batch["decisions"][0]
    batch["wake_triggers"] = intent.pop("wake_triggers")
    before = copy.deepcopy(batch)
    raw = json.dumps(batch, separators=(",", ":"))
    raw = raw.replace('"final_choice":"' + action + '"}}]',
                      '"final_choice":"' + action + '"}]')
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    recovered = DIRECT.extract_json(raw, "glitch.intent.batch.v1")
    DIRECT.normalize_batch(recovered, scenario)
    DIRECT.validate_batch(recovered, scenario)
    expected = copy.deepcopy(before)
    expected["decisions"][0]["protection_updates"] = expected.pop("protection_updates")
    expected["decisions"][0]["wake_triggers"] = expected.pop("wake_triggers")
    assert recovered == expected  # Every action, price, leg and audit value survives.


def test_identical_protection_copy_collapses_but_conflict_is_not_resolved():
    batch, scenario = management_batch()
    batch["decisions"][0]["protection_updates"] = copy.deepcopy(batch["protection_updates"])
    DIRECT.normalize_batch(batch, scenario)
    DIRECT.validate_batch(batch, scenario)
    batch["protection_updates"] = [{"leg_id": "LEG1", "stop_loss": 100.6}]
    DIRECT.normalize_batch(batch, scenario)
    with pytest.raises(ValueError, match="batch_unknown_fields:protection_updates"):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("tail", [
    '"protection_updates":[{"leg_id":"LEG1","stop_loss":100,"stop_loss":101}]',
    '"protection_updates":[{"leg_id":"LEG1","stop_loss":100}],"unknown_field":1',
])
def test_terminal_repair_rejects_duplicate_json_keys_and_unknown_batch_fields(tail):
    raw = ('{"schema_version":"glitch.intent.batch.v1","decisions":[{"action":"MOVE_STOP",'
           '"decision_audit":{"final_choice":"MOVE_STOP"}],"wake_triggers":[],' + tail + '}')
    assert DIRECT.repair_terminal_json_delimiters(raw) is None


@pytest.mark.parametrize("action", ["NOTHING", "HOLD", "EXIT", "ENTER_LONG", "ENTER_SHORT"])
def test_protection_relocation_does_not_apply_to_other_actions(action):
    batch, scenario = management_batch(action)
    DIRECT.normalize_batch(batch, scenario)
    assert "protection_updates" in batch
    with pytest.raises(ValueError, match="batch_unknown_fields:protection_updates"):
        DIRECT.validate_batch(batch, scenario)


def test_multi_book_protection_ownership_is_not_guessed():
    batch, scenario = management_batch()
    batch["decisions"].append(copy.deepcopy(batch["decisions"][0]))
    DIRECT.normalize_batch(batch, scenario)
    assert "protection_updates" in batch
    assert all("protection_updates" not in d for d in batch["decisions"])
    with pytest.raises(ValueError, match="batch_unknown_fields:protection_updates"):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("update,error", [
    ({"leg_id": "FOREIGN", "stop_loss": 100.5}, "protection_update_leg_unknown"),
    ({"stop_loss": 100.5}, "protection_update_fields_invalid"),
    ({"leg_id": "LEG1"}, "protection_update_fields_invalid"),
    ({"leg_id": "LEG1", "stop_loss": True}, "native_price_invalid"),
])
def test_relocation_cannot_bypass_native_leg_or_price_validation(update, error):
    batch, scenario = management_batch()
    batch["protection_updates"] = [update]
    DIRECT.normalize_batch(batch, scenario)
    with pytest.raises(ValueError, match=error):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("field", ["final_choice", "change_condition", "disconfirming_evidence"])
def test_only_identical_audit_siblings_collapse(field):
    batch, scenario = valid_batch("2026-09-10T22:20:00.0000000Z")
    batch["decisions"][0]["intent_id"] = "11111111-1111-4111-8111-111111111111"
    original = copy.deepcopy(batch)
    intent = batch["decisions"][0]
    intent[field] = intent["decision_audit"][field]
    DIRECT.normalize_batch(batch, scenario)
    DIRECT.validate_batch(batch, scenario)
    assert batch == original
    intent[field] = "CONFLICT"
    DIRECT.normalize_batch(batch, scenario)
    with pytest.raises(ValueError, match="intent_unknown_fields"):
        DIRECT.validate_batch(batch, scenario)


def geometry_packet():
    instruments = []
    for root, point_value, tick, atr1, atr5 in [
        ("MNQ", 2, 0.25, 8, 20), ("MES", 5, 0.25, 2, 5), ("M2K", 5, 0.1, 1.5, 4),
    ]:
        instruments.append({
            "instrument": root, "current_price": 100.0,
            "instrument_economics": {"point_value_usd": point_value, "tick_size": tick},
            "timeframe_bars": [
                {"minutes": 1, "indicators": {"atr": atr1}},
                {"minutes": 5, "indicators": {"atr": atr5}},
            ],
        })
    packet = {"packet_id": "test-cycle", "policy": {}, "frames": [
        {"market_snapshot": {"instruments": instruments}},
    ]}
    perception = {"source_packet_id": "test-cycle", "instruments": [
        {"instrument": root, "auction_reference_ladder": {
            "above": [[106, 6, ["range_high"]]], "below": [[94, -6, ["range_low"]]],
        }} for root in ("MNQ", "MES", "M2K")
    ]}
    _, scenario = valid_batch("2026-09-10T22:20:00Z")
    scenario["books"][0].update(followers=[], exposure=[], position_building_context={})
    return packet, perception, scenario


def annotate(packet, perception, scenario):
    model = DIRECT.packet_for_model(packet, scenario)
    DIRECT.attach_reference_distance_math(model, perception)
    return model["frames"][-1]["market_snapshot"]["instruments"]


def test_six_points_are_not_equal_dollars_or_noise_across_instruments():
    packet, perception, scenario = geometry_packet()
    before = copy.deepcopy((packet, perception, scenario))
    instruments = annotate(packet, perception, scenario)
    rows = [i["deterministic_geometry_context"]["reference_distances"]["rows"] for i in instruments]
    assert rows == [
        [[106, 6, 24, 12, 0.75, 0.3], [94, -6, 24, 12, 0.75, 0.3]],
        [[106, 6, 24, 30, 3, 1.2], [94, -6, 24, 30, 3, 1.2]],
        [[106, 6, 60, 30, 4, 1.5], [94, -6, 60, 30, 4, 1.5]],
    ]
    assert (packet, perception, scenario) == before


def test_missing_atr_is_unknown_and_missing_native_economics_not_guessed():
    packet, perception, scenario = geometry_packet()
    instruments = packet["frames"][0]["market_snapshot"]["instruments"]
    instruments[0]["timeframe_bars"] = []
    instruments[1].pop("instrument_economics")
    result = annotate(packet, perception, scenario)
    assert result[0]["deterministic_geometry_context"]["reference_distances"]["rows"][0][-2:] == [None, None]
    assert "reference_distances" not in result[1]["deterministic_geometry_context"]


@pytest.mark.parametrize("price", [None, True, float("nan"), float("inf"), "100"])
def test_bad_current_price_does_not_create_reference_math(price):
    packet, perception, scenario = geometry_packet()
    packet["frames"][0]["market_snapshot"]["instruments"][0]["current_price"] = price
    result = annotate(packet, perception, scenario)
    assert "reference_distances" not in result[0]["deterministic_geometry_context"]


def test_only_same_packet_existing_levels_are_converted_and_bounded():
    packet, perception, scenario = geometry_packet()
    perception["source_packet_id"] = "older"
    assert all("reference_distances" not in i["deterministic_geometry_context"]
               for i in annotate(packet, perception, scenario))
    perception["source_packet_id"] = packet["packet_id"]
    ladder = perception["instruments"][0]["auction_reference_ladder"]
    ladder["above"] = [[106 + n, 999, ["existing_reference"]] for n in range(10)]
    ladder["below"] = [[None], [True], [float("nan")]]
    rows = annotate(packet, perception, scenario)[0]["deterministic_geometry_context"]["reference_distances"]["rows"]
    assert [row[:2] for row in rows] == [[106, 6], [107, 7], [108, 8]]


def test_prompt_keeps_units_in_current_scoped_instrument_and_correct_wire_closure():
    packet, perception, scenario = geometry_packet()
    packet["frames"].insert(0, copy.deepcopy(packet["frames"][0]))
    scenario["books"][0]["instrument_contexts"] = {"MES": {"current_signed_quantity": 1}}
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []}, market_perception=perception)
    envelope = json.JSONDecoder().raw_decode(prompt.split("CURRENT_CYCLE=", 1)[1])[0]
    frames = envelope["decision_packet"]["frames"]
    assert [i["instrument"] for i in frames[-1]["market_snapshot"]["instruments"]] == ["MES"]
    assert "reference_distances" not in json.dumps(frames[0])
    assert len(frames[-1]["market_snapshot"]["instruments"][0]["deterministic_geometry_context"]["reference_distances"]["rows"]) == 2
    assert "End each decision exactly with" not in prompt
    assert "Keep protection_updates inside its decision" in prompt


def test_flat_prompt_prioritizes_auction_without_fixed_stops_or_more_confirmation():
    packet, perception, scenario = geometry_packet()
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []}, market_perception=perception)
    assert "choose the meaningful move and its horizon BEFORE the bracket" in prompt
    assert "numeric shifted stop/target pairs" in prompt
    assert "Anticipatory entry is allowed without a closed candle, retest or perfect flow" in prompt
    assert "Do not impose a stop floor or a preferred ratio" in prompt
    assert "An earlier target touch completes the OLD forecast" in prompt
    assert "Previously touched does not mean zero current room" in prompt
    assert "never count the earlier touch as success or revive the old order/forecast" in prompt
    assert len(prompt.split("CURRENT_CYCLE=")[0]) < 12500
