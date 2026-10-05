"""BigQuery schema for The Campaign Provisioner (single source of truth).

Used by ``scripts/setup_bigquery.py`` to create the dataset, tables and views, and
documented in ``bigquery/schema.sql``. Columns are (name, type, mode, description).

Design notes
- Reference data (items, vendors, catalog, campaigns, policy) is plain tables.
- Money and stock movements are APPEND-ONLY ledgers (inventory_reservations,
  budget_ledger, purchase_orders). Balances are computed by the views, so there are
  no read-modify-write updates and every movement is auditable.
"""

TABLES = {
    "inventory_items": {
        "description": "Campaign material catalog with physical stock on hand.",
        "columns": [
            ("sku", "STRING", "REQUIRED", "Unique item code"),
            ("name", "STRING", "REQUIRED", "Display name"),
            ("category", "STRING", "NULLABLE", "Swag, Signage, Booth, Print"),
            ("on_hand", "INT64", "REQUIRED", "Physical units in warehouse"),
        ],
    },
    "inventory_reservations": {
        "description": "Append-only stock reservations per campaign request.",
        "columns": [
            ("reservation_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", "Campaign request id"),
            ("sku", "STRING", "REQUIRED", ""),
            ("quantity", "INT64", "REQUIRED", ""),
            ("status", "STRING", "REQUIRED", "ACTIVE or RELEASED"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "vendors": {
        "description": "Approved suppliers.",
        "columns": [
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("vendor_name", "STRING", "REQUIRED", ""),
            ("active", "BOOL", "REQUIRED", "Only active vendors are quoted"),
        ],
    },
    "vendor_catalog": {
        "description": "Vendor price list and lead times per SKU.",
        "columns": [
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("unit_price", "FLOAT64", "REQUIRED", "USD per unit"),
            ("lead_time_days", "INT64", "REQUIRED", ""),
        ],
    },
    "campaigns": {
        "description": "Marketing campaigns and their approved total budget.",
        "columns": [
            ("campaign_id", "STRING", "REQUIRED", ""),
            ("campaign_name", "STRING", "REQUIRED", ""),
            ("event_name", "STRING", "NULLABLE", "Parent event, e.g. Google Next 2027"),
            ("owner", "STRING", "NULLABLE", ""),
            ("total_budget", "FLOAT64", "REQUIRED", "USD"),
        ],
    },
    "budget_ledger": {
        "description": "Append-only budget movements. COMMIT = approved spend, RELEASE = returned, SPEND = already spent.",
        "columns": [
            ("entry_id", "STRING", "REQUIRED", ""),
            ("campaign_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", "BASELINE for seeded opening spend"),
            ("entry_type", "STRING", "REQUIRED", "COMMIT, RELEASE or SPEND"),
            ("amount", "FLOAT64", "REQUIRED", "USD, always positive"),
            ("approved_by", "STRING", "NULLABLE", "auto-policy, human:<role>, or system"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "approval_policy": {
        "description": "Spend tiers: who must approve an amount. amount > min_amount AND <= max_amount.",
        "columns": [
            ("tier", "STRING", "REQUIRED", ""),
            ("min_amount", "FLOAT64", "REQUIRED", "Exclusive lower bound, USD"),
            ("max_amount", "FLOAT64", "REQUIRED", "Inclusive upper bound, USD"),
            ("requires_human", "BOOL", "REQUIRED", ""),
            ("approver_role", "STRING", "REQUIRED", ""),
        ],
    },
    "approvers": {
        "description": "Who is notified (email) when a role must approve. Configured at setup time; edit with SQL.",
        "columns": [
            ("approver_role", "STRING", "REQUIRED", "Must match approval_policy.approver_role"),
            ("email", "STRING", "REQUIRED", ""),
            ("active", "BOOL", "REQUIRED", "Only active rows are notified"),
        ],
    },
    "request_lines": {
        "description": "What each request asked for and what stock covered; the shortfall becomes the purchase plan.",
        "columns": [
            ("request_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("requested", "INT64", "REQUIRED", "Units wanted"),
            ("reserved", "INT64", "REQUIRED", "Units taken from stock"),
            ("shortfall", "INT64", "REQUIRED", "Units still to buy"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "approval_requests": {
        "description": "Human approvals requested by email. The decision is taken by a signed link in the email.",
        "columns": [
            ("approval_id", "STRING", "REQUIRED", ""),
            ("request_id", "STRING", "REQUIRED", ""),
            ("campaign_id", "STRING", "REQUIRED", ""),
            ("tier", "STRING", "REQUIRED", ""),
            ("approver_role", "STRING", "REQUIRED", ""),
            ("approver_emails", "STRING", "REQUIRED", "Comma separated; only these may decide"),
            ("amount", "FLOAT64", "REQUIRED", "USD, computed from the purchase plan"),
            ("plan", "STRING", "NULLABLE", "JSON: purchase lines (sku, quantity, vendor, price)"),
            ("justification", "STRING", "NULLABLE", ""),
            ("status", "STRING", "REQUIRED", "PENDING, APPROVED, REJECTED or FAILED"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
            ("expires_at", "TIMESTAMP", "REQUIRED", "Links stop working after this"),
            ("decided_by", "STRING", "NULLABLE", "Email of the person who clicked"),
            ("decided_at", "TIMESTAMP", "NULLABLE", ""),
            ("decision_note", "STRING", "NULLABLE", ""),
        ],
    },
    "campaign_requests": {
        "description": "Every request registered by the orchestrator.",
        "columns": [
            ("request_id", "STRING", "REQUIRED", ""),
            ("campaign_id", "STRING", "REQUIRED", ""),
            ("summary", "STRING", "NULLABLE", ""),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "purchase_orders": {
        "description": "Purchase orders created through Application Integration.",
        "columns": [
            ("po_number", "STRING", "REQUIRED", "Returned by the integration"),
            ("request_id", "STRING", "REQUIRED", ""),
            ("campaign_id", "STRING", "REQUIRED", ""),
            ("vendor_id", "STRING", "REQUIRED", ""),
            ("sku", "STRING", "REQUIRED", ""),
            ("quantity", "INT64", "REQUIRED", ""),
            ("total_amount", "FLOAT64", "REQUIRED", "USD, computed by the guard, not the model"),
            ("status", "STRING", "REQUIRED", "CREATED or CANCELLED"),
            ("integration_execution_id", "STRING", "NULLABLE", "Application Integration execution id"),
            ("created_at", "TIMESTAMP", "REQUIRED", ""),
        ],
    },
    "audit_log": {
        "description": "Append-only trail of every governed action.",
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
    "v_inventory_available": """
SELECT i.sku, i.name, i.category, i.on_hand,
       IFNULL(SUM(IF(r.status = 'ACTIVE', r.quantity, 0)), 0) AS reserved,
       i.on_hand - IFNULL(SUM(IF(r.status = 'ACTIVE', r.quantity, 0)), 0) AS free
FROM `{ds}.inventory_items` i
LEFT JOIN `{ds}.inventory_reservations` r USING (sku)
GROUP BY i.sku, i.name, i.category, i.on_hand
""",
    "v_campaign_budget": """
SELECT c.campaign_id, c.campaign_name, c.event_name, c.total_budget,
       IFNULL(SUM(IF(l.entry_type = 'SPEND', l.amount, 0)), 0) AS spent,
       IFNULL(SUM(CASE l.entry_type WHEN 'COMMIT' THEN l.amount WHEN 'RELEASE' THEN -l.amount ELSE 0 END), 0) AS committed,
       c.total_budget
         - IFNULL(SUM(IF(l.entry_type = 'SPEND', l.amount, 0)), 0)
         - IFNULL(SUM(CASE l.entry_type WHEN 'COMMIT' THEN l.amount WHEN 'RELEASE' THEN -l.amount ELSE 0 END), 0) AS remaining
FROM `{ds}.campaigns` c
LEFT JOIN `{ds}.budget_ledger` l USING (campaign_id)
GROUP BY c.campaign_id, c.campaign_name, c.event_name, c.total_budget
""",
    "v_request_headroom": """
SELECT l.request_id,
       SUM(CASE l.entry_type WHEN 'COMMIT' THEN l.amount WHEN 'RELEASE' THEN -l.amount ELSE 0 END) AS approved,
       IFNULL(ANY_VALUE(p.ordered), 0) AS ordered
FROM `{ds}.budget_ledger` l
LEFT JOIN (
  SELECT request_id, SUM(total_amount) AS ordered
  FROM `{ds}.purchase_orders` WHERE status = 'CREATED' GROUP BY request_id
) p USING (request_id)
WHERE l.entry_type IN ('COMMIT', 'RELEASE')
GROUP BY l.request_id
""",
}

# Tables that hold transactions (cleared by --reset-demo).
TRANSACTION_TABLES = ["inventory_reservations", "campaign_requests", "purchase_orders", "audit_log", "request_lines",
                      "approval_requests"]
