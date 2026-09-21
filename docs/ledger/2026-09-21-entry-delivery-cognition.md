# Entry-delivery cognition repair — September 21

The operator requested investigation, improvement and deployment after seeing
directional MNQ/MES/M2K movement with a flat SIM book. This authorizes a bounded
cognition repair, not a new strategy or a mandatory entry.

## Evidence and scope

At 10:36:47 UTC, today's model-attempt/outbox/receipt join contained 239 completed
decisions: 229 NOTHING and ten entries (six long, four short). All ten entries were
superseded before native submission because the newest executable price was outside
their authored range. There were also two non-completed attempt records. These
counts span today's earlier cognition versions, not just the current frozen epoch.

Median attempt durations were 72.42 seconds for scheduled scans, 63.85 for condition
followups and 50.33 for trigger reviews. Median serialized decision sizes were
10,913.5, 11,221 and 6,789 characters respectively. Attempt duration includes worker
processing; output size alone does not establish the cause of every second.

Example: the 06:47 MNQ long selected reference 30129, stop 30116.75, target 30159.25
and range 30127.5–30129. The chosen failure boundary was 30117. One tick of stop
clearance at the reference left no higher-fill allowance. The 152.50-second attempt
was checked at 30133.5 and correctly expired. Its prose initially proposed a higher
edge whose translated stop equaled failure, then narrowed the issued range. A
separate later entry described equality as strict clearance. Code must not widen
either issued order to make it executable.

Recent NOTHING audits repeatedly rejected fresh highs because no higher target was
"supplied", despite available trend/leg/volatility facts and existing instructions
allowing uncertain extension hypotheses. This demonstrates a reasoning-contract
problem; the subsequent rally alone does not prove a particular wager had edge.

Evidence: `D:/ab/artifacts/glitch-entry-delivery/2026-09-21/diagnosis.json`, joined
from immutable packet IDs, model attempts, outboxes and receipts. Native portfolio
state was flat/order-free and current-session P&L zero during investigation.

## Bounded change

- Existing geometry context explicitly identifies observed buy ask/sell bid, their
  provenance and the strict worst-fill stop relations. Invalid/crossed quotes stay
  unavailable; the native decision reference is unchanged.
- Hermes constructs the supported execution zone and structural stop offset
  together, then reassesses risk and value. No minimum width, stop distance or
  probability is prescribed. Existing execution revalidation remains byte-for-byte.
- Flat/trigger records target 6,000/4,000 characters with every required candidate,
  field and number retained. The target never truncates or rejects a response.
  Selected calculations appear once; management's output contract remains.
- At unmapped extremes, assess projected continuation using an observed anchor and
  distance basis. Absence of a mapped level is not by itself contrary evidence.
  A projection does not require an entry or promise room.

Diff budget: the direct worker's geometry evidence/output instruction/version;
SOUL, build-intent and market-scan wording; focused tests; release manifest/version,
README and this Rail record. No native AddOn/indicator, provider/model, Jev bundle,
inference cadence, admission, quantity, protection, replication or sizing change.

## Validation and rollout

Run regression coverage for geometry, full comparisons, delivery expiry, idempotent
receipts, management, Jev fallback and the full profile suite. A supported profile
update follows a verified streaming checkpoint and a bounded AI/job pause while
flat/order-free. Preserve authentication, policy, replication, learner evidence and
the prior AI/job state. Do not restart NinjaTrader.

The user-requested repair ends the old cognition baseline early. Preserve its frozen
manifest and records; do not call it a completed 24-hour run or mix its decisions
with the new prompt version. Start a separate prospective cognition checkpoint.
Jev's model/questions/cadence and original inference cutoff remain unchanged.

Fresh scheduled attempts and native receipts prove installation/use, not positive
expectancy. Report output length, elapsed time, proposed entries and expiration
separately. No additional paid offline comparison calls are part of this repair.

Rollback uses the supported profile updater with the verified pre-change profile
checkpoint, followed by setup/parity and restoration of the saved AI/job state.
Keep new journals; do not reset any trading epoch or account.

## Source proof

All 834 profile tests passed, including 12 new quote/contract regression cases.
An AST comparison against the prior canonical worker confirmed that 201 functions
are unchanged; only `deterministic_geometry_context` and `build_prompt` changed.
The prompt revision is separately versioned. No provider call was used in testing.
