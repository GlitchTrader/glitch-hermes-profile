import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_direct_glitch_cycle_trigger_continuity",
    ROOT / "scripts" / "run-direct-glitch-cycle.py",
)
DIRECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DIRECT)


def test_change_condition_prices_keep_instrument_identity() -> None:
    intent = {
        "instrument": "MES",
        "decision_audit": {
            "change_condition": (
                "Reassess if MES accepts above 7769.00 or below 7766.25; "
                "if M2K accepts above 3054.10 or below 3053.00; "
                "or if MNQ accepts above 29840.75 or below 29828.75."
            )
        },
        "wake_triggers": [],
    }

    DIRECT.normalize_wake_triggers(intent, {"MNQ", "MES", "M2K"})

    assert {
        (row["instrument"], row["direction"], row["price"])
        for row in intent["wake_triggers"]
    } == {
        ("MES", "ABOVE", 7769.0),
        ("MES", "BELOW", 7766.25),
        ("M2K", "ABOVE", 3054.1),
        ("M2K", "BELOW", 3053.0),
        ("MNQ", "ABOVE", 29840.75),
        ("MNQ", "BELOW", 29828.75),
    }


def test_persisted_triggers_are_frozen_instrument_aware_and_deduplicated(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    (exchange / "hermes" / "supervisor").mkdir(parents=True)
    trigger = {
        "type": "PRICE_CROSS",
        "instrument": "MNQ",
        "direction": "BELOW",
        "price": 29837.0,
    }
    batch = {"decisions": [{"wake_triggers": [trigger]}, {"wake_triggers": [trigger]}]}

    DIRECT.persist_wake_triggers(exchange, batch, "20260813T0110Z")

    state = json.loads((exchange / "hermes" / "supervisor" / "active-wake-triggers.json").read_text())
    assert state["schema_version"] == "glitch.hermes.wake_triggers.v2"
    assert state["triggers"] == [{
        **trigger,
        "source_cycle_id": "20260813T0110Z",
    }]


def test_clear_wake_triggers_consumes_the_set_once(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    (supervisor / "active-wake-triggers.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.wake_triggers.v2",
        "cycle_id": "source",
        "triggers": [{
            "type": "PRICE_CROSS",
            "instrument": "MNQ",
            "direction": "BELOW",
            "price": 100.0,
        }],
    }))

    DIRECT.clear_wake_triggers(exchange, "review")

    state = json.loads((supervisor / "active-wake-triggers.json").read_text())
    assert state["cycle_id"] == "review"
    assert state["triggers"] == []


def test_trigger_review_consumes_only_fired_trigger_and_preserves_unfired(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    unfired = {
        "type": "PRICE_CROSS",
        "instrument": "MNQ",
        "direction": "ABOVE",
        "price": 102.0,
        "source_cycle_id": "source",
    }
    (supervisor / "active-wake-triggers.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.wake_triggers.v2",
        "cycle_id": "source",
        "triggers": [
            {
                "type": "PRICE_CROSS",
                "instrument": "M2K",
                "direction": "BELOW",
                "price": 10.0,
                "source_cycle_id": "source",
            },
            unfired,
        ],
    }))

    DIRECT.consume_fired_wake_triggers(exchange, [{
        "instrument": "M2K",
        "direction": "BELOW",
        "price": 10.0,
        "source_cycle_id": "source",
    }], "review")

    state = json.loads((supervisor / "active-wake-triggers.json").read_text())
    assert state["cycle_id"] == "source"
    assert state["triggers"] == [unfired]


def test_only_the_instrument_that_crossed_its_own_level_fires(tmp_path: Path, monkeypatch) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    (supervisor / "active-wake-triggers.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.wake_triggers.v2",
        "cycle_id": "source",
        "triggers": [
            {"type": "PRICE_CROSS", "instrument": "MNQ", "direction": "BELOW", "price": 100.0, "source_cycle_id": "source"},
            {"type": "PRICE_CROSS", "instrument": "MES", "direction": "BELOW", "price": 10.0, "source_cycle_id": "source"},
        ],
    }))
    scenario = {"market": {"candidates": [{"instrument": "MNQ"}, {"instrument": "MES"}]}}
    packet = {"packet_id": "current"}
    prior = {"MNQ": 101.0, "MES": 11.0}
    current = {"MNQ": 100.5, "MES": 9.5}
    ranges = {"MNQ": (100.25, 101.0), "MES": (9.25, 11.0)}
    monkeypatch.setattr(DIRECT, "prior_packet_price", lambda _exchange, _packet, instrument: prior[instrument])
    monkeypatch.setattr(DIRECT, "candidate_price", lambda _packet, instrument: current[instrument])
    monkeypatch.setattr(DIRECT, "packet_one_minute_range", lambda _packet, instrument: ranges[instrument])

    fired = DIRECT.fired_wake_triggers(exchange, packet, scenario)

    assert len(fired) == 1
    assert fired[0]["instrument"] == "MES"
    assert fired[0]["price"] == 10.0


