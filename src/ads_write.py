"""Apply approved changes to Google Ads.

Only ever called after explicit Telegram approval. Writes:
  - approved negatives  -> your shared negative keyword list (SharedSet)
  - approved keywords   -> the routed ad group

Idempotent: existing criteria are read first and skipped, so re-runs never
create duplicates. Pass validate_only=True to dry-run the mutate against
Google's validation without applying anything.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from . import ads_client

_MATCH_TYPE = {"broad": "BROAD", "phrase": "PHRASE", "exact": "EXACT"}


@dataclass
class ApplyResult:
    negatives_added: int = 0
    negatives_skipped: int = 0
    keywords_added: int = 0
    keywords_skipped: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def summary(self) -> str:
        parts = [
            f"Added {self.negatives_added} negatives",
            f"{self.keywords_added} keywords",
        ]
        if self.negatives_skipped or self.keywords_skipped:
            parts.append(
                f"(skipped {self.negatives_skipped} neg + "
                f"{self.keywords_skipped} kw already present)"
            )
        if self.errors:
            parts.append(f"⚠️ {len(self.errors)} errors")
        return ", ".join(parts) + "."


def _match_enum(client, match_type: str):
    name = _MATCH_TYPE.get(match_type, "BROAD")
    return getattr(client.enums.KeywordMatchTypeEnum, name)


def apply_changes(
    negatives: list[dict],
    keywords: list[dict],
    *,
    validate_only: bool = False,
) -> ApplyResult:
    """negatives: [{term, match_type, reason}], keywords: [{term, match_type, ad_group}]."""
    client = ads_client._client()
    cid = config.CUSTOMER_ID
    result = ApplyResult()

    _apply_negatives(client, cid, negatives, result, validate_only)
    _apply_keywords(client, cid, keywords, result, validate_only)
    return result


def _apply_negatives(client, cid, negatives, result, validate_only):
    if not negatives:
        return
    existing = ads_client.existing_shared_negatives()
    shared_set_rn = client.get_service("SharedSetService").shared_set_path(
        cid, config.NEGATIVE_LIST_SHARED_SET_ID
    )
    ops = []
    for n in negatives:
        key = (n["term"].lower(), _MATCH_TYPE.get(n["match_type"], "BROAD"))
        if key in existing:
            result.negatives_skipped += 1
            continue
        op = client.get_type("SharedCriterionOperation")
        crit = op.create
        crit.shared_set = shared_set_rn
        crit.keyword.text = n["term"]
        crit.keyword.match_type = _match_enum(client, n["match_type"])
        ops.append(op)

    if not ops:
        return
    request = client.get_type("MutateSharedCriteriaRequest")
    request.customer_id = cid
    request.operations = ops
    request.validate_only = validate_only
    request.partial_failure = True
    try:
        svc = client.get_service("SharedCriterionService")
        svc.mutate_shared_criteria(request=request)
        result.negatives_added += len(ops)
    except Exception as e:  # noqa: BLE001 — surface to Telegram, don't crash run
        result.errors.append(f"negatives: {e}")


def _apply_keywords(client, cid, keywords, result, validate_only):
    if not keywords:
        return
    ag_map = ads_client.ad_group_map()
    ag_service = client.get_service("AdGroupService")

    # Group keywords by target ad group so we read existing criteria once each.
    by_group: dict[str, list[dict]] = {}
    for k in keywords:
        by_group.setdefault(k["ad_group"], []).append(k)

    for ag_name, items in by_group.items():
        ag_id = ag_map.get(ag_name)
        if not ag_id:
            result.errors.append(f"ad group not found: {ag_name!r}")
            continue
        existing = ads_client.existing_ad_group_keywords(ag_id)
        ag_rn = ag_service.ad_group_path(cid, ag_id)
        ops = []
        for k in items:
            key = (k["term"].lower(), _MATCH_TYPE.get(k["match_type"], "PHRASE"))
            if key in existing:
                result.keywords_skipped += 1
                continue
            op = client.get_type("AdGroupCriterionOperation")
            crit = op.create
            crit.ad_group = ag_rn
            crit.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
            crit.keyword.text = k["term"]
            crit.keyword.match_type = _match_enum(client, k["match_type"])
            ops.append(op)
        if not ops:
            continue
        request = client.get_type("MutateAdGroupCriteriaRequest")
        request.customer_id = cid
        request.operations = ops
        request.validate_only = validate_only
        request.partial_failure = True
        try:
            svc = client.get_service("AdGroupCriterionService")
            svc.mutate_ad_group_criteria(request=request)
            result.keywords_added += len(ops)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"keywords [{ag_name}]: {e}")
