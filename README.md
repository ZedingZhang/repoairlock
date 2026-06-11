# RepoAirlock

Safety-oriented execution harness for coding agents.

English | [中文](README.zh-CN.md)

## Problem

Coding agents modify code autonomously. Without isolation, recording, and
policy enforcement, it is difficult to answer basic questions:

- What did the agent do?
- Did it touch anything outside the repo?
- Can we replay its changes?
- Was the original workspace preserved?

RepoAirlock answers these questions through isolation, structured audit trails,
and reproducible artifacts.

## What RepoAirlock Does

RepoAirlock runs coding agents inside isolated Docker containers with git
worktree isolation, records structured execution traces, enforces safety
policies, and exports reproducible artifacts — all without modifying the
user's original working tree.

## Capability Tiers

| Tier | Name | What You Get |
|------|------|-------------|
| 0 | Process Wrapper | Container isolation, artifact recording, patch export, resource monitoring, HTML reports |
| 1 | Structured Events | Import agent tool-call traces for process quality metrics |
| 2 | Enforcement (preview only) | Pre-execution policy checks on individual tool calls (Bash/Edit/Write) via Claude Code hook adapter |

**Current status:** v0.1.0 alpha release candidate. Tier 0 stabilization in progress.
Claude Code Tier 2 hook adapter module is preview only; the v0.1 CLI `run` path
uses the command adapter.

## 5-Minute Demo

```bash
# 1. Install
git clone https://github.com/ZedingZhang/repoairlock.git && cd repoairlock
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Check your environment
repoairlock doctor

# 3. Run an agent in the sandbox
repoairlock run \
  --repo examples/demo-repo \
  --image alpine:latest \
  -- sh -c "echo 'print(\"Hello, RepoAirlock!\")' > /workspace/hello.py"

# 4. Inspect the results
repoairlock list
repoairlock inspect <run-id>

# 5. Replay the patch (no agent re-invocation)
repoairlock replay <run-id> --repo examples/demo-repo

# 6. Compare two runs
repoairlock compare <run-a> <run-b>

# 7. View the HTML report
open ~/.repoairlock/runs/<run-id>/report.html
```

## Safety Guarantees

- Agent never runs in the user's original working tree (INV-001)
- Containers run without network, without privileges, with CPU/memory/PID limits by default
- Environment variables are injected via explicit allowlist — never the full host environment
- Every sandbox execution attempt produces auditable artifacts (manifest, events, logs, patch, report) even on failure
- Original workspace fingerprints are verified before and after every run
- Patch integrity verified via SHA-256 before replay
- Sandbox-configuration policy enforcement rejects dangerous Docker parameters at construction time
- Command-level enforcement is only active when the Tier 2 Claude Code hook adapter is used

## Explicit Non-Guarantees

RepoAirlock **does not** and **cannot** guarantee:

- Prevention of container escape (this is a property of the Docker runtime)
- Observability of all agent internal actions at Tier 0
- Protection against actively malicious code inside the container
- Absolute isolation (Docker is a process-level boundary, not a hardware boundary)
- Network egress filtering beyond on/off at Tier 0

RepoAirlock is a **safety harness**, not a security sandbox. When you explicitly
enable network access (`--network bridge`), the agent can make outbound connections.

## Architecture

```
                        ┌────────────────────────────┐
                        │        repoairlock CLI       │
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

Run `repoairlock run --repo examples/demo-repo --image alpine -- sh -c "..."` to generate an HTML report with these sections:

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
| `claude_code` | 2 (preview only) | Claude Code hook adapter module — PreToolUse policy enforcement + PostToolUse recording; CLI wiring is not exposed in v0.1 |

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
| 8 | Done | Claude Code Tier 2 hook adapter module |
| 9 | In progress | Stabilization + public release |

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

RepoAirlock is a safety harness for coding agents. It does **not** perform code
generation, LLM inference, or autonomous repair. It does **not** guarantee
"complete security" or "absolute isolation." It provides a structured,
auditable, and reproducible execution environment so that agent actions
can be reviewed, replayed, and compared.
