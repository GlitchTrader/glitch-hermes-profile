---
name: glitch-setup-state
description: Maintain bullish, bearish, current, and next setup states for every candidate.
---
# Current, Directional, and Next Setup State

Treat each instrument as an evolving auction, not a static bull/bear label. Every instrument always has a current auction/path, even when it is low-quality or not tradeable. For every instrument maintain four separate concepts:

- **current setup:** the path currently active at this location;
- **bullish setup:** the evidence-supported long path, including its trigger, objective, invalidation, and status;
- **bearish setup:** the evidence-supported short path, including its trigger, objective, invalidation, and status;
- **next setup:** the path that could become active after a defined transition.

A bullish or bearish setup may be absent, conditional, mature, exhausted, failed, or invalid. Do not force one direction merely to fill a field. “Trend up” or “trend down” is context; it is not sufficient setup geometry.

For each state record:

- setup type and phase;
- anchor/location;
- accepted evidence;
- missing evidence and uncertainty;
- objective and genuine structural invalidation;
- room beyond ordinary noise;
- transition trigger;
- order-flow winner and price response;
- what would disconfirm the path.

A sweep/reclaim, failed acceptance, displacement, absorption, exhaustion, or microstructure break can transition the state. A break weakens or invalidates the affected path and may promote the next setup for reassessment; it does not force a reverse. At a session extreme or stated first objective, one delta change or one-minute bounce does not promote the opposing path without accepted price response through its named transition. A farther objective belongs to the next continuation setup until the nearer objective or transition is accepted. Preserve anticipatory entries when location is favorable, invalidation is genuine, the entry range and stop can survive the intended five-to-ten-bar horizon plus current one- and five-minute noise and execution delay, credible room remains, and probability-weighted asymmetry after latency is positive. A shallow pivot that only creates a small risk denominator is not sufficient invalidation. Do not require a closed candle, complete flow, or false numeric precision solely to eliminate uncertainty.

Keep entry confirmation separate from trade geometry. A trigger or promotion level establishes setup state; it is not automatically the primary target. After acceptance, derive the next structural destination and genuine invalidation from the current packet. These are Hermes interpretations of supplied evidence and need not arrive as pre-labeled authoritative fields.

Preserve transition identity across cycles. A fired frozen transition promotes its prior conditional path to active review. Classify it as `HELD`, `FAILED`, or `EXPIRED` from evidence observed after the crossing before creating a newer trigger. A reclaim or retest remains `HELD` while the named invalidation is intact; `FAILED` requires that invalidation or a specific structural contradiction. Do not ratchet confirmation to the newest high or low by asking for the same evidence again. A crossing is not an automatic order, and `HELD` does not lower the entry standard; require current evidence, a delivery-valid execution zone, a noise-surviving genuine invalidation, and positive current-zone expected value. Confirmation is one evidence source, not a permission gate. Separate path validity from entry quality and debit the displacement used as directional evidence from remaining room. Compare NOW with WAIT; WAIT is superior only before the primary objective and only when a concrete improvement in entry location, invalidation cost, or target-before-stop probability outweighs lost room. Waiting for perfect confirmation or a retest is never mandatory. If the prior path fails or expires, construct the strongest fresh compact setup from current evidence rather than waiting for the next full scan. A completed pullback or retest that preserves invalidation and renews favorable response can restore entry quality; maturity is path-specific.

The candidate ledger is incomplete until current, bullish, bearish, and next setup fields exist for every packet-eligible instrument. Rank only after this ledger is complete.
