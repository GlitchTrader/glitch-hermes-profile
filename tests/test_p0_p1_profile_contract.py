import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_direct_glitch_cycle_p0_p1",
    ROOT / "scripts" / "run-direct-glitch-cycle.py",
)
DIRECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DIRECT)


def comparison(action: str, instrument: str = "MNQ") -> str:
    lines = [DIRECT.CANDIDATE_COMPARISON_MARKER, f"INSTRUMENT {instrument}:"]
    for field in DIRECT.CANDIDATE_COMPARISON_FIELDS:
        value = "current evidence"
        if field == "NOISE_AND_GEOMETRY":
            value = "12 points, 48 ticks, 1m ATR 5, 5m ATR 11, $24 USD risk after latency"
        lines.append(f"{field}={value}")
    lines.extend([
        f"RANKING={instrument}",
        f"SELECTION_INSTRUMENT={instrument}",
        f"SELECTION_ACTION={action}",
        f"SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=55-65%;now_ev={'POSITIVE' if action == 'ENTER_LONG' else 'NEGATIVE'};wait_price=5008;wait_ev=NEGATIVE;decisive_reason=fixture",
        "SELECTION_REASON=positive expected value after execution uncertainty",
    ])
    return "\n".join(lines)


def management(action: str, instrument: str = "MNQ") -> str:
    lines = [DIRECT.POSITION_MANAGEMENT_MARKER, f"INSTRUMENT={instrument}"]
    lines.extend(f"{field}=current position evidence" for field in DIRECT.POSITION_MANAGEMENT_FIELDS)
    lines[-2] = f"SELECTION_ACTION={action}"
    return "\n".join(lines)


def audit(action: str, evidence: str) -> dict:
    return {
        "bull_case": "bull evidence",
        "bear_case": "bear evidence",
        "flat_case": "flat evidence",
        "aggressive_case": "aggressive alternative",
        "conservative_case": "conservative alternative",
        "decisive_evidence": evidence,
        "disconfirming_evidence": "specific invalidating evidence",
        "change_condition": "review next complete packet",
        "final_choice": action,
    }


def entry_batch() -> tuple[dict, dict]:
    scenario = {
        "cycle_id": "cycle-1",
        "market": {
            "snapshot_hash": "snapshot-1",
            "candidates": [{"instrument": "MNQ", "current_price": 105.0}],
        },
        "books": [{
            "route_id": "glitch",
            "master_account": "Sim101",
            "instrument_contexts": {"MNQ": {"current_signed_quantity": 0}},
        }],
    }
    batch = {
        "schema_version": "glitch.intent.batch.v1",
        "cycle_id": "cycle-1",
        "next_review_seconds": 300,
        "decisions": [{
            "schema_version": "glitch.intent.v3",
            "intent_id": "11111111-1111-4111-8111-111111111111",
            "created_utc": "2026-08-12T12:00:00Z",
            "instrument": "MNQ",
            "account": "Sim101",
            "operator_profile": "glitch",
            "action": "ENTER_LONG",
            "confidence": 0.65,
            "snapshot_hash": "snapshot-1",
            "model_version": DIRECT.CORE_MODEL,
            "prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
            "reason": "bounded positive expected value",
            "decision_audit": audit("ENTER_LONG", comparison("ENTER_LONG")),
            "wake_triggers": [],
            "quantity": 1,
            "order_type": "MARKET",
            "stop_loss": 100.0,
            "take_profit_1": 112.0,
            "entry_range_low": 104.0,
            "entry_range_high": 106.0,
            "forecast": {
                "event": DIRECT.FORECAST_EVENT_STOP_BEFORE_PRIMARY_TARGET,
                "probability": 0.38,
                "method": "auction and delta response",
                "confidence": 0.62,
            },
        }],
    }
    return batch, scenario


def test_prompt_version_tracks_the_exact_cognitive_bundle() -> None:
    assert DIRECT.DIRECT_PROMPT_VERSION.startswith(DIRECT.DIRECT_PROMPT_REVISION + "-")
    assert DIRECT.DIRECT_PROMPT_VERSION.endswith(DIRECT.cognitive_bundle_hash())


def test_entry_requires_calibration_and_a_slippage_tolerant_range() -> None:
    batch, scenario = entry_batch()
    DIRECT.validate_batch(batch, scenario)
    del batch["decisions"][0]["entry_range_high"]
    try:
        DIRECT.validate_batch(batch, scenario)
    except ValueError as error:
        assert str(error) == "entry_range_required:0"
    else:
        raise AssertionError("missing entry range was accepted")


def test_entry_rejects_geometry_evidence_that_hides_a_tiny_denominator() -> None:
    batch, scenario = entry_batch()
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = comparison("ENTER_LONG").replace(
        "12 points, 48 ticks, 1m ATR 5, 5m ATR 11, $24 USD risk after latency",
        "small structural stop with attractive ratio",
    )

    try:
        DIRECT.validate_batch(batch, scenario)
    except ValueError as error:
        assert str(error).startswith("entry_geometry_evidence_incomplete:0:candidate_comparison:")
    else:
        raise AssertionError("entry without explicit horizon and economic geometry was accepted")


