"""CompareService — structured comparison of two runs."""

from __future__ import annotations

from pathlib import Path

from patchguard.exceptions import ConfigurationError
from patchguard.models.manifest import Manifest


class CompareResult:
    """Structured comparison of two PatchGuard runs."""

    def __init__(self, run_a: str, run_b: str) -> None:
        self.run_a = run_a
        self.run_b = run_b
        self._fields: list[tuple[str, str, str]] = []

    def add(self, field: str, value_a: str, value_b: str) -> None:
        self._fields.append((field, value_a, value_b))

    def format(self) -> str:
        lines = [f"Comparing {self.run_a[:20]}... vs {self.run_b[:20]}..."]
        lines.append("-" * 65)
        max_field = max((len(f) for f, _, _ in self._fields), default=0)
        max_field = max(max_field, 20)
        fmt = "  {:<" + str(max_field) + "} | {:<20} | {}"
        lines.append(fmt.format("Field", self.run_a[:16], self.run_b[:16]))
        sep = "-" * max_field + "-+-" + "-" * 20 + "-+-" + "-" * 20
        lines.append(f"  {sep}")
        for field, va, vb in self._fields:
            lines.append(fmt.format(field, va, vb))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_a": self.run_a,
            "run_b": self.run_b,
            "fields": [
                {"field": f, "run_a": va, "run_b": vb}
                for f, va, vb in self._fields
            ],
        }


class CompareService:
    """Compares two runs by reading their manifests and artifacts."""

    def __init__(self, *, runs_dir: Path | None = None) -> None:
        from patchguard.constants import DEFAULT_RUNS_DIR
        self._runs_dir = runs_dir or DEFAULT_RUNS_DIR

    def compare(self, run_a: str, run_b: str) -> CompareResult:
        """Compare two runs and return a structured result."""
        ma = self._load_manifest(run_a)
        mb = self._load_manifest(run_b)

        result = CompareResult(run_a, run_b)

        # Status
        result.add("Status", str(ma.status.value), str(mb.status.value))

        # Capability tier
        result.add("Capability Tier", str(ma.capability_tier.value), str(mb.capability_tier.value))

        # Wall time
        wall_a = self._duration_ms(ma)
        wall_b = self._duration_ms(mb)
        result.add("Wall time (ms)", str(wall_a), str(wall_b))

        # Patch stats
        pa = self._load_patch(run_a)
        pb = self._load_patch(run_b)
        result.add("Patch files changed", str(pa[0]), str(pb[0]))
        result.add("Patch lines added", str(pa[1]), str(pb[1]))
        result.add("Patch lines deleted", str(pa[2]), str(pb[2]))

        # Sandbox config
        result.add("Network", ma.sandbox.network, mb.sandbox.network)
        result.add("CPUs", str(ma.sandbox.cpus), str(mb.sandbox.cpus))
        result.add("Memory", ma.sandbox.memory, mb.sandbox.memory)
        result.add("Timeouts (s)", str(ma.sandbox.timeout_seconds), str(mb.sandbox.timeout_seconds))

        # Repo
        result.add("HEAD SHA", ma.repo.head_sha[:12], mb.repo.head_sha[:12])
        result.add("Dirty before", str(ma.repo.dirty_before), str(mb.repo.dirty_before))

        # Integrity
        result.add("Patch integrity", ma.integrity.patch_diff[:16], mb.integrity.patch_diff[:16])

        return result

    def _load_manifest(self, run_id: str) -> Manifest:
        run_dir = self._runs_dir / run_id
        if not run_dir.exists():
            raise ConfigurationError(f"Run not found: {run_id}")
        mf = run_dir / "manifest.json"
        if not mf.exists():
            raise ConfigurationError(f"No manifest for run: {run_id}")
        return Manifest.model_validate_json(mf.read_text())

    def _load_patch(self, run_id: str) -> tuple[int, int, int]:
        """Return (files_changed, lines_added, lines_deleted) from patch.diff."""
        patch_path = self._runs_dir / run_id / "patch.diff"
        if not patch_path.exists():
            return (0, 0, 0)
        return _parse_patch_stats(patch_path.read_text())

    def _duration_ms(self, m: Manifest) -> int:
        """Compute approximate duration from manifest timestamps."""
        if not m.created_at or not m.completed_at:
            return 0
        try:
            from datetime import UTC, datetime
            fmt = "%Y-%m-%dT%H:%M:%S."
            ca = m.created_at[:19]
            cb = m.completed_at[:19]
            t0 = datetime.strptime(ca, fmt).replace(tzinfo=UTC)
            t1 = datetime.strptime(cb, fmt).replace(tzinfo=UTC)
            return int((t1 - t0).total_seconds() * 1000)
        except (ValueError, OSError):
            return 0


def _parse_patch_stats(patch: str) -> tuple[int, int, int]:
    """Parse git diff --stat style output from a patch."""
    files = 0
    added = 0
    deleted = 0
    for line in patch.split("\n"):
        if line.startswith("diff --git"):
            files += 1
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        if line.startswith("-") and not line.startswith("---"):
            deleted += 1
    return files, added, deleted
