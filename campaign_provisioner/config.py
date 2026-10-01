"""Central configuration for The Campaign Provisioner."""
import os

MODEL = os.getenv("CAMPAIGN_MODEL", "gemini-2.5-flash")

# Any budget approval above this amount (USD) needs a human decision.
HIGH_VALUE_THRESHOLD_USD = float(os.getenv("HIGH_VALUE_THRESHOLD_USD", "5000"))
