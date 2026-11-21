"""Access checks shared by the local tools and application."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class PathNotAllowed(ValueError):
    """The opened file is outside the authorized file set."""


@contextmanager
def open_authorized(root: Path, path: Path) -> Iterator[BinaryIO]:
    target = path.resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise PathNotAllowed("File is outside the authorized set")
    with target.open("rb") as handle:
        current = target.resolve(strict=True)
        opened = os.fstat(handle.fileno())
        if (not current.is_relative_to(root) or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1 or not os.path.samestat(opened, current.stat())):
            raise PathNotAllowed("File changed during authorization or is multiply linked")
        yield handle


@contextmanager
def exclusive_lock(path: Path, message: str) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b", buffering=0) as handle:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError(message) from error
        yield
