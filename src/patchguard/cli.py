"""PatchGuard CLI — safety-oriented execution harness for coding agents."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer

from patchguard import __version__
from patchguard.constants import APP_NAME, DEFAULT_RUNS_DIR
from patchguard.core.orchestrator import RunConfig
from patchguard.exceptions import PatchGuardError

app = typer.Typer(
    name=APP_NAME,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"{APP_NAME} v{__version__}")
        raise SystemExit(0)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """PatchGuard — safety-oriented execution harness for coding agents.

    Runs coding agents in isolated environments, records full execution
    traces, enforces safety policies, and produces auditable artifacts.
    """
    if ctx.invoked_subcommand is None:
        raise typer.Exit()


@app.command()
def doctor() -> None:
    """Check that the local environment is ready for PatchGuard."""
    results: list[tuple[str, bool, str]] = []

    # --- Python ---
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 12)
    results.append(("Python >= 3.12", py_ok, py_version))

    # --- Git ---
    git_ok, git_detail = _check_git()
    results.append(("Git CLI available", git_ok, git_detail))

    # --- Docker CLI ---
    docker_ok, docker_detail = _check_docker_cli()
    results.append(("Docker CLI available", docker_ok, docker_detail))

    # --- Docker daemon ---
    daemon_ok, daemon_detail = _check_docker_daemon()
    results.append(("Docker daemon reachable", daemon_ok, daemon_detail))

    # --- Docker run test ---
    if daemon_ok:
        run_ok, run_detail = _check_docker_run()
        results.append(("Docker can run containers", run_ok, run_detail))
    else:
        results.append(("Docker can run containers", False, "daemon not available"))

    # --- Worktree test ---
    worktree_ok, worktree_detail = _check_worktree(git_ok)
    results.append(("Git worktree works", worktree_ok, worktree_detail))

    # --- Runs directory ---
    runs_ok, runs_detail = _check_runs_dir()
    results.append(("Runs directory writable", runs_ok, runs_detail))

    # --- Print results ---
    print("PatchGuard Doctor — environment check")
    print("=" * 50)
    for label, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok or detail:
            print(f"         {detail}")

    failures = sum(1 for _, ok, _ in results if not ok)
    if failures == 0:
        print("\nAll checks passed — PatchGuard is ready.")
    else:
        print(f"\n{failures} check(s) failed. Fix issues before running patchguard.")
        raise typer.Exit(code=1)


# -- helper functions for doctor -------------------------------------------


def _check_git() -> tuple[bool, str]:
    if shutil.which("git") is None:
        return False, "git not found in PATH"
    try:
        r = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=False, timeout=5
        )
        if r.returncode == 0:
            return True, r.stdout.strip().split("\n")[0]
        return False, "git --version failed"
    except subprocess.TimeoutExpired:
        return False, "git --version timed out"


def _check_docker_cli() -> tuple[bool, str]:
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        return False, "docker not found in PATH"
    try:
        r = subprocess.run(
            ["docker", "--version"], capture_output=True, text=True, check=False, timeout=5
        )
        if r.returncode == 0:
            return True, r.stdout.strip().split("\n")[0]
        return False, "docker --version failed"
    except subprocess.TimeoutExpired:
        return False, "docker --version timed out"


def _check_docker_daemon() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, check=False, timeout=10
        )
        if r.returncode == 0:
            return True, "daemon reachable"
        detail = r.stderr.strip().split("\n")[0] if r.stderr else "docker info failed"
        return False, detail
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except FileNotFoundError:
        return False, "docker not found"


def _check_docker_run() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--cpus", "1", "--memory", "256m", "--pids-limit", "64",
                "alpine:latest", "echo", "patchguard-doctor-ok",
            ],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if r.returncode == 0 and "patchguard-doctor-ok" in r.stdout:
            return True, "container ran with safe defaults"
        detail = r.stderr.strip().split("\n")[0] if r.stderr else ""
        if not detail:
            detail = f"unexpected output: {r.stdout[:80]}"
        return False, detail
    except subprocess.TimeoutExpired:
        return False, "test container timed out"
    except FileNotFoundError:
        return False, "docker not found"


def _check_worktree(git_available: bool) -> tuple[bool, str]:
    if not git_available:
        return False, "git not available — skipped"
    try:
        repo = Path(tempfile.mkdtemp(prefix="patchguard-dr-"))
        subprocess.run(
            ["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True
        )
        git_cmd = ["git", "config", "user.email", "test@test"]
        subprocess.run(git_cmd, cwd=repo, capture_output=True, check=True)
        git_cmd = ["git", "config", "user.name", "Test"]
        subprocess.run(git_cmd, cwd=repo, capture_output=True, check=True)
        (repo / "test.txt").write_text("hello")
        subprocess.run(
            ["git", "add", "test.txt"], cwd=repo, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()
        tmp = Path(tempfile.gettempdir()) / "patchguard-doctor-wt-test"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(tmp), head],
            cwd=repo, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(tmp)],
            cwd=repo, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "worktree", "prune"], cwd=repo, capture_output=True, check=True,
        )
        shutil.rmtree(repo, ignore_errors=True)
        return True, "worktree created and removed successfully"
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip() if isinstance(e.stderr, str) else str(e)
        return False, f"worktree test failed: {detail}"
    except Exception as e:
        return False, f"worktree test error: {e}"


def _check_runs_dir() -> tuple[bool, str]:
    try:
        DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        test_file = DEFAULT_RUNS_DIR / ".doctor_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True, str(DEFAULT_RUNS_DIR)
    except OSError as e:
        return False, f"cannot write to {DEFAULT_RUNS_DIR}: {e}"


# -- run command -----------------------------------------------------------


@app.command()
def run(
    repo: Annotated[
        Path,
        typer.Option("--repo", exists=True, file_okay=False, help="Path to the git repository"),
    ],
    agent_command: Annotated[
        list[str] | None,
        typer.Argument(help="Agent command and arguments (after --)"),
    ] = None,
    image: Annotated[
        str, typer.Option("--image", help="Docker image for the sandbox")
    ] = "alpine:latest",
    verify: Annotated[
        str | None, typer.Option("--verify", help="Verification command to run after agent")
    ] = None,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Timeout in seconds")
    ] = 1800,
    cpus: Annotated[
        float, typer.Option("--cpus", help="CPU limit")
    ] = 2.0,
    memory: Annotated[
        str, typer.Option("--memory", help="Memory limit")
    ] = "4g",
    pids_limit: Annotated[
        int, typer.Option("--pids-limit", help="PID limit")
    ] = 256,
    network: Annotated[
        str, typer.Option("--network", help="Network mode: none or bridge")
    ] = "none",
    env_allow: Annotated[
        list[str] | None, typer.Option("--env-allow", help="Env vars to pass to container")
    ] = None,
    runs_dir: Annotated[
        Path | None, typer.Option("--runs-dir", help="Custom runs directory")
    ] = None,
    keep_worktree: Annotated[
        bool, typer.Option("--keep-worktree", help="Keep worktree after run (debug)")
    ] = False,
    unsafe_local_execution: Annotated[
        bool, typer.Option(
            "--unsafe-local-execution",
            help="Allow execution without Docker (DANGEROUS)",
        )
    ] = False,
) -> None:
    """Run a coding agent inside PatchGuard's isolated sandbox.

    All arguments after -- are passed to the agent as its command.

    Example:
        patchguard run --repo ./my-repo --image python:3.12 -- python agent.py
    """
    if agent_command is None:
        print("Error: No agent command provided. Use -- before the agent command.")
        print("Example: patchguard run --repo ./repo --image alpine -- echo hello")
        raise typer.Exit(code=10)

    verify_cmd: list[str] | None = None
    if verify:
        import shlex
        verify_cmd = shlex.split(verify)

    config = RunConfig(
        repo=repo.resolve(),
        agent_command=list(agent_command),
        image=image,
        verify_command=verify_cmd,
        timeout=timeout,
        cpus=cpus,
        memory=memory,
        pids_limit=pids_limit,
        network=network,
        env_allow=list(env_allow) if env_allow else [],
        runs_dir=runs_dir,
        keep_worktree=keep_worktree,
        unsafe_local_execution=unsafe_local_execution,
    )

    try:
        from patchguard.core.orchestrator import RunOrchestrator
        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)
    except PatchGuardError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=e.exit_code) from e

    # Print summary
    print(f"\nRun complete: {result.run_id}")
    print(f"  Status     : {result.status.value}")
    print(f"  Exit code  : {result.exit_code}")
    print(f"  Patch size : {result.patch_bytes} bytes")
    if result.verifier_exit_code is not None:
        if result.verifier_exit_code == 0:
            vstatus = "PASSED"
        else:
            vstatus = f"FAILED (exit {result.verifier_exit_code})"
        print(f"  Verifier   : {vstatus}")
    print(f"  Run dir    : {result.run_dir}")
    print(f"\nInspect: patchguard inspect {result.run_id}")


# -- list command ----------------------------------------------------------


@app.command(name="list")
def list_runs(
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum runs to show")
    ] = 20,
    runs_dir: Annotated[
        Path | None, typer.Option("--runs-dir", help="Custom runs directory")
    ] = None,
) -> None:
    """List past PatchGuard runs."""
    rd = runs_dir or DEFAULT_RUNS_DIR
    if not rd.exists():
        print("No runs yet.")
        return

    runs: list[dict[str, Any]] = []
    for entry in sorted(rd.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        runs.append(data)
        if len(runs) >= limit:
            break

    if not runs:
        print("No runs found.")
        return

    print(f"{'RUN ID':<38} {'STATUS':<16} {'CREATED'}")
    print("-" * 80)
    for r in runs:
        rid = r.get("run_id", "?")[:36]
        status = r.get("status", "?")
        created = r.get("created_at", "?")[:19]
        print(f"{rid:<38} {status:<16} {created}")


# -- inspect command -------------------------------------------------------


@app.command()
def inspect(
    run_id: Annotated[str, typer.Argument(help="Run ID to inspect")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON")
    ] = False,
    runs_dir: Annotated[
        Path | None, typer.Option("--runs-dir", help="Custom runs directory")
    ] = None,
) -> None:
    """Inspect a run's artifacts and display a summary."""
    rd = runs_dir or DEFAULT_RUNS_DIR
    run_dir = rd / run_id

    if not run_dir.exists():
        print(f"Run not found: {run_id}")
        raise typer.Exit(code=1)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest found for run: {run_id}")
        raise typer.Exit(code=1)

    try:
        m = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to read manifest: {e}")
        raise typer.Exit(code=1) from e

    if json_output:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return

    # Human-readable summary
    print(f"Run: {run_id}")
    print(f"{'=' * 50}")
    print(f"  Status      : {m.get('status', '?')}")
    print(f"  Created     : {m.get('created_at', '?')}")
    print(f"  Completed   : {m.get('completed_at', '?')}")
    print(f"  Capability  : {m.get('capability_tier', '?')}")

    repo = m.get("repo", {})
    print("\n  Repository:")
    print(f"    Path      : {repo.get('source_path', '?')}")
    print(f"    HEAD      : {repo.get('head_sha', '?')[:12]}")
    print(f"    Dirty     : {repo.get('dirty_before', '?')}")
    print(f"    FP before : {repo.get('source_fingerprint_before', '?')[:20]}...")
    print(f"    FP after  : {repo.get('source_fingerprint_after', '?')[:20]}...")

    sandbox = m.get("sandbox", {})
    print("\n  Sandbox:")
    print(f"    Image     : {sandbox.get('image', '?')}")
    print(f"    Network   : {sandbox.get('network', '?')}")
    print(f"    CPUs      : {sandbox.get('cpus', '?')}")
    print(f"    Memory    : {sandbox.get('memory', '?')}")

    artifacts = m.get("artifacts", {})
    print("\n  Artifacts:")
    for key, fname in artifacts.items():
        exists = (run_dir / fname).exists()
        marker = "" if exists else " (missing)"
        print(f"    {key}: {fname}{marker}")

    integrity = m.get("integrity", {})
    if integrity:
        print("\n  Integrity (SHA-256):")
        for k, v in integrity.items():
            if v:
                print(f"    {k}: {v[:16]}...")
            else:
                print(f"    {k}: (not yet computed)")

    # Check INV-001
    fp_before = repo.get("source_fingerprint_before", "")
    fp_after = repo.get("source_fingerprint_after", "")
    if fp_before and fp_after and fp_before == fp_after:
        print("\n  INV-001 (source workspace): PASSED")
    elif fp_before and fp_after:
        print("\n  INV-001 (source workspace): FAILED — fingerprints differ!")

    # Report findings summary
    report_path = run_dir / "report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            findings = report.get("quality_findings", [])
            if findings:
                print("\n  Findings:")
                for f in findings:
                    print(f"    • {f}")
            tier = report.get("capability_tier", "")
            print(f"\n  Capability Tier: {tier}")
        except (json.JSONDecodeError, OSError):
            pass

    # Replay hint
    print(f"\n  Replay: patchguard replay {run_id}")


