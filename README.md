# Flight Alerts

Telegram-first backend for cheap flight alerts based on Travelpayouts Data API.

## MVP Scope

- Telegram bot is the primary UI.
- FastAPI is a technical/admin API only.
- Travelpayouts cached data API is used for price checks.
- No frontend, no live booking flow, no heavy infrastructure.

## Runtime roles

- `api`: FastAPI health and admin endpoints.
- `worker`: aiogram bot, APScheduler, alerts processing, Telegram notifications.

## What is implemented

- Bot-first subscription management.
- Step-by-step `/new` dialogue.
- Enable, disable, delete, manual check, latest offers via bot actions.
- Shared service layer for bot, scheduler, and FastAPI.
- PostgreSQL persistence, API cache, price history, notification log.
- APScheduler worker with periodic checks and retry of failed notifications.
- FastAPI endpoints for health and admin debugging.

## Project structure

```text
app/
  api/           FastAPI health and admin endpoints
  bot/           aiogram handlers, keyboards, FSM states
  clients/       external API clients
  core/          config, logging, DB, container
  domain/        enums, schemas, SQLAlchemy models
  repositories/  DB access layer
  scheduler/     APScheduler setup
  services/      business logic
alembic/         migrations
tests/           MVP critical tests
```

## Required environment variables

Must be set before first run:

- `DATABASE_URL`
- `POSTGRES_PASSWORD`
- `ADMIN_API_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS` - numeric Telegram user IDs, comma-separated
- `TRAVELPAYOUTS_API_TOKEN`

## Local start with Docker Compose

1. Create `.env`: `make init-env`, then fill in secrets.
2. Validate compose config: `make docker-config`
3. Start services: `make docker-up`
4. Apply migrations: `make migrate`
5. Run smoke checks: `make smoke`
6. Start chatting with the bot in Telegram.

## Local start with venv

1. Create `.env`: `make init-env`.
2. Create a venv and install deps: `make install`
3. Start PostgreSQL separately or via Docker Compose.
4. Run migrations: `.venv/bin/alembic upgrade head`
5. Run API: `.venv/bin/python -m app.main_api`
6. Run worker in another terminal: `.venv/bin/python -m app.main_worker`

## Main bot commands

- Bot management flows are intended to run in a private chat with the bot.
- `/start`
- `/new`
- `/subscriptions`
- `/cancel`

During `/new`:

- date selection supports inline calendar or manual input like `01.06.2026` and `2026-06-01:2026-06-12`
- max price supports examples like `45000`, `45 000`, `45`, `45к`, or `-`

## Admin API

- `GET /health/live`
- `GET /health/ready`
- `GET /admin/subscriptions`
- `POST /admin/subscriptions/{subscription_id}/check`
- `GET /admin/subscriptions/{subscription_id}/offers`
- `GET /admin/checks`
- `GET /admin/notifications`

All admin endpoints except health require header `X-Admin-Token`.

## Health checks and smoke test

Quick checks after startup:

1. `curl -fsS http://127.0.0.1:8000/health/live`
2. `curl -fsS http://127.0.0.1:8000/health/ready`
3. `curl -fsS -H "X-Admin-Token: <token>" http://127.0.0.1:8000/admin/subscriptions`
4. Send `/start` to the bot.
5. Create one test subscription with `/new`.
6. Trigger manual check from the bot UI.

Or run `make smoke` after migrations. This smoke command executes the checks from inside the `api` container, so it is reliable even if local Docker networking or host port forwarding behaves differently on your machine.

## Tests

Critical MVP tests cover:

- Travelpayouts response parsing/normalization
- dedupe and alert rules
- subscription validation rules

Run with:

```bash
make test
```

## Troubleshooting

### `docker compose` fails because `.env` is missing

Create it first:

```bash
make init-env
```

### `health/ready` fails

- Check that PostgreSQL container is healthy.
- Ensure `DATABASE_URL` matches the DB credentials from `.env`.
- Run migrations with `make migrate`.

### Bot starts but does not answer

- Verify `TELEGRAM_BOT_TOKEN`.
- Check that your Telegram user id is present in `TELEGRAM_ALLOWED_USER_IDS`.
- Make sure you are talking to the bot in a private chat, not in a group.
- Telegram group privacy mode can pass `/new` but suppress the next plain-text reply in the dialog.
- Check worker logs: `make docker-logs`.

### Admin API returns `401`

- Send header `X-Admin-Token`.
- Ensure it matches `ADMIN_API_TOKEN` in `.env`.

### No offers are found

- This can be a valid cached API result.
- Try broader date ranges, higher `max_price`, or disable direct-only filtering.

## Notes

- The bot is the main UI.
- FastAPI is a technical layer for health-checks, admin debugging, and future web UI.
- The service uses cached Travelpayouts / Aviasales Data API, not live search.
- Offer timestamps reflect cached/provider data or bot observations:
  - `provider_found_at` means when the offer was found in the provider cache, only if the API actually returns it.
  - `first_seen_at` means when the bot first saved the offer.
  - `last_seen_at` means when the bot last saw the offer.
  - `observed_at` means the time of a concrete price observation by the bot.
- These timestamps are not purchase timestamps and should not be interpreted as booking or checkout events.
- Baggage filtering is stored in the subscription but is not enforced against Data API because the cache API does not expose a reliable baggage filter.
