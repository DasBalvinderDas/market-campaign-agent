import os

# Unit tests run without any cloud access: use the in-memory repository and local workflow test doubles.
os.environ["DATA_BACKEND"] = "memory"
os.environ["WORKFLOW_BACKEND"] = "mock"

import pytest

from campaign_provisioner.repositories import set_repo
from campaign_provisioner.repositories.memory_repo import MemoryRepository


@pytest.fixture(autouse=True)
def repo():
    r = MemoryRepository()
    set_repo(r)
    yield r
    set_repo(None)
