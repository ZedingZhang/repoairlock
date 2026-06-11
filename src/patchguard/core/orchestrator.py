"""RunOrchestrator — ties together all Tier 0 components for a complete run."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from patchguard.artifacts.store import ArtifactStore
from patchguard.core.lifecycle import (
    EventRecorder,
    record_run_created,
    record_run_failed,
)
from patchguard.core.run_context import RunContext, generate_run_id
from patchguard.exceptions import (
    PatchGuardError,
)
from patchguard.models.enums import CapabilityTier, RunStatus
from patchguard.models.events import EventType
from patchguard.models.manifest import (
    AdapterInfo,
    Manifest,
    RepoInfo,
    SandboxInfo,
)
from patchguard.sandbox.base import RunResult as SandboxRunResult
from patchguard.sandbox.base import SandboxConfig
from patchguard.sandbox.docker import DockerBackend
from patchguard.workspace.fingerprint import capture_fingerprint
from patchguard.workspace.git_client import GitClient
from patchguard.workspace.manager import WorkspaceManager


@dataclass
class RunConfig:
    """User-facing configuration for a single `patchguard run` invocation."""

    repo: Path
    agent_command: Sequence[str]
    image: str
    verify_command: Sequence[str] | None = None
    timeout: int = 1800
    cpus: float = 2.0
    memory: str = "4g"
    pids_limit: int = 256
    network: str = "none"
    env_allow: list[str] = field(default_factory=list)
    runs_dir: Path | None = None
    keep_worktree: bool = False
    unsafe_local_execution: bool = False


@dataclass
class RunResultSummary:
    """Summary returned to the CLI after a run."""

    run_id: str
    run_dir: Path
    status: RunStatus
    exit_code: int
    patch_bytes: int
    verifier_exit_code: int | None


class RunOrchestrator:
    """Orchestrates a complete Tier 0 execution pipeline.

    Flow:
    validate → RunContext → ArtifactStore → WorkspaceManager →
    DockerSandbox → patch export → verifier → cleanup → finalize
    """

    def __init__(self) -> None:
        self._git = GitClient()
        self._docker = DockerBackend()

    def execute(self, config: RunConfig) -> RunResultSummary:
        """Run the complete Tier 0 pipeline. Raises PatchGuardError on failure."""

        # 1. Validate
        repo_toplevel = self._git.assert_git_repo(config.repo)
        self._docker.assert_available()

        # Capture the name before we start building the manifest
        adapter_name = "command"
        capability_tier = CapabilityTier.PROCESS_WRAPPER

        # 2. Create RunContext
        ctx = RunContext(run_id=generate_run_id(), runs_dir=config.runs_dir)

        # 3. Create ArtifactStore
        store = ArtifactStore(ctx.runs_dir, ctx.run_id)
        store.create_run_dir()

        recorder = EventRecorder(store, ctx.run_id)
        manifest = Manifest.create(run_id=ctx.run_id, source_path=str(repo_toplevel))

        # Populate manifest metadata
        manifest.repo = RepoInfo(source_path=str(repo_toplevel))
        manifest.adapter = AdapterInfo(name=adapter_name, version="0.1.0")
        manifest.sandbox = SandboxInfo(
            backend="docker",
            image=config.image,
            network=config.network,
            cpus=config.cpus,
            memory=config.memory,
            pids_limit=config.pids_limit,
            timeout_seconds=config.timeout,
            unsafe_local_execution=config.unsafe_local_execution,
        )
        manifest.capability_tier = capability_tier
        store.write_manifest(manifest)

        # Record RUN_CREATED
        record_run_created(recorder, manifest)
        ctx.set_status(RunStatus.PREPARING)
        manifest.status = RunStatus.PREPARING

        workspace_mgr = WorkspaceManager(git=self._git)
        worktree_path = None
        before_fp = None
        sandbox_result: SandboxRunResult | None = None
        patch_content = ""
        verifier_exit_code: int | None = None

        try:
            # 5. Prepare workspace
            recorder.record(
                type=EventType.RUN_PREPARING,
                source="harness.core",
            )
            worktree_path, before_fp = workspace_mgr.prepare(
                repo_toplevel, ctx.run_id
            )
            manifest.repo.head_sha = before_fp.head_sha
            manifest.repo.source_fingerprint_before = before_fp.summary()
            recorder.record(
                type=EventType.WORKTREE_CREATED,
                source="harness.workspace",
                payload={"worktree": str(worktree_path)},
            )

            # 6. Run agent in sandbox
            recorder.record(
                type=EventType.SANDBOX_STARTING,
                source="harness.sandbox",
            )
            sandbox_config = SandboxConfig(
                image=config.image,
                command=list(config.agent_command),
                workspace=worktree_path,
                run_id=ctx.run_id,
                network=config.network,
                cpus=config.cpus,
                memory=config.memory,
                pids_limit=config.pids_limit,
                timeout_seconds=config.timeout,
                env_allow=config.env_allow,
            )
            recorder.record(
                type=EventType.PROCESS_STARTED,
                source="harness.sandbox",
                payload={"command": list(sandbox_config.command)},
            )

            ctx.set_status(RunStatus.RUNNING)
            manifest.status = RunStatus.RUNNING
            sandbox_result = self._docker.run(sandbox_config)

            recorder.record(
                type=EventType.PROCESS_EXITED,
                source="sandbox.docker",
                payload={
                    "exit_code": sandbox_result.exit_code,
                    "duration_ms": sandbox_result.duration_ms,
                    "timed_out": sandbox_result.timed_out,
                },
            )

            # Write stdout/stderr
            store.write_text("stdout.log", sandbox_result.stdout)
            store.write_text("stderr.log", sandbox_result.stderr)

            # 7. Export patch
            patch_content = workspace_mgr.export_patch(worktree_path)
            store.write_text("patch.diff", patch_content)
            recorder.record(
                type=EventType.PATCH_EXPORTED,
                source="harness.workspace",
                payload={"patch_bytes": len(patch_content)},
            )

            # 8. Verifier (optional)
            if config.verify_command:
                verifier_exit_code = self._run_verifier(
                    config=config,
                    sandbox_config=sandbox_config,
                    worktree_path=worktree_path,
                    recorder=recorder,
                    store=store,
                )

            # 9. Handle exit status
            if sandbox_result.timed_out:
                manifest.status = RunStatus.TIMED_OUT
            elif sandbox_result.exit_code != 0:
                manifest.status = RunStatus.FAILED
            else:
                manifest.status = RunStatus.COMPLETED

            return RunResultSummary(
                run_id=ctx.run_id,
                run_dir=store.run_dir,
                status=manifest.status,
                exit_code=sandbox_result.exit_code,
                patch_bytes=len(patch_content),
                verifier_exit_code=verifier_exit_code,
            )

        except PatchGuardError:
            raise
        except Exception as exc:
            record_run_failed(
                recorder, manifest, error_message=str(exc), phase=str(ctx.status)
            )
            raise
        finally:
            # 10. Cleanup
            try:
                if worktree_path and not config.keep_worktree:
                    after_fp = workspace_mgr.cleanup(repo_toplevel, worktree_path)
                    recorder.record(
                        type=EventType.WORKTREE_REMOVED,
                        source="harness.workspace",
                    )
            except Exception as cleanup_err:
                recorder.record(
                    type=EventType.CLEANUP_FAILED,
                    source="harness.workspace",
                    payload={"error": str(cleanup_err)},
                )

            # Verify source fingerprint unchanged
            try:
                after_fp = capture_fingerprint(repo_toplevel, self._git)
                manifest.repo.source_fingerprint_after = after_fp.summary()
                manifest.repo.dirty_before = self._git.is_dirty(repo_toplevel)
                if before_fp:
                    workspace_mgr.verify_source_unchanged(before_fp, after_fp)
            except Exception:
                recorder.record(
                    type=EventType.RUN_FAILED,
                    source="harness.core",
                    payload={"error": "INV-001: source workspace modified"},
                )

            # Generate report
            try:
                from patchguard.reporting.generator import ReportGenerator
                gen = ReportGenerator(store.run_dir, ctx.run_id)
                report_data = gen.generate()
                store.write_json("report.json", report_data)
                html = gen.generate_html(report_data)
                store.write_text("report.html", html)
                recorder.record(
                    type=EventType.REPORT_GENERATED,
                    source="harness.reporting",
                )
            except Exception as report_err:
                recorder.record(
                    type=EventType.RUN_FAILED,
                    source="harness.reporting",
                    payload={"error": f"Report generation failed: {report_err}"},
                )

            # Finalize
            manifest.completed_at = _now_iso()
            store.finalize_manifest(manifest)
            recorder.record(
                type=(
                    EventType.RUN_COMPLETED
                    if manifest.status == RunStatus.COMPLETED
                    else EventType.RUN_FAILED
                ),
                source="harness.core",
                payload={"status": str(manifest.status)},
            )

    def _run_verifier(
        self,
        *,
        config: RunConfig,
        sandbox_config: SandboxConfig,
        worktree_path: Path,
        recorder: EventRecorder,
        store: ArtifactStore,
    ) -> int:
        """Run the verifier command in a fresh container on the modified worktree."""
        assert config.verify_command
        recorder.record(
            type=EventType.VERIFICATION_STARTED,
            source="harness.verifier",
        )
        verify_config = SandboxConfig(
            image=config.image,
            command=list(config.verify_command),
            workspace=worktree_path,
            run_id=f"{sandbox_config.run_id}-verify",
            network=config.network,
            cpus=config.cpus,
            memory=config.memory,
            pids_limit=config.pids_limit,
            timeout_seconds=config.timeout,
            env_allow=config.env_allow,
        )
        verify_result = self._docker.run(verify_config)
        store.write_text("verify-stdout.log", verify_result.stdout)
        store.write_text("verify-stderr.log", verify_result.stderr)
        recorder.record(
            type=EventType.VERIFICATION_FINISHED,
            source="harness.verifier",
            payload={
                "exit_code": verify_result.exit_code,
                "duration_ms": verify_result.duration_ms,
                "passed": verify_result.exit_code == 0,
            },
        )
        return verify_result.exit_code


def _now_iso() -> str:
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
