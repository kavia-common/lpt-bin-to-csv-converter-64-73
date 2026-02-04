"""
Security utilities for the API.

Includes:
- Path normalization and allow-root validation for path-based conversion.
- Filename sanitization for download names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


# PUBLIC_INTERFACE
def resolve_and_validate_path(
    user_path: str, *, must_exist: bool, allowed_root: Optional[Path]
) -> Path:
    """Resolve and validate a user-provided filesystem path.

    This prevents obvious path traversal issues by resolving to an absolute path and,
    if configured, enforcing that it is within an allowed root directory.

    Args:
        user_path: Path string supplied by the client.
        must_exist: If True, require the path to exist on disk.
        allowed_root: If provided, the resolved path must be within this directory.

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: if the path is empty/invalid, violates allowed_root, or must_exist fails.
    """
    if user_path is None or str(user_path).strip() == "":
        raise ValueError("Path cannot be empty")

    # Resolve symlinks/.. segments to a canonical absolute path.
    p = Path(user_path).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except Exception as e:
        raise ValueError(f"Invalid path: {user_path}") from e

    if allowed_root is not None:
        root = allowed_root.resolve(strict=False)
        # Python 3.9+: Path.is_relative_to
        try:
            is_within = resolved.is_relative_to(root)
        except AttributeError:
            is_within = str(resolved).startswith(str(root) + "/") or str(
                resolved
            ) == str(root)

        if not is_within:
            raise ValueError(f"Path is outside allowed root: {user_path}")

    if must_exist and not resolved.exists():
        raise ValueError(f"Path does not exist: {user_path}")

    return resolved


# PUBLIC_INTERFACE
def sanitize_download_filename(filename: str, default: str = "output.csv") -> str:
    """Sanitize a filename for use in Content-Disposition.

    Args:
        filename: Proposed filename.
        default: Fallback if filename is empty.

    Returns:
        A safe filename containing only basic characters.
    """
    if not filename or filename.strip() == "":
        return default

    # Keep only a conservative set of characters.
    keep = []
    for ch in filename.strip():
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            keep.append(ch)
    cleaned = "".join(keep).strip().replace(" ", "_")
    if cleaned in ("", ".", ".."):
        return default
    return cleaned
