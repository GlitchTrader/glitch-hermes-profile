import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "reconcile_hermes_outcomes_for_attribution_tests",
    ROOT / "scripts" / "reconcile-hermes-outcomes.py",
)
RECONCILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RECONCILER)

LEARNING_SPEC = importlib.util.spec_from_file_location(
    "run_hermes_learning_cycle_for_attribution_tests",
    ROOT / "scripts" / "run-hermes-learning-cycle.py",
)
LEARNING = importlib.util.module_from_spec(LEARNING_SPEC)
assert LEARNING_SPEC.loader is not None
LEARNING_SPEC.loader.exec_module(LEARNING)


def dotnet_ticks(value: datetime) -> int:
    return RECONCILER.DOTNET_EPOCH_TICKS + int(value.timestamp() * 10_000_000)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def trade_ledger_line(
    account: str,
    source: str,
    quantity: int,
    entry_signal: str,
    entry_utc: datetime,
    exit_utc: datetime,
) -> str:
    columns = [
        f"trade-{account}",
        str(dotnet_ticks(entry_utc)),
        str(dotnet_ticks(exit_utc)),
        account,
        "MNQ",
        "Long",
        str(quantity),
        "100",
        "102",
        str(2 * quantity),
        entry_signal,
        "Manual / Other",
        "Asia",
        "Asia",
        source,
        "Strategy" if source == "Strategy" else "SYNC",
        "SYNC",
        entry_signal,
        f"exit-{account}",
        "0",
    ]
    return "\t".join(columns) + "\n"


def native_log_line(
    recorded_local: datetime,
    account: str,
    role: str,
    correlation: str,
    oco: str,
    quantity: int,
    state: str = "Accepted",
) -> str:
    timestamp = recorded_local.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]
    return (
        f"{timestamp}|1|32|Order='order-{role}/{account}' "
        f"Name='GLT-COPY-{role}-routehash-{correlation}-01' New state='{state}' "
        f"Instrument='MNQ 09-26' Action='Sell' Limit price=0 Stop price=99 "
        f"Quantity={quantity} Type='Stop Market' Time in force=GTC Oco='{oco}' "
        "Filled=0 Fill price=0 Error='No error' Native error=''\n"
    )


