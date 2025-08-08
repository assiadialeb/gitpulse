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

def assert_safe_repo_path(repo_path: str) -> Path:
    """Validate that repo_path is a safe, existing directory within allowed bases.

    Allowed base directories:
    - system temporary directory
    - optional GITPULSE_WORK_DIR if set
    """
    if not isinstance(repo_path, str) or not repo_path:
        raise ValueError("Invalid repository path")
    if "\x00" in repo_path:
        raise ValueError("Invalid null byte in path")

    repo_path_obj = Path(repo_path).resolve()
    if not repo_path_obj.is_absolute():
        raise ValueError("Repository path must be absolute")
    if not repo_path_obj.is_dir():
        raise ValueError("Repository path must be an existing directory")

    allowed_base_paths = [Path(tempfile.gettempdir()).resolve()]
    work_dir = os.environ.get("GITPULSE_WORK_DIR")
    if work_dir:
        allowed_base_paths.append(Path(work_dir).resolve())

    def _is_within(base: Path, path: Path) -> bool:
        try:
            path.relative_to(base)
            return True
        except Exception:
            return False

    if not any(_is_within(base, repo_path_obj) or repo_path_obj == base for base in allowed_base_paths):
        raise ValueError("Repository path is outside allowed directories")

    return repo_path_obj

