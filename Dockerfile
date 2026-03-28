FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY README.md /app/README.md

RUN pip install --no-cache-dir .

RUN mkdir -p /app/var/log/flight-alerts

CMD ["python", "-m", "app.main_api"]