def build_reconciliation_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    glitch_data = tmp_path / "GlitchData"
    decision_root = tmp_path / "exchange" / "hermes" / "outbox"
    output_path = glitch_data / "intents" / "hermes-trade-outcomes.jsonl"
    entry_utc = datetime(2026, 8, 3, 12, 50, 49, 100000, tzinfo=timezone.utc)
    exit_utc = entry_utc + timedelta(minutes=1)
    intent_id = "intent-1"
    correlation = "corr1234"

    write_jsonl(glitch_data / "intents" / "executions.jsonl", [
        {
            "recorded_utc": entry_utc.isoformat().replace("+00:00", "Z"),
            "intent_id": intent_id,
            "code": "group_entries_submitted",
            "message": (
                "correlation=corr1234|"
                "contract=MNQ 09-26|point_value_usd=2|tick_size=0.25"
            ),
        },
        {
            "recorded_utc": entry_utc.isoformat().replace("+00:00", "Z"),
            "intent_id": intent_id,
            "code": "group_structural_brackets_submitted",
            "message": (
                "account=Master|fill=100|sl1=99|leg1_qty=1|tp1=102|"
                "point_value_usd=2|tick_size=0.25"
            ),
        },
        {
            "recorded_utc": exit_utc.isoformat().replace("+00:00", "Z"),
            "intent_id": intent_id,
            "code": "master_exit_fill_observed",
            "message": (
                "account=Master|contract=MNQ 09-26|fill=102|signed_quantity=-1|"
                "execution_id=native-exit-master"
            ),
        },
    ])
    decision_root.mkdir(parents=True)
    (decision_root / "cycle-1.json").write_text(json.dumps({
        "cycle_id": "cycle-1",
        "account_groups_tsv": (
            "G\tgroup-a\tMaster\t1\n"
            "M\tgroup-a\tFollowerA\t2\t2\t1\t1\n"
            "M\tgroup-a\tFollowerB\t3\t3\t1\t1\n"
        ),
        "decisions": [{
            "intent_id": intent_id,
            "action": "ENTER_LONG",
            "account": "Master",
            "operator_profile": "group-a",
            "instrument": "MNQ",
            "confidence": 0.7,
            "stop_loss": 99,
            "take_profit_1": 102,
            "reason": "fixture",
            "decision_audit": {},
        }],
    }), encoding="utf-8")
    (glitch_data / "TradeLedger.tsv").write_text(
        trade_ledger_line(
            "Master", "Strategy", 1, f"GLT-AI-E-{correlation}-0", entry_utc, exit_utc
        )
        + trade_ledger_line(
            "FollowerA", "Replication", 2,
            f"GLT-COPY-E-accounta-{correlation}-R1-O1", entry_utc, exit_utc,
        )
        + trade_ledger_line(
            "FollowerB", "Replication", 3,
            f"GLT-COPY-E-accountb-{correlation}-R1-O1", entry_utc, exit_utc,
        ),
        encoding="utf-8",
    )
    snapshot_path = glitch_data / "snapshots" / "historical" / "portfolio" / "terminal.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_text(json.dumps({
        "created_utc": (exit_utc + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "accounts": [
            {"account": account, "positions": [], "working_orders": 0}
            for account in ("Master", "FollowerA", "FollowerB")
        ],
    }), encoding="utf-8")

    entry_local = entry_utc.astimezone().replace(tzinfo=None)
    log_directory = tmp_path / "log"
    log_directory.mkdir()
    (log_directory / f"log.{entry_local:%Y%m%d}.00000.txt").write_text(
        native_log_line(
            entry_local + timedelta(milliseconds=100),
            "FollowerA", "S", correlation, "pair-a", 2,
        )
        + native_log_line(
            entry_local + timedelta(milliseconds=120),
            "FollowerA", "T", correlation, "pair-a", 2,
        ),
        encoding="utf-8",
    )
    return glitch_data, decision_root, output_path


def test_reconcile_uses_immutable_outbox_group_manifest(tmp_path: Path) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)
    (glitch_data / "AccountGroups.tsv").write_text(
        "G\tcurrent\tMaster\t1\nM\tcurrent\tWrongFollower\t1\t1\t1\t1\n",
        encoding="utf-8",
    )

    outcomes = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )

    assert {row["account"] for row in outcomes[0]["account_outcomes"]} == {
        "Master", "FollowerA", "FollowerB"
    }


def test_native_log_requires_matching_account_correlation_and_oco_pair(tmp_path: Path) -> None:
    entry_utc = datetime(2026, 8, 3, 12, 50, 49, tzinfo=timezone.utc)
    entry_local = entry_utc.astimezone().replace(tzinfo=None)
    log_directory = tmp_path / "log"
    log_directory.mkdir()
    (log_directory / f"log.{entry_local:%Y%m%d}.00000.txt").write_text(
        native_log_line(entry_local, "FollowerA", "S", "corr1234", "pair-a", 2)
        + native_log_line(entry_local, "FollowerA", "T", "corr1234", "pair-a", 2)
        + native_log_line(entry_local, "FollowerA", "S", "solo1234", "pair-b", 2),
        encoding="utf-8",
    )
    trade = {
        "account": "FollowerA",
        "instrument": "MNQ",
        "contracts": 2,
        "entry_utc": entry_utc,
        "entry_signal": "GLT-COPY-E-accounta-corr1234-R1-O1",
    }

    assert RECONCILER.native_follower_protection_submitted(
        log_directory, trade, "FollowerA", {}
    ) is True
    assert RECONCILER.native_follower_protection_submitted(
        log_directory, trade, "FollowerB", {}
    ) is False
    assert RECONCILER.native_follower_protection_submitted(
        log_directory, {**trade, "entry_signal": "GLT-COPY-E-accounta-other-R1-O1"},
        "FollowerA", {},
    ) is False
    assert RECONCILER.native_follower_protection_submitted(
        log_directory, {**trade, "entry_signal": "GLT-COPY-E-accounta-solo1234-R1-O1"},
        "FollowerA", {},
    ) is False


