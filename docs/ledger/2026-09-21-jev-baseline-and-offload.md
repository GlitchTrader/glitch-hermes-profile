# Frozen Jev SIM baseline and offline Hermes workload comparison

The operator approved a longer real SIM test and an offline context/skill redesign
on September 21, then explicitly removed Jev monetary and call limits. This does
not change trading authority or authorize deployment of the redesigned cognition.

## Resolved scope

Deploy v0.0.2.95 with an explicit EVIDENCE-only `--unlimited-inference` opt-in.
Default modes and finite budgets remain unchanged. Uncapped monetary/call admission
requires a bounded recording duration and an absolute UTC inference cutoff. Record
the selected limits in the journal and health file; reserve accounting is not a
provider invoice. Preserve the single provider slot, cadence, 2-second deadline,
freshness/identity validation, append-only evidence and STOP behavior.

The baseline runs the existing eight questions and existing Hermes instructions
for 24 hours, then records one additional hour for final forward labels. Use a
3-GB total journal bound, including previous evidence; the local C drive had about
58 GB free before activation. No old evidence is deleted. The observer change
produces a new bundle hash because it is already included in the cognition manifest;
the direct prompt, SOUL and trading skills remain byte-identical. Freeze the new
baseline through GHP-004, checkpoint/install using the supported procedure, and
restore the prior AI/jobs state. The learner may retain observations but cannot
activate a new prompt during an unevaluated freeze.

The native NinjaTrader checkout and installed AddOn/indicators remain unchanged.
There is no new entry, exit, wake, rank, sizing or veto authority.

## Resource and cost evidence

The completed short trial made 120 calls: 102 valid, 2 malformed and 16 timed out.
The 104 responses with usage reported 941,410 input tokens, costing $0.03953922 at
the verified $0.042/M input-token rate; outputs are free. Unknown timeout billing
is excluded from that measured subtotal. At the configured maximum 720 calls/hour,
the observed mean payload projects about $0.274/hour or $6.57/day. This is a Jev-only
estimate, not a provider invoice or a guarantee for larger position contexts.

The current GHP-004 freezer materializes large JSONL evidence several times. Change
only its freeze-time reading to a streaming iterator, preserving strict validation,
hashes and copied bytes. Other evaluator callers keep the existing list interface.
This makes a real cognition freeze practical without loading the full 266-MB
decision ledger into Python objects at once.

## Offline candidate and comparison

Use two exact saved user prompts from the original trial, selected by source time
and invocation mode: scheduled cycle 20260921T0325Z and condition-change cycle
20260921T0327Z. Extract them with indexed, read-only queries from Hermes state; do
not scan or copy the 6.9-GB database. These are development cases, not holdout proof.

Prepare a concise, research-only skill that treats Jev as a provisional market
interpretation, reconciles disagreement, distinguishes forecast events/horizons,
and keeps price/geometry/native position facts authoritative. Build a deterministic
compact briefing without selecting instruments or acting on probability thresholds.
Keep current prices, timestamps, economics, spread, structure, position/protection,
original thesis, configured limits and required output contracts. Record omitted
or reorganized fields explicitly; retain each original prompt for audit. The first
candidate shares timeframe field names in tables and round-trips every original
value exactly. Across these cases it reduces total prompt characters by only
3.2%, including the added guidance; this alone does not justify promotion.

Use four paired arms so instruction effects are not mistaken for compression:

1. Exact current user prompt and existing skills.
2. Current context plus the candidate interpretation guidance.
3. Compact context plus that guidance and the same Jev probabilities.
4. The identical compact/guided context with Jev unavailable.

One isolated offline Hermes process at a time may produce research responses. It
has an empty toolset, no native control plugin, no live exchange output, and its
own local session directory. No response becomes an intent or enters a learner.
Preserve model/settings across arms, rotate arm order across cases, retain failures
without selective retry, and report latency, input/output size, contract validity,
actions and agreement. Decision differences on these cases are observations;
counterfactual native fills, management benefit and profitability are not inferred.
Full live position-management acceptance requires later naturally positioned cases.
The original chart files for these two cases are no longer retained. Every arm is
therefore text-only with the same explicit missing-chart notice. This is a paired
text comparison, not an exact replay of the original multimodal invocation.

The prior active freeze points to v0.0.2.70 (`v70-asia-20260906`), not the current
cognition. Preserve that manifest and both pointers before activating the new
freeze. Superseding its active pointer does not mark the older experiment scored
or completed and does not delete its evidence.

The new briefing and interpretation skill stay under `research/jev`, outside the
installed skill root and cognitive bundle. No candidate is promoted during this
baseline. The 24-hour test establishes operational and initial predictive evidence;
GHP-004's existing longer-sample release criteria remain in force.

