"""Independent Level 0 cache recorder. OFF by default; never invokes Hermes or Glitch."""
from __future__ import annotations

import argparse
import base64
from collections import deque
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
import uuid

from jev_observation import (MAX_BYTES, INPUT_EPOCH, STATE_VERSION, age, build_state, decode_cache,
                             digest, encoded, strict_json, timestamp, utc_now)
from jev_provider import (MODEL, PROVIDER, QUESTIONS, QUESTION_VERSION, RESERVED_USD_PER_CALL,
                          credentials, request_process)

DEFAULT_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
DEADLINE_SECONDS = 2
SEGMENT_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024


class EvidenceWriteError(RuntimeError):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def safe_path(path):
    if not path.is_absolute():
        raise ValueError("absolute_path_required")
    # Reject redirects out of the operator-selected evidence folder, including Windows junctions.
    for parent in (path, *path.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValueError("redirected_path")
    return path.resolve()


class EvidenceStore:
    """Append/fsync, rotate without pruning, recover complete records without repairing history."""
    def __init__(self, root, disk_bytes):
        self.root, self.disk_bytes = safe_path(root), disk_bytes
        if root.name != "jev-shadow":
            raise ValueError("dedicated_jev_shadow_directory_required")
        root.mkdir(parents=True, exist_ok=True)
        marker = root / "observer.json"
        if any(root.iterdir()) and not marker.is_file():
            raise ValueError("unowned_output_directory")
        if marker.is_file() and strict_json(marker.read_bytes()).get("owner") != "glitch.jev.shadow.v1":
            raise ValueError("output_owner_mismatch")
        if sum(1 for _ in root.iterdir()) > 10000:
            raise ValueError("evidence_file_count_limit")
        for path in root.iterdir():
            safe_path(path)
        self.lock = (root / "observer.lock").open("a+b")
        if self.lock.tell() == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise ValueError("observer_already_running") from None
        if not marker.exists():
            atomic_json(marker, {"owner": "glitch.jev.shadow.v1"})
        self.epoch = utc_now().replace(":", "").replace(".", "") + "-" + uuid.uuid4().hex[:12]
        self.total = sum(p.stat().st_size for p in root.iterdir() if p.is_file())
        self.calls, self.last_observation, self.torn_tails = 0, None, []
        self.unfinished = set()
        self.stream, self.segment_size, self.segment = None, 0, 0
        try:
            if self.total > disk_bytes:
                raise ValueError("disk_limit")
            for path in sorted(root.glob("evidence-*.jsonl")):
                with path.open("rb") as stream:
                    while line := stream.readline(MAX_RECORD_BYTES + 1):
                        if len(line) > MAX_RECORD_BYTES:
                            raise ValueError("record_size_limit")
                        if not line.endswith(b"\n"):
                            self.torn_tails.append(path.name)
                            break
                        row = strict_json(line, MAX_RECORD_BYTES)
                        if not isinstance(row, dict):
                            raise ValueError("evidence_record_shape")
                        if row.get("kind") == "observation":
                            raw = base64.b64decode(row.get("raw_cache_base64", ""), validate=True)
                            if len(raw) > MAX_BYTES or digest(raw) != row.get("raw_hash"):
                                raise ValueError("evidence_hash_mismatch")
                            self.last_observation = row
                        elif row.get("kind") == "request":
                            self.calls += 1
                            self.unfinished.add(row["request_id"])
                        elif row.get("kind") == "prediction":
                            self.unfinished.discard(row["request_id"])
        except Exception:
            self.close()
            raise

    def append(self, kind, **fields):
        row = dict(fields, kind=kind, process_epoch=self.epoch, recorded_utc=utc_now(), influenced=False)
        line = encoded(row) + b"\n"
        if len(line) > MAX_RECORD_BYTES:
            raise ValueError("record_size_limit")
        # Reserve space for atomic health even when the evidence budget is exhausted.
        if self.total + len(line) + 65536 > self.disk_bytes:
            raise ValueError("disk_limit")
        try:
            if self.stream is None or self.segment_size + len(line) > SEGMENT_BYTES:
                if self.stream:
                    self.stream.close()
                self.segment += 1
                self.stream = (self.root / f"evidence-{self.epoch}-{self.segment:05d}.jsonl").open("xb")
                self.segment_size = 0
            self.stream.write(line)
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except OSError:
            raise EvidenceWriteError("evidence_write_failed") from None
        self.total += len(line)
        self.segment_size += len(line)
        return row

    def close(self):
        if getattr(self, "stream", None):
            self.stream.close()
        self.lock.close()


class ProviderSlot:
    """One isolated process, hard wall deadline; new input replaces the pending observation."""
    def __init__(self):
        self.active = None

    def start(self, request_id, observation_id, raw_hash, state, keys):
        if self.active:
            raise ValueError("provider_busy")
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=request_process, args=(sender, state, keys), daemon=True)
        started = time.monotonic()
        try:
            process.start()
        except Exception:
            receiver.close()
            sender.close()
            raise
        sender.close()
        self.active = {"process": process, "receiver": receiver, "started": started,
                       "started_utc": utc_now(), "request_id": request_id,
                       "observation_id": observation_id, "raw_hash": raw_hash,
                       "state_hash": digest(state)}

    def finish(self, latest_id, forced=None):
        if not self.active:
            return None
        active = self.active
        elapsed = time.monotonic() - active["started"]
        connection, process = active["receiver"], active["process"]
        if forced or elapsed >= DEADLINE_SECONDS:
            result = {"status": forced or "deadline_exceeded"}
        elif connection.poll():
            try:
                result = connection.recv()
            except EOFError:
                result = {"status": "provider_worker_exited"}
        elif not process.is_alive():
            result = {"status": "provider_worker_exited"}
        else:
            return None
        if process.is_alive():
            process.terminate()
        process.join(timeout=.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=.5)
        connection.close()
        self.active = None
        return dict(result, request_id=active["request_id"], observation_id=active["observation_id"],
                    observation_hash=active["raw_hash"], start_utc=active["started_utc"], end_utc=utc_now(),
                    state_hash=active["state_hash"], state_schema_version=STATE_VERSION, input_epoch=INPUT_EPOCH,
                    latency_ms=round(elapsed * 1000, 3), superseded=active["observation_id"] != latest_id,
                    expired=elapsed >= DEADLINE_SECONDS, downstream_ids=None, retry_count=0)