# -- replay command --------------------------------------------------------


@app.command()
def replay(
    run_id: Annotated[str, typer.Argument(help="Run ID to replay")],
    repo: Annotated[
        Path | None, typer.Option("--repo", help="Override source repo path")
    ] = None,
    runs_dir: Annotated[
        Path | None, typer.Option("--runs-dir", help="Custom runs directory")
    ] = None,
) -> None:
    """Replay a run's patch and verify integrity.

    Does NOT re-invoke the agent. Only validates artifacts and applies
    the recorded patch to a fresh worktree to verify reproducibility.
    """
    from patchguard.replay.service import ReplayService

    rd = runs_dir or DEFAULT_RUNS_DIR
    service = ReplayService(runs_dir=rd)
    try:
        result = service.replay(run_id, repo_override=repo)
    except Exception as e:
        print(f"Replay failed: {e}")
        raise typer.Exit(code=1) from e

    print(f"Replay: {run_id}")
    print(f"{'=' * 50}")
    print(f"  Integrity check : {'PASSED' if result.integrity_ok else 'FAILED'}")
    print(f"  Patch applied    : {'yes' if result.patch_applied else 'no (empty patch)'}")
    print(f"  Patch matches    : {'yes' if result.patch_match else 'NO — mismatch detected'}")
    print(f"  HEAD SHA         : {result.head_sha[:12]}")
    print(f"  Original status  : {result.manifest_status}")

    if result.success:
        print("\nReplay successful — patch is reproducible.")
    else:
        print("\nReplay FAILED — artifacts cannot be reproduced.")
        raise typer.Exit(code=1)


# -- compare command -------------------------------------------------------


@app.command()
def compare(
    run_a: Annotated[str, typer.Argument(help="First run ID")],
    run_b: Annotated[str, typer.Argument(help="Second run ID")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON")
    ] = False,
    runs_dir: Annotated[
        Path | None, typer.Option("--runs-dir", help="Custom runs directory")
    ] = None,
) -> None:
    """Compare two PatchGuard runs."""
    from patchguard.analysis.compare import CompareService

    rd = runs_dir or DEFAULT_RUNS_DIR
    service = CompareService(runs_dir=rd)
    try:
        result = service.compare(run_a, run_b)
    except Exception as e:
        print(f"Compare failed: {e}")
        raise typer.Exit(code=1) from e

    if json_output:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.format())


# -- cleanup command -------------------------------------------------------


@app.command()
def cleanup(
    stale_only: Annotated[
        bool, typer.Option("--stale-only", help="Only clean up stale runs")
    ] = False,
) -> None:
    """Clean up run artifacts and temporary resources (not yet implemented)."""
    print("The 'cleanup' command is not implemented yet. Coming in a future phase.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