def test_crossing_during_model_latency_is_not_lost(tmp_path: Path, monkeypatch) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    (supervisor / "active-wake-triggers.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.wake_triggers.v2",
        "cycle_id": "source",
        "triggers": [{
            "type": "PRICE_CROSS",
            "instrument": "MNQ",
            "direction": "BELOW",
            "price": 100.0,
            "source_cycle_id": "source",
        }],
    }))
    scenario = {"market": {"candidates": [{"instrument": "MNQ"}]}}
    packet = {"packet_id": "current"}
    monkeypatch.setattr(DIRECT, "prior_packet_price", lambda *_args: 99.0)
    monkeypatch.setattr(DIRECT, "candidate_price", lambda *_args: 98.0)
    monkeypatch.setattr(DIRECT, "packet_one_minute_range", lambda *_args: (97.5, 99.0))
    monkeypatch.setattr(DIRECT, "trigger_path_extremes", lambda *_args: (101.0, 97.5, 101.0))

    fired = DIRECT.fired_wake_triggers(exchange, packet, scenario)

    assert len(fired) == 1
    assert fired[0]["source_price"] == 101.0
    assert fired[0]["previous_price"] == 99.0


def test_legacy_trigger_recovers_instrument_from_source_decision(tmp_path: Path, monkeypatch) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    outbox = exchange / "hermes" / "outbox"
    supervisor.mkdir(parents=True)
    outbox.mkdir(parents=True)
    (supervisor / "active-wake-triggers.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.wake_triggers.v1",
        "cycle_id": "source",
        "triggers": [{"type": "PRICE_CROSS", "direction": "BELOW", "price": 10.0}],
    }))
    (outbox / "source.json").write_text(json.dumps({
        "decisions": [{
            "instrument": "MNQ",
            "decision_audit": {
                "change_condition": "Reassess if MES accepts below 10.0 or MNQ accepts below 100.0."
            },
        }],
    }))
    scenario = {"market": {"candidates": [{"instrument": "MNQ"}, {"instrument": "MES"}]}}
    monkeypatch.setattr(DIRECT, "prior_packet_price", lambda *_args: 11.0)
    monkeypatch.setattr(DIRECT, "candidate_price", lambda *_args: 9.0)
    monkeypatch.setattr(DIRECT, "packet_one_minute_range", lambda *_args: (8.5, 11.0))
    monkeypatch.setattr(DIRECT, "trigger_path_extremes", lambda *_args: (11.0, 8.5, 11.0))

    fired = DIRECT.fired_wake_triggers(exchange, {"packet_id": "current"}, scenario)

    assert len(fired) == 1
    assert fired[0]["instrument"] == "MES"


