# Запуск и проверка Docker

Все команды выполняются из `C:\hackaton\final`. Нужен работающий Docker Desktop
с Linux-контейнерами. Сервисы доступны только на localhost; исходные DOCX не входят
в образы. Первой сборке нужен интернет для базовых образов и зависимостей.

## Запуск

На этом Windows-компьютере ошибка сокетов Docker Desktop повторяется после его
обычного перезапуска. Проверенный запуск с восстановлением временных папок:

```powershell
cd C:\hackaton\final
.\scripts\Start-Docker.ps1 -RepairDesktop
```

Скрипт временно останавливает Desktop. При доступном движке он запрещает ремонт,
если работают контейнеры других Compose-проектов. Папки проверяются по абсолютным
путям и допустимому содержимому; неизвестные файлы не перемещаются. Резервные копии
остаются на месте, тома и настройки не меняются. Перед новым запуском останавливается
только WSL-дистрибутив `docker-desktop`, чтобы исключить зависший предыдущий запуск;
он не удаляется, его диск сохраняется. `-SkipBuild` использует готовые образы.
Если Docker уже работает, достаточно `.\scripts\Start-Docker.ps1`.

Обычный вариант для исправно работающего Docker:

```powershell
cd C:\hackaton\final
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
```

У всех трёх контейнеров должен быть статус `healthy`:

- Backend: http://127.0.0.1:8080/swagger-ui/index.html
- ML: http://127.0.0.1:8000/docs
- PostgreSQL: `127.0.0.1:5432`, параметры из `.env` / `.env.example`.

При занятых портах измените `BACKEND_PORT`, `ML_PORT`, `POSTGRES_PORT` в `.env`.
Сервисы общаются по внутренним адресам `backend:8080`, `ml:8000`, `postgres:5432`.
Их внутренние адреса менять при этом не нужно.

Отправка документа из подготовленного Python-окружения:

```powershell
.\ml\.venv\Scripts\python.exe -X utf8 scripts/submit_protocol.py --backend http://127.0.0.1:8080 --file "C:\путь\протокол.docx" --study-type BREAST
```

Команда отправляет DOCX в backend, ждёт доставки результата ML и выводит JSON
из backend. Тестовые метаданные создаются автоматически; собственные можно передать
через `--metadata`, как описано в [контракте интеграции](integration.md).

## Остановка и данные

```powershell
docker compose stop
# Повторный запуск:
docker compose up -d --wait
```

PostgreSQL и журнал доставки ML хранятся в томах `meditron-final_pgdata` и
`meditron-final_mlstate`. Они сохраняются при остановке и пересоздании контейнеров.
Не добавляйте `-v` к `docker compose down`, если данные нужно сохранить.

## Повторная проверка

Тесты создают вымышленных пациентов; используйте демонстрационную базу.
JUnit запускается при сборке backend-образа. ML-тесты выполняются внутри того же
образа, который используется сервисом:

```powershell
docker run --rm --mount "type=bind,source=C:/hackaton/final/ml/tests,target=/app/tests,readonly" --mount "type=bind,source=C:/hackaton/final/ml/examples,target=/app/examples,readonly" meditron-final-ml python -m unittest discover -s tests -v
.\ml\.venv\Scripts\python.exe -X utf8 tests/integration.py --backend http://127.0.0.1:8080 --ml http://127.0.0.1:8000 --report .local/docker-integration.json
```

Для обработки локального корпуса добавьте к последней команде
`--corpus "C:\hackaton\src\протоколы"`. Документы читаются без изменения;
извлечённые данные сохраняются в локальных томах.

Проверка отказов и сохранности данных временно остановит сервисы этого Compose-проекта:

```powershell
.\ml\.venv\Scripts\python.exe -X utf8 tests/docker_resilience.py
```

Она проверяет ответ 502 без ML, повторную доставку без backend, сохранность SQLite
при пересоздании ML, отсутствие дублей и сохранность обеих баз при пересоздании
всех контейнеров. В конце запускает сервисы снова. Порты определяются через Compose.

## Исправление Docker Desktop на этом компьютере

04.10.2026 Docker Desktop завершался до запуска движка из-за недоступных сокетов
`dockerInference` и `engine.sock`. При остановленном Desktop папки временных сокетов
`%LOCALAPPDATA%\Docker\run` и `%LOCALAPPDATA%\docker-secrets-engine` были переименованы
в резервные копии `*.before-meditron-*`. Вместо них созданы новые пустые папки.
После этого Docker Engine 29.4.0 запустился. Обычный `docker desktop restart`
воспроизвёл проблему; разовое переименование не устраняет причину внутри Desktop/Windows.
Поэтому в `scripts/Start-Docker.ps1 -RepairDesktop` добавлено повторяемое восстановление.
Дополнительная проверка выявила зависание WSL init после остановки Desktop; скрипт
завершает только `docker-desktop` перед повторным запуском. Готовность проверяется
по `docker info`, а затем по healthcheck всех трёх контейнеров.
Это проверенный обход сбоя, а не исправление бинарного файла Docker Desktop.
Настройки Docker, WSL-диск, образы и тома не сбрасывались. Пути резервных копий
записаны локально в `.local/docker-repair*.json`.

При новом сбое сначала смотрите конкретную ошибку Desktop и его журнал.
Описанное восстановление относится к обнаруженным сокетам; это не рекомендация
удалять Docker-данные или выполнять сброс к заводским настройкам.
Аналогичная ошибка сокетов описана в [трекере Docker](https://github.com/docker/desktop-feedback/issues/625);
причина именно на этом компьютере на уровне Windows/драйвера не установлена.

Результаты испытаний: [отчёт проверки](verification.md).