def test_reconcile_uses_native_fallback_and_keeps_missing_follower_unknown(
    tmp_path: Path,
) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)

    outcomes = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["origin"] == "ai"
    assert outcome["master_learning_eligible"] is True
    assert outcome["learning_eligible"] is True
    assert outcome["native_outcome_reconciliation"]["status"] == "reconciled"
    assert outcome["attribution_status"] == "complete"
    account_outcomes = {row["account"]: row for row in outcome["account_outcomes"]}
    assert set(account_outcomes) == {"Master", "FollowerA", "FollowerB"}
    assert account_outcomes["FollowerA"]["protection_evidence"] == "ninjatrader_daily_log"
    assert account_outcomes["FollowerA"]["protection_status"] == "submitted"
    assert account_outcomes["FollowerB"]["protection_evidence"] == "unavailable"
    assert account_outcomes["FollowerB"]["protection_status"] == "unknown"
    assert account_outcomes["Master"]["entry_utc"].endswith("Z")
    assert outcome["normalized_outcome"]["first_touch"] == "NEITHER"
    assert outcome["forecast_outcome"]["status"] == "not_provided"
    assert outcome["execution_diagnostics"]["intent_fidelity"]["coverage"]["native_state"] == "fully_protected"
    assert outcome["replication_diagnostics"] == [{
        "account": "FollowerB",
        "status": "follower_protection_evidence_unknown",
        "learning_role": "replication_only",
    }]


def test_reconcile_keeps_native_master_truth_when_derived_ledger_conflicts(
    tmp_path: Path,
) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)
    executions = [
        json.loads(line)
        for line in (glitch_data / "intents" / "executions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    terminal = next(row for row in executions if row["code"] == "master_exit_fill_observed")
    terminal["code"] = "master_stop_exit_fill_observed"
    terminal["recorded_utc"] = "2026-08-03T12:51:00Z"
    terminal["message"] = (
        "account=Master|contract=MNQ 09-26|fill=99|signed_quantity=-1|"
        "execution_id=native-stop-master|entry=100|point_value_usd=2|realized_pnl_usd=-2"
    )
    write_jsonl(glitch_data / "intents" / "executions.jsonl", executions)

    outcome = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )[0]

    assert outcome["master_learning_eligible"] is True
    assert outcome["learning_eligible"] is True
    assert outcome["master_attribution_status"] == "complete"
    reconciliation = outcome["native_outcome_reconciliation"]
    assert reconciliation["status"] == "reconciled"
    assert reconciliation["discrepancies"] == []
    assert reconciliation["derived_trade_ledger"]["status"] == "mismatch"
    assert set(reconciliation["derived_trade_ledger"]["discrepancies"]) >= {
        "exit_price_mismatch",
        "exit_time_mismatch",
        "close_kind_mismatch",
    }
    assert outcome["master_realized_pnl_usd"] == -2
    assert outcome["account_outcomes"][0]["trade_evidence_source"] == (
        "intent_bound_native_execution_receipts"
    )


def test_reconcile_restores_native_master_when_derived_ledger_is_missing(
    tmp_path: Path,
) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)
    ledger = (glitch_data / "TradeLedger.tsv").read_text(encoding="utf-8").splitlines()
    (glitch_data / "TradeLedger.tsv").write_text(
        "\n".join(line for line in ledger if "\tMaster\t" not in line) + "\n",
        encoding="utf-8",
    )

    outcome = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )[0]

    assert outcome["master_learning_eligible"] is True
    assert outcome["native_outcome_reconciliation"]["derived_trade_ledger"] == {
        "status": "missing",
        "effect": "diagnostic_only_no_master_learning_effect",
    }
    master = next(
        row for row in outcome["account_outcomes"] if row["account"] == "Master"
    )
    assert master["trade_id"] == "native-receipt:intent-1"


