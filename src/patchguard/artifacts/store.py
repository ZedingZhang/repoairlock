"""ArtifactStore — manages run directories and artifact persistence."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from patchguard.artifacts.integrity import sha256_file
from patchguard.artifacts.serializer import append_jsonl, read_json, write_json_atomic
from patchguard.exceptions import ArtifactWriteError
from patchguard.models.manifest import IntegrityMap, Manifest


class ArtifactStore:
    """Manages creation and writing of run artifact directories.

    All JSON artifacts are written atomically (tmp → rename).
    Existing run directories are never overwritten.
    """

    def __init__(self, runs_dir: Path, run_id: str) -> None:
        self._runs_dir = runs_dir
        self._run_id = run_id
        self._run_dir = runs_dir / run_id

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    def create_run_dir(self) -> Path:
        """Create the run directory. Raises if it already exists."""
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._run_dir.mkdir()
        except FileExistsError as exc:
            raise ArtifactWriteError(
                f"Run directory already exists: {self._run_dir}"
            ) from exc
        return self._run_dir

    def write_manifest(self, manifest: Manifest) -> None:
        """Write (or overwrite) the manifest atomically."""
        self.write_json("manifest.json", manifest.model_dump(by_alias=True))

    def finalize_manifest(self, manifest: Manifest) -> None:
        """Finalize the manifest by computing artifact integrity hashes."""
        integrity = IntegrityMap()
        for filename in ("events.jsonl", "patch.diff", "report.json"):
            file_path = self._run_dir / filename
            if file_path.exists():
                integrity.set(filename, sha256_file(file_path))
        manifest.integrity = integrity
        self.write_manifest(manifest)

    def write_json(self, name: str, data: dict[str, Any]) -> None:
        """Atomically write a JSON artifact into the run directory."""
        path = self._run_dir / name
        write_json_atomic(path, data)

    def append_event(self, event: dict[str, Any]) -> None:
        """Append a single event line to events.jsonl."""
        path = self._run_dir / "events.jsonl"
        append_jsonl(path, event)

    def write_text(self, name: str, content: str) -> None:
        """Write a plain-text artifact."""
        path = self._run_dir / name
        path.write_text(content, encoding="utf-8")

    def read_json(self, name: str) -> dict[str, Any]:
        """Read a JSON artifact from the run directory."""
        return read_json(self._run_dir / name)

    def manifest_path(self) -> Path:
        return self._run_dir / "manifest.json"

    def events_path(self) -> Path:
        return self._run_dir / "events.jsonl"

    def remove_run_dir(self) -> None:
        """Remove the entire run directory, if it exists."""
        if self._run_dir.exists():
            shutil.rmtree(self._run_dir)
