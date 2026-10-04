# MEDITRON 2026 · Кейс СМ-Клиники

**Интеллектуальная система выявления клинически значимых находок и автоматической маршрутизации пациента.**

## Структура

```
meditron-smclinic/
├── backend/            Spring Boot API (Java 21)
├── ml/                 модели и сервис классификации находок
├── frontend/           интерфейс для врача / регистратуры
├── docs/               API-контракт, схемы, материалы для питча
├── docker-compose.yml  запуск всего проекта одной командой
└── .env.example        пример переменных окружения
```



| Роль | Зона в репозитории |
|---|---|
| Бэкенд-разработчик, капитан, медицинский эксперт | `backend/` |
| ML-разработчик / аналитик, продакт | `ml/`, `docs/` |
| Фронтенд-разработчик | `frontend/` |
| UX/UI-дизайнер | Figma → ссылка в `docs/links.md` |

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d postgres      # только база
cd backend && mvn spring-boot:run  # бэкенд локально (или Run в IntelliJ)
```

Проверка:

* http://localhost:8080/actuator/health → `{"status":"UP"}`
* http://localhost:8080/swagger-ui.html → документация API

Всё в Docker: `docker compose up --build`

### Демо-данные

При пустой базе бэкенд сам загружает 7 результатов ML из `backend/src/main/resources/demo/`
(протоколы из архива, пациенты выдуманные): полип эндометрия, ЖКБ, маленький полип желчного пузыря
(ниже порога), BI-RADS 4, отрицание тромбоза, нечитаемый файл, смешанный протокол ОМТ.
Отключить: `DEMO_SEED=false`. Начать заново: `docker compose down -v` (удалит данные базы).

Отправить свой результат ML вручную:

```bash
curl -X POST http://localhost:8080/api/integration/ml/results \
  -H "Content-Type: application/json" \
  -d @backend/src/main/resources/demo/02-gb-stones.json
```

## Правила работы с Git

1. **Не пушим напрямую в `main`.** `main` — всегда рабочая версия для демо.
2. Каждый работает в своей ветке: `backend/<задача>`, `ml/<задача>`, `frontend/<задача>`.
3. Изменения вливаем через Pull Request, капитан смотрит и мёржит.
4. пароли, токены — только в `.env`, он не попадает в Git.
