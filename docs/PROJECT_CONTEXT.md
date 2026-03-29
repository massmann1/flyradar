# Project Context

Этот файл нужен как компактный, но полный паспорт проекта. Его стоит читать первым, если потерялся контекст по коду, архитектуре или рабочим договоренностям.

Актуально на: `2026-03-29`

## 1. Что это за проект

`Flight Alerts` — личный Telegram-first сервис для отслеживания дешевых авиабилетов через cached `Travelpayouts / Aviasales Data API`.

Это:
- не live search;
- не booking engine;
- не веб-продукт с фронтендом;
- не микросервисная система.

Главная цель:
- пользователь создает подписки в Telegram;
- бот периодически проверяет cached цены;
- если находится подходящий оффер, приходит Telegram-уведомление.

## 2. Продуктовые рамки

### Что бот умеет сейчас

- `/start` и `/help`
- создание подписки через пошаговый диалог
- просмотр списка подписок
- включение и выключение подписок
- удаление подписок
- ручной запуск проверки
- просмотр последних найденных вариантов
- редактирование подписки
- inline-календарь для дат
- выбор города по названию, IATA-коду и через подсказки, если ввод неоднозначный

### Что в подписке можно задать

- название
- origin
- destination
- `one-way` или `round-trip`
- фиксированные даты или диапазон дат
- для `round-trip`: даты возврата или длительность поездки
- максимальную цену
- только прямые рейсы или нет

### Что в интерфейсе сознательно убрано

Для упрощения MVP и чтобы не обещать то, что cached Data API поддерживает неидеально:
- выбор валюты в боте убран, используется `RUB`
- выбор багажа в боте убран
- выбор авиакомпаний в боте убран
- выбор интервала проверки убран, используется `60 минут`

В модели часть полей может еще существовать, но в текущем bot UX они не настраиваются.

## 3. Архитектурная модель

Проект — один Python-монолит с двумя runtime-ролями поверх общей PostgreSQL.

### Runtime роли

- `worker`
  - Telegram bot на `aiogram`
  - `APScheduler`
  - checks, dedupe, alerting, notifications
- `api`
  - `FastAPI`
  - health-check
  - admin/debug endpoints
- `db`
  - `PostgreSQL`

### Почему так

- слабый VPS: `1 vCPU / 2 GB RAM / 25 GB disk`
- 1 пользователь
- нужна простота деплоя и поддержки
- нужен аккуратный shared service layer без Celery, Redis и прочей тяжелой обвязки

## 4. Ключевые директории

```text
app/
  api/           FastAPI admin/health endpoints
  bot/           aiogram handlers, keyboards, FSM states
  clients/       внешние API-клиенты
  core/          config, DI container, DB, logging
  domain/        enums, pydantic schemas, SQLAlchemy models
  repositories/  работа с БД
  scheduler/     APScheduler jobs/runner
  services/      бизнес-логика
  workers/       вспомогательные worker-обвязки
alembic/         миграции
tests/           критичные MVP-тесты
docs/            документация проекта
```

## 5. Основные точки входа

- API: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/main_api.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/main_api.py)
- Worker: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/main_worker.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/main_worker.py)
- Container wiring: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/core/container.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/core/container.py)

## 6. Главные файлы по ответственности

### Bot UX

- handlers: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/handlers/subscriptions.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/handlers/subscriptions.py)
- keyboards: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/keyboards/subscriptions.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/keyboards/subscriptions.py)
- FSM states: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/states.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/states.py)

### Search / normalization

- Travelpayouts client: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/clients/travelpayouts_rest.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/clients/travelpayouts_rest.py)

### Alerting / scheduling / notifications

- alert engine: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/alerts.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/alerts.py)
- dedupe rules: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/dedupe.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/dedupe.py)
- notifications: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py)
- price history: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/price_history.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/price_history.py)
- charts: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/charts.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/charts.py)
- scheduler jobs: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/scheduler/jobs.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/scheduler/jobs.py)

### Persistence

- models: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/models.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/models.py)
- schemas: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/schemas.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/schemas.py)
- repositories: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/repositories](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/repositories)

### Admin API

- routes: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/api/routers/admin.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/api/routers/admin.py)

## 7. Основные пользовательские сценарии

### Создание подписки

1. Пользователь пишет `/new`
2. Бот последовательно спрашивает:
   - название
   - откуда
   - куда
   - тип поездки
   - даты
   - max price
   - direct only
3. Ввод origin/destination:
   - можно давать названием
   - можно давать IATA-кодом
   - если найдено несколько вариантов, бот показывает кнопки выбора
4. На шаге подтверждения бот показывает summary
5. После подтверждения создается запись в `subscriptions`

### Плановая проверка

