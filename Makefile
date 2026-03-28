PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
COMPOSE ?= docker compose
ENV_FILE ?= .env

.PHONY: init-env venv install test compile docker-config docker-up docker-down docker-logs migrate smoke clean

init-env:
	cp -n .env.example .env || true

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -e ".[dev]"

test:
	$(VENV_BIN)/python -m pytest tests

compile:
	$(PYTHON) -m compileall app alembic

docker-config:
	ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) config

docker-up:
	ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) up --build -d

docker-down:
	ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) down

docker-logs:
	ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) logs -f api worker db

migrate:
	ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) exec api alembic upgrade head

smoke:
	@ENV_FILE=$(ENV_FILE) $(COMPOSE) --env-file $(ENV_FILE) exec api python -c "import os, urllib.request; token = os.environ['ADMIN_API_TOKEN']; checks = [('/health/live', {}), ('/health/ready', {}), ('/admin/subscriptions', {'X-Admin-Token': token})]; [urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:8000{path}', headers=headers), timeout=5).read() for path, headers in checks]; print('Smoke test passed')"

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage .coverage.* *.egg-info
