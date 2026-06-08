"""Component 3 — Proposal builder.

Turns classified search-term rows into a structured proposal object, with
period stats and flags. Dedup against already-processed terms is the caller's
job (Component 7); this module is pure.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .rules import classify

FORM_OPEN_ACTIONS = {"form_open"}
REAL_SUBMIT_ACTIONS = {"submit lead form"}


@dataclass
class SearchTermRow:
    search_term: str
    campaign: str = ""
    ad_group: str = ""
    clicks: int = 0
    impressions: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    conversion_action_name: str = ""

    @property
    def cost(self) -> float:
        return self.cost_micros / 1_000_000


@dataclass
class Proposal:
    period: str
    stats: dict = field(default_factory=dict)
    negatives: list[dict] = field(default_factory=list)
    new_keywords: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_proposal(
    rows: Iterable[SearchTermRow],
    period: str,
    *,
    skip_terms: set[str] | None = None,
) -> Proposal:
    skip = {t.lower() for t in (skip_terms or set())}

    # Aggregate metrics per distinct search term (rows split by conversion action).
    agg: dict[str, dict] = defaultdict(
        lambda: {"clicks": 0, "impressions": 0, "cost": 0.0,
                 "form_opens": 0.0, "real_submits": 0.0}
    )
    total = {"clicks": 0, "cost": 0.0, "form_opens": 0.0, "real_submits": 0.0}

    for r in rows:
        term = r.search_term.strip()
        a = agg[term]
        a["clicks"] = max(a["clicks"], r.clicks)
        a["impressions"] = max(a["impressions"], r.impressions)
        a["cost"] = max(a["cost"], r.cost)
        action = (r.conversion_action_name or "").strip().lower()
        if action in FORM_OPEN_ACTIONS:
            a["form_opens"] += r.conversions
        elif action in REAL_SUBMIT_ACTIONS:
            a["real_submits"] += r.conversions

    for a in agg.values():
        total["clicks"] += a["clicks"]
        total["cost"] += a["cost"]
        total["form_opens"] += a["form_opens"]
        total["real_submits"] += a["real_submits"]

    negatives: list[dict] = []
    new_keywords: list[dict] = []
    seen_neg: set[str] = set()
    seen_kw: set[str] = set()
    brand_flagged = False

    for term in agg:
        low = term.lower()
        if low in skip:
            continue
        c = classify(term)
        if c.kind == "negative" and low not in seen_neg:
            seen_neg.add(low)
            negatives.append(
                {"term": c.term, "match_type": c.match_type, "reason": c.reason}
            )
        elif c.kind == "keyword" and low not in seen_kw:
            seen_kw.add(low)
            new_keywords.append(
                {"term": c.term, "match_type": c.match_type, "ad_group": c.ad_group}
            )
            if c.brand:
                brand_flagged = True

    flags: list[str] = []
    if total["real_submits"] == 0:
        flags.append("0 real submits this period — check /apply form")
    if brand_flagged:
        flags.append("Brand searches detected — consider a dedicated Brand campaign")

    return Proposal(
        period=period,
        stats={
            "clicks": int(total["clicks"]),
            "cost": round(total["cost"], 2),
            "form_opens": int(total["form_opens"]),
            "real_submits": int(total["real_submits"]),
        },
        negatives=negatives,
        new_keywords=new_keywords,
        flags=flags,
    )


def format_for_telegram(p: Proposal) -> str:
    """Readable HTML message for the Telegram proposal."""
    import config
    s = p.stats
    lines = [
        f"<b>🔎 {config.ACCOUNT_NAME} — Search Terms Review</b>",
        f"<i>{p.period}</i>",
        "",
        f"📊 Clicks: <b>{s['clicks']}</b>  ·  Cost: <b>${s['cost']}</b>",
        f"📝 Form opens: {s['form_opens']}  ·  ✅ Real submits: <b>{s['real_submits']}</b>",
        "",
        f"<b>➖ Negatives ({len(p.negatives)})</b>",
    ]
    for n in p.negatives[:40]:
        lines.append(f"  • <code>{n['term']}</code> — {n['match_type']} — {n['reason']}")
    if len(p.negatives) > 40:
        lines.append(f"  … +{len(p.negatives) - 40} more")

    lines += ["", f"<b>➕ New keywords ({len(p.new_keywords)})</b>"]
    for k in p.new_keywords[:40]:
        lines.append(f"  • <code>{k['term']}</code> — {k['match_type']} → {k['ad_group']}")
    if len(p.new_keywords) > 40:
        lines.append(f"  … +{len(p.new_keywords) - 40} more")

    if p.flags:
        lines += ["", "<b>⚑ Flags</b>"]
        lines += [f"  • {f}" for f in p.flags]

    return "\n".join(lines)
