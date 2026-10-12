"""In-memory repository seeded from the same data as BigQuery (unit tests only)."""
import copy
from collections import Counter

from .. import approvers as approvers_cfg
from .. import config
from ..data.seed_data import APPROVER_ROLES, SEED, TEAM_ROLE
from .base import Repository, new_id, now

_OPTION_ORDER = {"FULL_NEW": 0, "REBALANCE": 1, "ECO": 2}


class MemoryRepository(Repository):
    def __init__(self):
        self.t = copy.deepcopy(SEED)
        self.t["approvers"] = approvers_cfg.expand(approvers_cfg.parse(config.APPROVER_EMAILS),
                                                   APPROVER_ROLES + [TEAM_ROLE])

    # ---- launches and requests
    def list_launches(self):
        return [dict(x) for x in self.t["launches"]]

    def get_launch(self, launch_id):
        return next((dict(x) for x in self.t["launches"] if x["launch_id"] == launch_id), None)

    def create_launch(self, launch):
        self.t["launches"].append(dict(launch))

    def update_launch_dates(self, launch_id, in_hand_by, embargo_date):
        for x in self.t["launches"]:
            if x["launch_id"] == launch_id:
                x["in_hand_by"], x["embargo_date"] = in_hand_by, embargo_date

    def create_request(self, launch_id, summary):
        rid = f"REQ-{len(self.t['launch_requests']) + 1:03d}"
        self.t["launch_requests"].append({"request_id": rid, "launch_id": launch_id, "summary": summary,
                                          "created_at": now()})
        return rid

    def get_request(self, request_id):
        return next((dict(r) for r in self.t["launch_requests"] if r["request_id"] == request_id), None)

    # ---- brief decomposition
    def list_bundle_types(self):
        return sorted({b["bundle_type"] for b in self.t["bundle_templates"]})

    def get_bundle_templates(self, bundle_type):
        return [dict(b) for b in self.t["bundle_templates"] if b["bundle_type"] == bundle_type]

    def guest_mix(self, launch_id):
        c = Counter((x["size"], x["region"], x["plug_type"]) for x in self.t["guests"] if x["launch_id"] == launch_id)
        return [{"size": s, "region": r, "plug_type": p, "n": n} for (s, r, p), n in sorted(c.items())]

    def get_regional_split(self, bundle_type):
        return [dict(x) for x in self.t["regional_split"] if x["bundle_type"] == bundle_type]

    def get_asset(self, sku):
        return next((dict(a) for a in self.t["assets"] if a["sku"] == sku), None)

    def list_assets(self):
        return [dict(a) for a in self.t["assets"]]

    def replace_requirement_lines(self, request_id, lines):
        self.t["requirement_lines"] = [x for x in self.t["requirement_lines"] if x["request_id"] != request_id]
        for i, ln in enumerate(lines, start=1):
            self.t["requirement_lines"].append({**ln, "request_id": request_id, "line_no": i, "created_at": now()})

    def get_requirement_lines(self, request_id):
        rows = [dict(x) for x in self.t["requirement_lines"] if x["request_id"] == request_id]
        return sorted(rows, key=lambda x: x["line_no"])

    # ---- sourcing data
    def get_planning_rules(self):
        return {r["rule_key"]: float(r["rule_value"]) for r in self.t["planning_rules"]}

    def get_lanes(self):
        return {(x["from_region"], x["to_region"]): {"days": x["days"], "cost_per_unit": x["cost_per_unit"]}
                for x in self.t["transit_lanes"]}

    def _delay(self, vendor_id):
        return sum(d["delay_days"] for d in self.t["vendor_disruptions"] if d["vendor_id"] == vendor_id and d["active"])

    def list_vendor_offers(self, sku):
        vendors = {v["vendor_id"]: v for v in self.t["vendors"] if v["active"]}
        return [{"vendor_id": o["vendor_id"], "vendor_name": vendors[o["vendor_id"]]["vendor_name"],
                 "home_region": vendors[o["vendor_id"]]["home_region"], "variant": o["variant"],
                 "unit_price": o["unit_price"], "lead_days": o["lead_days"], "carbon_kg": o["carbon_kg"],
                 "delay_days": self._delay(o["vendor_id"])}
                for o in self.t["vendor_offers"] if o["sku"] == sku and o["vendor_id"] in vendors]

    def list_vendor_offers_all(self):
        return [{**o, "sku": s} for s in sorted({x["sku"] for x in self.t["vendor_offers"]})
                for o in self.list_vendor_offers(s)]

    def depot_free(self, sku):
        depots = {d["depot_id"]: d for d in self.t["depots"]}
        out = []
        for s in self.t["depot_stock"]:
            if s["sku"] != sku:
                continue
            held = sum(h["quantity"] for h in self.t["depot_holds"] if h["depot_id"] == s["depot_id"]
                       and h["sku"] == sku and h["status"] in ("ACTIVE", "CONSUMED"))
            d = depots[s["depot_id"]]
            out.append({"depot_id": d["depot_id"], "depot_name": d["depot_name"], "region": d["region"],
                        "free": s["on_hand"] - held})
        return out

    def get_vendor(self, vendor_id):
        return next((dict(v) for v in self.t["vendors"] if v["vendor_id"] == vendor_id), None)

    def list_vendors(self):
        return [dict(v) for v in self.t["vendors"] if v["active"]]

    def list_depot_free(self):
        out = []
        for s in self.t["depot_stock"]:
            for d in self.depot_free(s["sku"]):
                if d["depot_id"] == s["depot_id"]:
                    out.append({**d, "sku": s["sku"], "on_hand": s["on_hand"]})
        return sorted(out, key=lambda x: (x["depot_id"], x["sku"]))

    def add_disruption(self, vendor_id, delay_days, reason):
        did = new_id("DSR")
        self.t["vendor_disruptions"].append({"disruption_id": did, "vendor_id": vendor_id, "delay_days": int(delay_days),
                                             "reason": reason, "active": True, "created_at": now()})
        return did

    def list_disruptions(self):
        return [dict(d) for d in self.t["vendor_disruptions"] if d["active"]]

    # ---- scenarios
    def replace_scenarios(self, request_id, scenarios, lines):
        self.t["scenarios"] = [s for s in self.t["scenarios"] if s["request_id"] != request_id]
        self.t["scenario_lines"] = [x for x in self.t["scenario_lines"] if x["request_id"] != request_id]
        self.t["scenarios"] += [{**s, "created_at": now()} for s in scenarios]
        self.t["scenario_lines"] += [dict(x) for x in lines]

    def get_scenarios(self, request_id):
        rows = [dict(s) for s in self.t["scenarios"] if s["request_id"] == request_id]
        return sorted(rows, key=lambda s: _OPTION_ORDER.get(s["option_code"], 9))

    def get_scenario(self, scenario_id):
        return next((dict(s) for s in self.t["scenarios"] if s["scenario_id"] == scenario_id), None)

    def get_scenario_lines(self, scenario_id):
        return sorted((dict(x) for x in self.t["scenario_lines"] if x["scenario_id"] == scenario_id),
                      key=lambda x: x["line_id"])

    def mark_lines_executed(self, line_ids):
        for lid in line_ids:
            self.mark_line_executed(lid)

    def mark_line_executed(self, line_id):
        for x in self.t["scenario_lines"]:
            if x["line_id"] == line_id:
                x["execution_status"] = "EXECUTED"

    # ---- sign-off
    def get_policy(self, amount):
        for p in self.t["approval_policy"]:
            if p["min_amount"] < amount <= p["max_amount"]:
                return dict(p)
        return dict(self.t["approval_policy"][0])

    def list_policies(self):
        return [dict(p) for p in self.t["approval_policy"]]

    def get_approver_emails(self, role):
        return [a["email"] for a in self.t["approvers"] if a["approver_role"] == role and a["active"]]

    def create_decision(self, decision):
        self.t["decisions"].append({"status": "PENDING", "decided_by": None, "decided_at": None,
                                    "decision_note": None, "created_at": now(), **decision})

    def get_decision(self, decision_id):
        return next((dict(d) for d in self.t["decisions"] if d["decision_id"] == decision_id), None)

    def get_decision_for_request(self, request_id):
        rows = [d for d in self.t["decisions"] if d["request_id"] == request_id]
        return dict(rows[-1]) if rows else None

    def decide(self, decision_id, status, decided_by, note=""):
        for d in self.t["decisions"]:
            if d["decision_id"] == decision_id and d["status"] == "PENDING" and d["expires_at"] > now():
                d.update(status=status, decided_by=decided_by, decided_at=now(), decision_note=note)
                return True
        return False

    def set_decision_note(self, decision_id, status, note):
        for d in self.t["decisions"]:
            if d["decision_id"] == decision_id:
                d.update(status=status, decision_note=note)

    # ---- surplus stock holds
    def create_holds(self, holds):
        for h in holds:
            self.t["depot_holds"].append({"hold_id": new_id("HLD"), "status": "ACTIVE", "created_at": now(), **h})

    def release_holds(self, request_id):
        n = 0
        for h in self.t["depot_holds"]:
            if h["request_id"] == request_id and h["status"] == "ACTIVE":
                h["status"] = "RELEASED"
                n += h["quantity"]
        return n

    def consume_holds(self, line_ids):
        for lid in line_ids:
            self.consume_hold(lid)

    def consume_hold(self, line_id):
        for h in self.t["depot_holds"]:
            if h["line_id"] == line_id and h["status"] == "ACTIVE":
                h["status"] = "CONSUMED"

    # ---- execution records
    def record_pos(self, pos):
        self.t["purchase_orders"] += [{**po, "created_at": now()} for po in pos]

    def record_transfers(self, transfers):
        self.t["depot_transfers"] += [{**t, "created_at": now()} for t in transfers]

    def list_pos(self, request_id):
        return [dict(p) for p in self.t["purchase_orders"] if p["request_id"] == request_id]

    def list_transfers(self, request_id):
        return [dict(p) for p in self.t["depot_transfers"] if p["request_id"] == request_id]

    def list_readiness(self, launch_id=None):
        out = []
        for r in self.t["launch_requests"]:
            if launch_id and r["launch_id"] != launch_id:
                continue
            launch = self.get_launch(r["launch_id"])
            dc = self.get_decision_for_request(r["request_id"])
            sc = self.get_scenario(dc["scenario_id"]) if dc else None
            lines = self.get_scenario_lines(dc["scenario_id"]) if dc else []
            if not dc:
                ready = "NO_DECISION"
            elif dc["status"] != "APPROVED":
                ready = dc["status"]
            else:
                ready = "RED" if sc["buffer_hours"] < 0 else "AMBER" if sc["buffer_hours"] < 24 else "GREEN"
            out.append({"request_id": r["request_id"], "launch_id": r["launch_id"], "launch_name": launch["launch_name"],
                        "in_hand_by": launch["in_hand_by"], "embargo_date": launch["embargo_date"],
                        "chosen_option": dc["option_code"] if dc else None,
                        "decision_status": dc["status"] if dc else None, "tier": dc["tier"] if dc else None,
                        "authorised_amount": dc["amount"] if dc else None,
                        "delivery_date": sc["delivery_date"] if sc else None,
                        "buffer_hours": sc["buffer_hours"] if sc else None, "readiness": ready,
                        "lines_executed": sum(1 for x in lines if x["execution_status"] == "EXECUTED"),
                        "lines_total": len(lines)})
        return out

    # ---- audit
    def log_audit(self, request_id, actor, action, details):
        self.t["audit_log"].append({"event_id": new_id("EVT"), "created_at": now(), "request_id": request_id,
                                    "actor": actor, "action": action, "details": self.dumps(details)})

    def log_audit_batch(self, request_id, events):
        for actor, action, details in events:
            self.log_audit(request_id, actor, action, details)

    def list_audit(self, request_id=None):
        rows = [a for a in self.t["audit_log"] if request_id in (None, a["request_id"])]
        return [{**a, "created_at": a["created_at"].isoformat(timespec="seconds")} for a in rows]
