"""The demo catalog: every row points at something that exists, and the items have real competition."""
from collections import Counter

from launchkit_provisioner.data.seed_data import SEED


def test_every_reference_points_at_something_that_exists():
    skus = {a["sku"] for a in SEED["assets"]}
    vendors = {v["vendor_id"] for v in SEED["vendors"]}
    depots = {d["depot_id"] for d in SEED["depots"]}
    assert all(o["sku"] in skus and o["vendor_id"] in vendors for o in SEED["vendor_offers"])
    assert all(s["sku"] in skus and s["depot_id"] in depots for s in SEED["depot_stock"])
    assert len(skus) == len(SEED["assets"]) and len(vendors) == len(SEED["vendors"])


def test_every_item_can_be_bought_from_at_least_two_vendors():
    by_sku = {}
    for o in SEED["vendor_offers"]:
        by_sku.setdefault(o["sku"], set()).add(o["vendor_id"])
    assert all(len(v) >= 2 for v in by_sku.values()) and set(by_sku) == {a["sku"] for a in SEED["assets"]}


def test_there_are_campaign_extras_with_stock_and_competing_vendors():
    extras = {"TOTE-CANVAS", "BOTTLE-STEEL", "BANNER-ROLLUP", "BADGE-LANYARD", "STICKER-PACK"}
    assert extras <= {a["sku"] for a in SEED["assets"]}
    assert Counter(s["sku"] for s in SEED["depot_stock"])["BOTTLE-STEEL"] == 2


def test_no_duplicate_offers():
    keys = [(o["vendor_id"], o["sku"], o["variant"]) for o in SEED["vendor_offers"]]
    assert len(keys) == len(set(keys))


def test_venues_map_to_regions_we_serve():
    regions = {"US", "EMEA", "APAC"}
    assert {v["venue_name"] for v in SEED["venues"]} == {"USA", "Canada", "London", "Singapore"}
    assert all(v["region"] in regions for v in SEED["venues"])
    assert {v["region"] for v in SEED["venues"] if v["venue_name"] == "Canada"} == {"US"}


def test_date_pricing_covers_every_day_count_and_is_standard_for_the_demo_window():
    by_vendor = {}
    for r in SEED["vendor_date_pricing"]:
        by_vendor.setdefault(r["vendor_id"], []).append(r)
    assert "*" in by_vendor and all(min(x["min_days_ahead"] for x in rows) == 0 for rows in by_vendor.values())
    for rows in by_vendor.values():
        assert next(r for r in sorted(rows, key=lambda r: -r["min_days_ahead"]) if r["min_days_ahead"] <= 25)["price_factor"] == 1.0
    assert set(by_vendor) <= {v["vendor_id"] for v in SEED["vendors"]} | {"*"}


def test_suggested_amounts_per_person_exist_for_the_campaign_extras():
    ratios = {a["sku"]: a.get("suggested_per_person") for a in SEED["assets"]}
    assert ratios["BADGE-LANYARD"] == 1.0 and ratios["BANNER-ROLLUP"] is None and ratios["GIFT-BOX-BLACK"] is None
    assert {b["bundle_type"] for b in SEED["bundle_templates"] if b.get("suggested_per_person")} == {"GUEST_KIT", "VENUE_DISPLAY", "SALES_PACK"}
