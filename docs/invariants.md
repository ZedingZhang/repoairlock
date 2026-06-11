# AgentFence Invariants

> All invariants must be covered by automated tests.

## INV-001 Original workspace immutability

No execution path may modify the user's original working tree.

**Test requirements:**
- Clean repo: worktree created and removed without altering original
- Dirty repo: uncommitted changes survive execution
- Untracked files: not deleted or modified
- Agent modifies temp worktree aggressively: original stays intact

## INV-002 No silent local execution

When the isolation backend is unavailable, `agentfence run` must fail.

**Test requirements:**
- Docker unavailable → run fails with clear error
- No local execution fallback is exposed by the CLI

## INV-003 Every run has a unique identity

Every run must have a non-colliding `run_id`. All events, logs, artifacts,
and temporary resources must be bound to that ID.

**Test requirements:**
- Two rapid successive runs get different IDs
- Run ID embedded in all artifacts

## INV-004 Every run is auditable

Even if the agent fails to start, times out, is policy-blocked, or the
container crashes, a minimal `manifest.json`, `events.jsonl`, and error
status must be written.

**Test requirements:**
- Failed agent → manifest and events exist
- Timeout → manifest and events exist
- Policy block → manifest and events exist

## INV-005 No sensitive env var injection by default

Environment variables use an allowlist. The full host environment must
never be passed by default.

**Test requirements:**
- Default container env only contains allowed variables
- Explicit `--env-allow` works
- Manifest records names, not values

## INV-006 Network disabled by default

MVP defaults to no-network mode. Network must be explicitly enabled via
config or CLI flag, and recorded in the manifest.

**Test requirements:**
- Default container has no network
- `--network bridge` enables network
- Manifest records network mode

## INV-007 Containers must not use privileged mode

`--privileged`, Docker socket mounts, host root mounts, and unnecessary
capabilities are forbidden.

**Test requirements:**
- Docker command builder rejects privileged flag
- Docker command builder rejects docker socket mount
- Docker command builder rejects host root mount

## INV-008 Artifacts are immutable

Existing run directories must not be overwritten. Export artifacts using
atomic write (write to .tmp, fsync, rename).

**Test requirements:**
- Creating a run with existing ID fails
- Atomic write produces valid file or no file, never half-written

## INV-009 Schema is versioned

Manifest, events, report, and configuration must all include a schema version.

**Test requirements:**
- Manifest includes schema_version
- Events include schema_version
- Unknown schema version is rejected on read

## INV-010 Replay != re-execute agent

`replay` reconstructs views, replays events, and verifies patch artifacts
by default. It must not invoke the agent. Re-execution requires a separate
`rerun` command.

**Test requirements:**
- `replay` does not spawn agent process
- `replay` applies patch to a fresh worktree
