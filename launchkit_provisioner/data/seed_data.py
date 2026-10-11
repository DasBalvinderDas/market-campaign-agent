"""Demo data for The LaunchKit Provisioner: a fictional flagship launch, "Project Aurora".

All names, prices and quantities are made up. Loaded by ``scripts/setup_bigquery.py`` (and used in memory by the
unit tests). Launch dates are relative to the day the data is set up, so the story always works:
in-hand deadline = setup day + 25, press embargo = setup day + 32 (``scripts/setup_bigquery.py --reset-demo``
moves them to today again).
"""
from datetime import date, timedelta

IN_HAND_DAYS = 25
EMBARGO_DAYS = 32

REGIONS = ["US", "EMEA", "APAC"]


def launch_dates(today: date | None = None) -> dict:
    today = today or date.today()
    return {"in_hand_by": today + timedelta(days=IN_HAND_DAYS), "embargo_date": today + timedelta(days=EMBARGO_DAYS)}


def _creators():
    """150 creators: sizes S20 M45 L60 XL25; regions US85 EMEA45 APAC20; plugs by region. Deterministic."""
    sizes = ["S"] * 20 + ["M"] * 45 + ["L"] * 60 + ["XL"] * 25
    sizes = [sizes[(i * 37) % 150] for i in range(150)]  # 37 is coprime with 150: a fixed shuffle
    regions = ["US"] * 85 + ["EMEA"] * 45 + ["APAC"] * 20
    plugs = ["US-A"] * 85 + ["UK-G"] * 30 + ["EU-C"] * 15 + ["JP-A"] * 12 + ["AU-I"] * 8
    return [{"creator_id": f"CR-{i + 1:03d}", "launch_id": "LAUNCH-AURORA", "handle": f"@creator_{i + 1:03d}",
             "name": f"Creator {i + 1:03d}", "size": sizes[i], "region": regions[i], "plug_type": plugs[i]}
            for i in range(150)]


_HOODIES = [("HOODIE-AURORA-S", "Aurora hoodie S"), ("HOODIE-AURORA-M", "Aurora hoodie M"),
            ("HOODIE-AURORA-L", "Aurora hoodie L"), ("HOODIE-AURORA-XL", "Aurora hoodie XL")]
_PLUGS = [("PWR-US-A", "Power adapter, US type A"), ("PWR-UK-G", "Power adapter, UK type G"),
          ("PWR-EU-C", "Power adapter, EU type C"), ("PWR-JP-A", "Power adapter, JP type A"),
          ("PWR-AU-I", "Power adapter, AU type I")]


def _offers():
    rows = []

    def add(vendor, sku, variant, price, lead, carbon):
        rows.append({"vendor_id": vendor, "sku": sku, "variant": variant, "unit_price": price, "lead_days": lead,
                     "carbon_kg": carbon})

    add("V-LUXPACK", "PKG-LUX-BOX-BLACK", "STANDARD", 85.0, 14, 4.2)
    add("V-LUXPACK", "PKG-LUX-BOX-BLACK", "ECO", 98.0, 16, 1.9)
    for sku, _ in _HOODIES:
        add("V-APPAREL", sku, "STANDARD", 42.0, 12, 9.0)
        add("V-APPAREL", sku, "ECO", 52.0, 15, 3.5)
    for sku, _ in _PLUGS:
        add("V-PWRTECH", sku, "STANDARD", 9.0, 7, 1.2)
    add("V-ENGRAVE", "CARD-ENGRAVED", "STANDARD", 6.0, 5, 0.2)
    add("V-ENGRAVE", "CARD-ENGRAVED", "ECO", 7.0, 6, 0.08)
    add("V-DISPLAYCO", "DISPLAY-COUNTER-AURORA", "STANDARD", 1400.0, 17, 120.0)
    add("V-DISPLAYCO", "DISPLAY-COUNTER-AURORA", "ECO", 1560.0, 19, 70.0)
    add("V-RAPIDDISPLAY", "DISPLAY-COUNTER-AURORA", "STANDARD", 1650.0, 10, 135.0)
    add("V-PRINTCO", "FOLIO-LEATHER-EXEC", "STANDARD", 25.0, 9, 2.4)
    add("V-PRINTCO", "FOLIO-LEATHER-EXEC", "ECO", 29.0, 11, 0.9)
    add("V-PRINTCO", "BROCHURE-AURORA", "STANDARD", 3.0, 6, 0.3)
    add("V-PRINTCO", "BROCHURE-AURORA", "ECO", 3.5, 7, 0.1)
    return rows


