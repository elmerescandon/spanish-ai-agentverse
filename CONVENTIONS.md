# Team Coding Conventions — Agentverse UCL Hackathon

**Hackathon rule:** build the core flow end to end first, then add features one at a time in priority order, in parallel preferably.

## Tooling

Automate formatting so the repo is standardised.

- **`uv`** manages Python and dependencies; `uv.lock` and `.python-version` (Python 3.14, via `uv python pin 3.14`) are committed.
- **`ruff`** formats and lints. `ruff format` + `ruff check --fix` before every commit.
- **79 characters per line, unless justified.** `ruff format` wraps code to 79, and `ruff check` (rule `E501`) fails on anything the formatter can't wrap: long strings, comments and docstrings. Split long strings with implicit concatenation and long comments over several lines. When a line genuinely can't be split (a verbatim quote a test must match, a generated value), justify it on that line: `# noqa: E501  verbatim protocol quote`. A bare `# noqa: E501` with no reason doesn't pass review. Comments that end in a long URL are allowed automatically.
- **`mypy`** checks types.
- **`pre-commit`** runs all three on commit. Don't bypass with `--no-verify`.
- **`Makefile`** holds every command (table below). New recurring command → new target.
- **`make dev` auto-restarts agents on save** (via `watchfiles`), so the edit-run loop takes seconds.
- **GitHub Actions CI** checks formatting, lint, types and the full test suite on every PR and push to main, so a broken `main` is caught before merge, not at the demo.
- **`scratch/` is gitignored** for notebooks and throwaway experiments. Prototype there, then move clean code into the package.

## Commands, pre-commit and CI

| Command | What it does |
| --- | --- |
| `make install` | `uv sync` + install pre-commit hooks + `bun install --cwd frontend`. Run once after cloning. |
| `make dev` | Run agents with hot reload. |
| `make dev-frontend` | Run Next.js frontend dev server via Bun. |
| `make format` | `ruff format` + `ruff check --fix`. |
| `make lint` | `ruff check` + `mypy` + frontend `eslint` + `next typegen && tsc --noEmit`. |
| `make test` | All backend (`pytest`) and frontend (`bun test`) tests except live and extended ones. Fast; part of `make check`. |
| `make test-extended` | Everything `make test` runs plus slow `@pytest.mark.extended` checks (e.g. reading the real demo PDFs). CI runs the same set. |
| `make check` | format + lint + test in one go. Run before every push. |
| `make test-live` | Live tests against real APIs. |
| `make run` | Run agents once, no reload. |
| `make demo` | `test-live`, then run. Use this on stage. |

**Pre-commit hooks** (on every `git commit`): `ruff format`, `ruff check --fix`, `mypy`. Tests stay out of pre-commit to keep commits fast; CI runs them.

**CI** in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every pull request (and each new commit to it) and on merge into `main`. Each check is its own named step, so a red run shows which one failed: formatting (`ruff format --check`), lint (`ruff check`, including the 79-character limit), types (`mypy`), tests (`pytest`, live tests skipped). It installs with `uv sync --locked`, so a stale `uv.lock` fails CI: run `uv sync` locally and commit the lock file.

Turn on branch protection for `main` so a red CI blocks the merge.

## Typing and naming

