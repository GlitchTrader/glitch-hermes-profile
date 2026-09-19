"""Offline recording, budget, crash recovery and no-influence lifecycle tests."""
import ast
import base64
import importlib.util
import json
import multiprocessing
from pathlib import Path
import time

import pytest

from test_jev_observation import sample_cache
from jev_observation import digest, encoded
from jev_provider import RESERVED_USD_PER_CALL

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jev_shadow", ROOT / "scripts/run-jev-shadow.py")
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def arguments(tmp_path, mode="RECORD_ONLY"):
    return shadow.parse_args(["--mode", mode, "--cache", str(tmp_path / "cache.json"),
                              "--output", str(tmp_path / "jev-shadow"), "--instrument", "MNQ 12-26"])


def records(root):
    return [json.loads(line) for path in sorted(root.glob("evidence-*.jsonl"))
            for line in path.read_text().splitlines() if line.endswith("}")]


def test_off_is_zero_side_effect_default(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "credentials", lambda *args: pytest.fail("credential read"))
    assert shadow.main(["--output", str(tmp_path / "jev-shadow")]) == 0
    assert not list(tmp_path.iterdir())


def test_record_exact_bytes_deduplicate_restart_and_report_torn_tail(tmp_path):
    args = arguments(tmp_path)
    raw = b" \n" + encoded(sample_cache())
    args.cache.write_bytes(raw)
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store)
    observer.capture()
    observer.capture()
    args.cache.write_bytes(raw)
    observer.capture()
    assert observer.duplicates == 1
    store.close()
    rows = records(args.output)
    assert len(rows) == 1
    assert base64.b64decode(rows[0]["raw_cache_base64"]) == raw
    assert rows[0]["raw_hash"] == digest(raw)
    assert rows[0]["influenced"] is False
    path = next(args.output.glob("evidence-*.jsonl"))
    with path.open("ab") as stream:
        stream.write(b'{"torn":')
    prior_bytes = path.read_bytes()
    recovered = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    assert recovered.torn_tails == [path.name]
    assert recovered.last_observation["observation_id"] == rows[0]["observation_id"]
    assert recovered.epoch != rows[0]["process_epoch"]
    shadow.Observer(args, recovered).capture()
    recovered.append("epoch_start", torn_tails=recovered.torn_tails)
    recovered.close()
    assert path.read_bytes() == prior_bytes


def test_reservations_survive_restart_even_when_provider_was_interrupted(tmp_path):
    args = arguments(tmp_path)
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    store.append("request", request_id="unknown-outcome", reserved_usd=RESERVED_USD_PER_CALL)
    store.close()
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    assert store.calls == 1 and store.unfinished == {"unknown-outcome"}
    store.close()


def test_lock_prevents_duplicate_recorder(tmp_path):
    store = shadow.EvidenceStore(tmp_path / "jev-shadow", 4 * 1024 * 1024)
    try:
        with pytest.raises(ValueError, match="observer_already_running"):
            shadow.EvidenceStore(tmp_path / "jev-shadow", 4 * 1024 * 1024)
    finally:
        store.close()


def test_disk_cap_never_deletes_or_overwrites_existing_evidence(tmp_path):
    args = arguments(tmp_path)
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    store.append("epoch_start")
    before = {p: p.read_bytes() for p in args.output.glob("evidence-*.jsonl")}
    store.disk_bytes = store.total + 65536
    with pytest.raises(ValueError, match="disk_limit"):
        store.append("observation", data="new")
    store.close()
    assert all(p.read_bytes() == data for p, data in before.items())


def test_stop_control_and_bounded_recording_never_load_keys(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    args.cache.write_bytes(encoded(sample_cache()))
    monkeypatch.setattr(shadow, "credentials", lambda *args: pytest.fail("credential read"))
    argv = ["--mode", "RECORD_ONLY", "--cache", str(args.cache), "--output", str(args.output),
            "--duration-seconds", ".01"]
    assert shadow.main(argv) == 0
    health = json.loads((args.output / "health.json").read_bytes())
    assert health["status"] == "stopped" and health["requests_total"] == 0
    (args.output / "STOP").touch()
    before = records(args.output)
    assert shadow.main(argv) == 1
    assert records(args.output) == before


def test_budget_prevents_network_but_recording_continues(tmp_path, monkeypatch):
    args = arguments(tmp_path, "SHADOW")
    args.max_usd = 0
    args.cache.write_bytes(encoded(sample_cache(time.time())))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store, {"TYPESAFE_API_KEY": "unused"})
    monkeypatch.setattr(observer.slot, "start", lambda *args: pytest.fail("network start"))
    observer.step()
    assert observer.last_error == "inference_budget_exhausted"
    assert len(records(args.output)) == 1
    store.close()


