"""Demo data for The LaunchKit Provisioner: a fictional flagship launch, "Spring Launch Event".

All names, prices and quantities are made up. Loaded by ``scripts/setup_bigquery.py`` (and used in memory by the
unit tests). Launch dates are relative to the day the data is set up, so the story always works:
in-hand deadline = setup day + 25, press embargo = setup day + 32 (``scripts/setup_bigquery.py --reset-demo``
moves them to today again).
"""
from datetime import date, timedelta

IN_HAND_DAYS = 25
EMBARGO_DAYS = 32
CAMPAIGN_DAYS = 30                 # the three standing campaigns (London, US, Singapore): in hand 30 days after setup
CAMPAIGN_EMBARGO_DAYS = 37

REGIONS = ["US", "EMEA", "APAC"]


def launch_dates(today: date | None = None, in_hand_days: int = IN_HAND_DAYS, embargo_days: int = EMBARGO_DAYS) -> dict:
    today = today or date.today()
    return {"in_hand_by": today + timedelta(days=in_hand_days), "embargo_date": today + timedelta(days=embargo_days)}


def _standing(launch_id: str, name: str) -> dict:
    return {"launch_id": launch_id, "launch_name": name, "product_name": name, "cost_center": "CC-EVENTS-GENERAL",
            "owner": "Marketing", **launch_dates(in_hand_days=CAMPAIGN_DAYS, embargo_days=CAMPAIGN_EMBARGO_DAYS)}


STANDING_CAMPAIGNS = [("LAUNCH-LONDON", "London Campaign"), ("LAUNCH-USA", "US Campaign"),
                      ("LAUNCH-SINGAPORE", "Singapore Campaign")]


def _guests():
    """150 guests: sizes S20 M45 L60 XL25; regions US85 EMEA45 APAC20; plugs by region. Deterministic."""
    sizes = ["S"] * 20 + ["M"] * 45 + ["L"] * 60 + ["XL"] * 25
    sizes = [sizes[(i * 37) % 150] for i in range(150)]  # 37 is coprime with 150: a fixed shuffle
    regions = ["US"] * 85 + ["EMEA"] * 45 + ["APAC"] * 20
    plugs = ["US-A"] * 85 + ["UK-G"] * 30 + ["EU-C"] * 15 + ["JP-A"] * 12 + ["AU-I"] * 8
    return [{"guest_id": f"GU-{i + 1:03d}", "launch_id": "LAUNCH-SPRING", "handle": f"@guest_{i + 1:03d}",
             "name": f"Guest {i + 1:03d}", "size": sizes[i], "region": regions[i], "plug_type": plugs[i]}
            for i in range(150)]


_HOODIES = [("HOODIE-EVENT-S", "Event hoodie S"), ("HOODIE-EVENT-M", "Event hoodie M"),
            ("HOODIE-EVENT-L", "Event hoodie L"), ("HOODIE-EVENT-XL", "Event hoodie XL")]
_PLUGS = [("PWR-US-A", "Power adapter, US type A"), ("PWR-UK-G", "Power adapter, UK type G"),
          ("PWR-EU-C", "Power adapter, EU type C"), ("PWR-JP-A", "Power adapter, JP type A"),
          ("PWR-AU-I", "Power adapter, AU type I")]


