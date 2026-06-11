class AgentFenceError(Exception):
    """Base exception for all AgentFence errors."""

    exit_code: int = 10


class ConfigurationError(AgentFenceError):
    """Input or configuration error."""

    exit_code = 10


class EnvironmentError(AgentFenceError):
    """Docker or Git environment not available."""

    exit_code = 20


class AgentProcessError(AgentFenceError):
    """Agent process failed."""

    exit_code = 30


class AgentTimeoutError(AgentFenceError):
    """Agent timed out."""

    exit_code = 31


class VerifierError(AgentFenceError):
    """Verifier failed."""

    exit_code = 40


class PolicyBlockedError(AgentFenceError):
    """Execution blocked by policy."""

    exit_code = 50


class ArtifactWriteError(AgentFenceError):
    """Failed to write artifact."""

    exit_code = 60


class CleanupError(AgentFenceError):
    """Cleanup failed."""

    exit_code = 70


class InvariantViolationError(AgentFenceError):
    """Original workspace invariant violated."""

    exit_code = 80


class WorkspaceError(AgentFenceError):
    """Workspace operation failed (worktree, git, fingerprint)."""

    exit_code = 20
