# Management path evidence, September 18

User authorized fixing the diagnosed weaknesses and publishing/installing through live verification. Baseline e730357/v91. Native AddOn 60ea2b7 is unchanged. No account/epoch reset, forced trades, NinjaTrader restart, or changes to execution, protection, replication, sizing, admission, model or job cadence.

## Evidence, not hindsight policy

MNQ entry `489130d9-89a3-540b-a55f-6093d9bb1be2` filled 29694.5 at 02:44:45Z, with stop 29678.5 and target 29712.5. Thirteen HOLD decisions preceded EXIT `2e6a07cb-ed64-523d-b416-e8999ed3857a` at 02:59:40Z, filled 29694.75. Master gross +$0.50, recorded commission $1.10. Both native SQLite and TradeLedger agree.

At 0248 Hermes declared negative unchanged-bracket value but defended HOLD by an intact thesis and small MFE. At 0259 it used negative value plus rollback to exit while acknowledging that the parent failure sequence was incomplete. This is inconsistent justification, not proof that every early exit is wrong. The target traded about six minutes after exit without the original stop being touched in the recorded path. Future prices were unavailable to the original decision.

The sampled native peak was $12. A completed wholly post-entry bar reached 29703.75, implying $18.50 gross price excursion per contract, not a guaranteed executable profit. The learner's debrief ended its path at exit+1 minute and could not see the later target; its assessment should not be mistaken for independent validation of the exit.

## Narrow changes

- Management prompt, SOUL and skill use the same evidence standard while green/red. Neither a small gain nor its rollback selects an action. Probability updates need causal justification at the chosen horizon; arithmetic precision is not probability calibration. Supported profitable exits remain available without a minimum-MFE switch; no hold-until-stop rule.
- Existing native sampled P&L is unchanged. A separate completed-bar excursion projection uses the exact contract and only complete observed minutes after a native full-fill bracket receipt. It excludes the entry minute, future/partial/malformed bars and unknown/scaled fills, and carries only matching episode/contract/size/average evidence. Missing history is not invented. This adds no disk scan to the hot path.
- A debrief receives a compact original-authored-bracket post-exit observation, at most 30 minutes. It waits for that window on the existing learner schedule, one debrief per outcome; no new job or extra model loop. Missing minutes, both-barrier bars and mixed exit-minute touches stay unresolved/ambiguous. This is not a fill, realized P&L or a replacement entry-forecast label. The summary survives into hourly supervision. Old episodes remain immutable.

## Proof boundary

Regression tests first failed against v91. Long/short, contract, time, entry-minute, overlap, size, missing-data and touch-order tests exercise the deterministic inputs. Full-suite and isolated historical reconstruction results accompany release verification. No historical model call, broker action or learner rewrite is used to make the past look successful. Prospective profit and trade-management quality remain to be measured after deployment.

Pre-install verification: all 680 profile tests passed. The isolated saved-packet replay also passed under the production Hermes Python runtime: native sampled peak remained $12; completed-bar excursion was $18.50; the original target first touched in the 03:06Z bar with no prior stop touch or missing minute. The replay made no provider call and changed no live data. Publication, installed parity and prospective live receipts are separate operational checks, not implied by these tests.
