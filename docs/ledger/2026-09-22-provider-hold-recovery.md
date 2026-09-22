# Provider hold: inactivity diagnosis and bounded recovery

The operator requested inspection, root-cause repair, implementation, deployment
and push after more than 24 hours without trades. Source: profile main bb5bcf5 /
installed 0.0.2.96; native main 60ea2b7 with 100 unrelated dirty paths preserved.

At 17:44:51 UTC, the last 24 hours contained 272 deferred model attempts, zero
completed market decisions, zero new decision receipts. Every deferral named
`provider_usage_limit_requires_explicit_resume`. Since the September 21 install,
four calls completed (three NOTHING, one expired short); 354 deferred. The durable
hold began September 21 at 11:13:27 UTC. Native accounts were flat/order-free and
AI, both cron jobs and replication were enabled. These were not 272 abstentions.

The existing provider exhaustion latch correctly avoids repeated quota failures
and requires explicit operator resume. However, native health read the fresh
`deferred` status without its quota reason and reported no degraded state. The
header reflected enabled jobs rather than the provider hold. Before checking the
hold, the worker also consumed fired wake conditions and built market charts and
briefings that could never reach the model. Resume left a recent learner quota
warning unchanged until its next run. Those are the supported defects.

Jev separately reached its previously authorized inference cutoff at 05:13:10 UTC
and recording cutoff at 06:13:10 UTC on September 22. Its absence is fail-open and
did not cause Hermes's hold. This repair does not extend that paid experiment.

## Change budget and protected behavior

- Profile worker: check a known hold before consuming triggers or constructing
  prompts/charts; record an explicit deferred, non-attempted call. Existing outbox
  delivery and native reconciliation still run first. Provider admission is still
  checked again under the shared model lock.
- Profile control: status says HELD, not ON, when provider access is held; explicit
  resume refreshes the learner's quota warning even if that status is recent.
- Native health: preserve decision/learner deferral reasons and mark provider
  holds degraded. The header becomes amber, labelled AI Needs Resume; clicking it
  uses the existing explicit resume control. Quota does not silently auto-retry.
- Native current-window text identifies provider access, rather than implying a
  new market decision is due. Localized strings retain the existing six columns.

Affected profile runtime files are the direct worker and control plugin, plus
release metadata, tests and this Rail. Native changes are the health evaluator,
existing AI control wrapper, main header/current-window presentation and existing
localization catalog, plus the compiled health harness. No indicator, executable
price check, intent submission, broker lifecycle, protection, replication, sizing,
model, cognition instruction, scheduler or account change. No NT restart.

The first supported operator resume needed elevated filesystem access to the
installed hold. The retry completed and restored AI ON. The next natural scheduled
review, cycle 20260922T1750Z, proposed an M2K long. Native evidence confirms master
fill 2913.1 at 17:51:56 UTC, structural stop 2911.1/target 2925.6, and follower
brackets for Sim102 quantity 2 and Sim103 quantity 5 (including partial fills).
The next naturally scheduled management review completed HOLD. This proves the
recovered decision/execution path, not profitability or optimal entry selection.

## Tests, installation and rollback

Focused tests cover held wake preservation, no briefing/model work, idempotent
deferral records, existing native delivery under a hold, explicit resume and
status recovery. The native executable harness covers quota/unreadable holds,
degraded JSON and recovery alongside existing failure/stall/data/session cases.
Run the full profile suite and full AddOn compile against installed NT references.

Publish only the scoped commits. Install the profile through the supported updater
and setup after a verified checkpoint; copy the complete AddOn through the global
deployment script. Preserve current native positions and management: installation
waits for a flat/order-free boundary, never forces a close. Verify source, remote,
installed hashes and loaded runtime separately. A copied C# file is not proof of
a newly loaded assembly. Keep all old and new runtime journals.

Rollback uses the verified pre-change profile/checkpoint and prior complete AddOn
file set with the same supported installation procedure. Restore only prior AI/job
states. Do not reset learning, accounts or trading epochs.

