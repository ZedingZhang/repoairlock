"""Tests for ArtifactStore and EventRecorder."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from patchguard.artifacts.integrity import sha256_file, sha256_hex
from patchguard.artifacts.store import ArtifactStore
from patchguard.core.lifecycle import (
    EventRecorder,
    record_run_created,
    record_run_failed,
)
from patchguard.core.run_context import generate_run_id
from patchguard.exceptions import ArtifactWriteError
from patchguard.models.enums import RunStatus
from patchguard.models.events import EventType
from patchguard.models.manifest import Manifest


@pytest.fixture
def runs_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def run_id() -> str:
    return generate_run_id()


@pytest.fixture
def store(runs_dir: Path, run_id: str) -> ArtifactStore:
    return ArtifactStore(runs_dir, run_id)


class TestArtifactStoreDirectory:
    def test_create_run_dir(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        assert store.run_dir.exists()
        assert store.run_dir.is_dir()

    def test_create_run_dir_fails_if_exists(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        with pytest.raises(ArtifactWriteError, match="already exists"):
            store.create_run_dir()

    def test_creates_parent_dirs(self, runs_dir: Path, run_id: str) -> None:
        nested = runs_dir / "deep" / "nested"
        store = ArtifactStore(nested, run_id)
        store.create_run_dir()
        assert store.run_dir.exists()

    def test_remove_run_dir(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        store.write_text("test.txt", "hello")
        store.remove_run_dir()
        assert not store.run_dir.exists()

    def test_remove_nonexistent_dir_no_error(self, store: ArtifactStore) -> None:
        store.remove_run_dir()  # should not raise


class TestArtifactStoreWrite:
    def test_atomic_write_json(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        data = {"key": "value", "num": 42}
        store.write_json("test.json", data)

        # No .tmp file should remain
        tmp_files = list(store.run_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

        # Content is correct
        result = store.read_json("test.json")
        assert result == data

    def test_write_and_read_manifest(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        m = Manifest.create(run_id=store._run_id)
        store.write_manifest(m)

        manifest_path = store.manifest_path()
        assert manifest_path.exists()

        read_back = store.read_json("manifest.json")
        assert read_back["run_id"] == store._run_id
        assert read_back["schema_version"] == "1.0"

    def test_append_event_to_jsonl(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        store.append_event({"event": "test", "seq": 1})
        store.append_event({"event": "test2", "seq": 2})

        events_path = store.events_path()
        lines = events_path.read_text().strip().split("\n")
        assert len(lines) == 2

        e1 = json.loads(lines[0])
        assert e1["seq"] == 1
        e2 = json.loads(lines[1])
        assert e2["seq"] == 2

    def test_write_text(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        store.write_text("hello.txt", "Hello World")
        content = (store.run_dir / "hello.txt").read_text()
        assert content == "Hello World"


class TestManifestFinalize:
    def test_finalize_with_events(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        store.append_event({"evt": 1})

        m = Manifest.create(run_id=store._run_id)
        m.status = RunStatus.COMPLETED
        store.finalize_manifest(m)

        manifest_data = store.read_json("manifest.json")
        assert "integrity" in manifest_data
        # events.jsonl exists so its hash should be set
        assert manifest_data["integrity"]["events.jsonl"] != ""

    def test_finalize_missing_files_have_empty_hash(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        m = Manifest.create(run_id=store._run_id)
        store.finalize_manifest(m)

        manifest_data = store.read_json("manifest.json")
        assert manifest_data["integrity"]["patch.diff"] == ""


class TestIntegrity:
    def test_sha256_hex(self) -> None:
        h = sha256_hex(b"hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256_deterministic(self) -> None:
        assert sha256_hex(b"a") == sha256_hex(b"a")
        assert sha256_hex(b"a") != sha256_hex(b"b")

    def test_sha256_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("test data")
        h = sha256_file(f)
        assert len(h) == 64


class TestEventRecorder:
    def test_sequence_monotonic(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        assert rec.sequence == 0

        rec.record(type=EventType.RUN_CREATED, source="test")
        assert rec.sequence == 1

        rec.record(type=EventType.RUN_PREPARING, source="test")
        assert rec.sequence == 2

        rec.record(type=EventType.SANDBOX_STARTING, source="test")
        assert rec.sequence == 3

    def test_events_are_written_to_jsonl(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        rec.record(type=EventType.RUN_CREATED, source="harness.core")

        events_path = store.events_path()
        assert events_path.exists()
        lines = events_path.read_text().strip().split("\n")
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["type"] == "RUN_CREATED"
        assert event["sequence"] == 1
        assert event["run_id"] == "run_test"

    def test_event_id_is_unique(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        ids = set()
        for _ in range(50):
            evt = rec.record(type=EventType.RUN_CREATED, source="test")
            ids.add(evt.event_id)
        assert len(ids) == 50

    def test_payload_is_recorded(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        rec.record(
            type=EventType.PROCESS_EXITED,
            source="sandbox.docker",
            payload={"exit_code": 1},
        )

        events_path = store.events_path()
        lines = events_path.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["payload"] == {"exit_code": 1}


class TestLifecycleHelpers:
    def test_record_run_created(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        m = Manifest.create(run_id="run_test")
        record_run_created(rec, m)

        events_path = store.events_path()
        lines = events_path.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["type"] == "RUN_CREATED"

    def test_record_run_failed(self, store: ArtifactStore) -> None:
        store.create_run_dir()
        rec = EventRecorder(store, "run_test")
        m = Manifest.create(run_id="run_test")
        record_run_failed(rec, m, error_message="timeout", phase="running")

        assert m.status == RunStatus.FAILED
        assert m.completed_at != ""

        events_path = store.events_path()
        lines = events_path.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["type"] == "RUN_FAILED"
        assert event["payload"]["error"] == "timeout"
        assert event["payload"]["phase"] == "running"