Official price/context reference: [Jev models](https://docs.typesafe.ai/models).

## Installation and prospective activation proof

Implementation commit `ad7af218b68fb4ee8f5adef127df010a824c15cd` passed 821 tests
and was published to canonical main. Supported profile update/setup installed
v0.0.2.95 with 35/35 matching owned hashes. Fourteen cognition files, including
the direct worker, SOUL, all trading skills and the Jev state/questions/provider,
remain byte-identical to the prior installation. The verified streaming checkpoint
contains 121 files / 474,085,441 bytes. Configuration, authentication, epoch, policy,
account groups/overrides and replication settings retained their original hashes;
both original jobs and AI were restored enabled. NinjaTrader was not restarted.

The new GHP-004 freeze is `jev-baseline-20260921`, created at 05:11:14 UTC, with
cognition `direct-v28-jev-advisory-evidence-f45f1499f9ac` and manifest hash
`915850b48a6211b66e05c08dd3d89a2d185b2ea77c810111976bc469e03f9b62`.
Its four-tick evaluation cost policy remains an explicit assumption, not verified
native commission evidence. The previous v70 freeze and pointers were preserved.

The new observer started at 05:13:11 UTC, PID 29360, process epoch
`2026-09-21T051311492468Z-4f55a9b708ec`. Its recorded cutoff is September 22 at
05:13:10 UTC for inference and 06:13:10 UTC for recording. Health confirms the
monetary/call caps are disabled by the operator. The fixed 15-second per-contract
cadence, one provider process, two-second deadline, freshness, STOP and 3-GB total
disk bound remain. At 05:22 UTC, 77 requests had produced 76 valid and one malformed
response; 18 otherwise valid results were superseded. Metered input cost was
$0.028890792, roughly $4.65/day at that initial realized rate versus $6.57/day at
the configured maximum with the earlier mean payload. Neither is an invoice.

Natural cycles `20260921T0519Z`, `20260921T0520Z` and `20260921T0521Z` consumed
matching request/state hashes and returned model `jev-1.13.0`, then completed as
NOTHING with successful native receipts. This proves installed consumption and
fallback integrity, not entry or management benefit. At the resource check the
observer used 26.8 MB working memory and NinjaTrader remained responsive at 954 MB.

Operational evidence is under
`D:/ab/artifacts/glitch-jev-research/2026-09-21/jev-baseline-24h`: launch protocol,
checkpoint manifest, installed verification, restored runtime proof, preserved old
freeze, natural-cycle artifacts and timestamped live checks. The task follow-up
`review-frozen-jev-baseline` is scheduled after the recording tail; it may assess
results but cannot renew inference, alter cognition or promote authority.

## Completed offline development comparison

The operator explicitly approved eight calls after automatic approval review
requested confirmation of the saved-data transfer. Eight initial local credential
failures made zero model calls and are preserved separately. The supported generic
global-auth fallback did not work for this installed Codex route; only its existing
OpenAI provider record was supplied to the isolated home. No other provider or
broker credential was copied. All eight actual model calls then completed without
retry. Their inputs were unchanged from the frozen variants. The temporary
isolated provider credential was removed after the completed comparison.

| Arm | Scheduled case seconds | Trigger case seconds | Mean seconds | Actions |
| --- | ---: | ---: | ---: | --- |
| Current | 58.703 | 37.141 | 47.922 | NOTHING / NOTHING |
| Added interpretation guidance | 87.062 | 39.594 | 63.328 | NOTHING / NOTHING |
| Compact briefing with Jev | 63.781 | 58.625 | 61.203 | NOTHING / NOTHING |
| Compact briefing without Jev | 66.344 | 57.188 | 61.766 | NOTHING / NOTHING |

All eight parsed and passed the worker's pure normalization/wire checks without a
model repair. Every trigger arm retained the same non-blocking
`selection_ev_numeric_invalid:0:trigger_review` diagnostic; it is not a difference
introduced by the candidate. These checks do not establish native order eligibility
and no offline result was delivered. The original chart attachment was unavailable
in every arm. Model/provider latency and caching were uncontrolled across this tiny
sample; the timing difference is descriptive, not a statistical performance claim.

The compact-with-Jev arm explicitly reconciled Jev in both audits. It distinguished
endpoint probability from target-first odds and identified MES advice as irrelevant
to an M2K-specific trigger. Current did so in one audit; added guidance alone did
not name it in either. Naming Jev is not proof of better cognition. All actions
agreed, no position-management case was tested, and the candidate reduced total
prompt characters by only 3.2% while taking longer here. Do not promote it.

The first reporter read `intents` instead of the actual batch `decisions` field.
The canonical report helper and a regression test correct this metadata defect;
no inference changed or was rerun. Original output records remain intact, and
`hermes-offload-v1/assessment.json` reconstructs authoritative actions from all eight
saved responses with a hash-checked copy of the actual worker validation path.
The correction passed seven focused research tests. The current live briefing and
interpretation rules remain unchanged for the frozen baseline. A useful next
candidate must reduce redundant interpretation work, not merely repeat fewer JSON
keys; evaluate that separately after these prospective outcomes are available.
