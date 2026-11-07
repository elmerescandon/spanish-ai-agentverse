.PHONY: install dev dev-frontend run format lint test test-live check demo

install:
	uv sync
	uv run pre-commit install
	bun install --cwd frontend

dev:
	uv run watchfiles "python -m backend.main" backend

dev-frontend:
	bun run --cwd frontend dev

run:
	uv run python -m backend.main

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run mypy backend
	bun run --cwd frontend lint
	bun run --cwd frontend typecheck

test:
	uv run pytest
	bun run --cwd frontend test

test-live:
	uv run pytest -m live

check: format lint test

demo: test-live run
