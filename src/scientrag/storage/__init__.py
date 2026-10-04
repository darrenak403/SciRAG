from functools import lru_cache

from scientrag.config import get_settings
from scientrag.storage.base import ObjectStorage
from scientrag.storage.local import LocalStorage


@lru_cache
def get_storage() -> ObjectStorage:
    return LocalStorage(get_settings().storage_dir)
