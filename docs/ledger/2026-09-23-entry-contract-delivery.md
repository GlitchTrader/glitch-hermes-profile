# September 23: live trading and entry contract delays

Operator request: investigate infrequent, unprofitable trading and improve it.
Source and installed baseline: v0.0.2.97 / main a6dfa21. Preserve the pre-existing
bounded Jev review document and its ledger changes, plus 100 unrelated native
worktree changes. This work continues GHP-008's delivery diagnosis.

At 08:21 UTC, the window from September 22 17:44 UTC contains 451 completed
decisions: 376 NOTHING, 47 HOLD, 26 proposed entries and two managed EXITs.
Twenty entries expired in profile price revalidation; three more expired at the
native check. Three filled. The current worker is healthy, without a quota hold.
Median decision duration is 52.04 seconds; entry duration is 75.13 seconds.
Twelve of 26 entries needed a second model call. Their median duration is 96.02
seconds, versus 61.71 without repair. These are descriptive delivery findings,
not proof that an earlier fill would have won.

Indexed read-only Hermes session joins recover original responses and their
correction prompts. Nine repairs named missing latency evidence. Seven of those
responses already explicitly described delivery/transport uncertainty; the
validator only recognized the literal substrings latency/delay. Four responses
also placed authored entry fields at batch level despite a sole, explicit entry
decision. Two further placement errors involved an empty
decision_level_wake_triggers alias. No new market reasoning is necessary to move
unambiguous values to their documented location. Conflicts must remain invalid.

## Change budget

- Direct worker: recognize explicit delivery/transport uncertainty as latency
  evidence; retain all five required geometry dimensions and reject bare spread
  or general uncertainty as a substitute. Normalize misplaced authored entry
  fields only for one unambiguous, self-consistent entry decision. Preserve every
  value; reject conflicts, instrument disagreement and multiple decisions.
- Direct prompt/build-intent skill: make decision-versus-batch nesting explicit
  and align the skill's comparison example to the current canonical fields.
- Focused tests: regression and negative cases, followed by full profile suite.
  Replay saved original responses offline through both validators without model
  calls or intent submission. Count avoided repair calls, not hypothetical PnL.
- Release metadata, this report and scoped GHP-008/source-authority evidence.

Protected: selected action, instrument, quantity, probability, stop/target/range,
all native/execution/freshness checks, cadence, provider, Jev cutoff, risk,
replication, positions, credentials, learner evidence and epoch. No new trading
threshold, forecast, strategy, paid inference renewal or NinjaTrader change.
Rollback restores the prior package via the supported updater after a verified
checkpoint and restores only the prior AI/job state.

The three realized trades and subsequent price paths are assessed separately;
this small sample does not justify calibrating a new trading rule. The completed
Jev endpoint trial also does not support promoting its current probabilities.

## Trade evidence and limits

| Entry cycle | Profile | Master price PnL | Evidence |
|---|---|---:|---|
| Sep 22 17:50, M2K long | v96 recovery | +$26.50 | Sampled peak +$49; completed post-entry bars reached 2923.3, below the 2925.6 target. Managed exit at 2918.4; the next 60 minutes' completed bars reached only 2919.7. Material giveback occurred, but those bars do not demonstrate an intact move was prematurely abandoned. |
| Sep 23 06:38, M2K long | v97 | -$2.50 | Sampled MFE +$5; completed-bar high 2914.2 versus native target 2915.3. Managed exit 2912.5; post-exit completed bars crossed the original 2911.0 stop at 07:01 without first reaching the target. |
| Sep 23 07:13, MNQ long | v97 | -$15.00 | Stopped after 3m54s; sampled MFE +$1.50, completed-bar high 31048.25. The entry bought recovery in a declining 15m path with a 7.25-point stop versus 7.97-point 1m ATR. The next 60 minutes never reached the original 31066.25 target. |

The two v97 master trades lost $17.50 in price PnL. Native TradeLedger records
$1.10 MNQ commission, producing -$18.60 after recorded commissions. The replication
group totals -$146.80 after recorded commissions. M2K commissions are recorded as
zero; that is not proof of zero external cost. One replicated idea counts once.
The earlier v96 recovery winner is kept separate from v97's results.

