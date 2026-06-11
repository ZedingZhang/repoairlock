"""Resource monitor — periodically samples container resource usage via docker stats."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any

from patchguard.sandbox.base import ResourceSample


class ResourceSampler:
    """Periodically collect docker stats for a container.

    Runs in a background thread. Call start() before the container,
    stop() after it exits.
    """

    def __init__(self, container_name: str, interval: float = 2.0) -> None:
        self._container = container_name
        self._interval = interval
        self._samples: list[ResourceSample] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def samples(self) -> list[ResourceSample]:
        return list(self._samples)

    def start(self) -> None:
        """Start the background sampling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            sample = self._poll()
            if sample is not None:
                self._samples.append(sample)
            self._stop_event.wait(self._interval)

    def _poll(self) -> ResourceSample | None:
        sample = _docker_stats(self._container)
        if sample is None:
            return None
        return ResourceSample(
            timestamp=time.time(),
            cpu_percent=_parse_cpu(sample),
            memory_bytes=_parse_int(sample, "mem_usage", 0),
            memory_limit_bytes=_parse_int(sample, "mem_limit", 0),
            network_rx_bytes=_parse_int_recv(sample),
            network_tx_bytes=_parse_int_xmit(sample),
            block_read_bytes=_parse_int_block(sample, "read"),
            block_write_bytes=_parse_int_block(sample, "write"),
            pids_current=_parse_int(sample, "pids", 0),
        )


def _docker_stats(container: str) -> dict[str, Any] | None:
    """Run `docker stats --no-stream --format json` for a container."""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "json", container],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line:
        return None
    try:
        stats: dict[str, Any] = json.loads(line)
        return stats
    except json.JSONDecodeError:
        return None


def _parse_cpu(sample: dict[str, Any]) -> float:
    cpustr = sample.get("CPUPerc", "0%")
    if isinstance(cpustr, str):
        return float(cpustr.rstrip("%"))
    return float(cpustr)


def _parse_int(sample: dict[str, Any], key: str, default: int) -> int:
    val = sample.get(key, default)
    if isinstance(val, str):
        try:
            return int(float(val) if "." in val else val)
        except (ValueError, TypeError):
            return default
    return int(val)


def _parse_int_recv(sample: dict[str, Any]) -> int:
    net = sample.get("NetIO", "0B/0B")
    if isinstance(net, str) and "/" in net:
        return _parse_size(net.split("/")[0].strip())
    return 0


def _parse_int_xmit(sample: dict[str, Any]) -> int:
    net = sample.get("NetIO", "0B/0B")
    if isinstance(net, str) and "/" in net:
        return _parse_size(net.split("/")[1].strip())
    return 0


def _parse_int_block(sample: dict[str, Any], direction: str) -> int:
    bio = sample.get("BlockIO", "0B/0B")
    if isinstance(bio, str) and "/" in bio:
        idx = 0 if direction == "read" else 1
        parts = bio.split("/")
        if len(parts) > idx:
            return _parse_size(parts[idx].strip())
    return 0


def _parse_size(s: str) -> int:
    """Parse a size string like '1.5GiB', '10MB', '500kB', '0B' into bytes."""
    s = s.strip()
    if not s or s == "0B":
        return 0
    units = {
        "B": 1, "kB": 1000, "MB": 1000_000,
        "GB": 1000_000_000, "TB": 1000_000_000_000,
        "KiB": 1024, "MiB": 1024 * 1024,
        "GiB": 1024 * 1024 * 1024, "TiB": 1024 * 1024 * 1024 * 1024,
    }
    for u, mult in sorted(units.items(), key=lambda x: -len(x[0])):
        if s.endswith(u):
            num = s[: -len(u)]
            return int(float(num) * mult)
    return 0
