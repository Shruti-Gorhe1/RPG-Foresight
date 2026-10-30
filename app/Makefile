.PHONY: help install dev worker migrate revision test lint compose-up compose-down

help:
	@echo "install       Create venv and install requirements"
	@echo "dev           Run FastAPI with reload (port 8010)"
	@echo "worker        Run the Temporal worker"
	@echo "migrate       Apply DB migrations (alembic upgrade head)"
	@echo "revision      Autogenerate a migration (m='message')"
	@echo "test          Run pytest"
	@echo "compose-up    Start full local stack (postgres, temporal, phoenix)"
	@echo "compose-down  Stop local stack"

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8010

worker:
	python -m workers.worker

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

test:
	pytest -q

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down
