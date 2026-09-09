"""keel_version, and program_version = declared string + source hash (§23.1)."""

from __future__ import annotations

import hashlib
import inspect
from typing import Any

KEEL_VERSION = "0.1.0"


def code_hash(fn: Any) -> str:
    """sha256 of the program's own source. A whitespace-only edit changes it; that is intended —
    program_version is an identity, and a shadow VERIFY is what decides whether it matters (§5)."""
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):  # interactively defined program
        src = repr(fn)
    return hashlib.sha256(src.encode()).hexdigest()


def program_version(declared: str, fn: Any) -> str:
    return f"{declared}+{code_hash(fn)[:6]}"
