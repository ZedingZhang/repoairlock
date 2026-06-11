"""Manifest model for AgentFence runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentfence.models.enums import CapabilityTier, RunStatus

MANIFEST_SCHEMA_VERSION = "1.0"


class RepoInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = ""
    head_sha: str = ""
    dirty_before: bool = False
    source_fingerprint_before: str = ""
    source_fingerprint_after: str = ""


class AdapterInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    version: str = ""
    command_redacted: list[str] = Field(default_factory=list)


class SandboxInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: str = "docker"
    image: str = ""
    network: str = "none"
    read_only_rootfs: bool = True
    cpus: float = 2.0
    memory: str = "4g"
    pids_limit: int = 256
    timeout_seconds: int = 1800


class ArtifactRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: str = "events.jsonl"
    patch: str = "patch.diff"
    report: str = "report.json"
    html_report: str = "report.html"


class IntegrityMap(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    events_jsonl: str = Field(default="", alias="events.jsonl")
    patch_diff: str = Field(default="", alias="patch.diff")
    report_json: str = Field(default="", alias="report.json")

    def set(self, filename: str, sha256: str) -> None:
        if filename == "events.jsonl":
            self.events_jsonl = sha256
        elif filename == "patch.diff":
            self.patch_diff = sha256
        elif filename == "report.json":
            self.report_json = sha256


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["1.0"] = Field(default="1.0")
    run_id: str
    created_at: str
    completed_at: str = ""
    status: RunStatus = RunStatus.CREATED
    capability_tier: CapabilityTier = CapabilityTier.PROCESS_WRAPPER
    repo: RepoInfo = Field(default_factory=lambda: RepoInfo())
    adapter: AdapterInfo = Field(default_factory=lambda: AdapterInfo())
    sandbox: SandboxInfo = Field(default_factory=lambda: SandboxInfo())
    artifacts: ArtifactRefs = Field(default_factory=lambda: ArtifactRefs())
    integrity: IntegrityMap = Field(default_factory=lambda: IntegrityMap())

    @classmethod
    def create(cls, *, run_id: str, source_path: str = "") -> Manifest:
        ts = _now_iso()
        return cls(
            run_id=run_id,
            created_at=ts,
            repo=RepoInfo(source_path=source_path),
        )


def _now_iso() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
