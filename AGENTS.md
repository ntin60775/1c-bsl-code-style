# Правила skill repo `1c-bsl-code-style`

## Границы

- Это отдельный git repo навыка `1c-bsl-code-style`.
- Не редактировать соседние skill repo и meta repo без явного scope.
- После изменения публичного контракта обновить `VERSION`, `CHANGELOG.md` и
  `skill.json`.
- После commit-а этого repo обновить `system.lock.json` в meta repo.

## Проверки

- Для изменений в документации навыка проверить русскую локализацию собственных
  текстовых артефактов через `owned-text-localization-guard`.
- Runtime-артефакты хранить вне skill tree, предпочтительно в `/tmp/1c-bsl-skills-pycache/1c-bsl-code-style`.
- Не фиксировать конкретную модель или `reasoning effort` внутри skill-а.
- Для реального BSL сохранять полный `real-code` coverage и не вводить light mode.