def _offers():
    rows = []

    def add(vendor, sku, variant, price, lead, carbon):
        rows.append({"vendor_id": vendor, "sku": sku, "variant": variant, "unit_price": price, "lead_days": lead,
                     "carbon_kg": carbon})

    add("V-LUXPACK", "GIFT-BOX-BLACK", "STANDARD", 85.0, 14, 4.2)
    add("V-LUXPACK", "GIFT-BOX-BLACK", "ECO", 98.0, 16, 1.9)
    for sku, _ in _HOODIES:
        add("V-APPAREL", sku, "STANDARD", 42.0, 12, 9.0)
        add("V-APPAREL", sku, "ECO", 52.0, 15, 3.5)
    for sku, _ in _PLUGS:
        add("V-PWRTECH", sku, "STANDARD", 9.0, 7, 1.2)
    add("V-ENGRAVE", "NAME-CARD", "STANDARD", 6.0, 5, 0.2)
    add("V-ENGRAVE", "NAME-CARD", "ECO", 7.0, 6, 0.08)
    add("V-DISPLAYCO", "DISPLAY-STAND", "STANDARD", 1400.0, 17, 120.0)
    add("V-DISPLAYCO", "DISPLAY-STAND", "ECO", 1560.0, 19, 70.0)
    add("V-RAPIDDISPLAY", "DISPLAY-STAND", "STANDARD", 1650.0, 10, 135.0)
    add("V-PRINTCO", "FOLDER-LEATHER", "STANDARD", 25.0, 9, 2.4)
    add("V-PRINTCO", "FOLDER-LEATHER", "ECO", 29.0, 11, 0.9)
    add("V-PRINTCO", "BROCHURE-PRODUCT", "STANDARD", 3.0, 6, 0.3)
    add("V-PRINTCO", "BROCHURE-PRODUCT", "ECO", 3.5, 7, 0.1)
    # Second and third vendors for the items above: real competition on the offer, always dearer or slower
    # than the vendor above, so the best price and the demo numbers stay the same.
    add("V-GIFTCRAFT", "GIFT-BOX-BLACK", "STANDARD", 92.0, 15, 4.5)
    for sku, _ in _HOODIES:
        add("V-THREADLY", sku, "STANDARD", 47.0, 14, 8.0)
    for sku, _ in _PLUGS:
        add("V-VOLTLINE", sku, "STANDARD", 9.8, 8, 1.1)
    add("V-INKWELL", "NAME-CARD", "STANDARD", 6.8, 6, 0.2)
    add("V-INKWELL", "FOLDER-LEATHER", "STANDARD", 31.0, 10, 2.6)
    add("V-INKWELL", "BROCHURE-PRODUCT", "STANDARD", 3.9, 7, 0.3)
    add("V-STAGEPRO", "DISPLAY-STAND", "STANDARD", 1760.0, 12, 140.0)
    # Campaign extras: items that are not part of a pack, each with at least two vendors
    add("V-THREADLY", "TOTE-CANVAS", "STANDARD", 6.5, 10, 1.8)
    add("V-THREADLY", "TOTE-CANVAS", "ECO", 8.0, 12, 0.6)
    add("V-GIFTCRAFT", "TOTE-CANVAS", "STANDARD", 7.2, 8, 2.0)
    add("V-GIFTCRAFT", "BOTTLE-STEEL", "STANDARD", 8.5, 9, 2.4)
    add("V-LUXPACK", "BOTTLE-STEEL", "STANDARD", 9.2, 11, 2.2)
    add("V-LUXPACK", "BOTTLE-STEEL", "ECO", 11.0, 13, 0.9)
    add("V-INKWELL", "BANNER-ROLLUP", "STANDARD", 55.0, 6, 6.0)
    add("V-PRINTCO", "BANNER-ROLLUP", "STANDARD", 48.0, 9, 5.5)
    add("V-INKWELL", "BADGE-LANYARD", "STANDARD", 2.2, 4, 0.4)
    add("V-ENGRAVE", "BADGE-LANYARD", "STANDARD", 2.6, 5, 0.4)
    add("V-PRINTCO", "STICKER-PACK", "STANDARD", 0.8, 5, 0.05)
    add("V-INKWELL", "STICKER-PACK", "STANDARD", 0.9, 4, 0.05)
    add("V-INKWELL", "STICKER-PACK", "ECO", 1.1, 5, 0.02)
    return rows


