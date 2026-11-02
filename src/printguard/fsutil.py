from __future__ import annotations

from pathlib import Path


def private_mkdir(path: Path) -> None:
    """Create the directory readable only by its owner. On Windows the mode is
    ignored and the folder's ACL applies, which the install guide tells you to set."""
    if not path.parent.exists():
        private_mkdir(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
