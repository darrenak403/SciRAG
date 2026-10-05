from collections.abc import Iterator
from pathlib import Path

import pytest

from scirag.storage.local import LocalStorage


def test_put_then_open_returns_the_same_bytes(tmp_path: Path):
    storage = LocalStorage(tmp_path)

    storage.put("papers/1/original.pdf", [b"first ", b"second"])

    assert storage.exists("papers/1/original.pdf")
    with storage.open("papers/1/original.pdf") as file:
        assert file.read() == b"first second"


def test_a_failed_put_leaves_nothing_behind(tmp_path: Path):
    storage = LocalStorage(tmp_path)

    def broken() -> Iterator[bytes]:
        yield b"first "
        raise RuntimeError("upload interrupted")

    with pytest.raises(RuntimeError):
        storage.put("papers/1/original.pdf", broken())

    assert not storage.exists("papers/1/original.pdf")
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_delete_removes_the_object_and_ignores_a_missing_one(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    storage.put("a.pdf", [b"x"])

    storage.delete("a.pdf")
    storage.delete("a.pdf")

    assert not storage.exists("a.pdf")
    with pytest.raises(FileNotFoundError):
        storage.open("a.pdf")


@pytest.mark.parametrize("key", ["../outside.pdf", "papers/../../outside.pdf", "/etc/passwd"])
def test_a_key_outside_the_root_is_refused(tmp_path: Path, key: str):
    storage = LocalStorage(tmp_path / "root")

    with pytest.raises(ValueError):
        storage.put(key, [b"x"])
    with pytest.raises(ValueError):
        storage.open(key)
