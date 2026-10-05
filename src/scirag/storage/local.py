"""Object storage backed by a local directory."""

import os
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    def put(self, key: str, chunks: Iterable[bytes]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write next to the target, then rename: a reader never sees a partial file,
        # and a failed upload leaves nothing under the real key.
        partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
        try:
            with partial.open("wb") as file:
                for chunk in chunks:
                    file.write(chunk)
                file.flush()
                os.fsync(file.fileno())
            partial.rename(path)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()
