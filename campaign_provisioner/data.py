"""In-memory mock enterprise data (stand-in for ERP / procurement / finance systems).

Replace these dicts with real API clients in production; the tool signatures
in ``tools/`` are the only integration surface the agents depend on.
"""

INVENTORY = {
    "TSHIRT-M": {"name": "Campaign T-shirt (M)", "available": 300, "reserved": 0},
    "TOTE-01": {"name": "Branded tote bag", "available": 50, "reserved": 0},
    "BANNER-XL": {"name": "Event banner XL", "available": 5, "reserved": 0},
    "BROCHURE-A5": {"name": "A5 brochure", "available": 2000, "reserved": 0},
    "LED-DISPLAY": {"name": "LED booth display", "available": 0, "reserved": 0},
}

VENDORS = {
    "V-PRINTCO": {"name": "PrintCo", "lead_time_days": 5,
                  "prices": {"TSHIRT-M": 9.5, "TOTE-01": 4.2, "BANNER-XL": 85.0, "BROCHURE-A5": 0.35}},
    "V-SWAGHUB": {"name": "SwagHub", "lead_time_days": 9,
                  "prices": {"TSHIRT-M": 8.2, "TOTE-01": 3.9, "BANNER-XL": 79.0}},
    "V-EXPOTECH": {"name": "ExpoTech", "lead_time_days": 14,
                   "prices": {"LED-DISPLAY": 1450.0, "BANNER-XL": 92.0}},
}

BUDGETS = {
    "CMP-SPRING-LAUNCH": {"name": "Spring Launch", "total": 40000.0, "spent": 12000.0, "committed": 3000.0},
    "CMP-LOCAL-POPUP": {"name": "Local Pop-up", "total": 4000.0, "spent": 500.0, "committed": 0.0},
}
