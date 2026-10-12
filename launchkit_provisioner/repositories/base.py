"""Repository contract: the only data-access surface the agents' tools depend on."""
import json
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class Repository:
    """Implemented by BigQueryRepository (real) and MemoryRepository (unit tests only)."""

    # ---- launches and requests
    def list_launches(self) -> list[dict]: raise NotImplementedError
    def get_launch(self, launch_id: str) -> dict | None: raise NotImplementedError
    def create_launch(self, launch: dict) -> None: raise NotImplementedError                 # a new event
    def update_launch_dates(self, launch_id: str, in_hand_by, embargo_date) -> None: raise NotImplementedError
    def create_request(self, launch_id: str, summary: str) -> str: raise NotImplementedError
    def get_request(self, request_id: str) -> dict | None: raise NotImplementedError

    # ---- brief decomposition
    def list_bundle_types(self) -> list[str]: raise NotImplementedError
    def get_bundle_templates(self, bundle_type: str) -> list[dict]: raise NotImplementedError
    def guest_mix(self, launch_id: str) -> list[dict]: raise NotImplementedError          # size, region, plug_type, n
    def get_regional_split(self, bundle_type: str) -> list[dict]: raise NotImplementedError  # region, share_pct
    def get_asset(self, sku: str) -> dict | None: raise NotImplementedError
    def list_venues(self) -> list[dict]: raise NotImplementedError                    # where a campaign can be held
    def list_date_pricing(self) -> list[dict]: raise NotImplementedError              # price factor by days ahead
    def list_assets(self) -> list[dict]: raise NotImplementedError
    def replace_requirement_lines(self, request_id: str, lines: list[dict]) -> None: raise NotImplementedError
    def get_requirement_lines(self, request_id: str) -> list[dict]: raise NotImplementedError

    # ---- sourcing data
    def get_planning_rules(self) -> dict: raise NotImplementedError                          # key -> float
    def get_lanes(self) -> dict: raise NotImplementedError                                   # (from, to) -> {days, cost_per_unit}
    def list_vendor_offers(self, sku: str) -> list[dict]: raise NotImplementedError          # active vendors, with delay_days
    def depot_free(self, sku: str) -> list[dict]: raise NotImplementedError                  # depot_id, depot_name, region, free
    def list_vendor_offers_all(self) -> list[dict]: raise NotImplementedError                # like list_vendor_offers, plus sku
    def get_vendor(self, vendor_id: str) -> dict | None: raise NotImplementedError
    def list_vendors(self) -> list[dict]: raise NotImplementedError
    def list_depot_free(self) -> list[dict]: raise NotImplementedError                        # depot_id, depot_name, region, sku, on_hand, free
    def add_disruption(self, vendor_id: str, delay_days: int, reason: str) -> str: raise NotImplementedError
    def list_disruptions(self) -> list[dict]: raise NotImplementedError

    # ---- scenarios
    def replace_scenarios(self, request_id: str, scenarios: list[dict], lines: list[dict]) -> None: raise NotImplementedError
    def get_scenarios(self, request_id: str) -> list[dict]: raise NotImplementedError
    def get_scenario(self, scenario_id: str) -> dict | None: raise NotImplementedError
    def get_scenario_lines(self, scenario_id: str) -> list[dict]: raise NotImplementedError
    def mark_line_executed(self, line_id: str) -> None: raise NotImplementedError
    def mark_lines_executed(self, line_ids: list[str]) -> None: raise NotImplementedError

    # ---- sign-off
    def get_policy(self, amount: float) -> dict: raise NotImplementedError
    def list_policies(self) -> list[dict]: raise NotImplementedError
    def get_approver_emails(self, role: str) -> list[str]: raise NotImplementedError
    def create_decision(self, decision: dict) -> None: raise NotImplementedError
    def get_decision(self, decision_id: str) -> dict | None: raise NotImplementedError
    def get_decision_for_request(self, request_id: str) -> dict | None: raise NotImplementedError
    def decide(self, decision_id: str, status: str, decided_by: str, note: str = "") -> bool: raise NotImplementedError
    def set_decision_note(self, decision_id: str, status: str, note: str) -> None: raise NotImplementedError

    # ---- surplus stock holds
    def create_holds(self, holds: list[dict]) -> None: raise NotImplementedError
    def release_holds(self, request_id: str) -> int: raise NotImplementedError
    def consume_hold(self, line_id: str) -> None: raise NotImplementedError
    def consume_holds(self, line_ids: list[str]) -> None: raise NotImplementedError

    # ---- execution records
    def record_pos(self, pos: list[dict]) -> None: raise NotImplementedError                 # bulk
    def record_transfers(self, transfers: list[dict]) -> None: raise NotImplementedError     # bulk
    def list_pos(self, request_id: str) -> list[dict]: raise NotImplementedError
    def list_transfers(self, request_id: str) -> list[dict]: raise NotImplementedError
    def list_readiness(self, launch_id: str | None = None) -> list[dict]: raise NotImplementedError

    # ---- audit
    def log_audit(self, request_id: str | None, actor: str, action: str, details: dict) -> None: raise NotImplementedError
    def log_audit_batch(self, request_id: str | None, events: list[tuple]) -> None: raise NotImplementedError   # (actor, action, details)
    def list_audit(self, request_id: str | None = None) -> list[dict]: raise NotImplementedError

    @staticmethod
    def dumps(details: dict) -> str:
        return json.dumps(details, default=str, sort_keys=True)
