import pytest

from campaign_provisioner.repositories import set_repo
from campaign_provisioner.repositories.memory_repo import MemoryRepository


@pytest.fixture(autouse=True)
def repo():
    r = MemoryRepository()
    set_repo(r)
    yield r
    set_repo(None)
