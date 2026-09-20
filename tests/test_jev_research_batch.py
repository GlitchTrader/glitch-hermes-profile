"""Offline fake-provider checks: budgets, uncertain calls and frozen-job identity."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "research/jev/run_batch.mjs"


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture(tmp_path):
    client = tmp_path / "fake-client.mjs"
    client.write_text("""import fs from 'node:fs/promises';
export async function infer(provider,state,q){
await fs.appendFile(new URL('./called.jsonl',import.meta.url),JSON.stringify(state)+'\\n');
return {status:'ok',http_status:200,returned_model:'jev-1.13.0',response:{usage:{input_tokens:100}},latency_ms:1};}
""")
    protocol = tmp_path / "protocol.md";protocol.write_text("offline synthetic test")
    jobs = []
    for i in range(2):
        state = {"schema":"synthetic", "value":i};questions = {"a":{"type":"noul"}}
        jobs.append({"id":str(i),"anchor":str(i),"state":state,"questions":questions,
                     "wire_hash":digest(encoded({"model":"jev-1.13.0","state":state,"questions":questions}))})
    raw=b"".join(encoded(j)+b"\n" for j in jobs);(tmp_path/"jobs.jsonl").write_bytes(raw)
    manifest={"model":"jev-1.13.0","influence":"none","max_calls":2,"max_usd":.1,
              "provider_client_sha256":digest(client.read_bytes()),"jobs_sha256":digest(raw),
              "protocol_path":str(protocol),"protocol_sha256":digest(protocol.read_bytes())}
    (tmp_path/"batch.json").write_bytes(encoded(manifest))
    return client,jobs,manifest


def run(root,client):
    return subprocess.run(["node",str(RUNNER),str(root),str(client)],capture_output=True,text=True,timeout=30)


def test_completed_and_uncertain_dispatches_never_retry(tmp_path):
    client,jobs,_=fixture(tmp_path)
    (tmp_path/"dispatches.jsonl").write_bytes(encoded({"id":"0","wire_hash":jobs[0]["wire_hash"]})+b"\n")
    r=run(tmp_path,client);assert r.returncode==0,r.stderr
    assert len((tmp_path/"called.jsonl").read_text().splitlines())==1
    summary=json.loads(r.stdout.strip().splitlines()[-1]);assert summary["calls"]==2
    assert summary["accounted_usd"]>=.03
    r=run(tmp_path,client);assert r.returncode==0,r.stderr
    assert len((tmp_path/"called.jsonl").read_text().splitlines())==1
    assert not (tmp_path/"RUNNING.lock").exists()


@pytest.mark.parametrize("field,value",[("provider_client_sha256","wrong"),("jobs_sha256","wrong"),("protocol_sha256","wrong"),("model","jev-latest")])
def test_frozen_identity_failure_prevents_dispatch(tmp_path,field,value):
    client,_,m=fixture(tmp_path);m[field]=value;(tmp_path/"batch.json").write_bytes(encoded(m))
    assert run(tmp_path,client).returncode != 0
    assert not (tmp_path/"called.jsonl").exists()
    assert not (tmp_path/"dispatches.jsonl").exists()
    assert not (tmp_path/"RUNNING.lock").exists()


def test_budget_reserves_unknown_call_before_dispatch(tmp_path):
    client,_,m=fixture(tmp_path);m["max_usd"]=.029;(tmp_path/"batch.json").write_bytes(encoded(m))
    r=run(tmp_path,client);assert r.returncode==0,r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["halt"]
    assert not (tmp_path/"called.jsonl").exists()


def test_existing_lock_is_never_stolen(tmp_path):
    client,_,_=fixture(tmp_path);(tmp_path/"RUNNING.lock").write_text("other process")
    assert run(tmp_path,client).returncode != 0
    assert (tmp_path/"RUNNING.lock").read_text()=="other process"
    assert not (tmp_path/"called.jsonl").exists()


def test_unexpected_provider_throw_stops_without_leaking_or_retrying(tmp_path):
    client,_,m=fixture(tmp_path)
    client.write_text("export async function infer(){throw new Error('private-provider-error-content');}")
    m["provider_client_sha256"]=digest(client.read_bytes());(tmp_path/"batch.json").write_bytes(encoded(m))
    r=run(tmp_path,client)
    assert r.returncode != 0
    assert "private-provider-error-content" not in r.stdout+r.stderr
    summary=json.loads(r.stdout.strip().splitlines()[-1])
    assert summary["worker_errors"]==2 and summary["accounted_usd"]==.06
    assert not (tmp_path/"RUNNING.lock").exists()
    r=run(tmp_path,client);assert r.returncode==0,r.stderr
    assert len((tmp_path/"dispatches.jsonl").read_text().splitlines())==2
