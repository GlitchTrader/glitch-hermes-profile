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

A sweep/reclaim, failed acceptance, displacement, absorption, exhaustion, or microstructure break can transition the state. A break weakens or invalidates the affected path and may promote the next setup for reassessment; it does not force a reverse. At a session extreme or stated first objective, one delta change or one-minute bounce does not promote the opposing path without accepted price response through its named transition. A farther objective belongs to the next continuation setup until the nearer objective or transition is accepted. Preserve anticipatory entries when location is favorable, invalidation is genuine, the entry range and stop can survive current noise, credible room remains, and probability-weighted asymmetry after latency is positive. Do not require a closed candle, complete flow, or false numeric precision solely to eliminate uncertainty.

Preserve transition identity across cycles. A fired frozen transition promotes its prior conditional path to active review. Classify it as `HELD`, `FAILED`, or `EXPIRED` from evidence observed after the crossing before creating a newer trigger. Do not ratchet confirmation to the newest high or low by asking for the same evidence again. A crossing is not an automatic order; reject a held path only for new disconfirmation or insufficient remaining objective relative to noise, execution uncertainty, and invalidation.

The candidate ledger is incomplete until current, bullish, bearish, and next setup fields exist for every packet-eligible instrument. Rank only after this ledger is complete.
