# API-контракт

## Backend ↔ Frontend

Реализованные методы — [`openapi-runtime.yaml`](openapi-runtime.yaml).
Исходный проектный контракт с будущими методами — [`openapi.yaml`](openapi.yaml).
Живая документация запущенного бэкенда — http://localhost:8080/swagger-ui.html
Требования к экранам по макетам (что показывать и откуда брать данные) — [`FRONTEND-REQUIREMENTS.md`](FRONTEND-REQUIREMENTS.md).

| Экран | Эндпоинты | Готово в коде |
| --- | --- | --- |
| Инбокс | `GET /api/patients` (search, reviewState, studyType, dateFrom, dateTo) | да |
| Карточка пациента | `GET /api/patients/{id}`, `GET /api/protocols/{id}` | да |
| Находки | `POST /api/patients/{id}/findings/confirm`, `PATCH` / `DELETE /api/findings/{id}`, `POST /api/patients/{id}/findings`, `GET /api/dictionary/findings` | да |
| Составление маршрута | `POST` / `GET /api/patients/{id}/routes`, `GET /api/routes/{id}`, `PATCH /api/routes/{id}/steps/{stepId}` | следующий шаг |
| Пуш | `POST` / `GET /api/routes/{id}/notifications` | следующий шаг |
| Трекинг | `GET /api/routes` | следующий шаг |

## Backend ↔ ML

Итоговая цепочка: backend принимает DOCX через `POST /api/integration/protocols`,
передаёт его ML и принимает callback через `POST /api/integration/ml/results`.
Подробности: [инструкция интеграции](integration.md).

- Формат входа и выхода — документ «Требования к ML-сервису»:
  https://claude.ai/code/artifact/9b5ff0ee-7d29-4975-b5e6-c6748e2fe7cf
- Словарь находок — [`backend/src/main/resources/dictionary/findings-dictionary.yaml`](../backend/src/main/resources/dictionary/findings-dictionary.yaml),
  через API: `GET /api/dictionary/findings?full=true`.
- Требования к ML-сервису (контракт `POST /api/integration/ml/results`, флаги, правила извлечения, данные и метрики) — [`ML-REQUIREMENTS.md`](ML-REQUIREMENTS.md).
- Что изменилось в словаре `dict-v2` / `dict-v2.1` по сравнению с `dict-v1-ml` — [`CHANGELOG-dict-v2.md`](CHANGELOG-dict-v2.md).
- Пример сообщения — любой файл из [`backend/src/main/resources/demo/`](../backend/src/main/resources/demo/).
