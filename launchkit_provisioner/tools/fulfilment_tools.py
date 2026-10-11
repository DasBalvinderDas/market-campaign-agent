"""Tool of the fulfilment agent."""
from .. import execution
from ..repositories import get_repo
from ..workflow.integration_client import IntegrationExecutor


def execute_plan(request_id: str) -> dict:
    """Place every order of the APPROVED sourcing scenario in one call: a purchase order per vendor line and a depot
    transfer per surplus-stock line (Application Integration workflows), then the tracking update to the launch team.
    Nothing is placed unless the sign-off is APPROVED. Safe to call again: placed lines are skipped.

    Args:
        request_id: Request id with an approved sign-off.
    """
    return execution.execute_plan(get_repo(), IntegrationExecutor(), request_id)
