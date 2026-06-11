"""Patch diff metrics — analyses patch.diff content."""

from __future__ import annotations

SENSITIVE_PATHS = [
    ".git/hooks", ".env", "credentials", "secrets",
    "id_rsa", "id_ed25519", "authorized_keys",
    "/etc/passwd", "/etc/shadow", ".ssh/",
]


def compute_diff_metrics(patch: str) -> dict[str, object]:
    """Compute structural metrics from a git diff patch."""
    files_changed = 0
    files_added = 0
    files_deleted = 0
    lines_added = 0
    lines_deleted = 0
    binary_files = 0
    changed_paths: list[str] = []
    touched_sensitive: list[str] = []

    current_file = ""
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            files_changed += 1
            # Extract file path
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].removeprefix("b/")
                changed_paths.append(current_file)
                if _is_sensitive(current_file):
                    touched_sensitive.append(current_file)
        elif line.startswith("new file mode"):
            files_added += 1
        elif line.startswith("deleted file mode"):
            files_deleted += 1
        elif line.startswith("Binary files"):
            binary_files += 1
        elif line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
        elif line.startswith("-") and not line.startswith("---"):
            lines_deleted += 1

    return {
        "files_changed": files_changed,
        "files_added": files_added,
        "files_deleted": files_deleted,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "binary_files_changed": binary_files,
        "changed_paths": sorted(set(changed_paths)),
        "touched_sensitive_paths": sorted(set(touched_sensitive)),
    }


def _is_sensitive(path: str) -> bool:
    return any(
        sp in path or path.startswith(sp.lstrip("/"))
        for sp in SENSITIVE_PATHS
    )
