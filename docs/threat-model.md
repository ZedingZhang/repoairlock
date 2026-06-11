# PatchGuard Threat Model

## Protected Assets

1. User's original Git working tree
2. User's host filesystem
3. User's credentials and environment variables
4. User's network environment
5. User's CPU, memory, disk, and process resources
6. Integrity of the execution trace
7. Traceability of exported patches

## Trust Boundaries

### Untrusted
- Commands generated or executed by the coding agent
- Scripts, tests, Makefiles, package scripts, and dependency install scripts in the repaired repo
- Code after agent modification
- Structured fields in agent output (unless schema-validated)
- Processes inside the container

### Limited Trust
- Local Git and Docker CLI
- PatchGuard's own process
- PatchGuard configuration files
- User-explicitly-provided agent command

## Risks Explicitly Mitigated (MVP)

| Risk | Mitigation |
|------|-----------|
| Modification of original working tree | Detached git worktree + pre/post fingerprints |
| Deletion of files outside the repo | Container isolation + read-only rootfs |
| Unrestricted container resources | CPU, memory, PID limits |
| Full host environment leaked to agent | Env allowlist |
| SSH keys, cloud credentials exposed | Not mounted by default |
| Unrestricted network access | Default `--network none` |
| Privileged containers | Blocked at Docker command builder level |
| No audit trail | Minimum manifest + events on every run |
| Untraceable patches | Patch stored with SHA-256 integrity hash |
| Orphaned worktrees/containers | Cleanup on all exit paths |

## Risks NOT Fully Mitigated (MVP)

- Container escape
- Docker daemon vulnerabilities
- Supply chain attacks
- Data exfiltration when network is explicitly enabled
- Malicious kernel or host
- Cross-platform behavioral differences
- Full observability of all agent internal actions (Tier 0 limitation)
