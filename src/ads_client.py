"""Google Ads API access (read path).

Authenticates through the MCC and pulls the search terms report for the client
account, plus the read helpers the write path needs (ad-group lookup and
existing-criteria mirrors for idempotency).
"""
from __future__ import annotations

import datetime as dt
from typing import Iterator

import config
from .proposal import SearchTermRow

# Reporting timezone for the client account (set via ACCOUNT_TZ in .env).
ACCOUNT_TZ = config.ACCOUNT_TZ

# Volume metrics per search term. NOTE: segments.conversion_action_name cannot
# coexist with clicks/cost/impressions in one query (API limitation), so the
# per-action conversion breakdown is pulled separately below and merged.
SEARCH_TERMS_GAQL = """
SELECT
  search_term_view.search_term,
  campaign.name,
  ad_group.name,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions
FROM search_term_view
WHERE {date_filter}
ORDER BY metrics.conversions DESC
"""

# Conversions broken down by action (form_open vs Submit lead form). Only the
# conversions metric is compatible with the conversion_action_name segment.
CONVERSIONS_GAQL = """
SELECT
  search_term_view.search_term,
  segments.conversion_action_name,
  metrics.conversions
FROM search_term_view
WHERE {date_filter}
  AND metrics.conversions > 0
"""

# Google Ads only accepts a fixed set of LAST_N_DAYS literals.
_ALLOWED_WINDOWS = {7, 14, 30}


def _client():
    from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient.load_from_dict(config.google_ads_config())


def _window_days(days: int) -> int:
    """Snap requested lookback to the nearest allowed DURING literal (>=)."""
    for w in sorted(_ALLOWED_WINDOWS):
        if days <= w:
            return w
    return max(_ALLOWED_WINDOWS)


def account_today() -> dt.date:
    """Today's date in the account's reporting timezone (US Eastern)."""
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo(ACCOUNT_TZ)).date()


def _date_filter(start: dt.date | None, end: dt.date | None, days: int) -> str:
    """Build the WHERE date clause: explicit BETWEEN if dates given, else
    snap to an allowed DURING LAST_N_DAYS literal."""
    if start and end:
        return f"segments.date BETWEEN '{start:%Y-%m-%d}' AND '{end:%Y-%m-%d}'"
    return f"segments.date DURING LAST_{_window_days(days)}_DAYS"


def pull_search_terms(
    days: int | None = None,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[SearchTermRow]:
    """Pull the search terms report. Pass start+end for an exact period (the
    'stats for the previous days since last run' case), or days for a window."""
    days = days or config.LOOKBACK_DAYS
    date_filter = _date_filter(start, end, days)
    client = _client()
    ga_service = client.get_service("GoogleAdsService")
    cid = config.CUSTOMER_ID

    rows: list[SearchTermRow] = []

    # 1. Volume metrics (one row per term/campaign/ad_group).
    for batch in ga_service.search_stream(
        customer_id=cid, query=SEARCH_TERMS_GAQL.format(date_filter=date_filter)
    ):
        for row in batch.results:
            rows.append(
                SearchTermRow(
                    search_term=row.search_term_view.search_term,
                    campaign=row.campaign.name,
                    ad_group=row.ad_group.name,
                    clicks=row.metrics.clicks,
                    impressions=row.metrics.impressions,
                    cost_micros=row.metrics.cost_micros,
                    conversions=row.metrics.conversions,
                )
            )

    # 2. Per-action conversions, merged in as zero-cost rows so the proposal
    #    builder can split form_open vs Submit lead form.
    for batch in ga_service.search_stream(
        customer_id=cid, query=CONVERSIONS_GAQL.format(date_filter=date_filter)
    ):
        for row in batch.results:
            rows.append(
                SearchTermRow(
                    search_term=row.search_term_view.search_term,
                    conversions=row.metrics.conversions,
                    conversion_action_name=row.segments.conversion_action_name,
                )
            )

    return rows


# ── read helpers for the write path ─────────────────────────────────────────
def ad_group_map() -> dict[str, int]:
    """Map ENABLED ad-group name -> ad_group.id for the client account.

    Names are not globally unique (e.g. 'general'), but the names we route to
    (Owner Operator Jobs / CDL A Jobs / OTR Jobs) are. First ENABLED match wins.
    """
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = (
        "SELECT ad_group.id, ad_group.name, campaign.name FROM ad_group "
        "WHERE ad_group.status = 'ENABLED'"
    )
    out: dict[str, int] = {}
    for batch in ga.search_stream(customer_id=config.CUSTOMER_ID, query=query):
        for row in batch.results:
            out.setdefault(row.ad_group.name, row.ad_group.id)
    return out


def existing_shared_negatives() -> set[tuple[str, str]]:
    """(lowercased text, match_type name) already in the shared negative set."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = (
        "SELECT shared_criterion.keyword.text, shared_criterion.keyword.match_type "
        "FROM shared_criterion "
        f"WHERE shared_set.id = {config.NEGATIVE_LIST_SHARED_SET_ID}"
    )
    out: set[tuple[str, str]] = set()
    for batch in ga.search_stream(customer_id=config.CUSTOMER_ID, query=query):
        for row in batch.results:
            kw = row.shared_criterion.keyword
            out.add((kw.text.lower(), kw.match_type.name))
    return out


def existing_ad_group_keywords(ad_group_id: int) -> set[tuple[str, str]]:
    """(lowercased text, match_type name) already present in an ad group."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = (
        "SELECT ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type FROM ad_group_criterion "
        f"WHERE ad_group.id = {ad_group_id} "
        "AND ad_group_criterion.type = 'KEYWORD'"
    )
    out: set[tuple[str, str]] = set()
    for batch in ga.search_stream(customer_id=config.CUSTOMER_ID, query=query):
        for row in batch.results:
            kw = row.ad_group_criterion.keyword
            out.add((kw.text.lower(), kw.match_type.name))
    return out


def check_connection() -> Iterator[str]:
    """Lightweight auth smoke test — lists accessible customers under the MCC."""
    client = _client()
    svc = client.get_service("CustomerService")
    res = svc.list_accessible_customers()
    for name in res.resource_names:
        yield name
