"""Tests for ReplayService."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentfence.artifacts.integrity import sha256_file
from agentfence.artifacts.serializer import write_json_atomic
from agentfence.exceptions import ConfigurationError
from agentfence.replay.service import ReplayService
from agentfence.workspace.git_client import GitClient
from agentfence.workspace.manager import WorkspaceManager


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def service(runs_dir: Path) -> ReplayService:
    return ReplayService(runs_dir=runs_dir)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )


def _commit(path: Path, filename: str, content: str, msg: str) -> str:
    (path / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=path, capture_output=True, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _write_run_manifest(
    *,
    runs_dir: Path,
    run_id: str,
    repo: Path,
    head_sha: str,
    patch_hash: str,
) -> None:
    run_dir = runs_dir / run_id
    mf = {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": "2026-06-11T00:00:00.000Z",
        "status": "completed",
        "capability_tier": "tier_0_process_wrapper",
        "repo": {"source_path": str(repo), "head_sha": head_sha},
        "adapter": {"name": "command", "version": "0.1.0"},
        "sandbox": {"image": "img", "network": "none"},
        "artifacts": {},
        "integrity": {
            "events.jsonl": "",
            "patch.diff": patch_hash,
            "report.json": "",
        },
    }
    write_json_atomic(run_dir / "manifest.json", mf)


def _make_patch(
    repo: Path,
    head_sha: str,
    files: dict[str, bytes],
    *,
    staged: bool = False,
) -> str:
    git = GitClient()
    wm = WorkspaceManager(git=git)
    wt, _ = wm.prepare(repo, f"make_patch_{head_sha[:8]}", ref=head_sha)
    try:
        for rel_path, content in files.items():
            path = wt / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if staged:
                subprocess.run(["git", "add", rel_path], cwd=wt, capture_output=True, check=True)
        return wm.export_patch(wt)
    finally:
        wm.cleanup(repo, wt)


def _store_and_replay(
    *,
    service: ReplayService,
    runs_dir: Path,
    run_id: str,
    repo: Path,
    head_sha: str,
    patch: str,
):
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    patch_path = run_dir / "patch.diff"
    patch_path.write_text(patch)
    _write_run_manifest(
        runs_dir=runs_dir,
        run_id=run_id,
        repo=repo,
        head_sha=head_sha,
        patch_hash=sha256_file(patch_path),
    )
    return service.replay(run_id)


class TestReplayErrors:
    def test_run_not_found(self, service: ReplayService) -> None:
        with pytest.raises(ConfigurationError, match="Run not found"):
            service.replay("nonexistent_run")

    def test_no_manifest(self, service: ReplayService, runs_dir: Path) -> None:
        run_dir = runs_dir / "run_test"
        run_dir.mkdir(parents=True)
        with pytest.raises(ConfigurationError, match="Manifest not found"):
            service.replay("run_test")

    def test_no_patch(self, service: ReplayService, runs_dir: Path) -> None:
        run_dir = runs_dir / "run_nopatch"
        run_dir.mkdir(parents=True)
        # Write a minimal manifest
        mf = {
            "schema_version": "1.0",
            "run_id": "run_nopatch",
            "created_at": "2026-06-11T00:00:00.000Z",
            "status": "completed",
            "capability_tier": "tier_0_process_wrapper",
            "repo": {"source_path": "/nonexistent", "head_sha": ""},
            "adapter": {"name": "command", "version": "0.1.0"},
            "sandbox": {"image": "img", "network": "none"},
            "artifacts": {},
            "integrity": {"events.jsonl": "", "patch.diff": "", "report.json": ""},
        }
        write_json_atomic(run_dir / "manifest.json", mf)
        with pytest.raises(ConfigurationError, match="patch.diff not found"):
            service.replay("run_nopatch")

    def test_unknown_schema(self, service: ReplayService, runs_dir: Path) -> None:
        run_dir = runs_dir / "run_schema"
        run_dir.mkdir(parents=True)
        mf = {
            "schema_version": "99.0",
            "run_id": "run_schema",
            "created_at": "2026-06-11T00:00:00.000Z",
            "status": "completed",
            "capability_tier": "tier_0_process_wrapper",
            "repo": {"source_path": "/nonexistent", "head_sha": ""},
            "adapter": {"name": "command", "version": "0.1.0"},
            "sandbox": {"image": "img", "network": "none"},
            "artifacts": {},
            "integrity": {"events.jsonl": "", "patch.diff": "", "report.json": ""},
        }
        write_json_atomic(run_dir / "manifest.json", mf)
        with pytest.raises(ConfigurationError, match="Failed to parse manifest"):
            service.replay("run_schema")

    def test_tampered_patch_detected(
        self, service: ReplayService, runs_dir: Path, tmp_path: Path
    ) -> None:
        """When patch integrity check fails, replay should fail."""
        run_dir = runs_dir / "run_tampered"
        run_dir.mkdir(parents=True)
        original_patch = b"diff --git a/test b/test\n+added line\n"
        patch_path = run_dir / "patch.diff"
        patch_path.write_bytes(original_patch)
        patch_hash = sha256_file(patch_path)

        # Write manifest with the CORRECT hash
        mf = {
            "schema_version": "1.0",
            "run_id": "run_tampered",
            "created_at": "2026-06-11T00:00:00.000Z",
            "status": "completed",
            "capability_tier": "tier_0_process_wrapper",
            "repo": {"source_path": str(tmp_path / "repo"), "head_sha": ""},
            "adapter": {"name": "command", "version": "0.1.0"},
            "sandbox": {"image": "img", "network": "none"},
            "artifacts": {},
            "integrity": {
                "events.jsonl": "",
                "patch.diff": patch_hash,
                "report.json": "",
            },
        }
        write_json_atomic(run_dir / "manifest.json", mf)

        # Now tamper with the patch
        patch_path.write_bytes(b"tampered content!\n")

        with pytest.raises(ConfigurationError, match="Patch integrity check FAILED"):
            service.replay("run_tampered")


class TestReplaySuccess:
    def test_replay_uses_manifest_head_when_repo_has_advanced(
        self, service: ReplayService, runs_dir: Path, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        original_head = _commit(repo, "hello.txt", "base\n", "base")

        git = GitClient()
        wm = WorkspaceManager(git=git)
        wt, _ = wm.prepare(repo, "make_replay_patch", ref=original_head)
        (wt / "hello.txt").write_text("patched\n")
        patch = wm.export_patch(wt)
        wm.cleanup(repo, wt)

        _commit(repo, "hello.txt", "advanced\n", "advance current repo")

        run_id = "run_replay_old_head"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        patch_path = run_dir / "patch.diff"
        patch_path.write_text(patch)
        _write_run_manifest(
            runs_dir=runs_dir,
            run_id=run_id,
            repo=repo,
            head_sha=original_head,
            patch_hash=sha256_file(patch_path),
        )

        result = service.replay(run_id)

        assert result.success
        assert result.head_sha == original_head

    def test_replay_staged_patch(
        self, service: ReplayService, runs_dir: Path, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo_staged"
        _init_repo(repo)
        head = _commit(repo, "hello.txt", "base\n", "base")

        patch = _make_patch(repo, head, {"hello.txt": b"staged\n"}, staged=True)
        result = _store_and_replay(
            service=service,
            runs_dir=runs_dir,
            run_id="run_staged",
            repo=repo,
            head_sha=head,
            patch=patch,
        )

        assert result.success
        assert result.patch_applied

    def test_replay_untracked_new_file(
        self, service: ReplayService, runs_dir: Path, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo_untracked"
        _init_repo(repo)
        head = _commit(repo, "hello.txt", "base\n", "base")

        patch = _make_patch(repo, head, {"new_file.txt": b"new\n"})
        result = _store_and_replay(
            service=service,
            runs_dir=runs_dir,
            run_id="run_untracked",
            repo=repo,
            head_sha=head,
            patch=patch,
        )

        assert result.success
        assert result.patch_applied

    def test_replay_untracked_binary_file(
        self, service: ReplayService, runs_dir: Path, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo_binary"
        _init_repo(repo)
        head = _commit(repo, "hello.txt", "base\n", "base")

        patch = _make_patch(repo, head, {"data.bin": b"\x00\x01binary\n"})
        assert "GIT binary patch" in patch
        result = _store_and_replay(
            service=service,
            runs_dir=runs_dir,
            run_id="run_binary",
            repo=repo,
            head_sha=head,
            patch=patch,
        )

        assert result.success
        assert result.patch_applied


class TestParsePatchStats:
    def test_empty_patch(self) -> None:
        from agentfence.analysis.compare import _parse_patch_stats
        files, added, deleted = _parse_patch_stats("")
        assert files == 0
        assert added == 0
        assert deleted == 0

    def test_single_file_patch(self) -> None:
        from agentfence.analysis.compare import _parse_patch_stats
        patch = (
            "diff --git a/hello.py b/hello.py\n"
            "--- a/hello.py\n"
            "+++ b/hello.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        files, added, deleted = _parse_patch_stats(patch)
        assert files == 1
        assert added == 1
        assert deleted == 1


class TestCompareResult:
    def test_format_empty(self) -> None:
        from agentfence.analysis.compare import CompareResult
        cr = CompareResult("run_a", "run_b")
        output = cr.format()
        assert "run_a" in output
        assert "run_b" in output

    def test_format_with_fields(self) -> None:
        from agentfence.analysis.compare import CompareResult
        cr = CompareResult("run_a", "run_b")
        cr.add("Status", "completed", "failed")
        cr.add("Exit code", "0", "1")
        output = cr.format()
        assert "completed" in output
        assert "failed" in output

    def test_to_dict(self) -> None:
        from agentfence.analysis.compare import CompareResult
        cr = CompareResult("short_a", "short_b")
        cr.add("Status", "completed", "failed")
        d = cr.to_dict()
        assert d["run_a"] == "short_a"
        assert d["run_b"] == "short_b"
        assert len(d["fields"]) == 1

    def test_duration_ms_parses_manifest_timestamps(self, tmp_path: Path) -> None:
        from agentfence.analysis.compare import CompareService
        from agentfence.models.manifest import Manifest
        manifest = Manifest.create(run_id="run_duration")
        manifest.created_at = "2026-06-11T00:00:00.000Z"
        manifest.completed_at = "2026-06-11T00:00:01.500Z"
        service = CompareService(runs_dir=tmp_path)
        assert service._duration_ms(manifest) == 1500