## Remaining measured limitations

Source validation completed: 841 profile tests passed, including seven new provider
recovery cases; 46 relevant native contract tests passed; the compiled native
health harness passed; all 86 AddOn/bridge source files compile against installed
NT references. An AST comparison found only `run_once` changed among 203 worker
functions. The model-facing guidance hash is unchanged. The complete runner hash
still advances release provenance to
`direct-v29-delivery-aware-cognition-3b5c95fb3b04`; do not mix it silently with the
prior `6bc6a44b2baa` runner in frozen evaluation.

The four pre-hold v96 decisions took a median 62.57 seconds and remained around
10.5k serialized characters despite the softer length target; the first recovered
entry took 104.09 seconds. Output latency still needs a frozen compact-contract
comparison. The quiet 24 hours cannot evaluate that change or Jev's effect on
trading because Hermes made no decisions. Do not weaken entry revalidation or
invent profitability from chart hindsight. Preserve the old frozen run as an
interrupted/unavailable interval, not a completed clean cognition experiment.

## Completed rollout and runtime proof

Published runtime commits: profile `568c73e24f3c71cf2c4ea4ce58c0e49f7e114348`
and Glitch `3df4e59c38aab0ff2448b06cc54b67d2283bcbc1`. Both canonical remote
main refs were independently verified. The 100 unrelated native worktree changes
remain untouched. Subsequent commits append this rollout evidence only.

After the naturally managed position closed and every native account was flat
and order-free, AI and both jobs were paused for installation. The verified
checkpoint contains 219 files / 487,730,739 bytes, including learner/intents,
configuration, prior frozen evidence, the installed profile and the complete
prior AddOn. Supported profile update and setup installed v0.0.2.97. All 35
managed profile files and all 95 copied AddOn files match canonical source.
No indicators changed. No native account or learner epoch was reset.

NinjaTrader compiled automatically after the supported full AddOn copy:
NinjaTrader.Custom.dll changed at 19:11:39 UTC. At 19:11:51 UTC, fresh native
health included the newly added learning-worker `deferral_reason` field, proving
the new evaluator loaded. The NinjaTrader process was not restarted. This is
assembly/runtime proof; visual appearance of the held button was not exercised
by artificially exhausting quota or injecting a live hold.

The new runner is frozen separately under `provider-recovery-20260922`.
AI, both original job definitions/enabled states, and replication were restored.
At 19:23:39 UTC, fresh installed cycles 1913, 1915, 1917, 1918, 1920 and 1922
had completed with matching new provenance and receipts. All six were actual
NOTHING decisions, rather than deferred calls. Native health reported `on` and
policy validation passed. These outcomes prove resumed processing, not decision
quality. The first installed result retained two nonblocking cognitive audit
warnings; this operational repair does not claim to solve those cognition issues.

Seven protected files remain byte-identical, including profile credentials,
model configuration, account groups/overrides, runtime policy, epoch and prior
freeze. The eighth, Configuration.v1.tsv, differs only in the encrypted license
row. The existing serializer generates a new encryption IV on save. Verification
through the production decoder under the signed-in Windows identity confirmed
identical decoded license values and every other row unchanged. No secret value
was emitted or added to evidence.

The recovered M2K trade was authored by the prior v96 profile before installing
this repair. Master Sim101 bought one at 2913.1 and a natural Hermes EXIT sold at
2918.4 at 18:28:03 UTC, with follower fills reconciled. Price PnL was +$26.50 on
the master and +$209.50 across the replication group. Commissions/external costs
are unverified, so this is not verified all-in net profit. This is one replicated
idea, not three independent observations, and establishes no profitability.

Local proof artifacts are under `D:/ab/artifacts/glitch-recovery/2026-09-22/`:
`diagnosis.json`, `checkpoint-manifest.json`, `deployment-installed.json`,
`native-installed.json`, `deployment-restored.json`,
`configuration-preservation.json` and `final-proof.json`.
