"""Unit tests for WorkspaceFingerprint."""

from __future__ import annotations

import pytest

from patchguard.exceptions import InvariantViolationError
from patchguard.workspace.fingerprint import WorkspaceFingerprint


class TestWorkspaceFingerprint:
    def test_identical_fingerprints_pass(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        b = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        a.assert_unchanged(b)  # should not raise

    def test_head_change_detected(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        b = WorkspaceFingerprint(
            head_sha="def456", status_hash="s1", diff_hash="d1"
        )
        with pytest.raises(InvariantViolationError, match="HEAD changed"):
            a.assert_unchanged(b)

    def test_status_change_detected(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        b = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s2", diff_hash="d1"
        )
        with pytest.raises(
            InvariantViolationError, match="Working tree status changed"
        ):
            a.assert_unchanged(b)

    def test_diff_change_detected(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        b = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d2"
        )
        with pytest.raises(InvariantViolationError, match="Tracked file diffs"):
            a.assert_unchanged(b)

    def test_untracked_change_detected(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123",
            status_hash="s1",
            diff_hash="d1",
            untracked_files=("a.txt",),
        )
        b = WorkspaceFingerprint(
            head_sha="abc123",
            status_hash="s1",
            diff_hash="d1",
            untracked_files=("a.txt", "b.txt"),
        )
        with pytest.raises(InvariantViolationError, match="Untracked files"):
            a.assert_unchanged(b)

    def test_summary_is_stable(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc", status_hash="s", diff_hash="d"
        )
        assert a.summary() == a.summary()
        assert a.summary().startswith("sha256:")

    def test_label_in_error_message(self) -> None:
        a = WorkspaceFingerprint(
            head_sha="abc123", status_hash="s1", diff_hash="d1"
        )
        b = WorkspaceFingerprint(
            head_sha="def456", status_hash="s1", diff_hash="d1"
        )
        with pytest.raises(
            InvariantViolationError, match="After something: HEAD changed"
        ):
            a.assert_unchanged(b, label="After something")
