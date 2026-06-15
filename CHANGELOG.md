# Changelog

All notable user-facing changes are recorded here.

## v0.1.1-alpha - 2026-06-15

### Added

- README badges for CI, PyPI version, supported Python versions, and license.
- Demo screenshots for HTML report, audit trail, and CLI output.
- Mermaid architecture diagram in both English and Chinese READMEs.
- Python package metadata for project URLs and Python version classifiers.
- Package data configuration for `policy/defaults.yaml` and the HTML report
  Jinja template.
- Build and release workflow with `python -m build`, `twine check`, TestPyPI,
  PyPI, and Trusted Publishing jobs.

### Changed

- Project version synchronized to `0.1.1-alpha` in `pyproject.toml`,
  `repoairlock.__version__`, and report constants.
- README status updated from release-candidate language to
  `v0.1.1-alpha. Tier 0 alpha verified.`
- Release documentation split into this changelog and focused release notes in
  `RELEASE.md`.

### Notes

- Python packaging normalizes `0.1.1-alpha` to `0.1.1a0` in distribution
  filenames and PyPI metadata.
- Tier 2 Claude Code hook adapter remains preview-only.

## v0.1.0-alpha - 2026-06-11

### Added

- Initial Tier 0 process-wrapper implementation.
- Docker sandbox execution with worktree isolation.
- Artifact store with manifest, events, logs, patch, integrity hashes, and
  best-effort reports.
- `run`, `doctor`, `list`, `inspect`, `replay`, `compare`, and `cleanup` CLI
  commands.
- Policy engine infrastructure and default safety rules.
- Replay service with patch integrity validation.
- HTML and JSON report generation with capability-tier disclosure.
- Claude Code Tier 2 hook adapter module as preview-only.

### Verified

- Full Docker mount E2E passed on GitHub Actions `ubuntu-latest`
  (`26 passed, 0 failed`) via manual workflow dispatch.
