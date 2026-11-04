# Intent evaluation results

Eval set: 50 labelled synthetic utterances (`eval_set.py`), 11 intents. Noisy sets: each utterance corrupted 10 times per level with `simulate_stt_errors` (seeded, reproducible).

| condition | utterances | accuracy |
|---|---|---|
| clean | 50 | 100.0% |
| noisy p=0.1 | 500 | 95.0% |
| noisy p=0.2 | 500 | 90.4% |
| noisy p=0.3 | 500 | 83.2% |

## Per-intent accuracy

| intent | clean | noisy p=0.1 | noisy p=0.2 | noisy p=0.3 |
|---|---|---|---|---|
| charge_time_cost | 100% | 100% | 100% | 98% |
| fallback | 100% | 100% | 100% | 100% |
| greeting | 100% | 87% | 93% | 73% |
| range | 100% | 100% | 100% | 98% |
| safety | 100% | 83% | 80% | 72% |
| savings | 100% | 100% | 98% | 92% |
| stations | 100% | 98% | 96% | 86% |
| trip | 100% | 98% | 92% | 86% |
| trouble_not_detecting | 100% | 95% | 68% | 52% |
| trouble_range_drop | 100% | 95% | 85% | 78% |
| trouble_slow_charging | 100% | 88% | 80% | 70% |

## Confusion table (noisy p=0.2)

Rows = expected intent, columns = predicted. `clarify` means the agent asked a question instead of guessing; it is counted as wrong.

| expected \ predicted | time_cost | clarify | fallback | greeting | range | safety | savings | stations | trip | t_not_detecting | t_range_drop | t_slow_charging |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| time_cost | 50 |  |  |  |  |  |  |  |  |  |  |  |
| fallback |  |  | 50 |  |  |  |  |  |  |  |  |  |
| greeting |  |  | 2 | 28 |  |  |  |  |  |  |  |  |
| range |  |  |  |  | 50 |  |  |  |  |  |  |  |
| safety |  |  | 12 |  |  | 48 |  |  |  |  |  |  |
| savings |  | 1 |  |  |  |  | 39 |  |  |  |  |  |
| stations |  |  | 2 |  |  |  |  | 48 |  |  |  |  |
| trip |  | 2 |  |  |  |  |  | 2 | 46 |  |  |  |
| t_not_detecting |  |  | 11 |  |  | 2 |  |  |  | 27 |  |  |
| t_range_drop |  | 3 | 3 |  |  |  |  |  |  |  | 34 |  |
| t_slow_charging |  | 2 | 6 |  |  |  |  |  |  |  |  | 32 |

## Caveats

- The eval set was written by the same author as the rules, before the rules were implemented. On the first run, before any rule changes, clean accuracy was 48/50 (96%). Two keyword gaps found by that run were then fixed (`range bahut ghat gayi`, `करंट लगा`), so the clean number in the table above is optimistic.
- After the first noisy run, two more changes were made because of what it showed: safety keywords use fuzzy matching (safety was at 77% for p=0.2; fuzzy is limited to distinctive words after 'jana' was found to fuzzy-match 'jalna'), and 'hi' counts as a greeting only as the first word (Hindi 'hi' = 'even'). The noisy numbers above are after those changes.
- The STT-error simulator is synthetic. It is not a measurement of Gnani Prisma's error rate.
- No embedding classifier is included, so there is no 'with embeddings' column.
