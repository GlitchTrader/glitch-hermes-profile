# Weekend release: adaptive judgment, exact mechanics

## Authority and baseline

Alan authorized end-to-end implementation on 2026-09-04 after the read-only audit. Baseline: profile `b202503` / installed `0.0.2.69`; NT `0b917a1`. The profile checkout is clean. Unrelated NT documentation/web changes are outside this release. Native trading is OFF, replication desired is false, both Hermes jobs and the Codex monitor are paused. Preserve those states; no NinjaTrader restart or order action.

## Bounded change budget

1. **Native risk facts:** share the existing initial-bracket arithmetic between outcome reconciliation and active-position context. Initial risk comes from the original intent-bound native fill/protection receipt, never a subsequently moved stop or current-to-stop distance. Missing provenance remains unknown. Keep minute-sampled excursions explicitly labeled and prevent cross-instrument episode carryover.
2. **Management judgment:** remove the deterministic `nonpositive EXIT => FAILED required` gate and its forced-HOLD repair. Preserve explicit thesis review, loss/noise versus structural deterioration, profit protection, non-widening stops, native leg IDs and final position revalidation. EXIT remains Hermes's comparative decision, not a PnL-sign rule.
3. **Selection consistency:** stop silently relabeling contradictory NOTHING forecasts as UNCERTAIN. Check the arithmetic meaning of all probability ranges, including UNCERTAIN. A bounded correction may repair arithmetic labels but cannot invent a new entry, change geometry, or back-solve probabilities. Positive terminal-bracket value does not force a trade when a specifically justified WAIT or another alternative is better. Entry still requires internally positive stated value.
4. **Cognitive load:** shorten duplicated hot-path instructions, preserving adaptive regime/setup reasoning, early entry, wider-path geometry, plan continuity, anti-churn, current native state, and strict wire format. Remove the dollar-stop and preferred-ratio presumptions; use actual instrument/horizon noise, structure and costs. Distinguish the immediate 5-10-bar description from the unchanged-bracket target/stop forecast; managed exits are a separate outcome.
5. **Invocation safety:** recheck market/data/AI admission after acquiring the shared profile lock. Share a durable provider-usage-limit hold across operator and learner, cleared by explicit operator resume; distinguish quota exhaustion from transient failures. Scope control operations to the installed plugin's own profile store using Hermes's supported context API, with missing-job failures explicit. No changes to global Hermes installation or native trading controls.

Implementation surfaces: SOUL, affected runtime skills, direct worker, learner invocation boundary, existing subprocess/control helpers, shared native-risk helper, focused regression tests, release docs/version/hash manifest. Existing NT mechanics are validated rather than redesigned. No new conditional-order API, fixed strategy, trade quota, specialist agents, metrics project, learner promotion relaxation, epoch reset, or automated trading activation.

## Proof and rollback

- Add focused tests for immutable native initial risk (modified stops, missing receipts, independent reentries, instrument switch); losing EXIT before/after favorable movement; numeric EV contradictions without action invention; provider holds across both workers; post-lock admission; profile-scoped pause/resume.
- Run the full profile suite plus existing native replication/state safety checks. Inspect every changed hunk and preserve native transport/admission invariants.
- Checkpoint and hash-verify deployed cognition and irreplaceable learner/epoch evidence before supported profile update. Publish only scoped files. Verify remote commit and distribution-owned installed hashes separately.
- Preserve paused state through installation; run offline/closed-market admission checks without paid LLM calls or live orders. Fresh-market execution and profitability cannot be certified during the weekend.
- Rollback is the recorded baseline profile release using the supported updater plus the verified evidence checkpoint, never an epoch reset or deletion of learning.

## Status

Release `0.0.2.70` implemented within the stated budget. Full profile suite: **328 passed**. Existing native replication, request bounds, control, partial-fill, intent-recovery and completed-bar suites: **70 passed**. The C# Glitch state-machine harness passed; all 11 Python modules parse under the installed Hermes Python. `git diff --check` is clean. No NinjaTrader source, routing, replication, order lifecycle, limits or cadence changes.

The duplicated SOUL text decreased from 21,341 to 8,564 characters; the common/mode prompt-construction section decreased from 31,128 to approximately 12,700. This measures instruction text, not total packet size, tokens, latency or trading improvement. Those require fresh-market evidence.

Verified pre-release checkpoint: `D:/ab/checkpoints/glitch/20260904-pre70-4bfa8190/checkpoint-manifest.json` — 112 files, 3,358,685,396 bytes. Includes deployed cognition/config, memories, learner/supervisor evidence, intents/journals/epoch, and online SQLite backups of Hermes history and NinjaTrader. Every copy was hash-verified; both database snapshots passed `quick_check`. AI and both jobs remained paused. No evidence was reset or deleted.

Remote main still equals the recorded baseline `b2025032575e96975554d8b866f64c148e479722` before publication. Publication/install/parity and a new prospective freeze follow these checks. Live market execution, response-time improvement and profitability remain unproven during the closed session.

Reference check: NinjaTrader documents that fills may be partial and provider event sequencing is not guaranteed ([OnExecutionUpdate](https://ninjatrader.com/support/helpGuides/nt8/onexecutionupdate.htm)). Native execution-driven protection and state reconciliation remain intact; the profile changes do not replace them with delayed model reasoning.
