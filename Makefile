.PHONY: install dev run format lint test test-live check demo

install:
	uv sync
	uv run pre-commit install

dev:
	uv run watchfiles "python -m backend.main" backend

run:
	uv run python -m backend.main

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run mypy backend

test:
	uv run pytest

test-live:
	uv run pytest -m live

check: format lint test

demo: test-live run