def test_management_counterfactual_is_sampled_and_observational() -> None:
    entry = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    decision = entry + timedelta(minutes=5, seconds=30)
    exit_utc = entry + timedelta(minutes=10)
    snapshots = [(entry + timedelta(minutes=5), {
        "accounts": [{
            "account": "Master",
            "positions": [{"instrument_root": "MNQ", "unrealized_pnl": 10}],
        }],
    })]
    intents = {"hold-1": {
        "intent_id": "hold-1",
        "_cycle_id": "cycle-hold",
        "created_utc": decision.isoformat().replace("+00:00", "Z"),
        "account": "Master",
        "instrument": "MNQ",
        "action": "HOLD",
        "reason": "fixture hold",
    }}

    counterfactuals = RECONCILER.management_intent_counterfactuals(
        intents, snapshots, "Master", "MNQ", entry, exit_utc, -5
    )
    rows = counterfactuals["representative_decisions"]

    assert counterfactuals["summary"]["total_decisions"] == 1
    assert rows[0]["sampled_exit_then_pnl_usd_before_costs"] == 10
    assert rows[0]["sampled_exit_then_advantage_usd"] == 15
    assert counterfactuals["summary"]["effect"] == (
        "informational_only_not_execution_or_strategy_gate"
    )


def test_managed_exit_receipt_is_attributed_to_the_open_entry_intent(
    tmp_path: Path,
) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)
    executions = [
        json.loads(line)
        for line in (glitch_data / "intents" / "executions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    entry_utc = datetime(2026, 8, 3, 12, 50, 49, 100000, tzinfo=timezone.utc)
    executions.insert(2, {
        "recorded_utc": entry_utc.isoformat().replace("+00:00", "Z"),
        "intent_id": "intent-1",
        "code": "master_entry_fill_observed",
        "message": (
            "account=Master|contract=MNQ 09-26|fill=100|signed_quantity=1|"
            "execution_id=native-entry-master|native_order=GL1-GABC-HME"
        ),
    })
    terminal = next(row for row in executions if row["code"] == "master_exit_fill_observed")
    terminal["intent_id"] = "managed-exit-intent"
    terminal["message"] = (
        "account=Master|contract=MNQ 09-26|fill=102|signed_quantity=-1|"
        "execution_id=native-managed-exit|native_order=GL1-GDEF-HMX"
    )
    write_jsonl(glitch_data / "intents" / "executions.jsonl", executions)

    outcome = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )[0]

    assert outcome["intent_id"] == "intent-1"
    assert outcome["native_outcome_reconciliation"]["status"] == "reconciled"
    terminal_receipt = outcome["native_outcome_reconciliation"]["native_terminal_events"][0]
    assert terminal_receipt["source_intent_id"] == "managed-exit-intent"
    assert outcome["master_realized_pnl_usd"] == 4


def test_native_master_quantity_contradiction_remains_quarantined(
    tmp_path: Path,
) -> None:
    glitch_data, decision_root, output_path = build_reconciliation_fixture(tmp_path)
    executions = [
        json.loads(line)
        for line in (glitch_data / "intents" / "executions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    executions.insert(2, {
        "recorded_utc": "2026-08-03T12:50:49.100000Z",
        "intent_id": "intent-1",
        "code": "master_entry_fill_observed",
        "message": (
            "account=Master|contract=MNQ 09-26|fill=100|signed_quantity=1|"
            "execution_id=native-entry-master"
        ),
    })
    terminal = next(row for row in executions if row["code"] == "master_exit_fill_observed")
    terminal["message"] = (
        "account=Master|contract=MNQ 09-26|fill=102|signed_quantity=-2|"
        "execution_id=native-exit-master|entry=100|point_value_usd=2|realized_pnl_usd=8"
    )
    write_jsonl(glitch_data / "intents" / "executions.jsonl", executions)

    outcome = RECONCILER.reconcile(
        glitch_data, None, output_path, decision_root=decision_root
    )[0]

    assert outcome["master_learning_eligible"] is False
    assert outcome["native_outcome_reconciliation"]["status"] == "quarantined"
    assert "native_exit_quantity_unattributed" in (
        outcome["native_outcome_reconciliation"]["discrepancies"]
    )


def test_one_native_exit_is_fifo_allocated_across_open_entry_intents() -> None:
    executions = [
        {
            "recorded_utc": "2026-08-03T12:00:00Z",
            "intent_id": "entry-a",
            "code": "master_entry_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=100|signed_quantity=1|execution_id=a",
        },
        {
            "recorded_utc": "2026-08-03T12:01:00Z",
            "intent_id": "entry-b",
            "code": "master_entry_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=101|signed_quantity=1|execution_id=b",
        },
        {
            "recorded_utc": "2026-08-03T12:02:00Z",
            "intent_id": "exit-intent",
            "code": "master_exit_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=102|signed_quantity=-2|execution_id=x",
        },
    ]
    by_intent = {}
    for row in executions:
        by_intent.setdefault(row["intent_id"], []).append(row)

    RECONCILER.attribute_native_terminal_events(executions, by_intent)

    for intent_id in ("entry-a", "entry-b"):
        terminal = next(
            row for row in by_intent[intent_id]
            if row["code"] == "master_exit_fill_observed"
        )
        assert terminal["_source_intent_id"] == "exit-intent"
        assert terminal["_attributed_signed_quantity"] == -1


def test_closed_ledger_episode_does_not_consume_a_later_native_exit() -> None:
    executions = [
        {
            "recorded_utc": "2026-08-03T11:00:00Z",
            "intent_id": "stale-entry",
            "code": "master_entry_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=99|signed_quantity=1|execution_id=old|native_order=old-order",
        },
        {
            "recorded_utc": "2026-08-03T12:00:00Z",
            "intent_id": "entry-a",
            "code": "master_entry_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=100|signed_quantity=1|execution_id=a|native_order=order-a",
        },
        {
            "recorded_utc": "2026-08-03T12:01:00Z",
            "intent_id": "entry-b",
            "code": "master_entry_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=101|signed_quantity=1|execution_id=b|native_order=order-b",
        },
        {
            "recorded_utc": "2026-08-03T12:02:00Z",
            "intent_id": "exit-intent",
            "code": "master_exit_fill_observed",
            "message": "account=Master|contract=M2K 09-26|fill=102|signed_quantity=-2|execution_id=x",
        },
    ]
    by_intent = {}
    for row in executions:
        by_intent.setdefault(row["intent_id"], []).append(row)
    trade_ledger = [{
        "account": "Master",
        "instrument": "M2K 09-26",
        "entry_signal": "old-order",
        "entry_order_identity": "old-order",
        "exit_utc": datetime(2026, 8, 3, 11, 5, tzinfo=timezone.utc),
    }]

    RECONCILER.attribute_native_terminal_events(executions, by_intent, trade_ledger)

    assert not any(
        row["code"] == "master_exit_fill_observed"
        for row in by_intent["stale-entry"]
    )
    for intent_id in ("entry-a", "entry-b"):
        terminal = next(
            row for row in by_intent[intent_id]
            if row["code"] == "master_exit_fill_observed"
        )
        assert terminal["_attributed_signed_quantity"] == -1


def test_close_kind_accepts_native_compact_stop_and_target_roles() -> None:
    assert RECONCILER.infer_close_kind({
        "exit_type": "TP",
        "exit_signal": "GL1-GABC-HT0-L1",
    }) == "target"
    assert RECONCILER.infer_close_kind({
        "exit_type": "SL",
        "exit_signal": "GL1-GABC-HS0-L1",
    }) == "stop"


def test_manual_master_trade_preserves_snapshot_and_ai_comparison(tmp_path: Path) -> None:
    glitch_data = tmp_path / "GlitchData"
    frame_root = glitch_data / "hermes" / "exchange" / "glitch" / "minute-frames"
    frame_root.mkdir(parents=True)
    (frame_root / "20260803T1250Z.json").write_text(json.dumps({
        "minute_id": "20260803T1250Z",
        "market_snapshot": {"snapshot_hash": "market-at-entry"},
    }), encoding="utf-8")
    entry_utc = datetime(2026, 8, 3, 12, 50, 30, tzinfo=timezone.utc)
    exit_utc = entry_utc + timedelta(minutes=4)
    snapshots = [(entry_utc - timedelta(seconds=30), {
        "snapshot_id": "portfolio-at-entry",
        "created_utc": "2026-08-03T12:50:00Z",
        "accounts": [{"account": "Master", "positions": [], "working_orders": 0}],
    })]
    intents = {"ai-nearby": {
        "intent_id": "ai-nearby",
        "_cycle_id": "ai-cycle",
        "account": "Master",
        "instrument": "MNQ",
        "created_utc": "2026-08-03T12:50:20Z",
        "action": "ENTER_SHORT",
        "confidence": 0.41,
        "snapshot_hash": "market-at-entry",
        "reason": "AI considered the opposite side",
    }}
    trade = {
        "trade_id": "manual-native-trade-1",
        "account": "Master",
        "instrument": "MNQ",
        "side": "Long",
        "contracts": 2,
        "entry_price": 20000,
        "exit_price": 20008,
        "pnl_points": 16,
        "commission_total": 2,
        "entry_utc": entry_utc,
        "exit_utc": exit_utc,
        "trade_source": "Manual",
        "entry_type": "Manual",
        "entry_signal": "ChartTrader",
        "exit_signal": "Close",
        "open_reason": "Manual Entry",
        "close_reason": "Manual / Other",
    }

    outcome = RECONCILER.manual_trade_outcome(glitch_data, snapshots, intents, trade)

    assert outcome is not None
    assert outcome["origin"] == "manual"
    assert outcome["intent_id"].startswith("manual-")
    assert outcome["snapshot_reference"]["portfolio"]["snapshot_id"] == "portfolio-at-entry"
    assert outcome["snapshot_reference"]["market"]["snapshot_hash"] == "market-at-entry"
    assert outcome["ai_comparison"]["intent_id"] == "ai-nearby"
    assert outcome["master_learning_eligible"] is True
    assert outcome["attribution"]["origin"] == "manual"

    context = LEARNING.entry_decision_context(glitch_data, outcome, None, outcome["account_outcomes"][0])
    assert context["origin"] == "manual"
    assert context["human_trade"]["entry_signal"] == "ChartTrader"
    assert context["contemporaneous_ai_decision"]["intent_id"] == "ai-nearby"
    assert context["canonical_outcome_layers"]["forecast_outcome"]["status"] == "not_provided"


def test_canonical_outcome_layers_normalize_first_touch_and_forecast() -> None:
    intent = {
        "intent_id": "intent-1",
        "_cycle_id": "cycle-1",
        "action": "ENTER_LONG",
        "instrument": "MNQ",
        "account": "Master",
        "quantity": 1,
        "entry_range_low": 19999.5,
        "entry_range_high": 20000.5,
        "stop_loss": 19990.0,
        "take_profit_1": 20020.0,
        "forecast": {
            "event": "STOP_BEFORE_PRIMARY_TARGET",
            "probability": 0.25,
            "method": "bounded_path",
            "confidence": 0.8,
        },
    }
    account_outcome = {
        "quantity": 1,
        "entry_utc": "2026-08-03T12:50:00Z",
        "entry_price": 20001.0,
        "exit_price": 19990.0,
        "exit_utc": "2026-08-03T12:51:00Z",
        "point_value_usd": 5.0,
        "tick_size": 0.25,
        "initial_protection_legs": [{
            "leg": 1,
            "quantity": 1,
            "initial_stop_price": 19990.0,
        }],
        "initial_native_risk_usd": 50.0,
        "risk_normalization_status": "complete",
        "realized_pnl_usd": -51.25,
        "sampled_mfe_usd": 5.0,
        "sampled_mae_usd": -55.0,
        "close_kind": "stop",
        "protection_status": "submitted",
        "protection_evidence": "execution_receipt",
    }
    market_reference = {
        "created_utc": "2026-08-03T12:49:59Z",
        "current_price": 20000.0,
    }
    submitted = {"recorded_utc": "2026-08-03T12:49:59.500Z", "message": "correlation=corr1234"}
    bracket_event = {
        "recorded_utc": "2026-08-03T12:50:01Z",
        "message": "fill=20001|tp1=20020",
    }

    layers = RECONCILER.canonical_outcome_layers(
        intent, account_outcome, submitted, bracket_event, market_reference, []
    )

    assert layers["normalized_outcome"]["realized_r"] == -1.025
    assert layers["normalized_outcome"]["first_touch"] == "STOP_FIRST"
    assert layers["forecast_outcome"]["observed"] is True
    assert layers["forecast_outcome"]["brier_score"] == 0.5625
    assert layers["decision_geometry"]["planned_entry_range_low"] == 19999.5
    assert layers["decision_geometry"]["planned_entry_range_high"] == 20000.5
    fill_quality = layers["execution_diagnostics"]["intent_fidelity"]["entry_range_fill_quality"]
    assert fill_quality["status"] == "outside_declared_range"
    assert fill_quality["range_relation"] == "adverse_beyond_range"
    assert fill_quality["deviation_points"] == 0.5
    assert fill_quality["deviation_ticks"] == 2.0
    assert fill_quality["effect"] == "observation_only_no_execution_effect"
    assert layers["execution_diagnostics"]["intent_fidelity"]["timing"][
        "full_protection_acknowledgement_status"
    ] == "unavailable_native_receipt"


def test_manual_learning_rejects_replication_identity() -> None:
    now = datetime(2026, 8, 3, 12, 50, tzinfo=timezone.utc)
    replicated = {
        "trade_id": "follower-trade",
        "account": "Follower",
        "instrument": "MNQ",
        "side": "Long",
        "contracts": 1,
        "entry_price": 20000,
        "exit_price": 20001,
        "pnl_points": 1,
        "commission_total": 0,
        "entry_utc": now,
        "exit_utc": now + timedelta(minutes=1),
        "trade_source": "Replication",
        "entry_type": "Manual",
        "entry_signal": "GLT-COPY-E-route-correlation-R1-O1",
    }

    assert RECONCILER.manual_trade_outcome(Path("unused"), [], {}, replicated) is None


def manual_identity_trade(entry_utc: datetime) -> dict:
    return {
        "trade_id": "mutable-trade-id",
        "account": "Master",
        "instrument": "MNQ 09-26",
        "side": "Long",
        "contracts": 1,
        "entry_price": 20000,
        "exit_price": 20004,
        "pnl_points": 4,
        "commission_total": 1,
        "entry_utc": entry_utc,
        "exit_utc": entry_utc + timedelta(minutes=2),
        "trade_source": "Manual",
        "entry_type": "Manual",
        "entry_signal": "ChartTrader",
        "exit_signal": "Close",
        "open_reason": "Manual Entry",
        "close_reason": "Manual / Other",
    }


def test_ai_comparison_never_uses_post_entry_decision() -> None:
    entry_utc = datetime(2026, 8, 3, 12, 50, 30, tzinfo=timezone.utc)
    trade = manual_identity_trade(entry_utc)
    intents = {
        "before": {
            "intent_id": "before",
            "account": "Master",
            "instrument": "MNQ",
            "created_utc": (entry_utc - timedelta(seconds=90)).isoformat(),
        },
        "after": {
            "intent_id": "after",
            "account": "Master",
            "instrument": "MNQ",
            "created_utc": (entry_utc + timedelta(seconds=1)).isoformat(),
        },
        "too-old": {
            "intent_id": "too-old",
            "account": "Master",
            "instrument": "MNQ",
            "created_utc": (entry_utc - timedelta(seconds=91)).isoformat(),
        },
    }

    comparison = RECONCILER.contemporaneous_ai_comparison(intents, trade)

    assert comparison["intent_id"] == "before"
    assert RECONCILER.contemporaneous_ai_comparison({"after": intents["after"]}, trade) is None
    assert RECONCILER.contemporaneous_ai_comparison({"too-old": intents["too-old"]}, trade) is None


def test_manual_identity_survives_correction_and_prefers_entry_order() -> None:
    entry_utc = datetime(2026, 8, 3, 12, 50, 30, tzinfo=timezone.utc)
    original = manual_identity_trade(entry_utc)
    corrected = {
        **original,
        "trade_id": "corrected-mutable-trade-id",
        "contracts": 3,
        "entry_price": 20001.25,
        "exit_price": 20007.75,
        "pnl_points": 19.5,
        "exit_utc": original["exit_utc"] + timedelta(seconds=20),
        "exit_signal": "CorrectedClose",
    }

    assert RECONCILER.manual_episode_identity(original) == RECONCILER.manual_episode_identity(corrected)
    first = RECONCILER.manual_trade_outcome(Path("unused"), [], {}, original)
    second = RECONCILER.manual_trade_outcome(Path("unused"), [], {}, corrected)
    assert first["intent_id"] == second["intent_id"]
    assert first["cycle_id"] == second["cycle_id"]

    order_original = {**original, "entry_order_identity": "native-order-1"}
    order_corrected = {**corrected, "entry_order_identity": "native-order-1"}
    other_order = {**corrected, "entry_order_identity": "native-order-2"}
    assert RECONCILER.manual_episode_identity(order_original) == RECONCILER.manual_episode_identity(order_corrected)
    assert RECONCILER.manual_episode_identity(order_original) != RECONCILER.manual_episode_identity(other_order)


def test_corrected_manual_episode_replaces_legacy_mutable_id(tmp_path: Path) -> None:
    entry_utc = datetime(2026, 8, 3, 12, 50, 30, tzinfo=timezone.utc)
    trade = manual_identity_trade(entry_utc)
    corrected = {
        **trade,
        "trade_id": "changed",
        "contracts": 4,
        "entry_price": 20002,
        "entry_order_identity": "native-order-1",
    }
    current = RECONCILER.manual_trade_outcome(Path("unused"), [], {}, corrected)
    legacy = RECONCILER.manual_trade_outcome(Path("unused"), [], {}, trade)
    legacy["intent_id"] = "manual-legacy-mutable-trade-id"
    fields = [
        "changed", str(dotnet_ticks(entry_utc)), str(dotnet_ticks(corrected["exit_utc"])),
        "Master", "MNQ", "Long", "4", "20002", "20004", "8",
        "Manual Entry", "Manual / Other", "Asia", "Asia", "Manual", "Manual",
        "Manual", "ChartTrader", "Close", "1", "native-order-1", "native-exit-1",
    ]
    glitch_data = tmp_path / "GlitchData"
    (glitch_data / "intents").mkdir(parents=True)
    (glitch_data / "TradeLedger.tsv").write_text(
        "\t".join(fields) + "\n", encoding="utf-8"
    )
    output = glitch_data / "intents" / "hermes-trade-outcomes.jsonl"
    output.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    rows = RECONCILER.reconcile(glitch_data, None, output)

    assert len(rows) == 1
    assert rows[0]["intent_id"] == current["intent_id"]
    assert rows[0]["account_outcomes"][0]["quantity"] == 4


def test_trade_ledger_reader_accepts_optional_entry_order_identity(tmp_path: Path) -> None:
    entry_utc = datetime(2026, 8, 3, 12, 50, 30, tzinfo=timezone.utc)
    exit_utc = entry_utc + timedelta(minutes=2)
    fields = [
        "mutable-id", str(dotnet_ticks(entry_utc)), str(dotnet_ticks(exit_utc)),
        "Master", "MNQ", "Long", "1", "20000", "20004", "4",
        "Manual Entry", "Manual / Other", "Asia", "Asia", "Manual", "Manual",
        "Manual", "ChartTrader", "Close", "1", "native-order-1", "native-exit-1",
    ]
    ledger = tmp_path / "TradeLedger.tsv"
    ledger.write_text("\t".join(fields) + "\n", encoding="utf-8")

    rows = RECONCILER.read_trade_ledger(ledger)

    assert rows[0]["entry_order_identity"] == "native-order-1"
    assert RECONCILER.manual_episode_identity(rows[0]).endswith("|native-order-1")
