"""
Input validation utilities to protect Mongo queries from injection.
"""
import re
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

