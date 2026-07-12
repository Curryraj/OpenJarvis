"""Default filesystem sandbox for file_read/file_write.

Both tools accept an ``allowed_dirs`` constructor argument that restricts
which paths they may touch, but every call site instantiates them with no
arguments (``cls()`` in ``mcp/server.py`` and ``agents/executor.py``), so
``allowed_dirs`` was always empty and any agent handed either tool got
unrestricted read/write access to the whole filesystem. ``default_allowed_dirs``
computes a sane default instead — the working directory the process was
started from, plus a dedicated workspace under ``~/.openjarvis`` — used
whenever a caller doesn't explicitly pass ``allowed_dirs``. Passing
``allowed_dirs=[]`` explicitly still means "unrestricted", preserving that
escape hatch for callers that deliberately want it.
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def default_allowed_dirs() -> List[str]:
    from openjarvis.core.config import load_config
    from openjarvis.core.paths import get_config_dir

    try:
        cfg = load_config()
        configured = (cfg.tools.filesystem_allowed_dirs or "").strip()
    except Exception:
        configured = ""

    if configured:
        return [d.strip() for d in configured.split(",") if d.strip()]

    workspace = get_config_dir() / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    return [str(Path.cwd()), str(workspace)]


__all__ = ["default_allowed_dirs"]
