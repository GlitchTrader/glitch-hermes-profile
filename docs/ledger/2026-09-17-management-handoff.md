# Entry-to-management continuity, September 17

Request: investigate current warning and continuing poor trades, fix warranted roots, publish/install and verify live. Baselines: profile e43a096 (v89), native e813e2e. Preserve learning, epoch, configuration and unrelated native working-tree changes. No native restart, forced order or account/replication change.

## Evidence

- After v89 resumed at 04:38:52Z, native SQLite executions and TradeLedger agree on five Sim101 round trips: four losses, one win, gross -$22. All five exits were HMX (Hermes EXIT), not protective stops. MNQ commissions total $1.10; MES commissions are zero in native records and therefore unverified, not free. This is a small adverse sample, not proof of an edge or its absence.
- MNQ1017 selected a parent recovery with a permitted pullback through 29569 and parent failure below29557.5. Its disconfirmation also called29569 local-attempt failure. active_trade_state carried that disconfirmation but dropped the original selected geometry. Manager1020 treated29569 as failure and exited. The code omission is confirmed; holding would not necessarily have won.
- MES1954 requested stop7711.25. Native execution31b6a24d-8b70-5af6-939f-520abbf79bee failed with protection_market_side_invalid because market was already7711.25. This was a valid native rejection. recent_management dropped protection_updates and the execution result, leaving the requested change's outcome absent from the compact management ledger.
- Four provider-overload failures and two incomplete geometry responses occurred among600 calls inspected since installation. Twenty responses required output repair. These are not fifty new JSON crashes; provider availability and incomplete responses remain operational risks. Validation is not relaxed.
- Twenty-two entry proposals produced five fills; the other17 were superseded by latest-price/range revalidation. Narrow executable zones relative to model latency remain a participation weakness, not permission to bypass ranges. Existing current-zone/latency instructions are retained; this repair is not another range or probability retuning.
- At reopening, the worker rejected five-frame packages containing stale opening data. It naturally resumed on2205 packet, completing22:06:37Z. The UI's worker-overdue diagnosis was wrong; admission itself was correct.

## Narrow repair

1. active_trade_state projects the selected entry's existing auction, directional path, objective/invalidation, range and geometry text. Trigger-review entries retain their corresponding three fields. No new inferred levels or strategy classification. Missing legacy fields remain empty.
2. Recent management carries exact requested protection updates and the latest intent-bound native result available as of the packet. Native working orders remain authoritative; pending, missing or failed records never rewrite them. Existing account/instrument/episode boundaries remain intact.
3. Entry disconfirmation must describe the same chosen wager. Management resolves conflicts using its horizon/allowed pullback and current evidence, without silently promoting a review level into failure. Actual deterioration, expiry, binding risk, supported profit protection and early EXIT remain allowed. No hold-until-stop rule or stop widening.
4. Paired native health fix labels fresh stale-data admission deferrals as data-not-ready (still degraded), rather than missing-worker. Failed/stalled attempts retain priority. No admission, session, freshness or execution rule changes.

Prompt budget is preserved, not increased. Regression tests and release checks are recorded separately from runtime evidence. Tests and historical reconstruction prove information delivery and safety invariants, not prospective profitability. Keep the v89 evidence; do not reset the epoch or tune to make these five outcomes appear successful.

## Source verification

All658 profile tests passed. The new six handoff tests first failed against v89, then passed with the repair; historical1020/1955 packets reconstructed into isolated workspace folders and demonstrated the actual previously missing geometry/rejection, without an LLM call or live write. Prompt-size limits were kept, not raised. Native health harness passed its stale-data, stale-event, failure and stall cases; full86-file AddOn source compile and96 native-side Python tests passed. Native paired commit60ea2b7 changes only health/UI/localization plus tests/documentation. Profile parser, admission, price revalidation, submit/delivery, position-risk calculations, model and cadence functions remain unchanged.

Final receipt-wording review is version91: a failed or missing receipt does not prove all legs are unchanged; reconcile each native leg, including partial updates. This removes ambiguity, not an execution rule. Version90 completed two naturally scheduled no-action cycles2238/2239 with accepted receipts, zero repairs/retries and no positions before this clarification. Keep their distinct prompt hash ed7e90644920; do not attribute them to v91.
