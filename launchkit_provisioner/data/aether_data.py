"""Demo data for the "Aether Athletics" live demo: the vendors, the items they hold, our own stock and the athlete size curve.

Same shape as ``seed_data.SEED`` (one list of rows per table), so it loads into the same tables. There is NO campaign in it:
the demo user creates "Aether Strider Pro Global Marathon Launch" in the chat. Prices, lead times, depot stock and the athlete
size curve come from the demo pack: VIP athlete seeding kits, illuminated expo podiums and cork buyer folios, with surplus boxes in
Boston and surplus cork binders in Portland.

The athlete list (120 athletes, their sizes and handles) is kept as a standing guest list, not tied to a campaign, so the
seeding kits get the right singlet sizes for whichever campaign asks for them.
"""

from .seed_data import SEED

GUEST_LIST_ID = "GUEST-MIX-TEMPLATE"      # the standing athlete list (see planner.STANDARD_GUEST_LIST)
CAMPAIGN_NAME = "Aether Strider Pro Global Marathon Launch"      # what the demo user types in the chat
COST_CENTER = "CC-GLOBAL-BRAND-4410"
ATHLETES = 120

# 120 athletes: women XS18 S24 M18, men S20 M25 L15 (the registry's sizing breakdown), added up per size
SIZES = {"XS": 18, "S": 44, "M": 43, "L": 15}
SAMPLE_ATHLETES = [("Emily S.", "@emily_runs_fast", "S", "US"), ("Marcus T.", "@marathon_marcus", "M", "EMEA"),
                   ("David K.", "@kenya_stride", "S", "EMEA")]


def _athletes() -> list[dict]:
    sizes = [s for s, n in SIZES.items() for _ in range(n)]
    sizes = [sizes[(i * 37) % ATHLETES] for i in range(ATHLETES)]        # 37 is coprime with 120: a fixed shuffle
    regions = ["US"] * 70 + ["EMEA"] * 50                                # US runners; UK and Kenya runners are EMEA
    for i, (_, _, size, region) in enumerate(SAMPLE_ATHLETES):           # the three named athletes get their own size and place
        j = next(k for k in range(i, ATHLETES) if sizes[k] == size)
        sizes[i], sizes[j] = sizes[j], sizes[i]
        j = next(k for k in range(i, ATHLETES) if regions[k] == region)
        regions[i], regions[j] = regions[j], regions[i]
    rows = []
    for i in range(ATHLETES):
        name, handle = (SAMPLE_ATHLETES[i][0], SAMPLE_ATHLETES[i][1]) if i < len(SAMPLE_ATHLETES) else (
            f"Athlete {i + 1:03d}", f"@aether_athlete_{i + 1:03d}")
        rows.append({"guest_id": f"ATH-{i + 1:03d}", "launch_id": GUEST_LIST_ID, "handle": handle, "name": name,
                     "size": sizes[i], "region": regions[i], "plug_type": "NA"})
    return rows


_SINGLETS = [(f"APP-SINGLET-{s}", f"Aether Elite Race Singlet, size {s}") for s in SIZES]


def _assets() -> list[dict]:
    return ([{"sku": "BOX-ACRYL-PREM-LID", "name": "Strider Pro magnetic presentation box", "component_type": "BOX",
              "ship_factor": 1.0},
             {"sku": "SVC-LASER-ETCH", "name": "Laser-etched athlete bib plate", "component_type": "PERSONALISATION",
              "ship_factor": 0.05}]
            + [{"sku": s, "name": n, "component_type": "APPAREL", "ship_factor": 0.3} for s, n in _SINGLETS]
            + [{"sku": "PACK-NUTRITION-FLASK", "name": "Electrolyte and energy flask kit", "component_type": "GIFT",
                "ship_factor": 0.4},
               {"sku": "DISP-PODIUM-CARB", "name": "Illuminated carbon-finish display podium", "component_type": "DISPLAY",
                "ship_factor": 15.0},
               {"sku": "BINDER-CORK-ECO", "name": "Cork buyer presentation folio", "component_type": "FOLDER",
                "ship_factor": 1.2}])


