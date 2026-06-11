class RepoAirlockError(Exception):
    """Base exception for all RepoAirlock errors."""

    exit_code: int = 10


class ConfigurationError(RepoAirlockError):
    """Input or configuration error."""

    exit_code = 10


class EnvironmentError(RepoAirlockError):
    """Docker or Git environment not available."""

    exit_code = 20


class AgentProcessError(RepoAirlockError):
    """Agent process failed."""

    exit_code = 30


class AgentTimeoutError(RepoAirlockError):
    """Agent timed out."""

    exit_code = 31


class VerifierError(RepoAirlockError):
    """Verifier failed."""

    exit_code = 40


class PolicyBlockedError(RepoAirlockError):
    """Execution blocked by policy."""

    exit_code = 50


class ArtifactWriteError(RepoAirlockError):
    """Failed to write artifact."""

    exit_code = 60


class CleanupError(RepoAirlockError):
    """Cleanup failed."""

    exit_code = 70


class InvariantViolationError(RepoAirlockError):
    """Original workspace invariant violated."""

    exit_code = 80


class WorkspaceError(RepoAirlockError):
    """Workspace operation failed (worktree, git, fingerprint)."""

    exit_code = 20
