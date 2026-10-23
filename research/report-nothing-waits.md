# NOTHING / WAIT scorecard

Gerado: 2026-10-23T18:10:50.471466Z

- NOTHING total: 2753 | scored com geometria: 1761 | sem geometria: 992
- Resolved first-touch (NOW contrafactual): 852
- Observed target-first (resolved): 0.4531
- Chronology: `{"stop_before_target": 466, "neither_reached": 899, "target_before_stop": 386, "ambiguous_same_bar": 10}`
- Missed good (absteve mas target_first): 386 (0.4531)
- Correct abstention (stop_first): 466 (0.5469)

## WAIT fill (níveis a ≥1.0 do entry)

- Com wait_price distante: 1704 (sem nível distante: 57)
- Touch rate (forward window): 0.7447
- wait_before_stop / stop_before_wait: 1069 / 62
- Claimed IMPROVED n=329, touch_rate=0.7538
- Missed good ∩ wait missed/filled: 75 / 304
- wait_vs_stop: `{"ambiguous_same_bar": 183, "wait_before_stop": 1069, "neither": 390, "stop_before_wait": 62}`

## Auditor EV proxy (declared positive NOW EV)

- Declared positive NOW EV: 753 (resolved 320)
- Observed target-first nesses: 0.1594
- WAIT fail share entre positive NOW: 0.2377 (n=179)
- Note: Levels within 1.0 of entry dropped. Positive NOW EV uses declared p and authored R:R only; wait_fail means distant wait_price never printed.

## Calibration buckets (NOW geometry)

- `p_0.40_0.50`: {"n": 398, "observed_target_first": 0.4271, "mean_declared_p": 0.4377}
- `p_0.50_0.60`: {"n": 31, "observed_target_first": 0.7742, "mean_declared_p": 0.5213}
- `p_ge_0.60`: {"n": 3, "observed_target_first": 1.0, "mean_declared_p": 0.615}
- `p_lt_0.40`: {"n": 413, "observed_target_first": 0.4552, "mean_declared_p": 0.326}
- `unknown_p`: {"n": 7, "observed_target_first": 0.1429, "mean_declared_p": null}

## By instrument

- **M2K**: {"n": 452, "resolved": 150, "chronology": {"neither_reached": 301, "target_before_stop": 69, "stop_before_target": 81, "ambiguous_same_bar": 1}, "wait_touch": {"not_touched": 239, "touched": 162, "no_distant_level": 51}}
- **MES**: {"n": 386, "resolved": 134, "chronology": {"neither_reached": 251, "stop_before_target": 81, "target_before_stop": 53, "ambiguous_same_bar": 1}, "wait_touch": {"touched": 259, "not_touched": 121, "no_distant_level": 6}}
- **MNQ**: {"n": 923, "resolved": 568, "chronology": {"stop_before_target": 304, "target_before_stop": 264, "neither_reached": 347, "ambiguous_same_bar": 8}, "wait_touch": {"touched": 848, "not_touched": 75}}
