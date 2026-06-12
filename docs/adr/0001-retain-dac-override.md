# ADR 0001: Retain DAC_OVERRIDE for bind-mounted workspace writes

## Status

Accepted

## Context

RepoAirlock runs the agent command in Docker with conservative defaults:
`--cap-drop ALL`, no Docker privileged mode, `--security-opt no-new-privileges`,
`--network none`, a read-only root filesystem, and explicit resource limits.

The workspace is a host-side detached git worktree bind-mounted into the
container at `/workspace`. On GitHub Actions hosted Linux runners, files in that
worktree are owned by the runner user, typically uid 1001. The process inside
the container runs as root by default, but after `--cap-drop ALL` it cannot
reliably write to those bind-mounted files when discretionary access control
blocks the write. Full Docker E2E failed until the container retained enough
permission to write to the mounted workspace.

## Decision

RepoAirlock keeps `--cap-drop ALL` and then adds back only
`--cap-add DAC_OVERRIDE`.

This preserves the intended Tier 0 behavior: the agent can modify the detached
workspace mounted at `/workspace`, while Docker privileged mode, host network
mode, Docker socket mounts, host root mounts, and broad capabilities such as
`SYS_ADMIN`, `NET_ADMIN`, and `SYS_PTRACE` remain rejected.

## Risks

- `DAC_OVERRIDE` lets processes inside the container bypass normal Unix file
  permission checks for paths visible inside the container.
- If a future configuration mounts additional host paths, this capability would
  apply to those visible paths too.
- This is not equivalent to a strict "no capabilities" sandbox. Documentation
  must not claim that containers run "without privileges" in an absolute sense.

The current blast radius is constrained by the default mount set: the detached
workspace, tmpfs paths, and container filesystem view. RepoAirlock continues to
reject Docker privileged mode, Docker socket mounts, and host root mounts.

## Alternatives Considered

### Drop all capabilities and run as the host uid

This would avoid `DAC_OVERRIDE`, but it requires mapping the correct host uid
and gid into every supported environment. Hosted CI, local Linux, and Docker
Desktop differ here, and the option adds platform-specific setup to the default
path.

### Chown or chmod the detached worktree before running the container

This keeps the container capability set smaller, but it mutates the worktree
permissions before agent execution and adds cleanup risk. It can also interact
poorly with shared checkouts, filesystems with limited ownership support, and
Docker Desktop file sharing.

### Copy the workspace into the container and copy the result out

This avoids host bind-mount write permissions, but it loses the simple detached
worktree model and increases complexity around git metadata, large repositories,
incremental patch export, and cleanup.

### Use a Docker volume instead of a host bind mount

This gives Docker control over ownership, but it makes patch export and replay
less direct because RepoAirlock must synchronize repository contents into and
out of the volume.

## Consequences

RepoAirlock documentation and reports should describe the sandbox as "without
Docker privileged mode" and "all capabilities dropped except `DAC_OVERRIDE`",
not as "without privileges". If future releases support configurable users,
copy-in/copy-out workspaces, or rootless runtimes, this ADR should be revisited.
