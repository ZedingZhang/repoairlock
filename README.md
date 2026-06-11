# PatchGuard

Safety-oriented execution harness for coding agents.

## Problem

Coding agents modify code autonomously. Without isolation, recording, and
policy enforcement, it is difficult to answer basic questions:

- What did the agent do?
- Did it touch anything outside the repo?
- Can we replay its changes?
- Was the original workspace preserved?

PatchGuard answers these questions through isolation, structured audit trails,
and reproducible artifacts.

## What PatchGuard Does

PatchGuard runs coding agents inside isolated Docker containers with git
worktree isolation, records structured execution traces, enforces safety
policies, and exports reproducible artifacts — all without modifying the
user's original working tree.

## Capability Tiers

| Tier | Name | What You Get |
|------|------|-------------|
| 0 | Process Wrapper | Container isolation, artifact recording, patch export, resource monitoring, HTML reports |
| 1 | Structured Events | Import agent tool-call traces for process quality metrics |
| 2 | Enforcement | Pre-execution policy checks on individual tool calls (Bash/Edit/Write) |

**Current status:** Tier 0 complete (MVP). Tier 2 adapter for Claude Code implemented.

## 5-Minute Demo

```bash
# 1. Install
git clone <repo-url> && cd patchguard
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Check your environment
patchguard doctor

# 3. Run an agent in the sandbox
patchguard run \
  --repo examples/demo-repo \
  --image alpine:latest \
  -- sh -c "echo 'print(\"Hello, PatchGuard!\")' > /workspace/hello.py"

# 4. Inspect the results
patchguard list
patchguard inspect <run-id>

# 5. Replay the patch (no agent re-invocation)
patchguard replay <run-id> --repo examples/demo-repo

# 6. Compare two runs
patchguard compare <run-a> <run-b>

# 7. View the HTML report
open ~/.patchguard/runs/<run-id>/report.html
```

## Safety Guarantees

- Agent never runs in the user's original working tree (INV-001)
- Containers run without network, without privileges, with CPU/memory/PID limits by default
- Environment variables are injected via explicit allowlist — never the full host environment
- Every run produces auditable artifacts (manifest, events, logs, patch, report) even on failure
- Original workspace fingerprints are verified before and after every run
- Patch integrity verified via SHA-256 before replay
- 12 default policy rules deny destructive operations

## Explicit Non-Guarantees

PatchGuard **does not** and **cannot** guarantee:

- Prevention of container escape (this is a property of the Docker runtime)
- Observability of all agent internal actions at Tier 0
- Protection against actively malicious code inside the container
- Absolute isolation (Docker is a process-level boundary, not a hardware boundary)
- Network egress filtering beyond on/off at Tier 0

PatchGuard is a **safety harness**, not a security sandbox. When you explicitly
enable network access (`--network bridge`), the agent can make outbound connections.

## Architecture

```
                        ┌────────────────────────────┐
                        │        patchguard CLI       │
                        │  run / inspect / replay /   │
                        │  compare / list / doctor    │
                        └──────────────┬─────────────┘
                                       │
                             create RunContext
                                       │
                        ┌──────────────▼─────────────┐
                        │       Run Orchestrator      │
                        │  (full Tier 0 pipeline)     │
                        └───────┬───────────┬────────┘
                                │           │
                  ┌─────────────▼───┐   ┌──▼────────────────┐
                  │ WorkspaceManager │   │   ArtifactStore    │
                  │  git worktree    │   │  JSONL / JSON /    │
                  │  fingerprint     │   │  atomic writes     │
                  └─────────────┬───┘   └──▲───┬─────────────┘
                                │          │   │
                        ┌───────▼──────────┴───┴───────┐
                        │         SandboxBackend       │
                        │   DockerSandbox (safe args)  │
                        └───────┬──────────────────────┘
                                │
                  ┌─────────────▼──────────────┐
                  │        AgentAdapter         │
                  │  Tier 0: CommandAdapter     │
                  │  Tier 2: ClaudeCodeAdapter  │
                  └─────────────┬──────────────┘
                                │
              ┌─────────────────▼────────────────┐
              │ PolicyEngine   │ ReportGenerator │
              │ (12 rules)     │ (JSON + HTML)   │
              │ EventRecorder  │ CompareService  │
              └─────────────────────────────────┘
```

## Example Report

Run `patchguard run --repo examples/demo-repo --image alpine -- sh -c "..."` to generate an HTML report with these sections:

1. **Run Summary** — status, wall time, exit code, HEAD SHA
2. **Safety Posture** — network mode, privileged status, env allowlist, INV-001
3. **Repository Change Summary** — files/lines changed, sensitive path detection
4. **Verification Result** — verifier exit code (if configured)
5. **Resource Usage** — peak memory, avg CPU, peak PIDs, network I/O
6. **Quality & Policy Findings** — capability tier notice, safety findings
7. **Artifact Integrity** — SHA-256 hashes
8. **Replay Instructions** — exact command to reproduce

Every report explicitly states the capability tier and what conclusions
**cannot** be drawn at that tier.

## Supported Adapters

| Adapter | Tier | Description |
|---------|------|-------------|
| `command` | 0 | Any CLI agent — wraps command as-is for sandbox execution |
| `claude_code` | 2 | Claude Code — PreToolUse policy enforcement + PostToolUse recording |

## Development Roadmap

| Phase | Status | Deliverable |
|-------|--------|------------|
| 0 | Done | Repository scaffolding + constraints |
| 1 | Done | Artifact store + event logging |
| 2 | Done | WorkspaceManager + source repo protection |
| 3 | Done | DockerSandbox + doctor |
| 4 | Done | CommandAdapter + first complete run |
| 5 | Done | Inspect, replay, compare |
| 6 | Done | Metrics + HTML report |
| 7 | Done | Policy engine (12 default rules) |
| 8 | Done | Claude Code Tier 2 adapter |
| 9 | In Progress | Stabilization + public release |

See [docs/progress.md](docs/progress.md) for details.

## Limitations

- **Platform:** Linux-first. macOS via Docker Desktop is supported but resource
  limits, filesystem semantics, and performance differ. CI targets Linux.
- **Windows:** No native Windows support in v0.1.
- **Tier 0 visibility:** Cannot observe agent internal tool calls, LLM token
  usage, or per-command reasoning. The HTML report explicitly states this.
- **Network filtering:** Only on/off (`none`/`bridge`). No domain allowlisting.
- **Docker dependency:** Requires Docker daemon. Podman/buildah not yet supported.
- **PostToolUse testing:** The Claude Code Tier 2 adapter's PostToolUse recording
  requires a real Claude Code binary for full end-to-end testing.

## Running Tests

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest -q                    # unit + integration (skips Docker tests without daemon)
pytest -q tests/e2e          # e2e tests (requires Docker)
```

## Attribution

PatchGuard is a safety harness for coding agents. It does **not** perform code
generation, LLM inference, or autonomous repair. It does **not** guarantee
"complete security" or "absolute isolation." It provides a structured,
auditable, and reproducible execution environment so that agent actions
can be reviewed, replayed, and compared.
