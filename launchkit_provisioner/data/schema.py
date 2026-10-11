"""BigQuery schema for The LaunchKit Provisioner (single source of truth).

Used by ``scripts/setup_bigquery.py`` to create the dataset, tables and views, and
documented in ``bigquery/schema.sql``. Columns are (name, type, mode, description).

Design notes
- Reference data (launches, assets, bundle templates, creators, depots and their stock, transit lanes, vendors and
  their offers, planning rules, approval policy, approvers) is plain tables, changed without a release.
- Sourcing scenarios are COMPUTED from that data and stored (scenarios, scenario_lines): the numbers shown to a
  decision maker are never typed in by the model.
- Stock and orders are append-only records (depot_holds, purchase_orders, depot_transfers). Availability and
  readiness are computed by the views.
"""

TABLES = {
    # ------------------------------------------------------------------ reference data
    "launches": {
        "description": "Product launches to equip, with the two dates that matter: in-hand deadline and press embargo.",
        "columns": [
            ("launch_id", "STRING", "REQUIRED", ""),
            ("launch_name", "STRING", "REQUIRED", ""),
            ("product_name", "STRING", "NULLABLE", ""),
            ("cost_center", "STRING", "NULLABLE", "Finance cost center that carries the spend"),
            ("embargo_date", "DATE", "REQUIRED", "Public press embargo lifts"),
            ("in_hand_by", "DATE", "REQUIRED", "Everything must be in the recipients' hands by this date"),
            ("owner", "STRING", "NULLABLE", ""),
        ],
    },
    "assets": {
        "description": "Launch collateral catalog (one row per sellable item).",
        "columns": [
            ("sku", "STRING", "REQUIRED", ""),
            ("name", "STRING", "REQUIRED", ""),
            ("component_type", "STRING", "REQUIRED", "BOX, APPAREL, POWER, PERSONALISATION, DISPLAY, FOLIO, PRINT"),
            ("ship_factor", "FLOAT64", "REQUIRED", "Relative size/weight: multiplies the shipping lane cost"),
        ],
    },
    "bundle_templates": {
        "description": "What goes into one bundle (creator kit, showroom display, sales folio).",
        "columns": [
            ("bundle_type", "STRING", "REQUIRED", "CREATOR_KIT, SHOWROOM_DISPLAY, SALES_FOLIO"),
            ("description", "STRING", "NULLABLE", ""),
            ("sku_pattern", "STRING", "REQUIRED", "A SKU, or a pattern with {size} / {plug}"),
            ("qty_per_bundle", "INT64", "REQUIRED", ""),
            ("split_by", "STRING", "REQUIRED", "NONE, SIZE or PLUG: how the SKU is chosen per recipient"),
        ],
    },
    "creators": {
        "description": "VIP creator seeding list: size and power-plug per recipient (personalisation).",
        "columns": [
            ("creator_id", "STRING", "REQUIRED", ""),
            ("launch_id", "STRING", "REQUIRED", ""),
            ("handle", "STRING", "REQUIRED", ""),
            ("name", "STRING", "NULLABLE", ""),
            ("size", "STRING", "REQUIRED", "S, M, L, XL"),
            ("region", "STRING", "REQUIRED", "US, EMEA, APAC"),
            ("plug_type", "STRING", "REQUIRED", "US-A, UK-G, EU-C, JP-A, AU-I"),
        ],
    },
    "regional_split": {
        "description": "How a non-personalised bundle is spread over regions (share in percent).",
        "columns": [
            ("bundle_type", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", ""),
            ("share_pct", "FLOAT64", "REQUIRED", ""),
        ],
    },
    "depots": {
        "description": "Regional marketing depots holding reusable surplus stock.",
        "columns": [
            ("depot_id", "STRING", "REQUIRED", ""),
            ("depot_name", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", ""),
        ],
    },
    "depot_stock": {
        "description": "Surplus units physically on hand per depot and SKU.",
        "columns": [
            ("depot_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("on_hand", "INT64", "REQUIRED", ""),
        ],
    },
    "transit_lanes": {
        "description": "Shipping time and cost between regions.",
        "columns": [
            ("from_region", "STRING", "REQUIRED", ""),
            ("to_region", "STRING", "REQUIRED", ""),
            ("days", "INT64", "REQUIRED", "Transit days"),
            ("cost_per_unit", "FLOAT64", "REQUIRED", "USD per ship_factor unit"),
        ],
    },
    "vendors": {
        "description": "Approved manufacturers.",
        "columns": [
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("vendor_name", "STRING", "REQUIRED", ""),
            ("home_region", "STRING", "REQUIRED", "Where it ships from"),
            ("active", "BOOL", "REQUIRED", "Only active vendors are planned"),
        ],
    },
    "vendor_offers": {
        "description": "Vendor price, production lead time and carbon per SKU and variant.",
        "columns": [
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("variant", "STRING", "REQUIRED", "STANDARD or ECO"),
            ("unit_price", "FLOAT64", "REQUIRED", "USD per unit"),
            ("lead_days", "INT64", "REQUIRED", "Production lead time"),
            ("carbon_kg", "FLOAT64", "REQUIRED", "kg CO2e per unit"),
        ],
    },
    "planning_rules": {
        "description": "Numbers that steer the planner (safety buffers, handling time), editable by the launch team.",
        "columns": [
            ("rule_key", "STRING", "REQUIRED", "MIN_BUFFER_HOURS, TARGET_BUFFER_HOURS, DEPOT_HANDLING_DAYS, ..."),
            ("rule_value", "FLOAT64", "REQUIRED", ""),
            ("description", "STRING", "NULLABLE", ""),
        ],
    },
    "approval_policy": {
        "description": "Sign-off tiers by amount: who decides, and whether a person must.",
        "columns": [
            ("tier", "STRING", "REQUIRED", "AUTOPILOT, VP_SIGNOFF, CMO_SIGNOFF"),
            ("min_amount", "FLOAT64", "REQUIRED", "Exclusive lower bound"),
            ("max_amount", "FLOAT64", "REQUIRED", "Inclusive upper bound"),
            ("requires_human", "BOOL", "REQUIRED", ""),
            ("approver_role", "STRING", "REQUIRED", ""),
        ],
    },
    "approvers": {
        "description": "Email addresses per approver role (configurable). Role 'Launch Team' receives tracking updates.",
        "columns": [
            ("approver_role", "STRING", "REQUIRED", ""),
            ("email", "STRING", "REQUIRED", ""),
            ("active", "BOOL", "REQUIRED", ""),
        ],
    },
    # ------------------------------------------------------------------ transactions
    "launch_requests": {
        "description": "Every brief registered by the root agent.",
        "columns": [
            ("request_id", "STRING", "REQUIRED", ""),
            ("launch_id", "STRING", "REQUIRED", ""),
            ("summary", "STRING", "NULLABLE", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "requirement_lines": {
        "description": "The brief broken down into what is needed where: one line per SKU and destination region.",
        "columns": [
            ("request_id", "STRING", "REQUIRED", ""),
            ("line_no", "INT64", "REQUIRED", ""),
            ("bundle_type", "STRING", "REQUIRED", ""),
            ("channel", "STRING", "REQUIRED", "CREATOR, SHOWROOM, SALES"),
            ("sku", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", "Destination region"),
            ("quantity", "INT64", "REQUIRED", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "scenarios": {
        "description": "The sourcing options computed for a request (full new build, depot rebalance, eco launch).",
        "columns": [
            ("scenario_id", "STRING", "REQUIRED", "<request_id>-<FN|RB|EC>"),
            ("request_id", "STRING", "REQUIRED", ""),
            ("option_code", "STRING", "REQUIRED", "FULL_NEW, REBALANCE or ECO"),
            ("option_name", "STRING", "REQUIRED", ""),
            ("total_cost", "FLOAT64", "REQUIRED", "USD, product plus shipping"),
            ("shipping_cost", "FLOAT64", "REQUIRED", "USD"),
            ("savings_usd", "FLOAT64", "REQUIRED", "Versus the full new build"),
            ("delivery_date", "DATE", "REQUIRED", "When the last line arrives"),
            ("buffer_hours", "INT64", "REQUIRED", "Hours between delivery and the in-hand deadline (negative = late)"),
            ("carbon_kg", "FLOAT64", "REQUIRED", ""),
            ("risk", "STRING", "REQUIRED", ""),
            ("feasible", "BOOL", "REQUIRED", "Meets the in-hand deadline and every line has a source"),
            ("recommended", "BOOL", "REQUIRED", ""),
            ("summary", "STRING", "NULLABLE", "One-line description"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "scenario_lines": {
        "description": "What each scenario would do per line: reuse depot stock or buy from a vendor.",
        "columns": [
            ("line_id", "STRING", "REQUIRED", "<scenario_id>-L<nn>"),
            ("scenario_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("channel", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", "Destination region"),
            ("quantity", "INT64", "REQUIRED", ""),
            ("source_type", "STRING", "REQUIRED", "DEPOT or VENDOR"),
            ("source_id", "STRING", "REQUIRED", "depot_id or vendor_id"),
            ("variant", "STRING", "NULLABLE", "STANDARD or ECO (vendor lines)"),
            ("unit_price", "FLOAT64", "REQUIRED", "0 for depot stock"),
            ("shipping_cost", "FLOAT64", "REQUIRED", ""),
            ("line_total", "FLOAT64", "REQUIRED", ""),
            ("days_to_deliver", "INT64", "REQUIRED", ""),
            ("carbon_kg", "FLOAT64", "REQUIRED", ""),
            ("execution_status", "STRING", "REQUIRED", "PLANNED or EXECUTED"),
        ],
    },
    "decisions": {
        "description": "The sign-off on one chosen scenario: autopilot or a human decision through Application Integration.",
        "columns": [
            ("decision_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("scenario_id", "STRING", "REQUIRED", ""),
            ("option_code", "STRING", "REQUIRED", ""),
            ("tier", "STRING", "REQUIRED", ""),
            ("approver_role", "STRING", "REQUIRED", ""),
            ("approver_emails", "STRING", "NULLABLE", "Comma separated"),
            ("amount", "FLOAT64", "REQUIRED", "USD authorised: the scenario total"),
            ("justification", "STRING", "NULLABLE", ""),
            ("status", "STRING", "REQUIRED", "PENDING, APPROVED, REJECTED or FAILED"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
            ("expires_at", "TIMESTAMP", "REQUIRED", ""),
            ("decided_by", "STRING", "NULLABLE", "autopilot or the approval workflow"),
            ("decided_at", "TIMESTAMP", "NULLABLE", ""),
            ("decision_note", "STRING", "NULLABLE", "While pending: execution:<Application Integration execution id>"),
        ],
    },
    "depot_holds": {
        "description": "Surplus stock held for a pending or approved scenario (released on a rejection).",
        "columns": [
            ("hold_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("scenario_id", "STRING", "REQUIRED", ""),
            ("line_id", "STRING", "REQUIRED", ""),
            ("depot_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("quantity", "INT64", "REQUIRED", ""),
            ("status", "STRING", "REQUIRED", "ACTIVE, CONSUMED or RELEASED"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "vendor_disruptions": {
        "description": "Reported vendor delays that the planner adds to the lead time.",
        "columns": [
            ("disruption_id", "STRING", "REQUIRED", ""),
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("delay_days", "INT64", "REQUIRED", ""),
            ("reason", "STRING", "NULLABLE", ""),
            ("active", "BOOL", "REQUIRED", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "purchase_orders": {
        "description": "Purchase orders issued through Application Integration for the approved scenario.",
        "columns": [
            ("po_number", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("line_id", "STRING", "REQUIRED", ""),
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", ""),
            ("quantity", "INT64", "REQUIRED", ""),
            ("total_amount", "FLOAT64", "REQUIRED", ""),
            ("status", "STRING", "REQUIRED", ""),
            ("integration_execution_id", "STRING", "NULLABLE", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "depot_transfers": {
        "description": "Stock transfer orders from a depot to the destination region.",
        "columns": [
            ("transfer_number", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("line_id", "STRING", "REQUIRED", ""),
            ("depot_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("region", "STRING", "REQUIRED", ""),
            ("quantity", "INT64", "REQUIRED", ""),
            ("status", "STRING", "REQUIRED", ""),
            ("integration_execution_id", "STRING", "NULLABLE", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "audit_log": {
        "description": "Every governed action: who did what, when.",
        "columns": [
            ("event_id", "STRING", "REQUIRED", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
            ("request_id", "STRING", "NULLABLE", ""),
            ("actor", "STRING", "REQUIRED", "Agent or human role"),
            ("action", "STRING", "REQUIRED", ""),
            ("details", "STRING", "NULLABLE", "JSON text"),
        ],
    },
}

# Views. {ds} is replaced with `project.dataset`.
VIEWS = {
    "v_depot_available": """
SELECT d.depot_id, d.depot_name, d.region, s.sku, s.on_hand,
       IFNULL(SUM(IF(h.status IN ('ACTIVE', 'CONSUMED'), h.quantity, 0)), 0) AS held,
       s.on_hand - IFNULL(SUM(IF(h.status IN ('ACTIVE', 'CONSUMED'), h.quantity, 0)), 0) AS free
FROM `{ds}.depot_stock` s
JOIN `{ds}.depots` d ON d.depot_id = s.depot_id
LEFT JOIN `{ds}.depot_holds` h ON h.depot_id = s.depot_id AND h.sku = s.sku
GROUP BY d.depot_id, d.depot_name, d.region, s.sku, s.on_hand
""",
    "v_launch_readiness": """
SELECT r.request_id, l.launch_id, l.launch_name, l.in_hand_by, l.embargo_date,
       dc.option_code AS chosen_option, dc.status AS decision_status, dc.tier, dc.amount AS authorised_amount,
       sc.delivery_date, sc.buffer_hours,
       CASE WHEN dc.request_id IS NULL THEN 'NO_DECISION'
            WHEN dc.status != 'APPROVED' THEN dc.status
            WHEN sc.buffer_hours < 0 THEN 'RED'
            WHEN sc.buffer_hours < 24 THEN 'AMBER'
            ELSE 'GREEN' END AS readiness,
       (SELECT COUNT(*) FROM `{ds}.scenario_lines` x
         WHERE x.scenario_id = dc.scenario_id AND x.execution_status = 'EXECUTED') AS lines_executed,
       (SELECT COUNT(*) FROM `{ds}.scenario_lines` x WHERE x.scenario_id = dc.scenario_id) AS lines_total
FROM `{ds}.launch_requests` r
JOIN `{ds}.launches` l ON l.launch_id = r.launch_id
LEFT JOIN (
  SELECT * FROM `{ds}.decisions` QUALIFY ROW_NUMBER() OVER (PARTITION BY request_id ORDER BY created_at DESC) = 1
) dc ON dc.request_id = r.request_id
LEFT JOIN `{ds}.scenarios` sc ON sc.scenario_id = dc.scenario_id
""",
}

# Tables that hold transactions (cleared by --reset-demo).
TRANSACTION_TABLES = ["launch_requests", "requirement_lines", "scenarios", "scenario_lines", "decisions",
                      "depot_holds", "vendor_disruptions", "purchase_orders", "depot_transfers", "audit_log"]
