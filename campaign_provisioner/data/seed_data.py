"""Demo seed data: Google Next 2027 campaigns (fictional figures).

Loaded into BigQuery by ``scripts/setup_bigquery.py`` and used directly by the
in-memory repository, so both backends start from identical data.
"""
from datetime import datetime, timezone

_T0 = datetime(2027, 1, 1, tzinfo=timezone.utc)

SEED = {
    "inventory_items": [
        {"sku": "LANYARD-STD", "name": "Event lanyard", "category": "Swag", "on_hand": 1500},
        {"sku": "TSHIRT-NEXT", "name": "Next 2027 T-shirt", "category": "Swag", "on_hand": 800},
        {"sku": "HOODIE-NEXT", "name": "Next 2027 hoodie", "category": "Swag", "on_hand": 120},
        {"sku": "TOTE-NEXT", "name": "Next 2027 tote bag", "category": "Swag", "on_hand": 400},
        {"sku": "STICKER-PACK", "name": "Sticker pack", "category": "Swag", "on_hand": 5000},
        {"sku": "WATER-BOTTLE", "name": "Insulated water bottle", "category": "Swag", "on_hand": 0},
        {"sku": "BANNER-XL", "name": "Event banner XL", "category": "Signage", "on_hand": 10},
        {"sku": "BROCHURE-A5", "name": "A5 brochure", "category": "Print", "on_hand": 3000},
        {"sku": "DEMO-KIOSK", "name": "Interactive demo kiosk", "category": "Booth", "on_hand": 2},
        {"sku": "BOOTH-LEDWALL", "name": "Booth LED video wall", "category": "Booth", "on_hand": 0},
    ],
    "vendors": [
        {"vendor_id": "V-PRINTCO", "vendor_name": "PrintCo", "active": True},
        {"vendor_id": "V-SWAGHUB", "vendor_name": "SwagHub", "active": True},
        {"vendor_id": "V-EXPOVISION", "vendor_name": "ExpoVision", "active": True},
        {"vendor_id": "V-KIOSKWORKS", "vendor_name": "KioskWorks", "active": True},
    ],
    "vendor_catalog": [
        {"vendor_id": "V-PRINTCO", "sku": "LANYARD-STD", "unit_price": 1.10, "lead_time_days": 5},
        {"vendor_id": "V-SWAGHUB", "sku": "LANYARD-STD", "unit_price": 0.95, "lead_time_days": 9},
        {"vendor_id": "V-PRINTCO", "sku": "TSHIRT-NEXT", "unit_price": 9.50, "lead_time_days": 5},
        {"vendor_id": "V-SWAGHUB", "sku": "TSHIRT-NEXT", "unit_price": 8.20, "lead_time_days": 9},
        {"vendor_id": "V-SWAGHUB", "sku": "HOODIE-NEXT", "unit_price": 25.00, "lead_time_days": 12},
        {"vendor_id": "V-PRINTCO", "sku": "HOODIE-NEXT", "unit_price": 28.00, "lead_time_days": 7},
        {"vendor_id": "V-SWAGHUB", "sku": "TOTE-NEXT", "unit_price": 3.90, "lead_time_days": 9},
        {"vendor_id": "V-PRINTCO", "sku": "TOTE-NEXT", "unit_price": 4.20, "lead_time_days": 5},
        {"vendor_id": "V-SWAGHUB", "sku": "WATER-BOTTLE", "unit_price": 5.90, "lead_time_days": 9},
        {"vendor_id": "V-PRINTCO", "sku": "WATER-BOTTLE", "unit_price": 6.40, "lead_time_days": 6},
        {"vendor_id": "V-PRINTCO", "sku": "STICKER-PACK", "unit_price": 0.25, "lead_time_days": 4},
        {"vendor_id": "V-PRINTCO", "sku": "BROCHURE-A5", "unit_price": 0.35, "lead_time_days": 5},
        {"vendor_id": "V-PRINTCO", "sku": "BANNER-XL", "unit_price": 85.00, "lead_time_days": 5},
        {"vendor_id": "V-EXPOVISION", "sku": "BANNER-XL", "unit_price": 92.00, "lead_time_days": 8},
        {"vendor_id": "V-EXPOVISION", "sku": "BOOTH-LEDWALL", "unit_price": 18000.00, "lead_time_days": 21},
        {"vendor_id": "V-KIOSKWORKS", "sku": "BOOTH-LEDWALL", "unit_price": 20500.00, "lead_time_days": 14},
        {"vendor_id": "V-KIOSKWORKS", "sku": "DEMO-KIOSK", "unit_price": 3200.00, "lead_time_days": 14},
    ],
    "campaigns": [
        {"campaign_id": "NEXT27-MAIN", "campaign_name": "Next 2027 Main Event Booth",
         "event_name": "Google Next 2027", "owner": "Events Marketing", "total_budget": 400000.0},
        {"campaign_id": "NEXT27-PARTNER", "campaign_name": "Next 2027 Partner Summit",
         "event_name": "Google Next 2027", "owner": "Partner Marketing", "total_budget": 40000.0},
        {"campaign_id": "NEXT27-DEVLOUNGE", "campaign_name": "Next 2027 Developer Lounge",
         "event_name": "Google Next 2027", "owner": "Developer Relations", "total_budget": 12000.0},
    ],
    # Opening position: money already spent / committed before the demo starts.
    "budget_ledger": [
        {"entry_id": "BASE-1", "campaign_id": "NEXT27-MAIN", "request_id": "BASELINE", "entry_type": "SPEND",
         "amount": 120000.0, "approved_by": "system", "created_at": _T0},
        {"entry_id": "BASE-2", "campaign_id": "NEXT27-MAIN", "request_id": "BASELINE", "entry_type": "COMMIT",
         "amount": 30000.0, "approved_by": "system", "created_at": _T0},
        {"entry_id": "BASE-3", "campaign_id": "NEXT27-PARTNER", "request_id": "BASELINE", "entry_type": "SPEND",
         "amount": 8000.0, "approved_by": "system", "created_at": _T0},
        {"entry_id": "BASE-4", "campaign_id": "NEXT27-DEVLOUNGE", "request_id": "BASELINE", "entry_type": "SPEND",
         "amount": 3000.0, "approved_by": "system", "created_at": _T0},
    ],
    "approval_policy": [
        {"tier": "AUTO", "min_amount": 0.0, "max_amount": 5000.0, "requires_human": False,
         "approver_role": "auto-policy"},
        {"tier": "MANAGER", "min_amount": 5000.0, "max_amount": 50000.0, "requires_human": True,
         "approver_role": "Marketing Director"},
        {"tier": "EXECUTIVE", "min_amount": 50000.0, "max_amount": 1e12, "requires_human": True,
         "approver_role": "VP Marketing + Finance Controller"},
    ],
    "approvers": [],  # filled by scripts/setup_bigquery.py from --approver-email / APPROVER_EMAILS
    "inventory_reservations": [],
    "campaign_requests": [],
    "purchase_orders": [],
    "audit_log": [],
}
