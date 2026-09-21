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
