# Совместимый мост: runtime-contract

Этот файл сохранён только для совместимости со старыми ссылками, historical
task-артефактами и repo-level ожиданием, что у 1С-навыка есть
`references/runtime-contract.md`.

## Источник истины

Актуальный execution contract навыка больше не живёт в этом файле.
Используйте:

- `../checks.jsonc` — manifest coverage, `check-id`, owner-ы, applicability,
  статусы и блокеры;
- `../process/execution-model.md` — режимы, coverage-plan, фазы и модель
  статусов;
- `../process/subagent-contract.md` — coordinator/subagent contract и
  `single-writer`;
- `../process/hard-gates.md` — жёсткие блокеры финального ответа.

## Совместимость с прежним `full-reference-pass`

Старое правило про обязательный полный проход по `references/*.md` не отменено:
оно остаётся legacy-compatible public entry contract для самостоятельного
ревью реального кода.

После такого прохода полнота доказывается более точной моделью:

- координатор материализует все обязательные и применимые checks из
  `checks.jsonc`;
- каждый такой check должен завершиться в `PASS`, `FIXED`, `FAIL` или `N/A`;
- `UNRUN` для mandatory+applicable проверки блокирует финальный ответ.

То есть `full-reference-pass` остаётся входом, а `checks.jsonc` —
доказательством покрытия этого входа.
