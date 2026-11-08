.PHONY: install dev run format lint test test-extended test-live check demo

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

test-extended:
	uv run pytest -m 'not live'

test-live:
	uv run pytest -m live -o log_cli=true --log-cli-level=INFO

check: format lint test

demo: test-live run
