"""
Input validation utilities for repository identifiers and filesystem paths.
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Optional


REPO_FULL_NAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


def assert_safe_repository_full_name(repository_full_name: str) -> None:
    """Validate owner/repo format with safe characters only."""
    if not isinstance(repository_full_name, str):
        raise ValueError("repository_full_name must be a string")
    if not REPO_FULL_NAME_PATTERN.match(repository_full_name):
        raise ValueError("Invalid repository_full_name format")


def parse_object_id_or_raise(id_str: str):
    """Parse a string as a BSON ObjectId, raising ValueError if invalid."""
    from bson import ObjectId
    try:
        return ObjectId(id_str)
    except Exception as exc:
        raise ValueError("Invalid ObjectId format") from exc

def _is_safe_path_string(path_str: str) -> bool:
    """Basic allowlist validation for path strings (POSIX focus).

    Rules:
    - Only allow characters: letters, numbers, hyphen, underscore, dot, slash
    - Disallow path traversal segments: '.' and '..'
    - Disallow backslashes and drive letters
    - Disallow consecutive slashes
    """
    if not isinstance(path_str, str) or not path_str:
        return False
    if "\x00" in path_str:
        return False
    # Allowlist of characters
    if not re.match(r'^[A-Za-z0-9_./-]+$', path_str):
        return False
    # Disallow Windows-style components
    if "\\" in path_str or ":" in path_str:
        return False
    # Normalize and check traversal segments
    segments = [seg for seg in path_str.split('/') if seg != '']
    for seg in segments:
        if seg in ('.', '..'):
            return False
    # Disallow consecutive slashes (already removed in segments, but check original)
    if '//' in path_str:
        return False
    return True

def assert_safe_repo_path(repo_path: str) -> Path:
    """Validate that repo_path is a safe, existing directory within allowed bases.

    Strategy (CodeQL-compliant):
    - Validate the raw input with an allowlist and forbid traversal/backslashes
    - Require absolute paths
    - Identify the matching allowed base via string prefix
    - Rebuild a normalized path using os.path.join(base, relative)
    - Verify the normalized path still lies under the base (prefix check)
    - Only then touch the filesystem (os.path.isdir)
    """
    if not _is_safe_path_string(repo_path):
        raise ValueError("Repository path has unsafe characters or traversal segments")

    if not os.path.isabs(repo_path):
        raise ValueError("Repository path must be absolute")

    # Prepare allowed base paths as normalized absolute strings with trailing sep trimmed
    allowed_bases: list[str] = []
    tmp_base = os.path.normpath(tempfile.gettempdir())
    allowed_bases.append(tmp_base)
    work_dir = os.environ.get("GITPULSE_WORK_DIR")
    if work_dir and _is_safe_path_string(work_dir) and os.path.isabs(work_dir):
        allowed_bases.append(os.path.normpath(work_dir))

    # Find a base that matches the beginning of the input path (string-level)
    matched_base: Optional[str] = None
    for base in allowed_bases:
        if repo_path == base or repo_path.startswith(base + os.sep):
            matched_base = base
            break

    if matched_base is None:
        raise ValueError("Repository path is outside allowed directories")

    # Compute relative segment safely, then rebuild the candidate path
    relative_part = repo_path[len(matched_base):].lstrip(os.sep)
    candidate = os.path.normpath(os.path.join(matched_base, relative_part))

    # Ensure the normalized candidate still lies within the matched base
    if not (candidate == matched_base or candidate.startswith(matched_base + os.sep)):
        raise ValueError("Repository path escapes allowed base after normalization")

    if not os.path.isdir(candidate):
        raise ValueError("Repository path must be an existing directory")

    return Path(candidate)

