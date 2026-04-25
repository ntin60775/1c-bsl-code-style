# Совместимый мост: checklist

Этот файл сохранён только для совместимости со старым путём
`references/checklist.md`.

## Источник истины

Финальная самопроверка теперь разнесена на два слоя:

- `../process/hard-gates.md` — бинарные блокеры завершения;
- `../process/review-heuristics.md` — финальная эвристическая перепроверка.

## Как использовать

Если старый playbook просит «пройти checklist», это теперь означает:

1. убедиться, что для самостоятельного real-code review уже выполнен
   `full-reference-pass` по `references/*.md`;
2. пройти `../process/hard-gates.md`;
3. затем пройти `../process/review-heuristics.md`;
4. вернуть наружу только residual `FAIL` и честные ограничения verify.