- **Type every function signature and class attribute.** No untyped `def`. Avoid `Any`; if you must, comment why. Use modern syntax: `list[str]`, `X | None` (enable ruff's `UP` rules to enforce it).
- **Structured data is a typed object**, not a loose `dict`: Pydantic `BaseModel` at boundaries, `@dataclass` internally.
- **A fixed set of values is an `Enum` or `Literal`**, not a raw string: `Urgency.HIGH`, not `"high"`. Typos become type errors.
- **No obscure abbreviations.** Meaning should be clear from reading the code. `patient_count`, not `pc`. Common ones are fine: `id`, `url`, `llm`, `api`, `db`. Never chain them: `usr_cfg_mgr` → `user_config_manager`.
- **Names say what the thing is or does.** Rules of thumb, not laws: functions read as actions (`fetch_patient_record`), booleans read as yes/no questions (`is_urgent`, not `urgent`).
- **Units in names** when they matter: `timeout_seconds`, `price_gbp`, `distance_km`.
- Case: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants, declared at the top of the file with a comment if the value isn't self-explanatory.

```python
def fetch_patient_record(
    patient_id: str, timeout_seconds: float = 10.0
) -> PatientRecord: ...
```

## Structure, constants and config

- **Encapsulate and reuse.** Logic used twice lives in one function. Search before you write a new helper.
- **Small functions that do one thing.** If you need "and" to describe it, split it. But don't over-split: a 20-line function that reads top to bottom beats five 4-line helpers you have to jump between.
- **Pure logic in the middle, side effects at the edges.** Network, LLM and file I/O go in thin wrappers; core logic takes data in and returns data out.
- **Constants in `UPPER_SNAKE_CASE` at the top of the module**, with a comment if the value isn't self-explanatory. No magic numbers inline.
- **Config out of code.** Secrets in `.env` (never committed); commit `.env.example` listing every key.
- **No dead or commented-out code.** Git remembers it.

```python
MAX_RETRIES = 3
LLM_TIMEOUT_SECONDS = (
    30  # upper bound so a hung LLM call can't stall the agent
)
URGENCY_THRESHOLD = 0.7  # score above which triage escalates to a doctor
```

## Errors and validation

- **Fail loudly.** No bare `except:`, no `except Exception: pass`. Catch specific exceptions, and log or re-raise.
- **Error messages say what was expected and what was received:** `ValueError(f"score must be in [0, 1], got {score}")`, not `ValueError("bad score")`.
- **Validate at the boundary.** Anything from outside (uploaded files, API responses, LLM output, user input) is parsed into a Pydantic model before use. Inside, code is still fully typed, but doesn't re-check data that was already validated.
- **`assert` for internal invariants only**, things that can't happen if our code is correct: `assert 0 <= score <= 1`. Never for validating outside input: `python -O` strips asserts.
- **Timeouts and retries on every external call**, especially LLM calls. Retry with backoff; give up after `MAX_RETRIES`.
- **Agents fail loudly to their caller.** An agent's entry point raises a specific exception, listed in its docstring; the caller (API or orchestrator) logs the traceback and turns it into a visible error, so a review never hangs or silently returns nothing.
- **Use `logging`, not `print`.** Include the agent name and the relevant ids in log lines. Format: what happened, then the state as key=value: `logger.info("triage scored: patient_id=%s score=%.2f", patient_id, score)`.

## Tests

Tests check the logic thoroughly and intelligently, not just line coverage.

- **Test behaviour, not implementation.** Assert on outputs and effects, not on which private function was called.
- **Hit the edges:** empty input, malformed input, boundary values (exactly at a threshold), an LLM returning garbage or timing out.
- **Mock the LLM and network** so tests are fast and deterministic. One optional live smoke test is fine, marked `@pytest.mark.live`: skipped by default and in CI, run by hand with `make test-live` (real keys from `.env`) before the demo. `make demo` runs it first, so the demo can't start without it passing.
- **The demo path must have an end-to-end test.** It's the one flow that can't break at 3am.
- **Test names describe the scenario:** `test_triage_escalates_when_score_above_threshold`, not `test_triage_2`.
- **A bug fix comes with a test** that would have caught it.

### Frontend testing (`bun test` + React Testing Library)

Frontend tests live in `frontend/src/__tests__/` and focus on **functional workflows and contract alignment** — making sure core user journeys and API schemas don't break, rather than exhaustive UI edge cases.

- **Native `bun:test` runner:** Preloaded via `frontend/bunfig.toml` and `frontend/src/__tests__/setup.ts` (which provides `jsdom`, `@testing-library/jest-dom` matchers, automatic DOM `cleanup()`, browser API stubs like `ResizeObserver` / `IntersectionObserver` / `matchMedia`, and default `next/navigation` App Router mocks).
- **Cross-stack schema & contract alignment (`contract.test.ts`):** `frontend/src/__tests__/contract.test.ts` extracts the live OpenAPI schema from FastAPI (`backend.main:app.openapi()`) and asserts that enum values, model property keys, component fallback data, and test fixtures in `frontend/src/__tests__/fixtures.ts` match `backend/api/schemas.py`. Any schema change in `backend/api/` must update `frontend/src/lib/api.ts` and `fixtures.ts` in the same PR.
- **Query by user-visible roles and text:** Use `screen.getByRole`, `screen.getByText`, and `screen.queryByText` (for asserting absence) rather than CSS classes or DOM structure, and drive interactions with `userEvent.setup()`.
- **Clean up mocks and timers:** Call `mock.restore()` in `beforeEach`, keep interactive state in `"use client"` components, and always clear `setTimeout` / `setInterval` timers in `useEffect` cleanup functions so async work never leaks across tests.

## Comments

- **Comments explain why, not what.** If you need to explain what, rename or split the code.
- **Docstrings where the name and types don't tell the whole story:** side effects, non-obvious behaviour, what it raises. `get_patient_id()` needs none; `score_triage()` with an LLM call and a fallback does.
- **Tag deliberate shortcuts and things to fix later** as `# [TO REFACTOR:(name)]: reason` so we can find them with one grep after the demo.

## Git & GitHub

- **`main` always runs and is always demoable.** Never push directly to it.
- **Short-lived branches** named `name/short-description` (e.g. `theo/triage-retry`).
- **Small PRs**, glanced over by one teammate. Fast review beats thorough review this weekend. The PR description points to the one or two spots that need eyes; the reviewer checks those, and always any change to `shared/messages.py`.
- **No reviewer free within X minutes? Merge it yourself** once CI is green, and say so in the chat. Waiting is the most expensive thing this weekend.
- **Commit messages say what and why** in the imperative: `add triage agent retry on timeout`, not `fix stuff`.
- **Before every `git pull`**: check `git status` and run `make check`. If it fails, report and stop. If it passes, run `git pull` and then run `make check` again to validate the updated code.

**PR template** in `.github/pull_request_template.md`. It isn't created for you: commit the file once, and from then on GitHub pre-fills every new PR description with it:

```markdown
## What
One or two sentences on what this PR does.

## Changes
- Feature or fix implemented

## Look at
- `path/to/file.py:42`: why this spot needs eyes

## Tested
- [ ] `make test` passes
- [ ] Tried it locally (how)
```

## AI coding tools

Everyone's AI agent follows these rules too, or we get four styles.

- Add `CLAUDE.md` and `AGENTS.md` at the repo root (Cursor reads `AGENTS.md`), each containing: `Follow all rules in CONVENTIONS.md.` plus the run/test commands.
- **You own what your AI writes.** Read the diff before committing; the same rules apply to generated code.

## Project layout

Frontend and backend split; inside the backend, one folder per agent. See [PROJECT.md](PROJECT.md) for the concrete agent definitions, domain models, and project architecture.

```text
.
├── frontend/                 # UI; talks to backend/api only
├── backend/
│   ├── api/                  # HTTP routes the frontend calls
│   ├── agents/
│   │   └── <agent_name>/
│   │       ├── agent.py      # async entry points callers use: I/O wiring
│   │       ├── logic.py      # pure functions, no I/O
│   │       └── prompts.py    # prompt constants
│   ├── clients/              # LLM + external API wrappers: timeouts, retries
│   ├── shared/
│   │   ├── messages.py       # every shared data model: the contract
│   │   └── config.py         # loads .env into typed settings
│   └── main.py               # starts API + agents
├── tests/
│   ├── backend/              # mirrors backend/
│   └── test_demo_path.py     # end-to-end demo flow
├── scratch/                  # gitignored
├── Makefile
├── pyproject.toml
├── .env.example
├── PROJECT.md
├── CONVENTIONS.md
├── CLAUDE.md
└── AGENTS.md
```

- **The frontend talks only to `backend/api`**, never to agents directly. The API is the one contract the frontend depends on.
- **Every external call goes through `clients/`**: one place for timeouts, retries and mocking in tests.
- **Agents import from `shared/` and `clients/`, never from each other.** The API or orchestrator calls each agent's async entry point directly (e.g. `await parse_protocol(...)`, several at once with `asyncio.gather`) and passes `messages.py` models between them.
- **New agent = copy an existing folder**, rename, add its tests. Frontend tests live in `frontend/` with its own tooling.

## Agents

See [PROJECT.md](PROJECT.md) for the concrete agent inventory, responsibilities, and interaction flows.

- **All shared data models live in one module** (`shared/messages.py`). It is the contract between agents: changes go through the team, not one person's branch.
- **One clear role per agent**, describable in one sentence ("triages symptoms and escalates urgent cases" is fine). Put that sentence in the agent's module docstring. Don't split further than you need: every extra agent is more messages to define and debug.
- **Entry points are safe to call twice.** A retried call must not double-charge, double-send or double-write.
- **Prompts live in their own files or constants**, since you'll tweak them all weekend and want them in one place. A one-line instruction inline is fine; anything longer goes in the agent's `prompts.py`.
