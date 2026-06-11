"""JSON serialization helpers with atomic writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def to_jsonl_line(obj: dict[str, Any]) -> str:
    """Serialize a dict to a single JSON line (no trailing newline)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON file atomically: write to .tmp, fsync, rename."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path.write_text(content, encoding="utf-8")
    _fsync_path(tmp_path)
    tmp_path.rename(path)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    """Append a complete JSON line to a JSONL file, then flush.

    Serializes the full object to a string first so that an interruption
    cannot leave a half-written partial line.
    """
    line = to_jsonl_line(obj) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file."""
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _fsync_path(path: Path) -> None:
    """fsync a file's contents to disk."""
    with open(path, "r+b") as f:
        os.fsync(f.fileno())
