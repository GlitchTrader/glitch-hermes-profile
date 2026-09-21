"""Bounded, isolated development comparison. Outputs never enter the live exchange."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from hermes_briefing import ARMS

SKILLS = "glitch-setup-state,glitch-order-flow,glitch-build-intent"
VISUAL_NOTE = ("\nOFFLINE REPLAY: The historical chart attachment is unavailable in every arm. "
               "Use the supplied numerical facts only; do not claim to have viewed the chart.\n")


def command(python, home, triggered):
    home = home.resolve()
    if home.name != "offline-home" or not (home / "RESEARCH_ONLY").is_file():
        raise ValueError("isolated_research_home_required")
    if any(p.is_file() for folder in ("plugins", "cron") for p in (home / folder).rglob("*")):
        raise ValueError("offline_home_must_not_have_plugins_or_cron")
    skills = SKILLS if triggered else (
        "glitch-market-scan,glitch-setup-state,glitch-order-flow,"
        "glitch-position-management,glitch-build-intent")
    args = ["chat", "-Q", "--source", "research", "--model", "gpt-5.6-luna",
            "--provider", "openai-codex", "--reasoning", "low", "--max-turns", "1",
            "--toolsets", "jev-offline-empty", "--skills", skills]
    wrapper = (
        "import os,sys;os.environ['HERMES_HOME']=" + repr(str(home)) + ";"
        "from toolsets import create_custom_toolset;"
        "create_custom_toolset('jev-offline-empty','Offline supplied evidence',tools=[],includes=[]);"
        "from hermes_cli.main import main;"
        "sys.argv=[sys.argv[0]]+" + repr(args) + "+['-q',sys.stdin.read()];main()"
    )
    return [str(python), "-c", wrapper]


def parse_response(text):
    # Structural report only, never an execution validator or a native submission.
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("schema_version") == "glitch.intent.batch.v1":
            return value
    raise ValueError("batch_json_not_found")


def decision_summary(batch):
    decisions = batch.get("decisions", [])
    return {"actions": [v.get("action") for v in decisions],
            "jev_named_in_audit": ["jev" in json.dumps(v.get("decision_audit", {})).lower()
                                   for v in decisions]}


def run(args):
    root, home = args.root.resolve(), args.home.resolve()
    if not home.is_relative_to(root):
        raise ValueError("home_outside_research_root")
    cases = [root / "cases" / name for name in ("20260921T0325Z", "20260921T0327Z")]
    output = root / "comparison"; output.mkdir(exist_ok=False)
    protocol = {"model": "gpt-5.6-luna", "provider": "openai-codex", "reasoning": "low",
                "max_calls": 8, "timeout_seconds": args.timeout, "parallelism": 1,
                "retries": 0, "native_effect": "none", "chart": "unavailable_in_all_arms",
                "sample": "two_development_cases_not_holdout", "cases": [p.name for p in cases]}
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    env = os.environ.copy(); env["HERMES_HOME"] = str(home)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONIOENCODING="utf-8")
    results = []
    for index, case in enumerate(cases):
        manifest = json.loads((case / "comparison-manifest.json").read_text())
        order = ARMS[index:] + ARMS[:index]
        for arm in order:
            prompt = (case / "variants" / (arm + ".txt")).read_text(encoding="utf-8")
            if hashlib.sha256(prompt.encode()).hexdigest() != manifest["arms"][arm]["prompt_sha256"]:
                raise ValueError("frozen_prompt_hash_mismatch")
            command_line = command(args.python, home, index == 1)
            actual = prompt + VISUAL_NOTE
            dest = output / (case.name + "-" + arm); dest.mkdir()
            record = {"case": case.name, "arm": arm, "started_epoch": time.time(),
                      "input_chars": len(actual), "prompt_sha256": hashlib.sha256(actual.encode()).hexdigest()}
            started = time.monotonic()
            try:
                completed = subprocess.run(command_line, input=actual, text=True, encoding="utf-8",
                    errors="replace", capture_output=True, timeout=args.timeout, env=env, cwd=home,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
                (dest / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
                # Keep diagnostics local; never echo arbitrary provider output or credentials.
                (dest / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
                record.update(returncode=completed.returncode, output_chars=len(completed.stdout))
                if completed.returncode:
                    record["status"] = "process_error"
                else:
                    try:
                        batch = parse_response(completed.stdout)
                        (dest / "batch.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
                        record.update(status="batch_json", **decision_summary(batch),
                                      parsed_batch=True, native_contract_validation="not_performed")
                    except ValueError:
                        record["status"] = "invalid_batch_json"
            except subprocess.TimeoutExpired:
                record["status"] = "timeout"
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            results.append(record)
            (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(record), flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240, choices=range(30, 301))
    run(parser.parse_args())
