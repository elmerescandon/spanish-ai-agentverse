# spanish-ai-agentverse

Our multi-agent project for the Agentverse UCL hackathon. The frontend lives in `frontend/` and the backend (API + agents) in `backend/`.

## Setup

You need [uv](https://docs.astral.sh/uv/) installed.

```bash
make install          # installs Python 3.14, dependencies and pre-commit hooks
cp .env.example .env  # then fill in the keys
make dev              # runs the backend with hot reload
```

## Before you push

```bash
make check            # format + lint + test
```

Read [CONVENTIONS.md](CONVENTIONS.md) before writing code. It covers naming, typing, tests and the git workflow.
