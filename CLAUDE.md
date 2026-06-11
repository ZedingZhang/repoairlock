# PatchGuard Engineering Rules

## Product boundary
PatchGuard is a safety-oriented execution harness for coding agents. It is not a coding agent. Do not add LLM orchestration, code repair logic, autonomous planning, retrieval, memory, or multi-agent features.

## Non-negotiable invariants
- Never mutate the user's original working tree.
- Never silently fall back to local execution.
- Never pass the full host environment into a sandbox.
- Never enable privileged Docker execution.
- Never mount the Docker socket.
- Always produce minimum artifacts on failure.
- Replay must not rerun the agent unless explicitly requested by a distinct rerun command.

## Scope discipline
Implement only the requested phase from docs/design.md. Do not pre-create speculative modules. Do not introduce a database, web UI, remote service, Kubernetes, or extra framework unless the design document is intentionally revised first.

## Code quality
- Python 3.12+
- Strict typing for public interfaces
- subprocess argv lists; avoid shell=True unless a verifier command explicitly requires a shell and the risk is documented
- Pydantic models reject unknown fields
- Every security rule needs positive and negative tests
- Every cleanup path must be testable

## Required checks
Run before finishing each phase:
- ruff check .
- mypy src
- pytest -q

## Documentation
Update docs/progress.md after each phase. Record deviations as ADRs instead of silently changing architecture.
