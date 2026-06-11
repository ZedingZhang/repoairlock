"""Tests for RunContext."""

from __future__ import annotations

import time
from pathlib import Path

from patchguard.core.run_context import RunContext, generate_run_id
from patchguard.models.enums import RunStatus


class TestGenerateRunId:
    def test_format(self) -> None:
        run_id = generate_run_id()
        assert run_id.startswith("run_")
        parts = run_id.split("_")
        assert len(parts) >= 3  # run, timestamp, suffix

    def test_uniqueness(self) -> None:
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_contains_timestamp(self) -> None:
        run_id = generate_run_id()
        # Second part after "run_" is the timestamp
        ts_part = run_id.split("_")[1]
        assert len(ts_part) == 16  # YYYYMMDDTHHMMSSZ (8+1+6+1)
        assert "T" in ts_part
        assert ts_part.endswith("Z")


class TestRunContext:
    def test_default_construction(self) -> None:
        ctx = RunContext()
        assert ctx.run_id.startswith("run_")
        assert ctx.status == RunStatus.CREATED
        assert ctx.elapsed_seconds >= 0

    def test_explicit_run_id(self) -> None:
        ctx = RunContext(run_id="run_myid")
        assert ctx.run_id == "run_myid"

    def test_custom_runs_dir(self) -> None:
        custom = Path("/tmp/custom_runs")
        ctx = RunContext(runs_dir=custom)
        assert ctx.runs_dir == custom
        assert ctx.run_dir == custom / ctx.run_id

    def test_set_status(self) -> None:
        ctx = RunContext(run_id="run_s")
        ctx.set_status(RunStatus.RUNNING)
        assert ctx.status == RunStatus.RUNNING

    def test_elapsed_time_increases(self) -> None:
        ctx = RunContext(run_id="run_etime")
        t0 = ctx.elapsed_seconds
        time.sleep(0.02)
        assert ctx.elapsed_seconds > t0
