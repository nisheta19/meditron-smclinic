# Frontend
Интерфейс для пользователя системы (врач / регистратура).


## Демо
[https://0-o.gitverse.site/hackaton_sechenov_2026/](https://0-o.gitverse.site/hackaton_sechenov_2026/)\
[https://0-o.gitverse.site/hackaton_sechenov_2026/next_step.html](https://0-o.gitverse.site/hackaton_sechenov_2026/next_step.html)

## Figma
-[План](https://www.figma.com/board/7SyLd8Nnc4H5fvO0uvdbCJ/%25D0%25A1%25D0%25B5%25D1%2587_%25D0%25A5%25D0%25B0%25D0%25BA%25D0%25B0%25D1%2582%25D0%25BE%25D0%25BD?node-id=0-1&t=f83aYeel98UNYtNl-0)\
-[Дизайн](https://www.figma.com/design/HOLfWIsqBlWIjm1LwqF4H6/%25D0%25A1%25D0%25B5%25D1%2587_%25D0%25A5%25D0%25B0%25D0%25BA%25D0%25B0%25D1%2582%25D0%25BE%25D0%25BD_%25D0%2592%25D1%2591%25D1%2580%25D1%2581%25D1%2582%25D0%25BA%25D0%25B0?node-id=0-1&t=S7tlJtRMhxTySm6m-0)

## Запуск

```bash
npm install
npm run dev        # http://localhost:5173, по умолчанию демо-режим
```

## Документация OpenAPI
[http://localhost/open-api](http://localhost/open-api)
[http://localhost/next-step/demo](http://localhost/next-step/demo)

## Демо-режим и backend

Переключение одним флагом (`.env.local`, образец в `.env.example`):

```bash
VITE_USE_MOCK=true                    # заглушки и демо-данные (по умолчанию)
VITE_USE_MOCK=false                   # реальный API
VITE_API_URL=http://localhost:8080    # адрес backend
```
