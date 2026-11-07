# AGENTS.md

Read and follow all rules in [CONVENTIONS.md](CONVENTIONS.md) before writing code. They apply to every line you write or change.

## Commands

- `make install`: set up after cloning
- `make dev`: run agents with hot reload
- `make check`: format + lint + test; run before saying a change is done
- `make test-live`: live tests against real APIs (only when asked)

## Most important rules

- Type every function signature; no `Any` without a comment.
- Lines are at most 79 characters; a longer line needs a reason: `# noqa: E501  <reason>`.
- Clear names, no obscure abbreviations; constants in `UPPER_SNAKE_CASE` at the top of the file.
- Validate outside data with Pydantic at the boundary; fail loudly, no swallowed exceptions.
- Pure logic in `logic.py`, wiring in `agent.py`, external calls through `backend/clients/`.
- Tests check behaviour and edge cases, with the LLM mocked.
- Never change `backend/shared/messages.py` or `backend/api/` without flagging it: other people's code depends on them.
- Keep diffs small and focused on the task; no drive-by refactors.