SEED = {
    "launches": [
        {"launch_id": "LAUNCH-AURORA", "launch_name": "Project Aurora Global Launch", "product_name": "Aurora",
         "cost_center": "CC-PROD-MKTG-8820", "owner": "Product Marketing", **launch_dates()},
    ],
    "assets": (
        [{"sku": "PKG-LUX-BOX-BLACK", "name": "Rigid luxury magnetic presentation box (black)",
          "component_type": "BOX", "ship_factor": 1.0}]
        + [{"sku": s, "name": n, "component_type": "APPAREL", "ship_factor": 0.5} for s, n in _HOODIES]
        + [{"sku": s, "name": n, "component_type": "POWER", "ship_factor": 0.1} for s, n in _PLUGS]
        + [{"sku": "CARD-ENGRAVED", "name": "Engraved creator handle plaque", "component_type": "PERSONALISATION",
            "ship_factor": 0.05},
           {"sku": "DISPLAY-COUNTER-AURORA", "name": "Flagship showroom counter display", "component_type": "DISPLAY",
            "ship_factor": 15.0},
           {"sku": "FOLIO-LEATHER-EXEC", "name": "Recycled leather executive folio", "component_type": "FOLIO",
            "ship_factor": 1.2},
           {"sku": "BROCHURE-AURORA", "name": "Aurora product brochure", "component_type": "PRINT",
            "ship_factor": 0.2}]),
    "bundle_templates": [
        {"bundle_type": "CREATOR_KIT", "description": "VIP creator unboxing kit", "sku_pattern": "PKG-LUX-BOX-BLACK",
         "qty_per_bundle": 1, "split_by": "NONE"},
        {"bundle_type": "CREATOR_KIT", "description": "VIP creator unboxing kit", "sku_pattern": "HOODIE-AURORA-{size}",
         "qty_per_bundle": 1, "split_by": "SIZE"},
        {"bundle_type": "CREATOR_KIT", "description": "VIP creator unboxing kit", "sku_pattern": "PWR-{plug}",
         "qty_per_bundle": 1, "split_by": "PLUG"},
        {"bundle_type": "CREATOR_KIT", "description": "VIP creator unboxing kit", "sku_pattern": "CARD-ENGRAVED",
         "qty_per_bundle": 1, "split_by": "NONE"},
        {"bundle_type": "SHOWROOM_DISPLAY", "description": "Flagship showroom counter display",
         "sku_pattern": "DISPLAY-COUNTER-AURORA", "qty_per_bundle": 1, "split_by": "NONE"},
        {"bundle_type": "SALES_FOLIO", "description": "Executive sales leave-behind",
         "sku_pattern": "FOLIO-LEATHER-EXEC", "qty_per_bundle": 1, "split_by": "NONE"},
        {"bundle_type": "SALES_FOLIO", "description": "Executive sales leave-behind",
         "sku_pattern": "BROCHURE-AURORA", "qty_per_bundle": 1, "split_by": "NONE"},
    ],
    "creators": _creators(),
    "regional_split": [
        {"bundle_type": "SHOWROOM_DISPLAY", "region": "US", "share_pct": 40.0},
        {"bundle_type": "SHOWROOM_DISPLAY", "region": "EMEA", "share_pct": 40.0},
        {"bundle_type": "SHOWROOM_DISPLAY", "region": "APAC", "share_pct": 20.0},
        {"bundle_type": "SALES_FOLIO", "region": "US", "share_pct": 50.0},
        {"bundle_type": "SALES_FOLIO", "region": "EMEA", "share_pct": 33.33},
        {"bundle_type": "SALES_FOLIO", "region": "APAC", "share_pct": 16.67},
    ],
    "depots": [
        {"depot_id": "DEPOT-LON-01", "depot_name": "London EMEA Marketing Hub", "region": "EMEA"},
        {"depot_id": "DEPOT-DAL-02", "depot_name": "Dallas Marketing Depot", "region": "US"},
        {"depot_id": "DEPOT-SIN-03", "depot_name": "Singapore APAC Depot", "region": "APAC"},
    ],
    "depot_stock": [
        {"depot_id": "DEPOT-LON-01", "sku": "PKG-LUX-BOX-BLACK", "on_hand": 60},
        {"depot_id": "DEPOT-LON-01", "sku": "PWR-UK-G", "on_hand": 40},
        {"depot_id": "DEPOT-LON-01", "sku": "PWR-EU-C", "on_hand": 10},
        {"depot_id": "DEPOT-DAL-02", "sku": "FOLIO-LEATHER-EXEC", "on_hand": 120},
        {"depot_id": "DEPOT-SIN-03", "sku": "PWR-JP-A", "on_hand": 15},
        {"depot_id": "DEPOT-SIN-03", "sku": "PWR-AU-I", "on_hand": 10},
    ],
    "transit_lanes": [
        {"from_region": "US", "to_region": "US", "days": 2, "cost_per_unit": 1.0},
        {"from_region": "EMEA", "to_region": "EMEA", "days": 2, "cost_per_unit": 1.0},
        {"from_region": "APAC", "to_region": "APAC", "days": 2, "cost_per_unit": 1.0},
        {"from_region": "US", "to_region": "EMEA", "days": 5, "cost_per_unit": 4.0},
        {"from_region": "EMEA", "to_region": "US", "days": 5, "cost_per_unit": 4.0},
        {"from_region": "US", "to_region": "APAC", "days": 8, "cost_per_unit": 5.0},
        {"from_region": "APAC", "to_region": "US", "days": 8, "cost_per_unit": 5.0},
        {"from_region": "EMEA", "to_region": "APAC", "days": 7, "cost_per_unit": 4.5},
        {"from_region": "APAC", "to_region": "EMEA", "days": 7, "cost_per_unit": 4.5},
    ],
    "vendors": [
        {"vendor_id": "V-LUXPACK", "vendor_name": "LuxPack Studio", "home_region": "US", "active": True},
        {"vendor_id": "V-APPAREL", "vendor_name": "Aurora Apparel Co", "home_region": "US", "active": True},
        {"vendor_id": "V-PWRTECH", "vendor_name": "PowerTech Accessories", "home_region": "APAC", "active": True},
        {"vendor_id": "V-ENGRAVE", "vendor_name": "EngraveWorks", "home_region": "US", "active": True},
        {"vendor_id": "V-DISPLAYCO", "vendor_name": "DisplayCo", "home_region": "US", "active": True},
        {"vendor_id": "V-RAPIDDISPLAY", "vendor_name": "RapidDisplay", "home_region": "US", "active": True},
        {"vendor_id": "V-PRINTCO", "vendor_name": "PrintCo", "home_region": "EMEA", "active": True},
    ],
    "vendor_offers": _offers(),
    "planning_rules": [
        {"rule_key": "MIN_BUFFER_HOURS", "rule_value": 24.0,
         "description": "A scenario with less safety buffer than this is flagged as risky and is not recommended"},
        {"rule_key": "TARGET_BUFFER_HOURS", "rule_value": 48.0,
         "description": "The planner prefers vendor offers that keep at least this buffer before the in-hand date"},
        {"rule_key": "DEPOT_HANDLING_DAYS", "rule_value": 1.0, "description": "Pick, pack and release at a depot"},
        {"rule_key": "TRANSFER_CARBON_KG_PER_FACTOR", "rule_value": 0.4,
         "description": "kg CO2e per ship_factor unit moved between regions"},
    ],
    "approval_policy": [
        {"tier": "AUTOPILOT", "min_amount": 0.0, "max_amount": 5000.0, "requires_human": False,
         "approver_role": "launch-autopilot"},
        {"tier": "VP_SIGNOFF", "min_amount": 5000.0, "max_amount": 50000.0, "requires_human": True,
         "approver_role": "VP Product Marketing"},
        {"tier": "CMO_SIGNOFF", "min_amount": 50000.0, "max_amount": 1e12, "requires_human": True,
         "approver_role": "CMO"},
    ],
    "approvers": [],  # written by scripts/setup_bigquery.py from --approver-email
    # transaction tables start empty
    "launch_requests": [], "requirement_lines": [], "scenarios": [], "scenario_lines": [], "decisions": [],
    "depot_holds": [], "vendor_disruptions": [], "purchase_orders": [], "depot_transfers": [], "audit_log": [],
}

APPROVER_ROLES = ["VP Product Marketing", "CMO"]
TEAM_ROLE = "Launch Team"  # receives tracking updates