class Observer:
    def __init__(self, args, store, keys=None):
        self.args, self.store, self.keys = args, store, keys
        self.slot, self.history = ProviderSlot(), deque(maxlen=192)
        prior = store.last_observation or {}
        self.latest_id, self.raw_hash = prior.get("observation_id"), prior.get("raw_hash")
        self.previous_sources = prior.get("source_times", {})
        self.raw, self.fingerprint = None, None
        self.instruments, self.sequence = prior.get("instruments", {}), 0
        self.duplicates, self.read_errors, self.last_error = 0, 0, None
        self.next_call, self.next_health, self.next_capture, self.last_attempt_id = 0, 0, 0, None
        self.last_result = None

    def capture(self):
        """At most three short reads; record bytes, not a fabricated sample per poll."""
        path = self.args.cache
        for attempt in range(3):
            try:
                before = path.stat()
                fingerprint = (before.st_mtime_ns, before.st_size)
                if fingerprint == self.fingerprint:
                    return
                started = utc_now()
                with path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                after = path.stat()
                if fingerprint != (after.st_mtime_ns, after.st_size):
                    raise OSError("replacement_race")
                if len(raw) > MAX_BYTES:
                    raise ValueError("cache_size_limit")
                raw_hash = digest(raw)
                self.fingerprint = fingerprint
                if raw_hash == self.raw_hash:
                    self.duplicates += 1
                    return
                self.sequence += 1
                self.raw_hash, self.raw = raw_hash, raw
                self.latest_id = f"{self.store.epoch}:{self.sequence}:{raw_hash[:16]}"
                self.instruments, error = {}, None
                try:
                    self.instruments = decode_cache(raw, time.time())
                except (ValueError, TypeError, OverflowError):
                    error = "invalid_cache"
                sources = dict(self.previous_sources)
                for contract, item in self.instruments.items():
                    frame = item["frames"].get("1", {})
                    source = frame.get("reading_utc")
                    if source:
                        sources[contract] = source
                    previous = self.previous_sources.get(contract)
                    if source and previous and timestamp(source) < timestamp(previous):
                        item["issues"].append("source_time_regression")
                        item["eligible"] = False
                        sources[contract] = previous  # Preserve the high-water mark through replay and restart.
                    if source and (not previous or timestamp(source) > timestamp(previous)):
                        self.history.append({"contract": contract, "source_utc": source,
                                             "price": frame.get("values", {}).get("CurrentPrice")})
                if len(sources) > 128:
                    raise ValueError("contract_history_limit")
                self.store.append("observation", schema_version="glitch.fast_observation.v1",
                                  observation_id=self.latest_id, raw_hash=raw_hash,
                                  raw_cache_base64=base64.b64encode(raw).decode("ascii"),
                                  sequence=self.sequence, read_start_utc=started, read_end_utc=utc_now(),
                                  file_mtime_ns=before.st_mtime_ns, file_bytes=len(raw),
                                  source_times=sources, instruments=self.instruments, status=error or "recorded",
                                  observed_generation_gap="unknown; latest-only producer has no sequence")
                self.previous_sources = sources
                self.last_error = error
                return
            except OSError:
                if attempt < 2:
                    time.sleep(.025)
                else:
                    self.read_errors += 1
                    self.last_error = "cache_read_error"

    def prediction(self, result):
        if result:
            for field in ("returned_model", "raw_response", "usage", "estimated_cost_usd", "error_category"):
                result.setdefault(field, None)
            try:
                current = decode_cache(self.raw, time.time()) if self.raw else {}
                result["input_stale_or_invalid"] = not current.get(self.args.instrument, {}).get("eligible", False)
            except (ValueError, TypeError):
                result["input_stale_or_invalid"] = True
            result["eligible_for_research_scoring"] = (result["status"] == "ok" and not result["superseded"]
                                                      and not result["expired"] and not result["input_stale_or_invalid"])
            self.last_result = result["status"]
            self.store.append("prediction", schema_version="glitch.jev.prediction.v1",
                              provider=PROVIDER, requested_model=MODEL,
                              question_version=QUESTION_VERSION, question_hash=digest(QUESTIONS), **result)

    def step(self):
        if time.monotonic() >= self.next_capture:
            self.next_capture = time.monotonic() + 1
            self.capture()
        self.prediction(self.slot.finish(self.latest_id))
        if self.args.mode != "SHADOW" or self.slot.active or time.monotonic() < self.next_call:
            return
        if not self.raw or self.latest_id == self.last_attempt_id:
            return
        if self.store.calls >= self.args.max_calls or (self.store.calls + 1) * RESERVED_USD_PER_CALL > self.args.max_usd:
            self.last_error = "inference_budget_exhausted"
            return  # Recording continues, but no calls can be started.
        try:
            current = decode_cache(self.raw, time.time())  # Reassess age at admission, not at file read.
            original = self.instruments.get(self.args.instrument, {})
            if "source_time_regression" in original.get("issues", []):
                return
            state = build_state(current, self.args.instrument, self.latest_id, self.raw_hash, self.history)
        except (ValueError, TypeError):
            return
        request_id = uuid.uuid4().hex
        self.store.append("request", request_id=request_id, observation_id=self.latest_id,
                          observation_hash=self.raw_hash, provider=PROVIDER, requested_model=MODEL,
                          question_version=QUESTION_VERSION, question_hash=digest(QUESTIONS),
                          state_schema_version=STATE_VERSION, state_hash=digest(state), state=state,
                          reserved_usd=RESERVED_USD_PER_CALL, downstream_ids=None)
        self.store.calls += 1  # Reservation is durable before the side effect; never refund unknown calls.
        self.last_attempt_id = self.latest_id
        self.next_call = time.monotonic() + 60
        self.slot.start(request_id, self.latest_id, self.raw_hash, state, self.keys)

    def health(self, status="running"):
        atomic_json(self.store.root / "health.json", {
            "schema_version": "glitch.jev.health.v1", "updated_utc": utc_now(), "pid": os.getpid(),
            "process_epoch": self.store.epoch, "mode": self.args.mode, "status": status,
            "input_epoch": INPUT_EPOCH, "latest_observation_id": self.latest_id,
            "influenced": False, "provider_in_flight": bool(self.slot.active),
            "requests_total": self.store.calls, "reserved_usd_total": self.store.calls * RESERVED_USD_PER_CALL,
            "evidence_bytes": self.store.total, "duplicate_reads": self.duplicates, "read_errors": self.read_errors,
            "last_error": self.last_error, "last_provider_status": self.last_result,
            "input_issues": {key: item["issues"] for key, item in self.instruments.items()},
            "source_age_seconds_now": {key: age(item.get("frames", {}).get("1", {}).get("reading_utc"), time.time())
                                       for key, item in self.instruments.items()},
        })


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("OFF", "RECORD_ONLY", "SHADOW"), default="OFF")
    parser.add_argument("--cache", type=Path, default=DEFAULT_DATA / "AnalyticsBridgeCache.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA / "jev-shadow")
    parser.add_argument("--instrument", help="Exact native contract required for SHADOW; no automatic selection")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--duration-seconds", type=float, default=0, help="0 runs until STOP or interrupt")
    parser.add_argument("--max-disk-mb", type=int, default=512)
    parser.add_argument("--max-calls", type=int, default=500)
    parser.add_argument("--max-usd", type=float, default=1)
    args = parser.parse_args(argv)
    if not 4 <= args.max_disk_mb <= 4096 or not 0 <= args.duration_seconds <= 7 * 86400:
        parser.error("disk budget must be 4..4096 MB; duration must be 0..7 days")
    if not 0 <= args.max_calls <= 10000 or not 0 <= args.max_usd <= 10:
        parser.error("call budget must be 0..10000 and USD reserve 0..10")
    if args.mode == "SHADOW" and not args.instrument:
        parser.error("SHADOW requires --instrument with the exact contract")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.mode == "OFF":
        print(json.dumps({"mode": "OFF", "influenced": False}))
        return 0  # No credentials, cache reads, directory creation, cron or side effects.
    store = observer = None
    status, exit_code = "stopped", 0
    try:
        args.cache, args.output = safe_path(args.cache), safe_path(args.output)
        if args.cache == args.output or args.cache.is_relative_to(args.output):
            raise ValueError("input_output_overlap")
        store = EvidenceStore(args.output, args.max_disk_mb * 1024 * 1024)
        if (store.root / "STOP").exists():
            raise ValueError("stop_file_present")
        keys = credentials(args.env_file) if args.mode == "SHADOW" else None
        observer = Observer(args, store, keys)
        store.append("epoch_start", mode=args.mode, input_epoch=INPUT_EPOCH, questions=QUESTIONS,
                     question_version=QUESTION_VERSION, question_hash=digest(QUESTIONS),
                     requested_model=MODEL, provider=PROVIDER, state_schema_version=STATE_VERSION,
                     prior_observation_id=observer.latest_id, torn_tails=store.torn_tails,
                     interrupted_request_ids=sorted(store.unfinished),
                     source_hashes={p.name: digest(p.read_bytes()) for p in
                                    (Path(__file__), Path(__file__).with_name("jev_observation.py"),
                                     Path(__file__).with_name("jev_provider.py"))})
        started = time.monotonic()
        while not (store.root / "STOP").exists():
            tick = time.monotonic()
            observer.step()
            if tick >= observer.next_health:
                observer.health()
                observer.next_health = tick + 5
            if args.duration_seconds and time.monotonic() - started >= args.duration_seconds:
                break
            # Deadline/kill checks are responsive; cache metadata remains at most once/second.
            time.sleep(.025 if observer.slot.active else .2)
    except KeyboardInterrupt:
        status = "interrupted"
    except (OSError, ValueError, TypeError, EvidenceWriteError) as exc:
        status, exit_code = "observer_error", 1
        if observer:
            observer.last_error = str(exc) if str(exc) in {
                "disk_limit", "cache_size_limit", "record_size_limit", "evidence_write_failed"
            } else "observer_storage_or_contract_error"
        print(json.dumps({"status": status, "influenced": False}), file=sys.stderr)
    finally:
        if observer:
            result = observer.slot.finish(observer.latest_id, "observer_stopped")
            try:
                observer.prediction(result)
                store.append("epoch_stop", status=status)
            except (OSError, ValueError, EvidenceWriteError):
                status, exit_code = "evidence_write_failed", 1
            try:
                observer.health(status)
            except OSError:
                print('{"status":"health_write_failed","influenced":false}', file=sys.stderr)
        if store:
            store.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