1. `APScheduler` будит `AlertService.run_due_subscriptions`
2. Из БД выбираются подписки с `next_check_at <= now`
3. Строится запрос к Travelpayouts
4. Сначала проверяется локальный `api_cache`
5. Если кэш невалиден, идет внешний HTTP-запрос
6. Ответ нормализуется в `OfferDTO`
7. Применяются фильтры
8. Берутся только top-N офферов для сохранения
9. Обновляются `offers`, `offer_prices`, `subscription_checks`
10. Если сработали правила alerting и не сработал dedupe, создается `notification_event`
11. Бот отправляет уведомление

### Ручная проверка

- запускается через кнопку у подписки в Telegram
- использует тот же `AlertService`, а не отдельный кодовый путь

## 8. Интеграция с Travelpayouts

### Используемые endpoint-ы

- `https://autocomplete.travelpayouts.com/places2`
  - для распознавания городов и аэропортов в боте
- `/aviasales/v3/prices_for_dates`
  - для fixed dates
- `/aviasales/v3/grouped_prices`
  - для диапазонов дат и сценариев с trip duration
- `/data/{locale}/airlines.json`
  - для человекочитаемых названий авиакомпаний

### Как выбирается endpoint

Логика в [_build_request](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/clients/travelpayouts_rest.py):

- `ONE_WAY + exact departure date` -> `prices_for_dates`
- `ROUND_TRIP + exact departure + exact return` -> `prices_for_dates`
- иначе -> `grouped_prices`

### Важное замечание по round-trip

Был критичный баг:
- fixed `round-trip` запрос в `prices_for_dates` уходил без `one_way=false`
- у Travelpayouts у этого endpoint `one_way=true` по умолчанию
- из-за этого API мог вернуть результат только “туда”

Фикс уже внесен в код:
- round-trip fixed dates теперь всегда отправляются с `one_way=false`

### Ограничения cached Data API

- это не live search
- если в кэше нет данных на точные даты, API может вернуть ближайшие даты
- цена и наличие в уведомлении не гарантированно актуальны в момент открытия ссылки

## 9. Как устроены уведомления

Форматирование: [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py)

В уведомлении сейчас показывается:
- название подписки
- маршрут
- дата вылета
- дата возврата, если есть
- цена
- причина уведомления
- пересадки
- авиакомпания
- история наблюдений бота
- deeplink в Aviasales
- disclaimer, что данные кэшированные

### Deeplink

Ссылка в уведомлении:
- визуально скрыта за текстом
- открывает Aviasales
- принудительно добивает `locale=ru`
- принудительно добивает `currency=rub`

## 10. Price history и storage efficiency

Проект уже содержит ограничения роста БД.

### Детальная история

Таблица `offer_prices` хранит детальные наблюдения.

Новая запись **не создается**, если:
- цена та же, что и у последнего наблюдения для того же `offer_id + subscription_id`
- и прошло меньше 24 часов

### Агрегация

Есть дневная агрегация в `offer_price_daily_stats`.

### Ограничение количества сохраняемых офферов

Из одного прогона сохраняются не все офферы, а только top-N после hard filtering.

### Cleanup

Cleanup запускается из существующего `APScheduler`.

Он чистит:
- `api_cache`
- `subscription_checks`
- `notification_events`
- старую price history
- тяжелый `raw_payload`, если полное хранение отключено

## 11. Модель данных

Главные таблицы:

- `users`
- `subscriptions`
- `offers`
- `offer_prices`
- `offer_price_daily_stats`
- `subscription_checks`
- `notification_events`
- `api_cache`

### Семантика timestamp-ов

- `provider_found_at`
  - только если реально пришел от провайдера
- `first_seen_at`
  - когда бот впервые сохранил оффер
- `last_seen_at`
  - когда бот в последний раз видел оффер
- `observed_at`
  - время конкретного наблюдения цены

Важно:
- это **не** timestamps покупки
- в тексте и коде сознательно не используем формулировки про “покупку”

## 12. Alerting и dedupe

Уведомление шлется, если:
- цена ниже лимита
- или цена ниже последней отправленной
- или найден новый интересный вариант

Антиспам:
- exact duplicate не отправляется повторно
- есть cooldown на одинаковый оффер
- dedupe строится по маршруту/датам/цене/перевозчику и другим ключевым полям

## 13. Планировщик

Используется `APScheduler`, не `Celery`.

Почему:
- один пользователь
- слабый VPS
- не нужен broker
- не нужна распределенная очередь

Основные jobs:
- run due subscriptions
- retry pending notifications
- cleanup old data

## 14. Служебный FastAPI

FastAPI не является продуктовым UI.

Он нужен для:
- `health/live`
- `health/ready`
- admin/debug
- ручного запуска check через API
- просмотра подписок, логов, офферов
- future-proof базы под возможную web-панель

## 15. Команды бота и UX-особенности

