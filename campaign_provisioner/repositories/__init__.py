"""Repository selection: BigQuery (default). An in-memory repository exists for unit tests only."""
from .. import config
from .base import Repository

_repo: Repository | None = None


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        if config.DATA_BACKEND == "memory":  # unit tests only
            from .memory_repo import MemoryRepository
            _repo = MemoryRepository()
        else:
            from .bigquery_repo import BigQueryRepository
            _repo = BigQueryRepository(config.PROJECT, config.BQ_DATASET, config.BQ_LOCATION)
    return _repo


def set_repo(repo: Repository | None) -> None:
    """Swap the repository (used by tests)."""
    global _repo
    _repo = repo
