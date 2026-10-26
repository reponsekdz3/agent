"""Security primitives shared by NOVA-APEX controllers and API routes."""
from pathlib import Path


def resolve_inside(root: Path | str, untrusted_path: str | Path) -> Path:
    """Resolve a path and reject traversal (including symlinks) outside *root*.

    Relative paths are interpreted beneath root. Absolute paths are accepted only
    when their resolved target is still beneath root. strict=False lets callers
    validate a new file before it exists while still resolving existing symlinks.
    """
    if untrusted_path is None:
        raise ValueError("A relative workspace path is required.")
    raw = str(untrusted_path).strip()
    if not raw:
        raise ValueError("A non-empty workspace path is required.")

    root_path = Path(root).expanduser().resolve()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Path must remain inside the configured workspace.") from exc
    return resolved