### Команды

- `/start`
- `/help`
- `/new`
- `/subscriptions`
- `/subs`
- `/cancel`

### Постоянная клавиатура

Внизу бота есть reply keyboard:
- `➕ Новая подписка`
- `📋 Мои подписки`
- `ℹ️ Помощь`
- `✖️ Отмена`

### Действия в “Мои подписки”

- включить
- выключить
- проверить
- последние
- редактировать
- удалить

### Редактирование подписки

- идет через тот же flow, что и создание
- на текстовых шагах можно отправить `.`, чтобы оставить текущее значение
- на шагах с кнопками есть вариант оставить текущее значение

## 16. Важные технические нюансы

### Telegram

- бот должен работать только в личном чате
- whitelist пользователей задается через `TELEGRAM_ALLOWED_USER_IDS`
- если запущено больше одного worker с тем же bot token, будет `TelegramConflictError`

### Docker / VPS

- данные подписок сохраняются в PostgreSQL volume
- обычный `docker compose up -d --build` данные не удаляет
- опасная команда: `docker compose down -v`

### Сеть и внешний API

- внешний поиск делается через `httpx`
- есть retry/backoff
- есть обработка `429`
- есть локальный `api_cache`

## 17. Как быстро понять, где проблема

### Если бот не отвечает

Смотри:
- worker logs
- `TELEGRAM_ALLOWED_USER_IDS`
- private chat vs group
- нет ли второго polling-процесса

### Если подписка не находит билеты

Проверь:
- не слишком ли узкие фильтры
- есть ли вообще cached данные по этим датам
- что записалось в `subscription_checks`
- что записалось в `offer_prices`

### Если round-trip ведет себя как one-way

Проверить:
- что код на версии с фиксом `one_way=false` для fixed round-trip
- какой endpoint использован в `subscription_checks.endpoint_used`
- что в `offers.return_at` реально не пустой

### Если не приходят уведомления

Проверить:
- `notification_events`
- cooldown/dedupe
- worker logs
- не ушел ли event в `FAILED`

## 18. Полезные команды для VPS

### Обновление

```bash
cd /opt/flyradar
git pull
docker compose --env-file .env up -d --build
docker compose --env-file .env exec api alembic upgrade head
```

### Обновление worker-only

```bash
cd /opt/flyradar
git pull
docker compose --env-file .env up -d --build worker
```

### Логи

```bash
cd /opt/flyradar
docker compose --env-file .env logs -f worker
docker compose --env-file .env logs -f api
```

### Проверить подписки

```bash
cd /opt/flyradar
docker compose --env-file .env exec db psql -U flight_alerts -d flight_alerts -c "select id, name, enabled, next_check_at, last_checked_at from subscriptions order by created_at desc;"
```

### Проверить последние проверки

```bash
cd /opt/flyradar
docker compose --env-file .env exec db psql -U flight_alerts -d flight_alerts -c "select subscription_id, status, endpoint_used, offers_found, error_message, started_at from subscription_checks order by started_at desc limit 20;"
```

### Проверить уведомления

```bash
cd /opt/flyradar
docker compose --env-file .env exec db psql -U flight_alerts -d flight_alerts -c "select subscription_id, reason, status, price_amount, created_at, sent_at, error_message from notification_events order by created_at desc limit 20;"
```

## 19. Что читать первым при потере контекста

Если нужно быстро восстановить картину по проекту, читать в таком порядке:

1. этот файл
2. [README.md](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/README.md)
3. [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/handlers/subscriptions.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/bot/handlers/subscriptions.py)
4. [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/clients/travelpayouts_rest.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/clients/travelpayouts_rest.py)
5. [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/alerts.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/alerts.py)
6. [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/services/notifications.py)
7. [/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/models.py](/Users/ilnurgaliullin/Documents/Playground/flight-alerts/app/domain/models.py)

## 20. Последние важные правки, которые стоит помнить

- добавлены подсказки выбора города, если ввод неоднозначный
- fixed round-trip `prices_for_dates` теперь идет с `one_way=false`
- в уведомлениях ссылка визуально скрыта, но открывает Aviasales на русском и в рублях
- в боте убраны выборы валюты, багажа, авиакомпаний и интервала
- редактирование подписок уже есть
- инструкция в боте соответствует текущему UX

## 21. Что пока не реализовано

- web-панель
- live search
- реальное бронирование
- надежный baggage filter по Data API
- rich analytics dashboard
- multi-user SaaS-сценарий

## 22. Принципиальные проектные решения

Не предлагать в рамках этого проекта без сильной причины:
- микросервисы
- Celery
- Redis
- RabbitMQ
- Kafka
- Kubernetes
- frontend для MVP

Цель проекта — личный, аккуратный, экономный сервис на слабом VPS.
