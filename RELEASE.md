# RepoAirlock v0.1.1-alpha Release Notes

RepoAirlock v0.1.1-alpha is the first packaged alpha release prepared for
GitHub Releases and Python package indexes.

Package index note: the project version is declared as `0.1.1-alpha`; Python
packaging normalizes this prerelease to `0.1.1a0` in built distributions.

## Highlights

- Tier 0 process-wrapper pipeline remains the supported CLI path.
- Tier 0 alpha verification status is reflected in both READMEs.
- README now includes demo screenshots for the HTML report, audit trail, and
  CLI output.
- The architecture diagram now uses Mermaid instead of ASCII art.
- Python package metadata is prepared for PyPI/TestPyPI publication.
- Build and release workflow added for `python -m build`, `twine check`, and
  PyPI Trusted Publishing.

## Included Capabilities

### Core Pipeline (`repoairlock run`)

- Detached git worktree isolation: the agent never runs in the original working
  tree (INV-001).
- Docker sandbox with safe defaults: no network, no privileged mode, resource
  limits, and restricted Linux capabilities.
- Structured event recording in `events.jsonl`.
- Patch export with SHA-256 integrity verification.
- Optional verifier command execution.
- Automatic cleanup with manual cleanup instructions if cleanup fails.
- Best-effort JSON and HTML report generation.

### Inspection and Reproducibility

- `repoairlock inspect <run-id>` shows run metadata, artifacts, integrity, and
  INV-001 status.
- `repoairlock replay <run-id>` validates artifact integrity and replays the
  patch without re-invoking the agent.
- `repoairlock compare <a> <b>` compares two recorded runs.
- `repoairlock list` lists recorded runs.

### Safety

- Docker privileged execution and Docker socket mounts are rejected.
- Full host environment passthrough is not allowed.
- Source workspace fingerprints are checked before and after runs.
- Tampered patches are detected before replay.
- Dangerous Docker configuration is rejected before sandbox construction.

## Installation

After publication:

```bash
python3.12 -m pip install repoairlock
repoairlock --version
repoairlock doctor
```

For local development:

```bash
git clone https://github.com/ZedingZhang/repoairlock.git
cd repoairlock
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
repoairlock doctor
```

## Known Limitations

- Docker daemon is required.
- Linux is the primary target; macOS is supported through Docker Desktop with
  different filesystem and resource semantics.
- No native Windows support.
- Tier 0 cannot observe internal agent tool calls, LLM tokens, or per-command
  reasoning.
- Network filtering is limited to on/off.
- Claude Code Tier 2 hook adapter remains preview-only.

## Full Changelog

See [CHANGELOG.md](CHANGELOG.md).