def _templates() -> list[dict]:
    kit = "VIP athlete seeding kit"
    return [
        {"bundle_type": "GUEST_KIT", "description": kit, "sku_pattern": "BOX-ACRYL-PREM-LID", "qty_per_bundle": 1,
         "split_by": "NONE", "suggested_per_person": 1.0},
        {"bundle_type": "GUEST_KIT", "description": kit, "sku_pattern": "SVC-LASER-ETCH", "qty_per_bundle": 1,
         "split_by": "NONE", "suggested_per_person": 1.0},
        {"bundle_type": "GUEST_KIT", "description": kit, "sku_pattern": "APP-SINGLET-{size}", "qty_per_bundle": 1,
         "split_by": "SIZE", "suggested_per_person": 1.0},
        {"bundle_type": "GUEST_KIT", "description": kit, "sku_pattern": "PACK-NUTRITION-FLASK", "qty_per_bundle": 1,
         "split_by": "NONE", "suggested_per_person": 1.0},
        {"bundle_type": "VENUE_DISPLAY", "description": "Expo pop-up display podium", "sku_pattern": "DISP-PODIUM-CARB",
         "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 0.1},
        {"bundle_type": "SALES_PACK", "description": "Specialty buyer presentation kit", "sku_pattern": "BINDER-CORK-ECO",
         "qty_per_bundle": 1, "split_by": "NONE", "suggested_per_person": 2.0833},
    ]


_VENDORS = [
    ("V-APEXLUX", "Apex Luxury Packaging"), ("V-METRO", "Metro NYC Engraving"), ("V-APEXAPP", "Apex Technical Apparel"),
    ("V-MIDWEST", "Midwest Exhibit Fabricators"), ("V-ECOPACK", "EcoPackaging Ltd."), ("V-BIOHYDRATE", "BioHydrate Nutrition"),
    # second and third vendors: always dearer or slower than the vendor above, so the pack's prices stay the best price
    ("V-PACKRIGHT", "PackRight Premium"), ("V-ETCHLAB", "EtchLab NYC"), ("V-STRIDEWEAR", "StrideWear Textiles"),
    ("V-EXPOWORKS", "ExpoWorks Displays"), ("V-LUMINA", "Lumina Stage Systems"), ("V-GREENFOLIO", "GreenFolio Co."),
    ("V-HYDRAFUEL", "HydraFuel Labs")]


def _offers() -> list[dict]:
    rows = []

    def add(vendor, sku, variant, price, lead, carbon):
        rows.append({"vendor_id": vendor, "sku": sku, "variant": variant, "unit_price": price, "lead_days": lead,
                     "carbon_kg": carbon})

    # the pack's catalog: unit cost and lead time per item
    add("V-APEXLUX", "BOX-ACRYL-PREM-LID", "STANDARD", 65.0, 10, 4.0)
    add("V-APEXLUX", "BOX-ACRYL-PREM-LID", "ECO", 74.0, 12, 1.5)              # recycled ocean-plastic box
    add("V-METRO", "SVC-LASER-ETCH", "STANDARD", 20.0, 2, 0.1)
    for sku, _ in _SINGLETS:
        add("V-APEXAPP", sku, "STANDARD", 45.0, 8, 6.0)
        add("V-APEXAPP", sku, "ECO", 52.0, 10, 2.0)                           # organic-cotton singlet
    add("V-MIDWEST", "DISP-PODIUM-CARB", "STANDARD", 380.0, 16, 110.0)
    add("V-ECOPACK", "BINDER-CORK-ECO", "STANDARD", 22.0, 7, 0.8)
    add("V-BIOHYDRATE", "PACK-NUTRITION-FLASK", "STANDARD", 27.42, 4, 1.6)
    # competition
    add("V-PACKRIGHT", "BOX-ACRYL-PREM-LID", "STANDARD", 71.0, 12, 4.4)
    add("V-ETCHLAB", "SVC-LASER-ETCH", "STANDARD", 23.0, 3, 0.1)
    for sku, _ in _SINGLETS:
        add("V-STRIDEWEAR", sku, "STANDARD", 49.0, 10, 5.5)
    add("V-EXPOWORKS", "DISP-PODIUM-CARB", "STANDARD", 410.0, 18, 115.0)
    add("V-LUMINA", "DISP-PODIUM-CARB", "STANDARD", 455.0, 12, 120.0)         # faster, dearer
    add("V-GREENFOLIO", "BINDER-CORK-ECO", "STANDARD", 24.0, 8, 0.9)
    add("V-HYDRAFUEL", "PACK-NUTRITION-FLASK", "STANDARD", 29.9, 5, 1.7)
    return rows


# Vendors charge the catalog price from 14 days ahead, a rush charge below that and an early-bird discount well ahead,
# so the pack's prices hold on the demo date and moving the date still shows a saving or a cost.
DATE_PRICING = [
    {"vendor_id": "*", "min_days_ahead": 45, "price_factor": 0.92, "label": "Early bird: 8% off"},
    {"vendor_id": "*", "min_days_ahead": 35, "price_factor": 0.95, "label": "Early bird: 5% off"},
    {"vendor_id": "*", "min_days_ahead": 14, "price_factor": 1.00, "label": "Standard price"},
    {"vendor_id": "*", "min_days_ahead": 7, "price_factor": 1.06, "label": "Rush: 6% extra"},
    {"vendor_id": "*", "min_days_ahead": 0, "price_factor": 1.12, "label": "Rush: 12% extra"},
]


def build() -> dict:
    """Every table of the demo as {table: [rows]}. There are no campaigns, and the approvers are not included (they stay as configured)."""
    return {
        "launches": [],
        "assets": _assets(),
        "bundle_templates": _templates(),
        "guests": _athletes(),
        "venues": [dict(v) for v in SEED["venues"]],
        "vendors": [{"vendor_id": v, "vendor_name": n, "home_region": "US", "active": True} for v, n in _VENDORS],
        "vendor_offers": _offers(),
        "vendor_date_pricing": [dict(r) for r in DATE_PRICING],
        "regional_split": [dict(r) for r in SEED["regional_split"]],
        "depots": [{"depot_id": "DEPOT-BOS-01", "depot_name": "Boston Distribution Hub", "region": "US"},
                   {"depot_id": "DEPOT-PDX-02", "depot_name": "Portland West Depot", "region": "US"},
                   {"depot_id": "DEPOT-AMS-03", "depot_name": "Amsterdam EMEA Hub", "region": "EMEA"}],
        "depot_stock": [{"depot_id": "DEPOT-BOS-01", "sku": "BOX-ACRYL-PREM-LID", "on_hand": 50},       # grade A, pristine
                        {"depot_id": "DEPOT-PDX-02", "sku": "BINDER-CORK-ECO", "on_hand": 100},          # grade A, pristine
                        {"depot_id": "DEPOT-AMS-03", "sku": "DISP-PODIUM-CARB", "on_hand": 0}],         # depleted
        "transit_lanes": [dict(r) for r in SEED["transit_lanes"]],
        "planning_rules": [dict(r) for r in SEED["planning_rules"]],
        "approval_policy": [dict(r) for r in SEED["approval_policy"]],
    }
