# RepoAirlock v0.1.0 Alpha Release Candidate

## Overview

RepoAirlock v0.1.0 alpha release candidate is the first public preview of the RepoAirlock execution
harness for coding agents. It provides Tier 0 (Process Wrapper) capabilities:
container-based isolation, structured audit trails, policy enforcement for
Docker configuration, and reproducible artifacts including HTML reports.

Tier 2 (Enforcement) adapter for Claude Code is included as a preview.

## What's Included

### Core Pipeline (`repoairlock run`)
- Detached git worktree isolation — agent never touches the original working tree (INV-001)
- Docker sandbox with safe defaults: no network, no privileges, resource limits
- Full event recording: 21 event types written to structured JSONL
- Patch export with SHA-256 integrity verification
- Optional verifier command execution
- Automatic cleanup with manual cleanup instructions on failure
- HTML report generation with 8 standard sections

### Inspection & Reproducibility
- `repoairlock inspect <run-id>` — full run summary with INV-001 status
- `repoairlock replay <run-id>` — patch integrity check + replay without agent re-invocation
- `repoairlock compare <a> <b>` — structured comparison across 12 dimensions
- `repoairlock list` — browse past runs

### Safety
- 12 default policy rules (privileged containers, host network, Docker socket,
  destructive git, rm -rf /, curl|bash, git hooks, shell profiles, credential
  reading, fork bombs, long commands)
- Environment variable allowlist (never pass full host environment)
- Source workspace fingerprint verification before and after every run
- Tampered patch detection via SHA-256 integrity check
- All Docker forbidden options rejected at construction time

### Adapters
- `command` adapter (Tier 0): wraps any CLI agent as-is
- `claude_code` adapter (Tier 2 preview): PreToolUse policy enforcement via
  temporary hook configuration (never modifies user's global settings)

### Reports
- JSON report (`report.json`) — machine-readable structured data
- HTML report (`report.html`) — human-readable with color-coded findings,
  capability tier disclosure, and known visibility limits

## Installation

```bash
# Requires Python 3.12+
git clone <repo-url>
cd repoairlock
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
repoairlock doctor
```

## Quick Start

```bash
# Run an agent
repoairlock run --repo ./my-repo --image alpine:latest -- sh -c "echo patched > /workspace/file.txt"

# Inspect
repoairlock inspect <run-id>

# Replay
repoairlock replay <run-id> --repo ./my-repo
```

## Known Limitations

See [README.md](README.md#limitations) for the full list.

Key limitations in v0.1.0-alpha:
- Linux-first; macOS via Docker Desktop (different resource/FS semantics)
- No Windows native support
- Tier 0 cannot observe agent internal tool calls (stated in every report)
- Docker daemon required
- Network filtering limited to on/off

## What's NOT in v0.1.0-alpha

- Web UI or remote service
- Multi-tenancy or Kubernetes support
- Podman/buildah support
- Domain-level network filtering
- LLM token or turn-level metrics (requires Tier 1+)

## Compatibility

- Python: 3.12, 3.13
- Docker: 20.10+
- Git: 2.30+
- OS: Linux (primary), macOS via Docker Desktop

## Feedback

This is an early release. The project is designed as a portfolio piece
demonstrating safety-oriented infrastructure for coding agent execution.

Issues, questions, and contributions are welcome.
