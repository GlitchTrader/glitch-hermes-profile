# Gate 2026-10-23 — decisão pós 2a

Fontes: `report-prompt-size-latency-drift.md` / `.json`.

## Decisão: **C** — acumular N / eval only

Passo 1 (instrumentação hot path): **não**.

| Sinal | Valor | Limiar | Leitura |
| --- | --- | --- | --- |
| R² elapsed ~ prompt_chars | **0,015** | fraco &lt;0,15; forte ≥0,30 | fraco |
| R² elapsed ~ session_rows | **0,005** | idem | fraco |
| Quintil gordo/magro elapsed | **1,09×** | ≥1,15× | fraco |
| MNQ ENTER deriva USD p50 | **US$ 8,25** | barata &lt;10; cara ≥25 | barata |
| Seleção gap vs breakeven | +0,19 (implied **US$ 4,54**/ENTER) | n=28 &lt;30; gap_lower 0,016 &lt;0,05 | inconclusivo |

`session_rows` é ~47% do prompt reconstruído, mas **não explica latência**. Compactar agora seria mudança cognitiva sem evidência de ganho de tempo.

Stop-first alto (82%) vs breakeven (~37%) é economicamente suspeito, mas N e IC não passam o gate B. Continuar a acumular ENTERs resolvidos no hash `686f54d1a4fb`.

## Passo 0 (SOUL)

- Scripts do bundle: live = repo.
- SOUL: **repo à frente** (linha vacuum-stop do `dfb8f7b`). Sync **não** feita (quebraria freeze).

## Passo 4

- Freeze ativo: `20261022T202538Z-686f54d1a4fb`.
- `evaluate --publish` reemitiu o report já completed `b37431d8…1069` (gates LOCAL/DISTRIBUTION = false por N — esperado).
- Um **novo** freeze+eval para pontuar a janela desde 22/10 exige pause de AI/jobs (ops manual). Não feito automaticamente.

## Próximo

1. Deixar o hash atual correr; revisitar seleção quando n resolvido ≥30 com IC.
2. Não instrumentar nem compactar sem novo gate.
3. Opcional: quando puder pausar, novo freeze prospectivo no mesmo hash para eval limpo da janela corrente.
