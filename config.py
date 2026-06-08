"""Central config — loads .env and exposes settings + the Google Ads client config."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _req(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Missing required env var {name}. "
            f"Fill it in {Path(__file__).parent / '.env'}"
        )
    return val


# Google Ads
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "").strip()
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "").strip()

# Account specifics
ACCOUNT_NAME = os.getenv("ACCOUNT_NAME", "Account").strip()       # shown in reports
ACCOUNT_TZ = os.getenv("ACCOUNT_TZ", "America/New_York").strip()  # reporting timezone
NEGATIVE_LIST_NAME = os.getenv("NEGATIVE_LIST_NAME", "negatives").strip()
NEGATIVE_LIST_SHARED_SET_ID = os.getenv("NEGATIVE_LIST_SHARED_SET_ID", "").strip()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Run settings
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "4"))
APPROVAL_TIMEOUT_HOURS = int(os.getenv("APPROVAL_TIMEOUT_HOURS", "12"))

# Schedule (twice weekly by default)
SCHEDULE_TZ = os.getenv("SCHEDULE_TZ", "Europe/Lisbon").strip()
SCHEDULE_DAYS = os.getenv("SCHEDULE_DAYS", "tue,fri").strip()   # cron day_of_week
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))


def google_ads_config() -> dict:
    """Config dict for GoogleAdsClient.load_from_dict()."""
    return {
        "developer_token": _req("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": _req("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": _req("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": _req("GOOGLE_ADS_REFRESH_TOKEN"),
        "login_customer_id": _req("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
        "use_proto_plus": True,
    }