def test_condition_change_prompt_preserves_fired_prior_path_and_is_compact() -> None:
    packet = {
        "packet_id": "current",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [], "coverage": []},
            "portfolio_snapshot": {"accounts": []},
        }],
    }
    scenario = {
        "cycle_id": "current",
        "market": {
            "snapshot_hash": "snapshot",
            "candidates": [
                {"instrument": "MNQ", "current_price": 98.0},
                {"instrument": "MES", "current_price": 10.0},
            ],
        },
        "books": [{
            "route_id": "glitch",
            "master_account": "Sim101",
            "followers": [],
            "exposure": [],
            "position_building_context": {"instrument": "MNQ"},
            "instrument_contexts": {
                "MNQ": {"current_signed_quantity": 0},
                "MES": {"current_signed_quantity": 0},
            },
        }],
    }
    context = {
        "reason": "condition_change",
        "fired_triggers": [{
            "source_cycle_id": "source",
            "instrument": "MNQ",
            "direction": "BELOW",
            "price": 100.0,
            "previous_price": 101.0,
            "current_price": 98.0,
            "prior_decision": {"instrument_ledger": "BEARISH_PATH=conditional below 100"},
        }],
    }

    journals = {
        "decisions": [{
            "created_utc": "2026-08-17T11:16:57Z",
            "instrument": "MNQ",
            "action": "EXIT",
            "reason": "The prior long response failed below entry.",
        }],
        "executions": [{
            "recorded_utc": "2026-08-17T11:16:58Z",
            "intent_id": "exit-intent",
            "status": "executed",
            "code": "master_exit_fill_observed",
        }],
        "outcomes": [{
            "instrument": "MNQ",
            "action": "ENTER_LONG",
            "master_realized_pnl_usd": -13.75,
        }],
    }
    prompt = DIRECT.build_prompt(
        packet,
        scenario,
        journals,
        invocation_reason="condition_change",
        invocation_context=context,
    )

    assert '"decision_mode":"trigger_review"' in prompt
    assert DIRECT.TRIGGER_REVIEW_MARKER in prompt
    assert '"decisive_evidence":"INSTRUMENT_COMPARISON_V1' not in prompt
    assert '"source_cycle_id":"source"' in prompt
    assert "Do not require the same class of confirmation again at a newer extreme" in prompt
    assert "HELD preserves the hypothesis but supplies no extra directional evidence" in prompt
    assert "Price latency once" in prompt
    assert "deterministic latest-price revalidation skips stale entries" in prompt
    assert "multiple one-minute packets during model and transport delay" not in prompt
    assert "stop-distance points times the packet point_value_usd" in prompt
    assert "never defer because these interpretations were not prewritten" in prompt
    assert "separate the broader path invalidation from the immediate entry invalidation" in prompt
    assert "nearest setup-specific structural level" in prompt
    assert "both falsifies the immediate entry and survives ordinary horizon noise" in prompt
    assert "Use the broader path invalidation as the stop only when no nearer noise-surviving structural level exists" in prompt
    assert "an unconsumed objective produce positive target-before-stop expected value after costs" in prompt
    assert "entry is permitted without completed-bar acceptance or a retest" in prompt
    # Preserve the genuine abstention and latency boundaries while correcting
    # the inherited-invalidation false veto seen in the 14:06 trigger review.
    assert "Enter only when now_ev is POSITIVE" in prompt
    assert "choose NOTHING only when now_ev is NEGATIVE or irreducibly UNCERTAIN" in prompt
    assert "confirmation at or beyond that target consumes the trade" in prompt
    assert "confirmation transition is not automatically the primary profit objective" in prompt
    assert "construct the strongest fresh compact setup" in prompt
    assert "condition-change wake is consumed once" in prompt
    assert '"recent_glitch_ledger":{' in prompt
    assert '"action":"EXIT"' in prompt
    assert '"code":"master_exit_fill_observed"' in prompt
    assert '"master_realized_pnl_usd":-13.75' in prompt
    assert "master_stop_exit_fill_observed" in prompt
    assert "completed factual result" in prompt
    assert "state what materially changed after that exit" in prompt
    assert "This is evidence reconciliation, not a cooldown" in prompt


