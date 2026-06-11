"""Tests for resource monitor utilities."""

from __future__ import annotations

from patchguard.sandbox.resource_monitor import _parse_size


class TestParseSize:
    def test_zero_bytes(self) -> None:
        assert _parse_size("0B") == 0

    def test_empty_string(self) -> None:
        assert _parse_size("") == 0

    def test_kilobytes(self) -> None:
        assert _parse_size("5kB") == 5000

    def test_megabytes(self) -> None:
        assert _parse_size("10MB") == 10_000_000

    def test_gigabytes(self) -> None:
        assert _parse_size("2GB") == 2_000_000_000

    def test_mebibytes(self) -> None:
        assert _parse_size("1MiB") == 1024 * 1024

    def test_gibibytes(self) -> None:
        assert _parse_size("1.5GiB") == int(1.5 * 1024 * 1024 * 1024)

    def test_kibibytes(self) -> None:
        assert _parse_size("64KiB") == 64 * 1024

    def test_trailing_spaces(self) -> None:
        assert _parse_size("  100MB  ") == 100_000_000

    def test_just_bytes(self) -> None:
        assert _parse_size("500B") == 500
