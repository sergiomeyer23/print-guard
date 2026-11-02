from __future__ import annotations

import os
import sys
from pathlib import Path

from printguard.fsutil import private_mkdir


class LockBusy(Exception):
    pass


class ProcessLock:
    """Exclusive, non-blocking lock owned by the OS. It disappears with the process,
    so a crash can never leave a stale lock behind."""

    def __init__(self, path: Path):
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        private_mkdir(self.path.parent)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        try:
            _lock(fd)
        except OSError as exc:
            os.close(fd)
            raise LockBusy(f"another printguard instance holds {self.path}") from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            _unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> ProcessLock:
        self.acquire()
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()


if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