def test_cadence_stale_admission_and_regression_high_water(tmp_path, monkeypatch):
    args = arguments(tmp_path, "SHADOW")
    now = time.time()
    args.cache.write_bytes(encoded(sample_cache(now)))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store, {"TYPESAFE_API_KEY": "unused"})
    calls = []
    monkeypatch.setattr(observer.slot, "start", lambda *args: calls.append(args))
    observer.step()
    observer.step()
    assert len(calls) == 1 and store.calls == 1
    for offset in (-10, -5):
        args.cache.write_bytes(encoded(sample_cache(now + offset)))
        observer.next_capture = observer.next_call = 0
        observer.step()
        assert "source_time_regression" in observer.instruments[args.instrument]["issues"]
    assert len(calls) == 1
    observer.next_call = 0
    monkeypatch.setattr(shadow.time, "time", lambda: now + 100)
    observer.step()
    assert len(calls) == 1
    store.close()


def test_provider_deadline_kills_own_process_and_never_accepts_late_result():
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(False)
    process = context.Process(target=time.sleep, args=(10,))
    process.start()
    sender.close()
    slot = shadow.ProviderSlot()
    slot.active = {"process": process, "receiver": receiver, "started": time.monotonic() - 2.1,
                   "started_utc": "test", "request_id": "r", "observation_id": "old",
                   "raw_hash": "hash", "state_hash": "s"}
    result = slot.finish("new")
    assert result["status"] == "deadline_exceeded" and result["superseded"] and result["expired"]
    assert not process.is_alive() and slot.active is None


def test_complete_response_is_retained_but_superseded_is_ineligible(tmp_path):
    args = arguments(tmp_path, "SHADOW")
    args.cache.write_bytes(encoded(sample_cache(time.time())))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store)
    observer.capture()
    observer.prediction({"status": "ok", "request_id": "r", "superseded": True, "expired": False,
                         "raw_response": "original typed response"})
    row = records(args.output)[-1]
    assert row["raw_response"] == "original typed response"
    assert not row["eligible_for_research_scoring"] and row["influenced"] is False
    store.close()


def test_invalid_record_and_unowned_or_overlapping_output_fail_closed(tmp_path):
    args = arguments(tmp_path)
    args.output.mkdir()
    (args.output / "other.txt").write_text("preserve")
    with pytest.raises(ValueError, match="unowned_output_directory"):
        shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    assert shadow.main(["--mode", "RECORD_ONLY", "--output", str(args.output),
                        "--cache", str(args.output / "cache.json")]) == 1
    assert (args.output / "other.txt").read_text() == "preserve"


def test_complete_record_corruption_is_detected_before_restart(tmp_path):
    args = arguments(tmp_path)
    args.cache.write_bytes(encoded(sample_cache()))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    shadow.Observer(args, store).capture()
    store.close()
    path = next(args.output.glob("evidence-*.jsonl"))
    row = json.loads(path.read_bytes())
    row["raw_hash"] = "corrupt"
    path.write_bytes(encoded(row) + b"\n")
    with pytest.raises(ValueError, match="evidence_hash_mismatch"):
        shadow.EvidenceStore(args.output, 4 * 1024 * 1024)


def test_evidence_write_failure_is_not_swallowed_as_cache_retry(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    args.cache.write_bytes(encoded(sample_cache()))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    def failure(*args, **kwargs):
        raise shadow.EvidenceWriteError("evidence_write_failed")
    monkeypatch.setattr(store, "append", failure)
    with pytest.raises(shadow.EvidenceWriteError):
        shadow.Observer(args, store).capture()
    store.close()


def test_provider_busy_rejects_a_second_inflight_request():
    slot = shadow.ProviderSlot()
    slot.active = {"placeholder": True}
    with pytest.raises(ValueError, match="provider_busy"):
        slot.start("r", "o", "h", {}, {})


def test_malformed_generation_does_not_erase_source_high_water(tmp_path):
    args = arguments(tmp_path)
    now = time.time()
    args.cache.write_bytes(encoded(sample_cache(now)))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store)
    observer.capture()
    args.cache.write_bytes(b'{"torn":')
    observer.capture()
    store.close()
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store)
    args.cache.write_bytes(encoded(sample_cache(now - 5)))
    observer.capture()
    assert "source_time_regression" in observer.instruments[args.instrument]["issues"]
    store.close()


def test_no_trading_or_hermes_imports_and_no_scheduled_activation():
    allowed = {"argparse", "ast", "base64", "collections", "datetime", "hashlib", "json", "math", "multiprocessing",
               "os", "pathlib", "re", "sys", "time", "urllib", "uuid", "msvcrt", "fcntl", "__future__",
               "jev_observation", "jev_provider"}
    for filename in ("jev_observation.py", "jev_provider.py", "run-jev-shadow.py"):
        tree = ast.parse((ROOT / "scripts" / filename).read_text())
        for node in ast.walk(tree):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [entry.name for entry in node.names] if isinstance(node, ast.Import) else [])
            assert all(module.split(".")[0] in allowed for module in modules)
    for filename in ("run-direct-glitch-cycle.py", "run-hermes-learning-cycle.py", "market_structure.py"):
        assert "jev_" not in (ROOT / "scripts" / filename).read_text()
    setup = (ROOT / "setup.ps1").read_text()
    assert "-Name 'glitch-jev" not in setup
