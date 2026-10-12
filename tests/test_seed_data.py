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
