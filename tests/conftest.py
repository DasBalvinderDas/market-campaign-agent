import os

# Unit tests run without any cloud access: use the in-memory repository.
os.environ["DATA_BACKEND"] = "memory"

import pytest

from launchkit_provisioner.repositories import set_repo
from launchkit_provisioner.repositories.memory_repo import MemoryRepository


@pytest.fixture(autouse=True)
def _email_channel(monkeypatch):
    """The shipped default is the Inbox workflow with notice emails; most tests cover the email approval, so they start there."""
    from launchkit_provisioner import config
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "email")
    monkeypatch.setattr(config, "APPROVAL_NOTIFY_EMAIL", False)


@pytest.fixture(autouse=True)
def repo():
    r = MemoryRepository()
    # approvers for the two sign-off roles (the launch team is added by the tests that need it)
    r.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True},
                        {"approver_role": "CMO", "email": "cmo@example.com", "active": True}]
    set_repo(r)
    yield r
    set_repo(None)


BRIEF = [{"bundle_type": "GUEST_KIT", "quantity": 150}, {"bundle_type": "VENUE_DISPLAY", "quantity": 10},
         {"bundle_type": "SALES_PACK", "quantity": 300}]


@pytest.fixture
def aurora(repo):
    """A request for the full Spring Launch Event brief with its scenarios computed."""
    from launchkit_provisioner import planner
    rid = repo.create_request("LAUNCH-SPRING", "Spring Launch Event kits")
    repo.replace_requirement_lines(rid, planner.expand_bundles(repo, "LAUNCH-SPRING", BRIEF))
    scenarios, lines = planner.plan_scenarios(repo, rid)
    repo.replace_scenarios(rid, scenarios, lines)
    return rid


class FakeExecutor:
    """Stands in for Application Integration: records calls, answers like the real workflows."""

    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on
        self.execution = {"executionDetails": {"state": "SUSPENDED"}}
        self.suspensions = []

    def _out(self, trigger_id, inputs):
        from launchkit_provisioner import config
        if trigger_id == config.PO_TRIGGER:
            return {"po_number": f"PO-{inputs['plan_line_id']}", "execution_id": "exec-po"}
        if trigger_id == config.TRANSFER_TRIGGER:
            return {"transfer_number": f"TR-{inputs['plan_line_id']}", "execution_id": "exec-tr"}
        return {"status": "SENT"}

    def execute(self, trigger_id, inputs):
        self.calls.append((trigger_id, inputs))
        if self.fail_on and self.fail_on(trigger_id, inputs):
            raise RuntimeError("workflow down")
        return self._out(trigger_id, inputs)

    def start(self, trigger_id, inputs):
        self.calls.append((trigger_id, inputs))
        return {"executionId": "exec-9", "executionFailed": False}

    def get_execution(self, execution_id):
        assert execution_id == "exec-9"
        return self.execution

    def list_suspensions(self, execution_id):
        return self.suspensions
