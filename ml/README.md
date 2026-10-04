# ML-сервис — dict-v2.1-extractor-6

48 активных кодов, локальное извлечение фактов из DOCX по YAML. Обучаемой модели
и облачных вызовов нет. ML возвращает текст, заключение, факты, атрибуты, цитаты,
флаги и `notTriggered`; правила направления к специалистам исполняет backend.

Общий запуск: [README проекта](../README.md).
Контракт и полный цикл: [интеграция](../docs/integration.md).
Расширение справочника: [инструкция](../docs/ml-dictionary-extensions.md).

## Самостоятельный запуск ML

Команды из `ml/`, Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:BACKEND_URL="http://127.0.0.1:18080"
.\.venv\Scripts\python.exe -m app serve --port 18000 --database ../.local/events.sqlite3
```

Без `--dictionary` новый анализ запрашивает полный словарь через
`GET /api/dictionary/findings?full=true`. Для автономной работы передайте
`--dictionary configs/findings-dictionary.yaml`. Молчаливого перехода на локальный
словарь при ошибке HTTP нет: результат будет `FAILED / DICTIONARY_UNAVAILABLE`.

`POST /api/mis/events` принимает события подписания, исправления и аннулирования.
Один процесс обслуживает один SQLite-журнал. HTTP 202 означает сохранение результата;
доставка callback подтверждается значением `delivery: delivered` в
`GET /api/mis/events/{eventId}`. При недоступности backend отправка повторяется через
5, 30 и 120 секунд с тем же `resultId`. `POST /api/mis/events/{eventId}/retry` повторяет
доставку после отказа или исчерпания попыток; сам анализ он не пересчитывает.

## CLI

Только извлечь текст и разделы:

```powershell
.\.venv\Scripts\python.exe -m app "C:\путь\протокол.docx"
```

Сформировать входное событие и получить ML JSON без отправки:

```powershell
New-Item -ItemType Directory -Force ../.local | Out-Null
.\.venv\Scripts\python.exe -m app mis-event examples/mis-signed.json --file "C:\путь\протокол.docx" | Set-Content -Encoding UTF8 ../.local/event.json
.\.venv\Scripts\python.exe -m app process ../.local/event.json --dictionary configs/findings-dictionary.yaml --database ../.local/preview.sqlite3
```

В примере метаданных замените `eventId`, пациента, протокол, `studyType` и дату.
`process` сохраняет результат в очереди, но сам его не отправляет. Для предварительного
просмотра используйте отдельную БД, с которой затем не запускается `serve`.
Для нового анализа с изменённым словарём нужны новый `eventId` и новая версия протокола.

## Тесты и качество

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

165 тестов проверяют парсер, извлечение, словарь, контракты, HTTP и очередь.
Реальная связка с Java/PostgreSQL проверяется из корня `tests/integration.py`.

Последняя отдельная оценка извлечения v6: F1 полной находки 90,79% на 89 реальных
документах, 98,95% на 33 синтетических; вместе 92,68%. Это известный разработчику
корпус, не независимая клиническая валидация. При интеграции NLP-код и YAML не менялись;
сквозной прогон проверяет доставку и сохранение, не заменяет оценку F1.
Подробности предыдущей оценки: [отчёт v2.1](../docs/ml-v21-review.md).
Приватная разметка и исходные DOCX в исходники итогового проекта не копируются.

Новые коды/синонимы загружаются из YAML; простые новые атрибуты задаются через
`attributeExtractors`. Свободный текст `extraction/notThis` автоматически не исполняется:
новая медицинская семантика требует реализации профиля и проверочных примеров.
