"""Business advice on the shopping list: what the user may be missing."""
from datetime import date, timedelta

from conftest import BRIEF
from launchkit_provisioner import advisor, planner, presentation
from launchkit_provisioner.tools import brief_tools
from launchkit_provisioner.tools.brief_tools import BundleRequest, ItemRequest


def _what(repo, rid):
    return [t["what"] for t in advisor.suggestions(repo, rid)]


def test_spares_are_suggested_with_the_numbers(repo, aurora):
    tips = advisor.suggestions(repo, aurora)
    assert tips[0]["icon"] == "🛟" and "5% extra: 8 kits, 15 folders, 1 stand" in tips[0]["what"]


def test_a_missing_kind_of_bundle_is_called_out(repo):
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_bundles(repo, "LAUNCH-SPRING", [BRIEF[0]]))
    names = _what(repo, rid)
    assert "Venue display stands" in names and "Sales folders and brochures" in names and "VIP guest welcome kits" not in names


def test_a_single_item_gets_the_rest_of_its_bundle(repo):
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_items(repo, [{"item": "hoodie size M", "quantity": 5, "region": "US"}]))
    assert any(t["what"] == "Plan the whole campaign" for t in advisor.suggestions(repo, rid))
    tip = next(t for t in advisor.suggestions(repo, rid) if t["icon"] == "🧩")
    assert tip["what"] == "The rest of the VIP guest welcome kit" and "Black gift box" in tip["why"] and "Power adapter" in tip["why"]


def test_a_date_that_is_too_close_is_flagged(repo):
    repo.update_launch_dates("LAUNCH-SPRING", date.today() + timedelta(days=5), date.today() + timedelta(days=12))
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_bundles(repo, "LAUNCH-SPRING", BRIEF))
    tips = advisor.suggestions(repo, rid)
    assert any(t["icon"] == "🔴" and "the date is too close" in t["what"] for t in tips)
    assert len([t for t in tips if "Event hoodie" in t["what"]]) <= 1       # sizes are grouped into one line


def test_nothing_to_say_when_the_plan_is_complete_and_has_stock_and_time(repo):
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_bundles(repo, "LAUNCH-SPRING", [
        {"bundle_type": "SALES_PACK", "quantity": 100}, {"bundle_type": "GUEST_KIT", "quantity": 50},
        {"bundle_type": "VENUE_DISPLAY", "quantity": 4}]))
    assert not any(t["icon"] in ("🧩", "🖼️", "📁", "🎁") for t in advisor.suggestions(repo, rid))


def test_build_requirements_returns_the_advice_for_the_chat(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    out = brief_tools.build_requirements(rid, [BundleRequest(bundle_type="GUEST_KIT", quantity=40)])
    assert out["advice_count"] >= 2 and "Anything you may be missing?" in out["display_markdown"]
    assert "Looks good" in out["display_markdown"]
    item = brief_tools.build_requirements(rid, items=[ItemRequest(item="gift box", quantity=5, region="US")])
    assert "The rest of the VIP guest welcome kit" in presentation.advice_markdown(advisor.suggestions(repo, rid))


def test_plan_the_whole_campaign_is_only_suggested_for_items_only_requests(repo):
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_bundles(repo, "LAUNCH-SPRING", [BRIEF[1]])
                                   + planner.expand_items(repo, [{"item": "tote bag", "quantity": 10, "region": "EMEA"}]))
    assert "Plan the whole campaign" not in _what(repo, rid)
