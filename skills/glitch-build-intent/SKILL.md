---
name: glitch-build-intent
description: Serialize the selected multi-instrument Glitch judgment into the supported intent schema.
---
# Build the Intent

Serialization begins only after the market scan and setup-state process has selected one instrument, one supported action, quantity, and geometry. This skill does not reinterpret the market or substitute a strategy.

Preserve every user-configured constraint and Glitch authority.

Return exactly one `glitch.intent.batch.v1` object with one decision per ordered master book. Preserve supplied cycle ID, account, route, snapshot hash, model version, prompt version, and supported top-level shape. Use only supported actions. Copy the selected instrument exactly from the candidate packet; never default to MNQ.

Preserve exact required `decision_audit` keys and make `final_choice` appear once and equal `action`. Put current setup, next setup, transition trigger, order-flow winner, and candidate-selection evidence inside the supplied audit strings unless Glitch explicitly supplies an extended schema. Do not add unknown fields.

For entries use MARKET, a supplied valid positive master quantity, tick-aligned stop beyond genuine invalidation, and tick-aligned targets. For management use only supplied native leg IDs and supported protection updates. Never invent a leg ID, route, account, price, quantity, probability, or receipt. Never target followers or reverse through an entry.

Glitch final checks must not replace the selected direction, instrument, quantity, geometry, or supported action with an unrelated strategy.
