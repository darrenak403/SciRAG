from functools import lru_cache

from scirag.config import get_settings
from scirag.storage.base import ObjectStorage
from scirag.storage.local import LocalStorage


@lru_cache
def get_storage() -> ObjectStorage:
    return LocalStorage(get_settings().storage_dir)