SEED = {
    "launches": [
        {"launch_id": "LAUNCH-SPRING", "launch_name": "Spring Product Launch Event", "product_name": "Spring",
         "cost_center": "CC-PROD-MKTG-8820", "owner": "Product Marketing", **launch_dates()},
    ] + [_standing(i, n) for i, n in STANDING_CAMPAIGNS],
    "assets": (
        [{"sku": "GIFT-BOX-BLACK", "name": "Black gift box",
          "component_type": "BOX", "ship_factor": 1.0}]
        + [{"sku": s, "name": n, "component_type": "APPAREL", "ship_factor": 0.5} for s, n in _HOODIES]
        + [{"sku": s, "name": n, "component_type": "POWER", "ship_factor": 0.1} for s, n in _PLUGS]
        + [{"sku": "NAME-CARD", "name": "Engraved name card", "component_type": "PERSONALISATION",
            "ship_factor": 0.05},
           {"sku": "DISPLAY-STAND", "name": "Venue display stand", "component_type": "DISPLAY",
            "ship_factor": 15.0},
           {"sku": "FOLDER-LEATHER", "name": "Leather sales folder", "component_type": "FOLDER",
            "ship_factor": 1.2},
           {"sku": "BROCHURE-PRODUCT", "name": "Product brochure", "component_type": "PRINT",
            "ship_factor": 0.2},
           {"sku": "TOTE-CANVAS", "name": "Canvas tote bag", "component_type": "GIFT", "ship_factor": 0.3,
            "suggested_per_person": 1.0},
           {"sku": "BOTTLE-STEEL", "name": "Steel water bottle", "component_type": "GIFT", "ship_factor": 0.4,
            "suggested_per_person": 1.0},
           {"sku": "BANNER-ROLLUP", "name": "Roll-up banner", "component_type": "DISPLAY", "ship_factor": 2.0},
           {"sku": "BADGE-LANYARD", "name": "Name badge with lanyard", "component_type": "PERSONALISATION",
            "ship_factor": 0.05, "suggested_per_person": 1.0},
           {"sku": "STICKER-PACK", "name": "Sticker pack", "component_type": "PRINT", "ship_factor": 0.02}]),
    "bundle_templates": [
        {"bundle_type": "GUEST_KIT", "description": "VIP guest welcome kit", "sku_pattern": "GIFT-BOX-BLACK",
         "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.1},
        {"bundle_type": "GUEST_KIT", "description": "VIP guest welcome kit", "sku_pattern": "HOODIE-EVENT-{size}",
         "qty_per_bundle": 1, "split_by": "SIZE", "suggested_per_person": 0.1},
        {"bundle_type": "GUEST_KIT", "description": "VIP guest welcome kit", "sku_pattern": "PWR-{plug}",
         "qty_per_bundle": 1, "split_by": "PLUG", "suggested_per_person": 0.1},
        {"bundle_type": "GUEST_KIT", "description": "VIP guest welcome kit", "sku_pattern": "NAME-CARD",
         "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.1},
        {"bundle_type": "VENUE_DISPLAY", "description": "Venue display stand",
         "sku_pattern": "DISPLAY-STAND", "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.01},
        {"bundle_type": "SALES_PACK", "description": "Sales team folder pack",
         "sku_pattern": "FOLDER-LEATHER", "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.1},
        {"bundle_type": "SALES_PACK", "description": "Sales team folder pack",
         "sku_pattern": "BROCHURE-PRODUCT", "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.1},
    ],
    "venues": [
        {"venue_id": "VEN-USA", "venue_name": "USA", "country": "United States", "region": "US",
         "served_from": "US vendors and the Dallas warehouse"},
        {"venue_id": "VEN-CANADA", "venue_name": "Canada", "country": "Canada", "region": "US",
         "served_from": "US vendors and the Dallas warehouse (shipped across the border)"},
        {"venue_id": "VEN-LONDON", "venue_name": "London", "country": "United Kingdom", "region": "EMEA",
         "served_from": "UK and European vendors and the London warehouse"},
        {"venue_id": "VEN-SINGAPORE", "venue_name": "Singapore", "country": "Singapore", "region": "APAC",
         "served_from": "Asian vendors and the Singapore warehouse"},
    ],
    # Vendors charge less when the order is placed well ahead and more for a rush. The 21-34 day band is the
    # standard price for every vendor, so the demo numbers (a date 25 days away) do not change.
    "vendor_date_pricing": [
        {"vendor_id": "*", "min_days_ahead": 45, "price_factor": 0.92, "label": "Early bird: 8% off"},
        {"vendor_id": "*", "min_days_ahead": 35, "price_factor": 0.95, "label": "Early bird: 5% off"},
        {"vendor_id": "*", "min_days_ahead": 21, "price_factor": 1.00, "label": "Standard price"},
        {"vendor_id": "*", "min_days_ahead": 14, "price_factor": 1.06, "label": "Rush: 6% extra"},
        {"vendor_id": "*", "min_days_ahead": 7, "price_factor": 1.12, "label": "Rush: 12% extra"},
        {"vendor_id": "*", "min_days_ahead": 0, "price_factor": 1.20, "label": "Last minute: 20% extra"},
        # DisplayCo gives a bigger early-bird discount
        {"vendor_id": "V-DISPLAYCO", "min_days_ahead": 30, "price_factor": 0.93, "label": "Early bird: 7% off"},
        {"vendor_id": "V-DISPLAYCO", "min_days_ahead": 21, "price_factor": 1.00, "label": "Standard price"},
        {"vendor_id": "V-DISPLAYCO", "min_days_ahead": 14, "price_factor": 1.06, "label": "Rush: 6% extra"},
        {"vendor_id": "V-DISPLAYCO", "min_days_ahead": 7, "price_factor": 1.12, "label": "Rush: 12% extra"},
        {"vendor_id": "V-DISPLAYCO", "min_days_ahead": 0, "price_factor": 1.20, "label": "Last minute: 20% extra"},
    ],
    "guests": _guests(),
    "regional_split": [
        {"bundle_type": "VENUE_DISPLAY", "region": "US", "share_pct": 40.0},
        {"bundle_type": "VENUE_DISPLAY", "region": "EMEA", "share_pct": 40.0},
        {"bundle_type": "VENUE_DISPLAY", "region": "APAC", "share_pct": 20.0},
        {"bundle_type": "SALES_PACK", "region": "US", "share_pct": 50.0},
        {"bundle_type": "SALES_PACK", "region": "EMEA", "share_pct": 33.33},
        {"bundle_type": "SALES_PACK", "region": "APAC", "share_pct": 16.67},
    ],
    "depots": [
        {"depot_id": "DEPOT-LON-01", "depot_name": "London EMEA Marketing Hub", "region": "EMEA"},
        {"depot_id": "DEPOT-DAL-02", "depot_name": "Dallas Marketing Depot", "region": "US"},
        {"depot_id": "DEPOT-SIN-03", "depot_name": "Singapore APAC Depot", "region": "APAC"},
    ],
    "depot_stock": [
        {"depot_id": "DEPOT-LON-01", "sku": "GIFT-BOX-BLACK", "on_hand": 60},
        {"depot_id": "DEPOT-LON-01", "sku": "PWR-UK-G", "on_hand": 40},
        {"depot_id": "DEPOT-LON-01", "sku": "PWR-EU-C", "on_hand": 10},
        {"depot_id": "DEPOT-DAL-02", "sku": "FOLDER-LEATHER", "on_hand": 120},
        {"depot_id": "DEPOT-SIN-03", "sku": "PWR-JP-A", "on_hand": 15},
        {"depot_id": "DEPOT-SIN-03", "sku": "PWR-AU-I", "on_hand": 10},
        # stock of campaign extras (not part of any pack)
        {"depot_id": "DEPOT-LON-01", "sku": "TOTE-CANVAS", "on_hand": 200},
        {"depot_id": "DEPOT-DAL-02", "sku": "BOTTLE-STEEL", "on_hand": 150},
        {"depot_id": "DEPOT-SIN-03", "sku": "BOTTLE-STEEL", "on_hand": 80},
        {"depot_id": "DEPOT-DAL-02", "sku": "BANNER-ROLLUP", "on_hand": 25},
        {"depot_id": "DEPOT-LON-01", "sku": "BANNER-ROLLUP", "on_hand": 10},
        {"depot_id": "DEPOT-LON-01", "sku": "STICKER-PACK", "on_hand": 1000},
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
        {"vendor_id": "V-APPAREL", "vendor_name": "StyleWorks Apparel", "home_region": "US", "active": True},
        {"vendor_id": "V-PWRTECH", "vendor_name": "PowerTech Accessories", "home_region": "APAC", "active": True},
        {"vendor_id": "V-ENGRAVE", "vendor_name": "EngraveWorks", "home_region": "US", "active": True},
        {"vendor_id": "V-DISPLAYCO", "vendor_name": "DisplayCo", "home_region": "US", "active": True},
        {"vendor_id": "V-RAPIDDISPLAY", "vendor_name": "RapidDisplay", "home_region": "US", "active": True},
        {"vendor_id": "V-PRINTCO", "vendor_name": "PrintCo", "home_region": "EMEA", "active": True},
        {"vendor_id": "V-GIFTCRAFT", "vendor_name": "GiftCraft Packaging", "home_region": "EMEA", "active": True},
        {"vendor_id": "V-THREADLY", "vendor_name": "Threadly Apparel", "home_region": "APAC", "active": True},
        {"vendor_id": "V-VOLTLINE", "vendor_name": "VoltLine Adapters", "home_region": "EMEA", "active": True},
        {"vendor_id": "V-INKWELL", "vendor_name": "Inkwell Print", "home_region": "US", "active": True},
        {"vendor_id": "V-STAGEPRO", "vendor_name": "StagePro Displays", "home_region": "APAC", "active": True},
    ],
    "vendor_offers": _offers(),
    "planning_rules": [
        {"rule_key": "MIN_BUFFER_HOURS", "rule_value": 24.0,
         "description": "A scenario with less safety buffer than this is flagged as risky and is not recommended"},
        {"rule_key": "TARGET_BUFFER_HOURS", "rule_value": 48.0,
         "description": "The planner prefers vendor offers that keep at least this buffer before the in-hand date"},
        {"rule_key": "DEPOT_HANDLING_DAYS", "rule_value": 1.0, "description": "Pick, pack and release at a depot"},
        {"rule_key": "SPARE_PERCENT", "rule_value": 5.0,
         "description": "Extra units the assistant suggests ordering for late additions, damage and loss"},
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
