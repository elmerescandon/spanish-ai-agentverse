# CLAUDE.md

Follow all rules in CONVENTIONS.md. They apply to every line you write or change.

@CONVENTIONS.md

## Commands

- `make install`: set up after cloning
- `make dev`: run agents with hot reload
- `make check`: format + lint + test; run before saying a change is done
- `make test-live`: live tests against real APIs (only when asked)

## Working rules

- Read the relevant agent folder and `backend/shared/messages.py` before changing an agent.
- Never change `backend/shared/messages.py` or `backend/api/` without flagging it: other people's code depends on them.
- Keep diffs small and focused on the task; no drive-by refactors.
- Mark deliberate shortcuts with `# [TO REFACTOR:(name)]: reason`.