def test_trigger_context_preserves_a_prior_trigger_review_ledger(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    outbox = exchange / "hermes" / "outbox"
    outbox.mkdir(parents=True)
    prior_review = "\n".join([
        DIRECT.TRIGGER_REVIEW_MARKER,
        "FIRED_TRIGGER=MNQ below 100",
        "PRIOR_PATH=continue toward 90",
        "PRIOR_TRIGGER_REVIEW=HELD: accepted below 100",
        "CURRENT_AUCTION=sellers accepted",
        "REMAINING_OBJECTIVE_INVALIDATION=objective 90; invalidation 103",
        "ENTRY_RANGE_NOISE_GEOMETRY=95-97",
        "ORDER_FLOW_RESPONSE=negative delta with price response",
        "ALTERNATIVE_CANDIDATES=none displaced MNQ",
        "ASYMMETRY=positive after uncertainty",
        "SELECTION_INSTRUMENT=MNQ",
        "SELECTION_ACTION=NOTHING",
        "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture",
        "SELECTION_REASON=wait for executable location",
    ])
    (outbox / "source.json").write_text(json.dumps({
        "decisions": [{
            "instrument": "MNQ",
            "action": "NOTHING",
            "confidence": 0.7,
            "reason": "wait",
            "decision_audit": {
                "decisive_evidence": prior_review,
                "change_condition": "MNQ below 95",
            },
        }],
    }))

    context = DIRECT.trigger_invocation_context(exchange, [{
        "source_cycle_id": "source",
        "instrument": "MNQ",
        "direction": "BELOW",
        "price": 95.0,
    }])

    assert context is not None
    assert context["fired_triggers"][0]["prior_decision"]["instrument_ledger"] == prior_review


def test_trigger_review_contract_requires_explicit_prior_status() -> None:
    def review(status: str) -> str:
        lines = [DIRECT.TRIGGER_REVIEW_MARKER]
        for field in DIRECT.TRIGGER_REVIEW_FIELDS:
            value = "current evidence"
            if field == "PRIOR_TRIGGER_REVIEW":
                value = status
            elif field == "SELECTION_INSTRUMENT":
                value = "MNQ"
            elif field == "SELECTION_ACTION":
                value = "NOTHING"
            lines.append(f"{field}={value}")
        lines.insert(-1, "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture")
        return "\n".join(lines)

    DIRECT.validate_trigger_review(
        review("HELD: price accepted through the frozen trigger"), {"MNQ", "MES"}, "MNQ", "NOTHING", 0
    )
    # Trailing punctuation on the status token is formatting, not cognition.
    DIRECT.validate_trigger_review(
        review("HELD. Price accepted through the frozen trigger"), {"MNQ", "MES"}, "MNQ", "NOTHING", 0
    )

    try:
        DIRECT.validate_trigger_review(review("MAYBE: unclear"), {"MNQ", "MES"}, "MNQ", "NOTHING", 0)
    except ValueError as error:
        assert str(error).startswith("trigger_review_status_invalid:0:")
    else:
        raise AssertionError("an unknown prior trigger status was accepted")


def test_trigger_review_accepts_instrument_labeled_prior_statuses() -> None:
    lines = [DIRECT.TRIGGER_REVIEW_MARKER]
    for field in DIRECT.TRIGGER_REVIEW_FIELDS:
        value = "current evidence"
        if field == "PRIOR_TRIGGER_REVIEW":
            value = "M2K=FAILED after invalidation 3050 broke; MES=HELD; MNQ=HELD. Evidence follows."
        elif field == "SELECTION_INSTRUMENT":
            value = "MNQ"
        elif field == "SELECTION_ACTION":
            value = "NOTHING"
        lines.append(f"{field}={value}")
    lines.insert(-1, "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture")

    DIRECT.validate_trigger_review(
        "\n".join(lines), {"M2K", "MES", "MNQ"}, "MNQ", "NOTHING", 0
    )


def test_trigger_review_accepts_natural_instrument_status_prose() -> None:
    lines = [DIRECT.TRIGGER_REVIEW_MARKER]
    for field in DIRECT.TRIGGER_REVIEW_FIELDS:
        value = "current evidence"
        if field == "PRIOR_TRIGGER_REVIEW":
            value = "MNQ HELD through the retest; MES: FAILED after invalidation broke; M2K EXPIRED"
        elif field == "SELECTION_INSTRUMENT":
            value = "MNQ"
        elif field == "SELECTION_ACTION":
            value = "NOTHING"
        lines.append(f"{field}={value}")
    lines.insert(-1, "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12 points;reward_points=12 pts;friction_points=0;breakeven_target_first=50%;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture")

    DIRECT.validate_trigger_review(
        "\n".join(lines), {"M2K", "MES", "MNQ"}, "MNQ", "NOTHING", 0
    )


def test_trigger_review_rejects_failed_status_without_invalidation_or_contradiction() -> None:
    lines = [DIRECT.TRIGGER_REVIEW_MARKER]
    for field in DIRECT.TRIGGER_REVIEW_FIELDS:
        value = "current evidence"
        if field == "PRIOR_TRIGGER_REVIEW":
            value = "FAILED because price reclaimed the trigger"
        elif field == "SELECTION_INSTRUMENT":
            value = "MNQ"
        elif field == "SELECTION_ACTION":
            value = "NOTHING"
        lines.append(f"{field}={value}")
    lines.insert(-1, "SELECTION_EV=direction=SHORT;entry=100;stop=105;target=90;risk_points=5;reward_points=10;friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=20-30%;now_ev=NEGATIVE;wait_price=95;wait_ev=NEGATIVE;decisive_reason=fixture")

    try:
        DIRECT.validate_trigger_review("\n".join(lines), {"MNQ"}, "MNQ", "NOTHING", 0)
    except ValueError as error:
        assert str(error) == "trigger_review_failed_without_invalidation_or_contradiction:0"
    else:
        raise AssertionError("a trigger reclaim incorrectly invalidated the frozen path")


def test_semantic_contract_repair_allows_market_judgment_to_change() -> None:
    prompt = DIRECT.contract_repair_prompt(
        "ORIGINAL",
        {"decisions": []},
        ValueError("selection_ev_wait_consumes_target:0:trigger_review"),
    )
    assert "DECISION_CONSISTENCY_CORRECTION" in prompt
    assert "You may change action, instrument, prices" in prompt
    assert "FORMAT_CORRECTION_ONLY" not in prompt


def test_format_contract_repair_is_compact_and_names_every_selection_ev_field() -> None:
    prompt = DIRECT.contract_repair_prompt(
        "ORIGINAL_CURRENT_CYCLE_PACKET",
        {"decisions": [{"action": "NOTHING"}]},
        ValueError("selection_ev_fields_missing:0:candidate_comparison:breakeven_target_first"),
    )
    assert "FORMAT_CORRECTION_ONLY" in prompt
    assert "ORIGINAL_CURRENT_CYCLE_PACKET" not in prompt
    assert "PREVIOUS_RESPONSE=" in prompt
    assert "breakeven_target_first" in prompt
    assert "estimated_target_first_range" in prompt


def test_held_trigger_nothing_requests_one_minute_review() -> None:
    batch = {
        "next_review_seconds": 300,
        "decisions": [{
            "action": "NOTHING",
            "decision_audit": {
                "decisive_evidence": "TRIGGER_REVIEW_V1\nPRIOR_TRIGGER_REVIEW=HELD: invalidation intact"
            },
        }],
    }
    assert DIRECT.trigger_review_has_held_nothing(batch) is True


def test_trigger_review_rejects_deferring_setup_derivation_to_packet() -> None:
    lines = [DIRECT.TRIGGER_REVIEW_MARKER]
    for field in DIRECT.TRIGGER_REVIEW_FIELDS:
        value = "current evidence"
        if field == "PRIOR_TRIGGER_REVIEW":
            value = "HELD: accepted below the frozen trigger"
        elif field == "REMAINING_OBJECTIVE_INVALIDATION":
            value = "No authoritative primary objective and invalidation pair was supplied"
        elif field == "SELECTION_INSTRUMENT":
            value = "MNQ"
        elif field == "SELECTION_ACTION":
            value = "NOTHING"
        lines.append(f"{field}={value}")
    lines.insert(-1, "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture")

    try:
        DIRECT.validate_trigger_review("\n".join(lines), {"MNQ", "MES"}, "MNQ", "NOTHING", 0)
    except ValueError as error:
        assert str(error) == "setup_derivation_deferred:0:trigger_review"
    else:
        raise AssertionError("trigger review deferred setup interpretation back to the packet")


def test_trigger_entry_requires_explicit_horizon_and_economic_geometry() -> None:
    def review(geometry: str) -> str:
        lines = [DIRECT.TRIGGER_REVIEW_MARKER]
        for field in DIRECT.TRIGGER_REVIEW_FIELDS:
            value = "current evidence"
            if field == "PRIOR_TRIGGER_REVIEW":
                value = "HELD: price accepted through the frozen trigger"
            elif field == "ENTRY_RANGE_NOISE_GEOMETRY":
                value = geometry
            elif field == "SELECTION_INSTRUMENT":
                value = "MNQ"
            elif field == "SELECTION_ACTION":
                value = "ENTER_SHORT"
            lines.append(f"{field}={value}")
        lines.insert(-1, "SELECTION_EV=direction=SHORT;entry=5000;stop=5012;target=4988;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=55-65%;now_ev=POSITIVE;wait_price=4992;wait_ev=NEGATIVE;decisive_reason=fixture")
        return "\n".join(lines)

    complete = "12 points, 48 ticks, 1m ATR 5, 5m ATR 11, $24 USD risk after latency"
    DIRECT.validate_trigger_review(review(complete), {"MNQ", "MES"}, "MNQ", "ENTER_SHORT", 0)

    try:
        DIRECT.validate_trigger_review(
            review("small stop above the pivot"), {"MNQ", "MES"}, "MNQ", "ENTER_SHORT", 0
        )
    except ValueError as error:
        assert str(error).startswith("entry_geometry_evidence_incomplete:0:trigger_review:")
    else:
        raise AssertionError("trigger entry without explicit horizon and economic geometry was accepted")


def test_invalid_output_is_not_retried(monkeypatch) -> None:
    prompts = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        prompts.append(prompt)
        return {"decisions": []}

    def validate(*_args, **_kwargs):
        raise ValueError("invalid_output")

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    monkeypatch.setattr(DIRECT, "normalize_batch", lambda value, _scenario: value)
    monkeypatch.setattr(DIRECT, "stamp_decision_created_utc", lambda value: value)
    monkeypatch.setattr(DIRECT, "validate_batch", validate)

    try:
        DIRECT.invoke_validated_batch(
            "glitch",
            "ORIGINAL_PROMPT",
            {"books": []},
            None,
            30,
            decision_mode="flat_scan",
        )
    except ValueError as error:
        assert str(error) == "invalid_output"
    else:
        raise AssertionError("invalid output was accepted")

    assert prompts == ["ORIGINAL_PROMPT"]
