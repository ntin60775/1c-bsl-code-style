# Контракт работы с субагентами

## Назначение

Subagent-flow — внутренний инструмент для крупных и неоднородных задач. Он
должен уменьшать пропуски и дублирование, а не превращать skill в ритуал.

Используйте субагентов только если одновременно верны оба условия:

1. задача действительно велика, многомодульна или конфликтна по аспектам;
2. разделение на роли упрощает coverage и проверку результата.

Если задача локальна, текущий агент выполняет skill сам.

## Неподвижные правила

- Координатор владеет режимом, scope-флагами, coverage-plan и final sign-off.
- Ни один subagent не может самостоятельно объявить, что «все проверки
  выполнены».
- Код правит только один исполнитель: правило `single-writer` обязательно.
- Сокращенный проход внутри shard-а real-code review запрещен.
- Если два subagent-а расходятся по безопасности правки, побеждает более
  консервативный вариант: либо дополнительная проверка, либо residual finding.

## Роли

### Координатор

Обязан:

- определить режим;
- собрать scope-флаги;
- материализовать checks из `checks.jsonc`;
- распределить pack-и и shards;
- агрегировать результаты;
- удерживать один coverage-plan;
- принимать финальное решение по `PASS/FIXED/FAIL/N/A`.

### Инвентаризация и классификация

Определяет:

- есть ли целый `*.bsl`-модуль;
- есть ли whitespace-правки;
- есть ли `Запрос.Текст`;
- orchestration-модуль ли это;
- есть ли legacy/external-contract boundary;
- есть ли право на запись;
- нужен ли doc-comment review.

### Scout-роли

Рекомендуемое разбиение:

- `structure-scout` — `references/module-header.md`
- `formatting-scout` — `references/bsl-formatting.md`
- `composition-scout` — `references/principles.md`,
  `references/anti-overengineering.md`, `references/naming.md`,
  `references/method-composition.md`, `references/call-layout.md`
- `profile-scout` — `references/doc-comments.md`, `profiles/query-texts.md`,
  `profiles/orchestration.md`
- `behavior-guard-scout` — `references/behavior-change-guard.md`,
  `references/review-feedback.md`
- `final-verifier` — `process/verify-recipes.md`, `process/hard-gates.md`,
  `process/review-heuristics.md`

### Правило `single-writer`

Только этот исполнитель имеет право:

- менять код;
- объединять несколько безопасных deterministic fixes в один edit-pass;
- передавать diff на rerun и verify.

## Формат результата subagent-а

Subagent возвращает структурированный результат, а не свободное эссе.
Минимальная форма:

```json
{
  "agent": "structure-scout",
  "checked_ids": ["MOD-001", "MOD-002"],
  "na": [
    {
      "id": "QRY-001",
      "reason": "В scope нет Запрос.Текст"
    }
  ],
  "findings": [
    {
      "check_id": "MOD-002",
      "path": "CommonModule/ИмяМодуля/Ext/Module.bsl",
      "span": "1-18",
      "severity": "hard",
      "autofix": true,
      "summary": "В модуле нет завершённой шапки перед первой областью",
      "evidence": "Файл начинается сразу с #Область"
    }
  ],
  "risks": [],
  "confidence": "high"
}
```

Требования к результату:

- каждый finding привязан к `check-id`;
- `N/A` идет только с причиной;
- `checked_ids` отражают реально выполненный scope;
- никакой subagent не пишет terminal status за checks, которыми он не владеет.

## Дедупликация и merge-policy

Агрегатор дедуплицирует findings по комбинации:

- `check-id`
- `path`
- `span` или предметный объект
- смысловая причина

Если два finding-а описывают одну и ту же проблему разными словами, остается
один объединенный finding с сохранением более строгой формулировки.

## Разрешение конфликтов

### Если конфликт про стиль

- побеждает rule-pack над примером;
- побеждает hard-gate над heuristic;
- профиль применяется только при подтвержденной применимости.

### Если конфликт про безопасность

- побеждает `references/behavior-change-guard.md`;
- auto-fix отменяется, если не удается доказать безопасность;
- в сомнительном случае issue остается `FAIL` и выносится наружу.

## Политика повторного прогона

После правки single-writer обязан вернуть diff координатору.

Координатор затем:

1. помечает затронутые checks как требующие rerun;
2. повторно запускает соответствующие scout-и или выполняет rerun сам;
3. отдельно закрывает `SAF-*`, `VRF-*`, `HGT-*`.

`FIXED` без rerun недопустим.

## Companion-режим

Если навык работает как companion внутри другого pipeline:

- не перехватывайте ownership верхнеуровневой задачи;
- но свой coverage-plan ведите полностью внутри scope skill-а;
- если companion-применение идет к реальному BSL-коду, это полный `real-code`
  режим: `full-reference-pass`, все mandatory checks по manifest-у, auto-fix
  детерминированных findings, rerun, verify и hard-gates обязательны;
- облегчённый companion-guidance для реального BSL-кода запрещён;
- если внешний pipeline — `$1c-bsl-review-standards`, локальная форма кода,
  форматирование, декомпозиция и doc-comments остаются под приоритетом текущего
  skill-а; конфликт с формальным стандартом фиксируется как blocker/residual
  risk и не чинится автоматически;
- наружу возвращайте style coverage-summary, auto-fix summary и residual risks.
