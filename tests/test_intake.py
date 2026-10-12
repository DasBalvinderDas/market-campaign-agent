"""The guided questions: finding or creating the event, a date on file or a new one, and single items."""
from datetime import date, timedelta

from launchkit_provisioner import planner
from launchkit_provisioner.tools import brief_tools, sourcing_tools
from launchkit_provisioner.tools.brief_tools import BundleRequest, ItemRequest


def _future(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_event_is_found_by_name_and_keeps_the_date_on_file(repo):
    out = brief_tools.register_launch_request("spring product launch event", "kits")
    assert out["status"] == "ok" and out["campaign_status"] == "found" and out["launch_name"] == "Spring Product Launch Event"


def test_a_different_date_updates_the_event(repo):
    out = brief_tools.register_launch_request("Spring Product Launch Event", "x", _future(40))
    assert out["campaign_status"] == "date_updated" and out["in_hand_by"] == _future(40)
    assert repo.get_launch("LAUNCH-SPRING")["in_hand_by"] == date.today() + timedelta(days=40)
    assert any(a["action"] == "event_date_updated" for a in repo.list_audit())


def test_a_new_event_needs_a_date_and_is_created_with_it(repo):
    asked = brief_tools.register_launch_request("Autumn Roadshow", "x")
    assert asked["status"] == "error" and "date" in asked["message"]
    out = brief_tools.register_launch_request("Autumn Roadshow", "x", _future(30))
    assert out["status"] == "ok" and out["campaign_status"] == "created"
    assert repo.get_launch("EVT-AUTUMN-ROADSHOW")["in_hand_by"] == date.today() + timedelta(days=30)


def test_bad_or_past_dates_are_explained(repo):
    assert "not a date" in brief_tools.register_launch_request("Spring Product Launch Event", "x", "next friday")["message"]
    assert "not in the future" in brief_tools.register_launch_request("Spring Product Launch Event", "x", "2020-01-01")["message"]


def test_a_new_event_without_a_guest_list_uses_the_standard_mix(repo):
    rid = brief_tools.register_launch_request("Autumn Roadshow", "x", _future(30))["request_id"]
    out = brief_tools.build_requirements(rid, [BundleRequest(bundle_type="GUEST_KIT", quantity=20)])
    assert out["status"] == "ok" and out["total_units"] == 80 and "standard guest mix" in out["note"]


def test_a_single_item_is_taken_as_it_is(repo):
    rid = brief_tools.register_launch_request("Quick purchase", "20 stands", _future(30))["request_id"]
    out = brief_tools.build_requirements(rid, items=[ItemRequest(item="venue display stands", quantity=3, region="US")])
    assert out["status"] == "ok" and out["total_units"] == 3 and "Single items" in out["bom_markdown"]
    plan = sourcing_tools.build_scenarios(rid)
    assert plan["status"] == "ok" and "buying selected items works fine" in plan["decision_card"]


def test_a_whole_event_plan_has_no_single_item_tip(repo, aurora):
    card = planner.decision_card(aurora, repo.get_launch("LAUNCH-SPRING"), repo.get_scenarios(aurora), repo.list_policies())
    assert "buying selected items works fine" not in card


def test_items_are_matched_by_words_and_unclear_ones_ask_which(repo):
    assets = repo.list_assets()
    assert planner.resolve_item(assets, "hoodie size M")["sku"] == "HOODIE-EVENT-M"
    assert planner.resolve_item(assets, "gift box")["sku"] == "GIFT-BOX-BLACK"
    assert planner.resolve_item(assets, "power adapter US type A")["sku"] == "PWR-US-A"
    for text, word in (("hoodie", "Ask the user which one"), ("laptop", "Items we can buy")):
        try:
            planner.resolve_item(assets, text)
        except planner.PlanError as exc:
            assert word in str(exc)
        else:
            raise AssertionError(text)


def test_a_single_item_needs_a_region_and_a_known_item(repo):
    rid = brief_tools.register_launch_request("Quick purchase", "x", _future(30))["request_id"]
    no_region = brief_tools.build_requirements(rid, items=[ItemRequest(item="gift box", quantity=5, region="")])
    assert no_region["status"] == "error" and "region" in no_region["message"]
    nothing = brief_tools.build_requirements(rid)
    assert nothing["status"] == "error" and "Nothing to plan" in nothing["message"]


def test_the_campaign_is_created_as_soon_as_the_name_is_given(repo):
    out = brief_tools.create_campaign("Autumn Summit 2026", _future(25), 300, "USA")
    assert out["status"] == "ok" and out["campaign_status"] == "created" and out["launch_id"] == "EVT-AUTUMN-SUMMIT-2026"
    assert repo.get_launch("EVT-AUTUMN-SUMMIT-2026")["in_hand_by"] == date.today() + timedelta(days=25)
    md = out["display_markdown"]
    assert "Your campaign is created!" in md and "**Autumn Summit 2026**" in md and "| 👥 People | 300 |" in md and "| 📍 Where | USA |" in md
    assert any(a["action"] == "campaign_created" for a in repo.list_audit())


def test_creating_it_again_finds_it_and_the_request_uses_the_same_campaign(repo):
    first = brief_tools.create_campaign("Autumn Summit 2026", _future(25), 300, "USA")
    again = brief_tools.create_campaign("autumn summit 2026", _future(25), 300, "USA")
    assert again["campaign_status"] == "found" and again["launch_id"] == first["launch_id"]
    req = brief_tools.register_launch_request("Autumn Summit 2026", "x", _future(25))
    assert req["campaign_status"] == "found" and len([x for x in repo.list_launches() if x["launch_name"] == "Autumn Summit 2026"]) == 1


def test_creating_a_campaign_needs_a_future_date(repo):
    assert "not in the future" in brief_tools.create_campaign("X", "2020-01-01")["message"]
    assert "not a date" in brief_tools.create_campaign("X", "soon")["message"]
    assert "I do not know a campaign" in brief_tools.create_campaign("X", "")["message"]
