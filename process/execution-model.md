# Модель исполнения и покрытия

## Источник истины

`checks.jsonc` — единственный источник истины для coverage этого skill-а.

Для real-code review полнота доказывается не тем, что агент «прочитал все файлы
в каталоге», а тем, что он:

1. определил режим применения;
2. собрал scope-флаги;
3. материализовал обязательные `check-id`;
4. довел каждый обязательный и применимый check до терминального статуса.

Если обязательный и применимый check остается в `UNRUN`, финальный ответ
блокируется.

## Режимы

### `consultation`

Локальная консультация без review реального кода.

- Используйте manifest для выбора только тех checks, которые реально относятся
  к вопросу пользователя.
- Базовое ядро обычно составляют `references/principles.md` и
  `references/anti-overengineering.md`.
- Profile-паки подключайте только по явной теме.
- `examples/few-shots.md` не закрывает checks и не заменяет rules.

### `real-code`

Режим для написания, правки и прикладного style-review реального кода. Этот режим
обязателен и не урезается, если skill используется как companion-layer внутри
standards/BSP/внешнего pipeline.

- Для самостоятельного review сначала выполните legacy-compatible
  `full-reference-pass` по `references/*.md`.
- Сначала выполните inventory-pass.
- Затем материализуйте все checks, у которых `mandatory_for` включает
  `real-code`.
- Если применимость неочевидна, считайте check применимым, пока inventory-pass
  явно не докажет обратное.
- Для `N/A` всегда фиксируйте причину.

### `skill-audit`

Режим системного аудита skill-а.

- Прочитайте `checks.jsonc`, весь `process/`-слой, все `references/` и все
  `profiles/`.
- Проверяйте согласованность manifest-а, агентного конфига, mode boundaries,
  hard-gates и subagent-flow.
- Примеры можно читать выборочно, только если они реально нужны для аудита.

## Scope-флаги

Перед чтением domain-pack-ов координатор фиксирует scope-флаги. Минимальный
набор:

- `real_code`
- `writable_scope`
- `whole_bsl_module`
- `bsl_code`
- `bsl_whitespace_edit`
- `touched_methods`
- `new_or_changed_module`
- `changed_files`
- `has_query_text`
- `needs_doc_comments`
- `orchestration_module`
- `legacy_or_external_boundary`
- `uses_subagents`
- topic-флаги для consultation-режима

Не используйте молчаливое «наверное не относится». Если scope неясен, ставьте
временный флаг в сторону применимости и снимайте его только после явного
разбора.

## Модель статусов

Терминальные статусы:

- `PASS`
- `FIXED`
- `FAIL`
- `N/A`

Промежуточный статус:

- `UNRUN`

Правила:

- `UNRUN` запрещен для обязательной и применимой проверки к моменту финального
  ответа.
- `N/A` допустим только с конкретной причиной.
- `FIXED` допустим только если выполнен rerun соответствующих checks.
- `FAIL` допустим только как явный residual finding или осознанно оставленный
  риск; прятать его в формулировке «всё чисто» нельзя.

Удобная рабочая форма coverage-таблицы:

| id | статус | владелец | подтверждение / причина |
|---|---|---|---|
| MOD-001 | PASS | structure-scout | Верхний уровень модуля просмотрен до методов |
| QRY-001 | N/A | profile-scout | В scope нет `Запрос.Текст` |
| FMT-001 | FIXED | formatting-scout | Исправлены табы; rerun выполнен |

## Порядок фаз

1. `inventory`
2. `coverage-plan`
3. `scan`
4. `fix`
5. `rerun`
6. `verify`
7. `report`

### `inventory`

- определить режим;
- собрать scope-флаги;
- построить список обязательных checks;
- назначить owner-ов.

### `scan`

- прочитать все pack-и, которые владеют обязательными и применимыми checks;
- выполнить полный style-pass по текущему scope;
- для целого реального модуля сначала пройти верхний уровень файла по
  `references/module-header.md`, а потом методы.

### `fix`

Если scope допускает запись и проблема:

- локальна;
- детерминированно исправляется;
- не создает тяжелых последствий;
- не меняет внешний контракт неоднозначно,

ее нужно исправлять автоматически.

### `rerun`

После любой правки повторно прогоняйте:

- все checks, затронутые правкой;
- checks безопасности (`SAF-*`);
- verify-checks (`VRF-*`), если появился diff;
- релевантные hard-gates.

### `verify`

Используйте `process/verify-recipes.md`.

### `report`

Перед финальным ответом:

- выполните `process/hard-gates.md`;
- затем `process/review-heuristics.md`;
- наружу вынесите coverage-summary, auto-fix summary и residual `FAIL`/риски.

## Что считается доказательством coverage

Считается доказательством:

- materialized coverage-table по `check-id`;
- terminal status для каждой обязательной и применимой проверки;
- явные причины для `N/A`;
- rerun после `FIXED`;
- verify и hard-gates перед финальным ответом.

Не считается доказательством:

- чтение каталога `references/` по glob-шаблону;
- ссылка на один общий prose-отчет без check-status-ов;
- чтение примеров вместо rules;
- утверждение subagent-а «я все проверил» без общего coverage-plan.
