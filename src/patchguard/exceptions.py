class PatchGuardError(Exception):
    """Base exception for all PatchGuard errors."""

    exit_code: int = 10


class ConfigurationError(PatchGuardError):
    """Input or configuration error."""

    exit_code = 10


class EnvironmentError(PatchGuardError):
    """Docker or Git environment not available."""

    exit_code = 20


class AgentProcessError(PatchGuardError):
    """Agent process failed."""

    exit_code = 30


class AgentTimeoutError(PatchGuardError):
    """Agent timed out."""

    exit_code = 31


class VerifierError(PatchGuardError):
    """Verifier failed."""

    exit_code = 40


class PolicyBlockedError(PatchGuardError):
    """Execution blocked by policy."""

    exit_code = 50


class ArtifactWriteError(PatchGuardError):
    """Failed to write artifact."""

    exit_code = 60


class CleanupError(PatchGuardError):
    """Cleanup failed."""

    exit_code = 70


class InvariantViolationError(PatchGuardError):
    """Original workspace invariant violated."""

    exit_code = 80


class WorkspaceError(PatchGuardError):
    """Workspace operation failed (worktree, git, fingerprint)."""

    exit_code = 20
