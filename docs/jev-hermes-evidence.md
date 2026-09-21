# GHP-006: explicit Jev evidence for Hermes in SIM

The operator authorized implementation on 2026-09-21: classify regime, estimate
continuation/reversal and future direction, and feed that information to Hermes.
This selects Level 2 advisory evidence for a bounded SIM experiment. It does not
select wake, entry, exit, reversal, sizing, bracket or veto authority for Jev.
The earlier question studies remain development evidence; their weak forecast
results and uncertain thesis-replay benefit are not overwritten by this decision.

## Resolved implementation

Extend the existing independently bounded recorder with an explicitly selected
EVIDENCE mode. OFF, RECORD_ONLY and the original SHADOW experiment preserve their
contracts. One provider process at a time serves an explicit list of full native
contracts in deterministic rotation, no more than once per contract per 15 seconds.
No request runs inside Hermes, market publication, execution or reconciliation.
The two-second deadline, latest-input supersession, durable reservations, no retry,
model pin, disk/call/time limits and independent STOP remain in force.

The new frozen question bundle asks independent Choice questions over compact
hybrid state: current regime, 15/30/60-minute UP/DOWN/FLAT endpoints, 15-minute
continuation/reversal/rotation relative to the observed signed 15-minute move,
move maturity, price/flow acceptance, and original position-thesis state. An
unknown/no-direction outcome is available where the premise cannot be established.
Endpoint neutral bands are explicit mathematical label definitions, not order
levels. A green endpoint is not target-before-stop probability. Confidence is
distribution concentration, not demonstrated trading accuracy. No learned model
is exported and no raw probability threshold selects a trade or suppresses Hermes.

Raw native cache bytes remain in the existing append-only journal. Provider state
uses allowlisted market fields, code-computed relations, compact cross-market
context and, when attributable, the original Hermes thesis. Native contract,
position identity, original entry, current protection and timestamps bind position
context. Account names, broker credentials and native order IDs stay local.
Position notes are data, never instructions to the provider. Missing flow remains
missing. Sparse M2K publication stays explicitly ineligible when stale; changing a
timestamp or raising the freshness limit is not a repair.

The observer publishes an atomic latest evidence file. On an already-admitted SIM
review, Hermes reads it once without waiting, verifies provider/model/question
identity, current contract/position, fresh process health and a maximum 30-second
source age, and receives only validated structured answers. Canonical minute
packets and native portfolio state remain authoritative; newer advisory observation
times and anchors are shown separately. Missing, malformed, expired, stopped or
out-of-scope evidence produces an unavailable result with no admission effect.
The exact consumed context is persisted by cycle, and model attempts link the
prediction/request IDs. Inclusion in a prompt is recorded separately from an
unprovable claim that it caused the final choice.

Hermes must reconcile the advisory with current native facts and its own thesis,
including disagreement, in its existing reasoning fields. The outputs are
correlated interpretations of shared market evidence, not independent votes to
multiply or average. They cannot replace the authored original-bracket forecast.
No added response field or native intent schema is required.

## Scope, defects and proof

Canonical owner is `glitch-hermes-profile/main`. Changes belong in the observer,
typed provider contract, a small shared evidence module, the existing prompt
assembly/attempt provenance, focused tests, profile packaging and Rail docs.
GHP-006 explicitly supplies the probabilistic layer outside GHP-001 deterministic
perception. GHP-003/004 execution and learning boundaries remain. Missing active
Rail claims are repaired with current ownership, not invented historical dates.
The TypeSafe selected-choice contract remains strict; only floating-point equality
noise at a tied maximum is tolerated. Historical sealed responses are unchanged.

The observed stale-entry receipts are correct executions of the authored contract.
They do not justify silently widening entry ranges, forcing trades or changing
the five-minute flat/minute-positioned schedule. Those timing observations remain
an evaluation dimension for this iteration. No NT source, indicator, workspace,
account, replication or native protection change belongs to this implementation.

Tests cover conditional thesis attribution, exact numerical label anchors,
neutral/missing state, full distributions, version/contract/position mismatch,
malformed/late results, provider failure, process crash, STOP, bounded rotation,
duplicate observations, reserve exhaustion, source-age expiry, prompt inclusion,
attempt linkage, and the unchanged no-wake/no-native-action path. Run focused tests
then the relevant full profile suite with numerical-library thread counts bounded.
The offline scorer must keep the old and new question/state epochs separate.

Before installation, checkpoint current cognition, learner/epoch evidence and
AI/jobs/configuration; briefly pause AI through its supported control, update the
published profile through Hermes, run installed setup, verify all owned hashes,
and restore the prior AI/jobs state. No NT restart. Initial activation is a bounded
single-worker SIM trial followed by continued recording for future labels. Verify
one naturally admitted Hermes call consumed the exact fresh advisory. This proves
the connection, not predictive value; future 15/30/60-minute labels and false-exit
costs remain necessary for effectiveness claims.

Rollback: create the observer STOP file or let the budget/duration expire. Freshness
and health checks remove evidence automatically while existing Hermes continues.
Revert the profile through supported update if source rollback is needed, preserving
all journals and native state. No automatic authority promotion or recurring
activation is installed.

## Initial bounded operating protocol

After source, installed hashes and native SIM scope are verified, launch the
installed `scripts/run-jev-shadow.py` with `--mode EVIDENCE`, `--contracts
"MNQ 12-26" "MES 12-26" "M2K 12-26"`, `--account Sim101`,
`--cadence-seconds 15`, `--max-calls 120`, `--max-usd 4`,
`--duration-seconds 4500` and `--max-disk-mb 128`. Contract names must still match
the current native packet at launch. Read the key through the existing private
environment file; never include its content in a command, report or journal.
The reserve is a conservative admission bound, not a billing estimate. After
120 calls (at most $3.60 reserved), recording continues to the duration/disk bound
to preserve future 15/30/60-minute labels. No request budget replenishes itself.

Persist the exact source and question hashes, arguments and pre-trial runtime
checkpoint before activation. Use one hidden worker and no parallel research
jobs. Keep the previous recorder journal, stop its own process gracefully before
launch, and check that the current journal plus expected captures fits the disk
bound. Stop the observer immediately if publication or consumer contracts fail;
Hermes continues its existing admitted reviews without the evidence. Extend the
trial only as a separately recorded frozen run, not by changing this evaluation
interval or tuning probabilities against its outcomes.

Official references: [Choice semantics](https://docs.typesafe.ai/primitives/choice),
[shared state and independent questions](https://docs.typesafe.ai/concepts/state),
[HTTP API](https://docs.typesafe.ai/api), and
[typed verification with a reasoning model](https://docs.typesafe.ai/cookbooks/sde_cascade).
The latter informs decomposition, not a copied trading threshold or strategy.
