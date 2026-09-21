# Cost-disciplined Jev cognition: operator revision

On September 21 the operator replaced the unlimited-spend preference with an
economical testing mandate and proposed one-minute Jev sampling. The desired
business outcome is a small number of worthwhile trades, low drawdown and positive
results after all costs. $50/day and approximately $125-$150 on a nominal $25,000
account are evaluation targets, not forced trade counts, position-size instructions,
guaranteed daily returns or new live profit-taking rules.

## Immediate resolved change

Use the installed v0.0.2.95 observer's existing `--cadence-seconds 60` setting for
the same three native SIM contracts. Stop only the old observer through its STOP
contract, preserve the journal and old launch/health evidence, then launch one new
process. Retain the September 22 05:13:10 UTC inference cutoff and 06:13:10 UTC
recording cutoff; do not renew the test duration. No source/profile install,
NinjaTrader restart, AI/jobs change, epoch reset or native trading change is needed.

The previous 15-second phase ends at the operator-requested transition. It must
not be described as a completed 24-hour baseline. The new process epoch is a
separate cadence segment under the same frozen questions, state and cognition
bundle. Keep the GHP-004 freeze, but analyze prediction/availability/cost results
by observer epoch and cadence. Do not combine the segments as one unchanged trial.

This reduces the maximum request rate from 720 to 180 per hour. At the previously
measured mean input payload and TypeSafe's $0.042/M input rate, the maximum projects
about $1.64/day or $49.27 per 30 continuous days; closed/stale periods can reduce
actual usage. This is token-based estimation, excludes unknown timeout billing,
and is not a provider invoice. Financial/call caps remain explicitly disabled for
the already bounded test; the lower cadence controls spend. No new paid model
replay is part of this adjustment.

Keep the existing 30-second advisory freshness check. One-minute per-contract
sampling and staggered requests mean fewer instruments may have valid advice at
any particular Hermes invocation. That limitation is explicit. Expired advice
remains unavailable; Hermes continues from its current native evidence without
waiting. Do not disguise old evidence as fresh or widen expiry merely to improve
coverage. Record natural consumed and unavailable contexts after the transition.

## Where Luna calls actually occur

At 05:44 UTC, the operator attempts since 03:24 comprised 64 Luna attempts: 21
scheduled, 21 condition-change, 16 condition-followup, five entry-range
supersessions and one failed attempt without a completed invocation reason.
Scheduled calls produced 20 NOTHING and one ENTER_LONG; condition changes produced
18 NOTHING and three ENTER_SHORT; followups produced 15 NOTHING and one ENTER_LONG;
all five supersessions produced NOTHING. These are authored decisions, not claims
of native fills or a count of separate learner inferences. The minute cron is a
dispatcher, not one Luna inference per minute.

The five authored entry receipts were then checked directly. Every one was
`not_posted`, with `entry_range_superseded` / `latest_price_outside_entry_range`.
The source packet was 76.151 to 168.580 seconds old at that delivery check. All five
still had `geometry_valid: true`; four movements were targetward and one was a
better price outside the authored range. This does not prove those missed trades
would have won. It identifies a concrete latency/range-validity problem: the
author's allowed entry location expired before delivery. Preserve the firewall;
focus the next GHP-007 workload/contract design on shorter decisions and entry
conditions that remain coherent through actual delivery latency. Do not widen
ranges mechanically, loosen protection or infer a profitable counterfactual fill.

Removing every followup would remove at least one observed entry proposal. These
counts alone cannot value missed fills or avoided losses. Preserve positioned
minute management, scheduled fallback, operator directives and existing price wakes
for this adjustment. Replacing the price-wake/followup seam with Jev evidence needs
a separately frozen comparison of saved calls against missed opportunities and
management latency; a probability cutoff would otherwise become an unvalidated
trading gate. Nothing here changes that authority.

The account usage read showed 8% remaining in the general Codex weekly bucket and
97% in its Luna reserve. These account-wide counters do not attribute usage to this
task, the research calls or the installed Hermes worker.

## Learning and economic acceptance

Jev's model weights do not learn from this account. Improve question/state design
and calibrate predictions against causal outcomes. Separate regime description,
future endpoints and original-target-before-stop probability. Confidence thresholds
are not the final product: persistence, calibration, economic path geometry and
Hermes interpretation each need evaluation. A Jev threshold must not silently
authorize entries or exits. Native execution/protection/reconciliation stays Glitch's
responsibility; Hermes continues to own trade selection and management.

Use actual average realized win, average realized loss and costs, deducting each
cost only once. At 67% winners,
an average win half the average loss produces only 0.005 loss-units per trade before
costs. Nominal account size is not the available loss buffer. Assess the configured
drawdown buffer, loss clustering, MFE/giveback, missed favorable excursion and
withdrawable economics separately. Replicated fills remain one underlying trading
idea for statistical evidence. Never force an early entry, widen risk or exit an
intact thesis solely to reach a daily quota.

The next architecture target is one coordinated observation/review pipeline:
minute evidence from Jev; a concise horizon-matched interpretation for Hermes;
explicit Hermes decisions grounded in current price, stop/path geometry and native
position; Glitch execution; attributed outcomes for frozen evaluation. The current
offline briefing candidate has not earned promotion. The cost-adjusted baseline
and observed wake/latency failures decide the next minimal change.

Official reference: [TypeSafe models and customization](https://docs.typesafe.ai/models).

## Runtime verification

The old observer stopped cooperatively and its STOP marker, final health and
latest evidence were preserved. The 60-second observer started at 05:50:01 UTC,
PID 27800, epoch `2026-09-21T055001582847Z-897ad9c951f8`. Its shortened recording
duration is 87,789 seconds, retaining the original deadline. No installed source
file changed and no pause/restart of Hermes or NinjaTrader occurred.

Eight protected configuration/authentication/epoch/policy/replication/freeze hashes
matched afterward. Job names, enabled states, schedules and prompts also matched;
the running scheduler naturally updated jobs-file metadata. The first repeated
request reservations were at least 60.13 seconds apart for MNQ and 60.02 seconds
for MES; M2K's stale periods produced longer gaps. Provider wire-start intervals
are not the scheduler metric because child-process initialization varies.

Initial new-phase responses included deadline failures and unavailable advice;
these remained excluded by the unchanged two-second deadline and 30-second consumer
freshness. Neither lower sampling nor this short observation establishes a forecast
or economic improvement. The existing follow-up was updated to assess both cadence
segments separately and preserve the operator's new spending constraint.

Evidence is under `D:/ab/artifacts/glitch-jev-research/2026-09-21/jev-economy-v1`:
`before-and-protocol.json`, `launch-protocol.json`, `runtime-verification.json`,
`cadence-proof.json`, timestamped live checks and `entry-delivery-diagnosis.json`
with copied native receipts and exact authored decisions. Ledger validation and
diff checks suffice for this existing runtime-option change; no trading source
or test behavior was changed.
