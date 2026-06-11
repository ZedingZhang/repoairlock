"""Tests for ReplayService."""

from __future__ import annotations

from pathlib import Path

import pytest

from patchguard.artifacts.integrity import sha256_file
from patchguard.artifacts.serializer import write_json_atomic
from patchguard.exceptions import ConfigurationError
from patchguard.replay.service import ReplayService


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def service(runs_dir: Path) -> ReplayService:
    return ReplayService(runs_dir=runs_dir)


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


class TestParsePatchStats:
    def test_empty_patch(self) -> None:
        from patchguard.analysis.compare import _parse_patch_stats
        files, added, deleted = _parse_patch_stats("")
        assert files == 0
        assert added == 0
        assert deleted == 0

    def test_single_file_patch(self) -> None:
        from patchguard.analysis.compare import _parse_patch_stats
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
        from patchguard.analysis.compare import CompareResult
        cr = CompareResult("run_a", "run_b")
        output = cr.format()
        assert "run_a" in output
        assert "run_b" in output

    def test_format_with_fields(self) -> None:
        from patchguard.analysis.compare import CompareResult
        cr = CompareResult("run_a", "run_b")
        cr.add("Status", "completed", "failed")
        cr.add("Exit code", "0", "1")
        output = cr.format()
        assert "completed" in output
        assert "failed" in output

    def test_to_dict(self) -> None:
        from patchguard.analysis.compare import CompareResult
        cr = CompareResult("short_a", "short_b")
        cr.add("Status", "completed", "failed")
        d = cr.to_dict()
        assert d["run_a"] == "short_a"
        assert d["run_b"] == "short_b"
        assert len(d["fields"]) == 1