def test_entry_accepts_prompt_approved_horizon_noise_wording() -> None:
    variants = (
        "12 points, 48 ticks, 1m ATR 5, 5m ATR 11, $24 USD risk after latency",
        "12 points, 48 ticks, one-minute ATR 5 and five-minute ATR 11, $24 risk after latency",
        "12 points, 48 ticks, one- and five-minute ATR are 5 and 11, $24 risk after latency",
        "12 points, 48 ticks, supplied horizon noise is 5 and 11, $24 risk after latency",
    )
    for geometry in variants:
        DIRECT.validate_entry_geometry_evidence(geometry, 0, "candidate_comparison")


def test_entry_rejects_one_sided_atr_evidence() -> None:
    geometry = "12 points, 48 ticks, one-minute ATR 5, $24 risk after latency"
    try:
        DIRECT.validate_entry_geometry_evidence(geometry, 0, "candidate_comparison")
    except ValueError as error:
        assert str(error) == (
            "entry_geometry_evidence_incomplete:0:candidate_comparison:horizon_noise"
        )
    else:
        raise AssertionError("entry with only one-minute ATR evidence was accepted")


def test_latest_price_revalidation_accepts_inside_and_supersedes_outside(monkeypatch, tmp_path: Path) -> None:
    batch, _ = entry_batch()
    source = {"packet_id": "source"}
    latest = {
        "packet_id": "latest",
        "frames": [{"created_utc": "2026-08-12T12:00:00Z", "portfolio_snapshot": {"accounts": [{
            "account": "Sim101",
            "native_state_available": True,
            "positions": [],
            "working_orders": 0,
        }]}}],
    }
    prices = {id(source): 105.0, id(latest): 105.5}
    monkeypatch.setattr(DIRECT, "candidate_price", lambda packet, _instrument: prices[id(packet)])
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "market_snapshot_is_fresh", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "latest_market", lambda _packet: ({"snapshot_hash": "latest-hash"}, {}, []))

    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is False
    assert batch["decisions"][0]["entry_revalidation"]["status"] == "accepted_current_price_in_range"

    prices[id(latest)] = 107.0
    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    assert batch["decisions"][0]["entry_revalidation"]["reason"] == "latest_price_outside_entry_range"
    assert batch["decisions"][0]["entry_revalidation"]["reassessment_eligible"] is True
    assert batch["decisions"][0]["entry_revalidation"]["favorable_supersession"] is False
    assert batch["decisions"][0]["entry_revalidation"]["supersession_direction"] == "targetward"

    prices[id(latest)] = 103.0
    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    assert batch["decisions"][0]["entry_revalidation"]["reassessment_eligible"] is True
    assert batch["decisions"][0]["entry_revalidation"]["favorable_supersession"] is True
    assert batch["decisions"][0]["entry_revalidation"]["supersession_direction"] == "better_price"


def test_entry_revalidation_requires_latest_master_flat_and_order_free(monkeypatch, tmp_path: Path) -> None:
    batch, _ = entry_batch()
    source = {"packet_id": "source"}
    latest_account = {
        "account": "Sim101",
        "native_state_available": True,
        "positions": [],
        "working_orders": 0,
    }
    latest = {
        "packet_id": "latest",
        "frames": [{
            "created_utc": "2026-08-12T12:00:00Z",
            "portfolio_snapshot": {"accounts": [latest_account]},
        }],
    }
    monkeypatch.setattr(DIRECT, "candidate_price", lambda packet, _instrument: 105.0)
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "market_snapshot_is_fresh", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "latest_market", lambda _packet: ({"snapshot_hash": "latest-hash"}, {}, []))

    latest_account["positions"] = [{
        "instrument": "MES 09-26", "quantity": 1, "market_position": "Short",
    }]
    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    evidence = batch["decisions"][0]["entry_revalidation"]
    assert evidence["reason"] == "latest_master_not_flat"
    assert evidence["latest_master_position_contracts"] == 1
    assert evidence["reassessment_eligible"] is False
    assert evidence["supersession_direction"] is None

    latest_account["positions"] = []
    latest_account["working_orders"] = 1
    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    evidence = batch["decisions"][0]["entry_revalidation"]
    assert evidence["reason"] == "latest_master_has_working_orders"
    assert evidence["reassessment_eligible"] is False

    latest_account["working_orders"] = 0
    latest_account["native_state_available"] = False
    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    evidence = batch["decisions"][0]["entry_revalidation"]
    assert evidence["reason"] == "latest_master_state_unavailable"
    assert evidence["reassessment_eligible"] is False


