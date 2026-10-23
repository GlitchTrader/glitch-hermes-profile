# Relatório 2a — prompt size × latência × deriva × seleção

Gerado: 2026-10-23T15:50:54.718277Z

## Passo 0 (diff only)

- Scripts do bundle (exceto SOUL): **OK**
- SOUL: **repo_ahead_of_live_vacuum_stop_line** — Repo (dfb8f7b) rewrote volume-vacuum stop sentence; live still has older 'Supplied volume-at-price facts may add evidence...' wording. Syncing either way changes cognitive_bundle_hash.
- Sync: **não feita**

## Tamanho e latência

- Rows OK: 3620 (hash atual 727, foco `current_hash` n=727)
- prompt_chars p50: 260769.0
- session_rows chars p50: 130307.0 (share p50 0.475)
- R² elapsed~prompt_chars: 0.0148
- R² elapsed~session_rows: 0.0052
- Quintil gordo/magro elapsed p50: 1.0858
- Rebuild omissions: market_perception full + chart image + exact historical journals

## Deriva decisão→fim (hash atual)

- MNQ ENTER abs USD p50: 8.25
- ENTER by root: `{"M2K": {"n": 80, "abs_usd_p50": 1.25, "abs_usd_p95": 7.02500000000043, "abs_usd_mean": 2.162499999999966, "abs_pts_p50": 0.25}, "MES": {"n": 80, "abs_usd_p50": 3.75, "abs_usd_p95": 16.25, "abs_usd_mean": 5.5625, "abs_pts_p50": 0.75}, "MNQ": {"n": 80, "abs_usd_p50": 8.25, "abs_usd_p95": 47.074999999999996, "abs_usd_mean": 14.9375, "abs_pts_p50": 4.125}}`
- Nota: Drift uses packet prices at started_utc vs completed_utc via temporal join; 1m packets understate intraminute move when attempt finishes in same minute.

## Seleção ENTER vs breakeven

- n resolvidos: 28 (current_hash)
- observed target_first: 0.1786 (stop_first 0.8214)
- mean breakeven_target_first: 0.3722
- gap (breakeven − observed): 0.1936
- implied USD/ENTER: 4.54 (mean risk $23.46)
- gap_lower_approx: 0.0163

## Gate (limiares pré-declarados)

- **Decisão: C** — accumulate_N_and_eval_only
- Sinais: `{"size_latency": "weak", "best_r2": 0.0148, "prompt_r2": 0.0148, "session_rows_r2": 0.0052, "fat_over_thin_ratio": 1.0858, "drift": "cheap", "mnq_enter_drift_usd_p50": 8.25, "selection": "inconclusive_small_n", "implied_gap_usd_per_enter": 4.54}`
- Passo 1 necessário: **False** (gate_C_no_hot_path_change)
- Passo 4 eval hash: `686f54d1a4fb`

- Motivo: default accumulate: size=weak best_r2=0.0148 ratio=1.0858; drift=cheap mnq_enter_p50=8.25; selection=inconclusive_small_n implied=4.54
