# Trigger review field recovery - v0.0.2.86

A witnessed response-format defect placed ALTERNATIVE_CANDIDATES,
SELECTION_INSTRUMENT, SELECTION_ACTION and SELECTION_EV beside decisive_evidence
instead of as lines inside it. Strict audit validation rejected those explicit
values, and a second model pass could omit previously authored evidence.

The normalizer now relocates only these four known single-line string fields,
only in a trigger-review ledger. An identical existing line collapses its sibling
copy; conflicting values, multiple existing copies, empty values, wrong types
and multiline values remain invalid. Absent evidence is not synthesized. Normal
semantic, probability, geometry, native-price and delivery checks still run.

Offline replay covers both entry and NOTHING shapes. Regression tests verify
exact value/payload preservation, LF/CRLF compatibility, idempotence, conflict and
missing-evidence rejection, unchanged other modes, and no extra model invocation
for a repairable first response. Full validation and installation evidence are
recorded separately in the private maintenance checkpoint and canonical ledger.

This is a response-format repair, not a trading strategy or a profitability
claim. No SOUL, skill, prompt, learner, model, cadence, native protection,
replication, Flatten All, account or risk setting changes. Rollback is a scoped
source revert followed by the supported profile updater with runtime evidence
and configuration preserved.