def test_entry_revalidation_rejects_a_distinct_native_entry_newer_than_the_flat_snapshot(
    monkeypatch, tmp_path: Path,
) -> None:
    batch, _ = entry_batch()
    source = {"packet_id": "source"}
    latest = {
        "packet_id": "latest",
        "frames": [{
            "created_utc": "2026-08-12T12:00:00Z",
            "portfolio_snapshot": {"accounts": [{
                "account": "Sim101",
                "native_state_available": True,
                "positions": [],
                "working_orders": 0,
            }]},
        }],
    }
    executions = tmp_path / "intents" / "executions.jsonl"
    executions.parent.mkdir(parents=True)
    executions.write_text(json.dumps({
        "intent_id": "22222222-2222-4222-8222-222222222222",
        "recorded_utc": "2026-08-12T12:00:05Z",
        "code": "master_entry_fill_observed",
        "message": "account=Sim101|contract=MES 09-26|fill=5000|signed_quantity=1",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(DIRECT, "candidate_price", lambda packet, _instrument: 105.0)
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "market_snapshot_is_fresh", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "latest_market", lambda _packet: ({"snapshot_hash": "latest-hash"}, {}, []))

    assert DIRECT.apply_entry_revalidation(batch, source, latest, tmp_path) is True
    evidence = batch["decisions"][0]["entry_revalidation"]
    assert evidence["reason"] == "latest_master_state_precedes_distinct_entry"
    assert evidence["latest_master_position_contracts"] == 0
    assert evidence["latest_master_working_orders"] == 0
    assert evidence["newer_distinct_master_entry"] == {
        "intent_id": "22222222-2222-4222-8222-222222222222",
        "recorded_utc": "2026-08-12T12:00:05Z",
        "code": "master_entry_fill_observed",
        "instrument": "MES",
    }
    assert evidence["reassessment_eligible"] is False


def test_partial_multibook_supersession_does_not_request_a_duplicate_cycle() -> None:
    batch, _ = entry_batch()
    accepted = dict(batch["decisions"][0])
    accepted["intent_id"] = "33333333-3333-4333-8333-333333333333"
    accepted["entry_revalidation"] = {"status": "accepted_current_price_in_range"}
    batch["decisions"][0]["entry_revalidation"] = {"status": "superseded"}
    batch["decisions"].append(accepted)
    assert DIRECT.all_entry_actions_superseded(batch) is False
    accepted["entry_revalidation"] = {"status": "superseded"}
    assert DIRECT.all_entry_actions_superseded(batch) is True


def test_position_management_has_an_exact_native_leg_contract() -> None:
    scenario = {
        "cycle_id": "cycle-2",
        "market": {"snapshot_hash": "snapshot-2", "candidates": [{"instrument": "MNQ", "current_price": 108}]},
        "books": [{
            "route_id": "glitch",
            "master_account": "Sim101",
            "instrument_contexts": {"MNQ": {
                "current_signed_quantity": 1,
                "native_protection": {"orders": [{"leg_id": "LEG0"}]},
            }},
        }],
    }
    batch = {
        "schema_version": "glitch.intent.batch.v1",
        "cycle_id": "cycle-2",
        "next_review_seconds": 60,
        "decisions": [{
            "schema_version": "glitch.intent.v3",
            "intent_id": "22222222-2222-4222-8222-222222222222",
            "created_utc": "2026-08-12T12:01:00Z",
            "instrument": "MNQ",
            "account": "Sim101",
            "operator_profile": "glitch",
            "action": "MOVE_STOP",
            "confidence": 0.7,
            "snapshot_hash": "snapshot-2",
            "model_version": DIRECT.CORE_MODEL,
            "prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
            "reason": "protect earned optionality at a noise-supported level",
            "decision_audit": audit("MOVE_STOP", management("MOVE_STOP")),
            "wake_triggers": [],
            "protection_updates": [{"leg_id": "LEG0", "stop_loss": 105.25}],
        }],
    }
    DIRECT.validate_batch(batch, scenario)


def test_positioned_prompt_is_compact_and_excludes_follower_and_flat_market_scan() -> None:
    scenario = {
        "cycle_id": "cycle-3",
        "market": {
            "snapshot_hash": "snapshot-3",
            "candidates": [{"instrument": "MNQ", "current_price": 105}, {"instrument": "M2K", "current_price": 2200}],
        },
        "books": [{
            "route_id": "glitch",
            "master_account": "Sim101",
            "followers": [{"account": "Sim102", "enabled": True}],
            "exposure": [{"account": "Sim101", "role": "master"}, {"account": "Sim102", "role": "follower"}],
            "position_building_context": {"instrument": "MNQ"},
            "instrument_contexts": {
                "MNQ": {"current_signed_quantity": 1},
                "M2K": {"current_signed_quantity": 0},
            },
        }],
    }
    packet = {
        "packet_id": "cycle-3",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}, {"instrument": "M2K"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim102"}]},
        }],
    }
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": [], "memory": "must not enter fast path"})
    assert '"decision_mode":"position_management"' in prompt
    assert DIRECT.POSITION_MANAGEMENT_MARKER in prompt
    assert DIRECT.CANDIDATE_COMPARISON_MARKER not in prompt
    assert "Sim102" not in prompt
    assert '"instrument":"M2K"' not in prompt
    assert "must not enter fast path" not in prompt
