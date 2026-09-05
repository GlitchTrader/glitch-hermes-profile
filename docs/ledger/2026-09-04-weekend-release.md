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

Release code committed and pushed as `4b44b0e485ba73fae120c6177431c6409d8acdc3`. Remote main was verified before and after publication. Installed through `hermes profile update glitch --yes`, then the installed `setup.ps1`; only the Glitch Hermes gateway was restarted through its supported CLI and drained cleanly. NinjaTrader was not restarted. The existing Windows Startup-folder supervision remains in use; no UAC elevation or Scheduled Task change was required.

Installed proof:

- **29/29** profile manifest hashes match canonical source; config, authentication and environment overrides are unchanged. **79/79** checkpointed data/config/memory files were unchanged after installation.
- **95/95** native AddOn files match source, with no missing, extra or different files. Unrelated NT worktree changes were not staged, committed or deployed.
- Installed status: `Glitch trading: OFF; jobs: paused; policy: valid; replication: off; gateway: running.` All seven connected accounts are flat with zero working orders. Both installed operator and learner admission functions return `ai_auto_off_or_scope_invalid`; no market LLM calls or live order actions were used for validation. No provider-usage hold is currently present.
- Prospective freeze: `C:/Users/alan/Documents/NinjaTrader 8/GlitchData/hermes-checkpoints/cognition-experiments/v70-asia-20260906/freeze.json`, cognitive version `direct-v27-immediate-result-continuity-df96d8ced709`. This starts a new attributable evaluation; it does not reset trading history or promote a lesson. The existing unverified cost-stress policy remains explicitly unverified.
- Three old interpreter-launched `hermes.exe ... cron pause` command processes were found consuming CPU despite already-paused jobs. Their exact command identities were checked and only those processes stopped. They were not market decision workers. This deployment invoked the CLI executable directly, and profile job control now uses the scoped supported API.
- The Codex profitability monitor remains PAUSED. No automatic Sunday trading activation was scheduled. Use the normal Glitch AI Auto control when ready; replication is a separate operator setting.

Live market execution, actual response-time improvement and profitability remain unproven during the closed session. Sunday acceptance requires fresh packets, a naturally admitted decision under this exact cognitive hash, bounded delivery, and native receipts; passing offline tests is not a claim of guaranteed returns or zero possible defects.

Reference check: NinjaTrader documents that fills may be partial and provider event sequencing is not guaranteed ([OnExecutionUpdate](https://ninjatrader.com/support/helpGuides/nt8/onexecutionupdate.htm)). Native execution-driven protection and state reconciliation remain intact; the profile changes do not replace them with delayed model reasoning.