The MNQ case is compatible with an entry-location/local-noise problem; one stop
does not establish an ATR floor or a failing strategy class. M2K's entry text
claimed a 2911.1 stop cleared an observed 2910.8 adverse extreme, an explicit
geometry inconsistency. That stop was not the actual exit cause. These are
cognition weaknesses to measure, not retrospective rules to force through the
firewall. Neither loser had a material earned run that plainly required a fast
profit capture. The M2K exit reduced loss compared with reaching the unchanged
stop, although minute data cannot prove an executable counterfactual fill.

Bar analysis excludes entry/exit minutes, deduplicates completed bars and reports
missing coverage. It does not interpolate sub-minute paths or assume intrabar
barrier order. `trade-paths.json` preserves native ledger rows and these limits.

## Offline proof

`repair-replay.json` joins 22 original/correction session pairs to their original
packets. The old validator reproduces each original contract error. The candidate
accepts 12 first responses without a second model call: seven explicit
delivery/transport uncertainty cases, four unique entry-field placement cases and
one empty wake-alias case. Every original action, instrument, price, quantity,
forecast and confidence is preserved. All ten remaining incomplete/conflicting
cases still require correction. Two recovered first responses belonged to cycles
that subsequently failed under v97's model repair.

The avoided corrections consumed 472.149 seconds in the observed run. This is
measured repair duration, not a claim that earlier delivery would have filled or
earned money. The replay made no model/provider or native calls. AST comparison
confirms only three worker functions changed (`normalize_batch`,
`validate_entry_geometry_evidence`, `build_prompt`); 200 remain identical.

Source validation passed 105 focused tests and the full 872-test profile suite.
Negative cases cover missing evidence, conflicting/nested/type-disagreeing entry
values, ambiguous ownership, nonempty wake aliases, quantity, range, forecast and
off-tick prices. A mocked invocation proves the combined observed shape/language
defect completes with one model response and unchanged execution values.
`git diff --check` passed. No native source or installed code was changed during
the investigation. Installation and forward runtime evidence are recorded below
only after independent verification.

## Publication, installation and forward proof

Commit `7c8912c4baf8cbb2662433c135388903e4e71042` was independently verified
on `origin/main`. The unrelated bounded Jev review and its ledger hunks remain
outside this commit. The native worktree's 100 pre-existing changes were untouched.

After all accounts were natively flat with no working orders, the prior AI and
two job states were recorded and paused. A verified 219-file, 507,044,227-byte
checkpoint preceded the supported `hermes profile update glitch --yes` and
installed setup. Source and installed hashes match for all 35 owned files.
Eight protected hashes, including credentials/configuration, account groups,
policy, epoch and prior freeze, are unchanged. All 95 checkpointed native AddOn
files are unchanged. NinjaTrader was neither restarted nor redeployed.

The new `entry-contract-20260923` freeze began at 08:48:29 UTC with manifest
`a041266013236cf5f98f378f7da6179d98df1614803e5ce445e44535f7608310` and prompt
`direct-v29-delivery-aware-cognition-b4675cdc2a2c`. This records provenance without
resetting the trading epoch. AI, replication and the exact previous job definitions
are restored and health reports ON. Jev remains at its completed trial cutoff.

Natural cycle `20260923T0850Z` used the installed prompt, completed in 31.44 seconds
with no repair, and received a successful native-grounded HOLD receipt. A pending
v97 MES short from `20260923T0846Z` was revalidated against the fresh 08:49 packet
after resume and filled under the existing delivery contract. That entry retains
its v97 attribution; v98's subsequent management is separate evidence. Native
protection is present on the master and both followers. This first live cycle
proves installation and ongoing management; the repaired entry shapes are proven
by the offline saved-response replay, not yet by a fresh matching live occurrence.

A later v97 MNQ short, entered at 08:36:59 and closed at 08:38:34, hit its native
target for +$34.50 master price PnL (+$33.40 after recorded commission). It occurred
after the frozen diagnosis cutoff and before installation. Including it, the
three closed v97 master ideas total +$14.80 after recorded commissions. This
small, changing sample establishes neither profitability nor a patch effect.

Remaining bottleneck: uncorrected entry decisions still took a median 61.71
seconds in the diagnostic window. Removing redundant corrections addresses only
part of delivery delay; no claim is made that expired entries would have filled
profitably. The next evaluation must retain version attribution and measure
repair frequency, decision-to-native delay, expiries, executable geometry and
costed native outcomes together.

Local audit artifacts: `D:/ab/artifacts/glitch-cognition/2026-09-23/`, including
`repair-replay.json`, `trade-paths.json`, `profile-tests.txt`, checkpoint and
deployment manifests, and `live-verification.json`.
