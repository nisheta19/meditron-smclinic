# Frontend

Интерфейс для пользователя системы (врач / регистратура).

- API бэкенда: `http://localhost:8080/api`, документация — `http://localhost:8080/swagger-ui.html`
- Проверка связи: `GET /api/ping` → `{"status":"ok"}`
- **Главный документ для фронта (и для ИИ-ассистента, который пишет код):** [`docs/FRONTEND-REQUIREMENTS.md`](../docs/FRONTEND-REQUIREMENTS.md) — экраны по макетам, откуда брать каждое поле, действия врача, чего в API пока нет.
- Контракт API: [`docs/openapi.yaml`](../docs/openapi.yaml) (0.3.0)
- Макеты: ссылка на Figma — в `docs/links.md`

Чтобы подключить фронт в `docker-compose.yml`, добавь сюда `Dockerfile`
и раскомментируй блок `frontend`.
