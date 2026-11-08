.PHONY: install dev dev-frontend run parse format lint test test-extended test-live check clear-cache demo demo-peers sample-protocol

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

parse:
	uv run python -m backend.agents.parser $(PDF)

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

test-extended:
	uv run pytest -m 'not live'
	bun run --cwd frontend test

test-live:
	uv run pytest -m live -o log_cli=true --log-cli-level=INFO

check: format lint test

# Forget saved analyses so the next upload calls Gemini again
clear-cache:
	rm -rf data/cache

demo: test-live run

# Re-fetch the demo's peer trials into data/peers (needs network)
demo-peers:
	uv run python -m backend.agents.protocol_comparison.demo

sample-protocol:
	uv run python scripts/make_sample_protocol.py
