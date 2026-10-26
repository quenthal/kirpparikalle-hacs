"""Constants for the Kirppari-Kalle integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "kirpparikalle"

CONF_COMPANY_ID = "company_id"
CONF_SHOP_NAME = "shop_name"

BASE_URL = "https://www.kirpparikalle.net/sovellus/"
REQUEST_TIMEOUT = 30

# Sales are read this often while a reservation is active and the shop is open.
SALES_INTERVAL = timedelta(minutes=5)
# Otherwise a light page load keeps the session alive.
KEEPALIVE_INTERVAL = timedelta(minutes=60)
# One more sales read this long after closing time.
FINAL_READ_DELAY = timedelta(minutes=10)

EVENT_SALES_UPDATE = f"{DOMAIN}_sales_update"
EVENT_TYPE_SALES_UPDATE = "sales_update"

STORAGE_VERSION = 1
