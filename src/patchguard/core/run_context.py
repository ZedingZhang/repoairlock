"""RunContext — holds identity and lifecycle state for a single run."""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from patchguard.constants import DEFAULT_RUNS_DIR
from patchguard.models.enums import RunStatus


def generate_run_id() -> str:
    """Generate a unique, non-colliding run_id.

    Format: run_<timestamp>_<random_suffix>
    Example: run_20260611T140102Z_a3f8x2k1
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(4)
    return f"run_{ts}_{suffix}"


class RunContext:
    """Holds the identity and status for a single PatchGuard run.

    Does NOT hold filesystem state — that belongs to ArtifactStore.
    """

    def __init__(
        self,
        *,
        run_id: str | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        self.run_id = run_id or generate_run_id()
        self.runs_dir = runs_dir or DEFAULT_RUNS_DIR
        self.status = RunStatus.CREATED
        self.created_at = time.time()

    @property
    def run_dir(self) -> Path:
        return self.runs_dir / self.run_id

    def set_status(self, status: RunStatus) -> None:
        self.status = status

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.created_at
