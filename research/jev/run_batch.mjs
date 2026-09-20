// Explicit offline jobs only. No runtime/market loop, retries or promotion.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const [directory,clientFile]=process.argv.slice(2);
assert(directory&&clientFile, 'Supply a frozen study directory and audited provider client');
const dir=await fs.realpath(directory);
assert(!dir.toLowerCase().includes('glitchdata'), 'Research output must be outside native data');
// Concurrent invocations must not race past the durable dispatch journal.
// A crash leaves this guard for explicit local inspection; never steal a lock.
const lockPath=path.join(dir,'RUNNING.lock');
const lock=await fs.open(lockPath,'wx');
await lock.writeFile(JSON.stringify({pid:process.pid,started_utc:new Date().toISOString()}));
try {
const read=async name=>{try{return (await fs.readFile(path.join(dir,name),'utf8')).trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);}catch(e){if(e.code==='ENOENT')return [];throw e;}};
const manifest=JSON.parse(await fs.readFile(path.join(dir,'batch.json'),'utf8'));
assert.equal(manifest.model,'jev-1.13.0');
assert.equal(manifest.influence,'none');
assert.equal(hash(await fs.readFile(clientFile)),manifest.provider_client_sha256);
assert.equal(hash(await fs.readFile(path.join(dir,'jobs.jsonl'))),manifest.jobs_sha256);
assert.equal(hash(await fs.readFile(manifest.protocol_path)),manifest.protocol_sha256);
assert(manifest.max_calls>0&&manifest.max_calls<=5500&&manifest.max_usd>0&&manifest.max_usd<=1.5);
const {infer}=await import(pathToFileURL(clientFile));
const jobs=await read('jobs.jsonl'),dispatches=await read('dispatches.jsonl'),previous=await read('responses.jsonl');
assert.equal(new Set(jobs.map(j=>j.id)).size,jobs.length);
assert.equal(new Set(dispatches.map(j=>j.id)).size,dispatches.length);
assert.equal(new Set(previous.map(j=>j.id)).size,previous.length);
const jobmap=new Map(jobs.map(j=>[j.id,j]));
for(const j of jobs){
  assert.equal(j.wire_hash,hash(JSON.stringify({model:manifest.model,state:j.state,questions:j.questions})));
  assert(Buffer.byteLength(JSON.stringify(j.state))<49152);
  assert(Buffer.byteLength(JSON.stringify({model:manifest.model,state:j.state,questions:j.questions}))<65536);
}
const done=new Set(dispatches.map(j=>j.id));
for(const d of dispatches)assert.equal(d.wire_hash,jobmap.get(d.id)?.wire_hash);
for(const p of previous)assert(done.has(p.id)&&p.wire_hash===jobmap.get(p.id)?.wire_hash);
let calls=dispatches.length,completed=previous.length,index=0,reserved=0,failures=0,workerErrors=0,halt=false;
const cost=r=>Number.isInteger(r.response?.usage?.input_tokens)&&r.response.usage.input_tokens>=0?r.response.usage.input_tokens*.042/1e6:.03;
let charged=previous.reduce((a,r)=>a+cost(r),0)+.03*(calls-completed);
// One writer serializes journal lines even while independent calls are in flight.
let writes=Promise.resolve();
const append=(name,value)=>writes=writes.then(async()=>{
  const file=await fs.open(path.join(dir,name),'a');
  try {await file.writeFile(JSON.stringify(value)+'\n');await file.sync();} finally {await file.close();}
});
await Promise.all(Array.from({length:4},async()=>{
  try {
  while(index<jobs.length&&!halt){
    const j=jobs[index++];if(done.has(j.id))continue;
    if(calls>=manifest.max_calls||charged+reserved+.03>manifest.max_usd){halt=true;break;}
    calls++;reserved+=.03;
    await append('dispatches.jsonl',{id:j.id,wire_hash:j.wire_hash,reserve_usd:.03,utc:new Date().toISOString()});
    const r=await infer('typesafe',j.state,j.questions,{observation_id:j.anchor,state_schema:j.state.schema,timeout_ms:10000});
    const {state,questions,...meta}=j;Object.assign(r,meta,{protocol_hash:manifest.protocol_sha256,influenced:false});
    if(r.http_status===200&&r.returned_model!==manifest.model)halt=true;
    failures=['request_error','http_error'].includes(r.status)?failures+1:0;
    if(failures>=5)halt=true;
    charged+=cost(r);reserved-=.03;
    await append('responses.jsonl',r);completed++;
    if(completed%100===0)console.log(JSON.stringify({completed,calls,accounted_usd:charged,halt}));
  }
  } catch {halt=true;workerErrors++;} // Keep the lock until every in-flight worker settles.
}));
await writes;
const summary={completed,calls,planned:jobs.length,accounted_usd:charged+reserved,worker_errors:workerErrors,halt,finished_utc:new Date().toISOString(),runner_sha256:hash(await fs.readFile(new URL(import.meta.url)))};
await fs.writeFile(path.join(dir,`run-${Date.now()}.json`),JSON.stringify(summary,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(summary));
if(workerErrors)throw new Error('research_batch_worker_failed');
} finally {await lock.close();await fs.unlink(lockPath);}
