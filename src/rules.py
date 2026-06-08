"""Analysis rules — the per-account business logic. SWAP THIS FOR YOUR VERTICAL.

Ships with a worked EXAMPLE ruleset for a driver-recruitment advertiser, to show
how the engine handles real-world nuance (false-positive guards, plural-tolerant
matching, broad-vs-phrase match types). Replace the lists below with your own.

Classifies each search term as:
    - negative  -> propose for the shared negative keyword list
    - keyword   -> propose as a new keyword in a routed ad group
    - neutral   -> leave alone

CRITICAL: the false-positive guards win over everything. A term that matches a
guard is NEVER proposed as a negative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

Kind = Literal["negative", "keyword", "neutral"]
MatchType = Literal["broad", "phrase", "exact"]


@dataclass
class Classification:
    term: str
    kind: Kind
    match_type: Optional[MatchType] = None
    reason: str = ""
    ad_group: Optional[str] = None
    brand: bool = False


# ── helpers ────────────────────────────────────────────────────────────────
def _norm(term: str) -> str:
    return re.sub(r"\s+", " ", term.lower().strip())


def _has(term: str, needle: str) -> bool:
    """Whole-word-ish containment: matches needle as a substring on word
    boundaries so 'van' does not match inside 'caravan'."""
    return re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", term) is not None


def _is_oo(term: str) -> bool:
    """Plural-tolerant owner-operator detection."""
    return re.search(r"(?<![a-z])owner[- ]operators?(?![a-z])", term) is not None


# ── 1. False-positive guards (checked FIRST — these are protected) ──────────
# A term matching any guard is the real target audience and must never become a
# negative. See brief "CRITICAL false-positive guards".
def _is_guarded(term: str) -> Optional[str]:
    oo = _is_oo(term) or _has(term, "owner op")

    # Owner operator with their own equipment / long haul / OTR = the OO target.
    if oo and (
        _has(term, "own truck")
        or _has(term, "own transport")
        or _has(term, "own vehicle")
        or _has(term, "own semi")
        or _has(term, "dry van")
        or _has(term, "long haul")
        or _has(term, "otr")
        or _has(term, "loads")  # "owner operator steady loads" is legit
    ):
        return "guard: owner-operator target audience"

    # "dry van" is their equipment — never block anything containing it.
    if _has(term, "dry van"):
        return "guard: dry van is target equipment"

    # Account's best-converting term, counterintuitively.
    if _norm(term) == "driver work":
        return "guard: best-converting term"

    # Bare protective phrases that would clip real keywords.
    if _norm(term) == "truck work":
        return "guard: would clip real keywords (truck driving work)"

    return None


# ── 2. Brand ───────────────────────────────────────────────────────────────
# TODO: your brand names + common misspellings
_BRAND = ["acme logistics", "acme freight", "acme"]


def _is_brand(term: str) -> bool:
    return any(_has(term, b) for b in _BRAND)


# ── 3. Good-intent new keywords ────────────────────────────────────────────
_GOOD_INTENT_SIGNALS = [
    "apply", "application", "needed", "hiring", "recruitment", "recruiting",
    "now hiring", "jobs hiring", "wanted",
]
_AUDIENCE_SIGNALS = [
    "owner operator", "owner-operator", "cdl a", "cdl-a", "class a cdl",
    "otr", "over the road", "long haul", "semi truck", "semi-truck",
    "truck driver", "cdl driver",
]


def _is_good_intent(term: str) -> bool:
    has_audience = _is_oo(term) or any(_has(term, a) for a in _AUDIENCE_SIGNALS)
    has_intent = any(_has(term, s) for s in _GOOD_INTENT_SIGNALS)
    return has_audience and has_intent


# ── 4. Junk -> negatives ────────────────────────────────────────────────────
# Each entry: (needle, match_type, reason). Default broad unless word order
# matters or a broad version would clip a real keyword / the OO audience.
_NEGATIVES: list[tuple[str, MatchType, str]] = []


def _add(words: list[str], match_type: MatchType, reason: str) -> None:
    for w in words:
        _NEGATIVES.append((w, match_type, reason))


# Wrong vehicle (broad) — NOTE: bare "van" is deliberately excluded (guard).
_add(
    ["light truck", "box truck", "sprinter", "cargo van", "pickup", "hotshot",
     "hopper bottom", "tow truck", "dump", "tanker", "flatbed", "reefer",
     "car hauler", "dry bulk", "oversize", "double drop", "rgn", "heavy equipment"],
    "broad", "wrong vehicle",
)
# Wrong job type (broad)
_add(
    ["local", "near me", "delivery", "courier", "package", "route driver",
     "helper", "part-time", "part time", "seasonal", "warehouse", "forklift"],
    "broad", "wrong job type",
)
# Non-CDL / training (broad), bare "how to" excluded (guard)
_add(
    ["non cdl", "non-cdl", "class b", "cdl school", "cdl training", "cdl test",
     "cdl permit", "pay for cdl"],
    "broad", "non-cdl / training",
)
# Load-board / freight intent — bare "loads" forbidden, use phrases
_add(
    ["load board", "find loads", "get loads", "bulk loads", "truck loads",
     "military loads"],
    "phrase", "load-board / freight intent",
)
# Dispatcher / broker — bare "dispatch" forbidden
_add(["dispatcher", "dispatching"], "broad", "dispatcher / broker intent")
_add(["how to broker", "how to dispatch"], "phrase", "dispatcher / broker intent")
# Informational / business — bare "how to" forbidden
_add(
    ["business plan", "expenses", "side hustle", "for beginners", "salary",
     "how much do", "trucker hacks", "life as a truck driver"],
    "broad", "informational / business",
)
_add(["how to start"], "phrase", "informational / business")
# Visa
_add(["visa", "h2b", "sponsorship"], "broad", "visa")
# Felony / record
_add(["felon", "speeding tickets", "bad record", "dui", "dwi", "sap"],
     "broad", "felony / record")
# Foreign language (Spanish + Russian)
_add(
    ["trabajo", "chofer", "camionero", "camiones", "trailero", "conductor",
     "cuanto gana", "работа", "спринтер",
     "вэн", "пикап"],
    "broad", "foreign language",
)
# Competitor brand names
_add(
    ["landstar", "xpo", "crst", "saia", "melton", "knight", "us xpress",
     "hub group", "schneider", "prime", "werner", "swift"],
    "broad", "competitor brand",
)


def _match_negative(term: str) -> Optional[tuple[str, MatchType, str]]:
    # Plural-tolerant: "car hauler" also matches "car haulers", "tow truck" ->
    # "tow trucks". Google treats these as close variants anyway.
    for needle, mt, reason in _NEGATIVES:
        if re.search(rf"(?<![a-z]){re.escape(needle)}s?(?![a-z])", term):
            return needle, mt, reason
    return None


# ── ad-group routing for new keywords ──────────────────────────────────────
def route_ad_group(term: str) -> str:
    """Term with owner operator / lease -> Owner Operator Jobs; else Company."""
    t = _norm(term)
    if _is_oo(t) or _has(t, "lease"):
        return "Owner Operator Jobs"
    if _has(t, "cdl a") or _has(t, "cdl-a") or _has(t, "class a"):
        return "CDL A Jobs"
    return "OTR Jobs"


# ── public API ──────────────────────────────────────────────────────────────
def classify(term: str) -> Classification:
    t = _norm(term)

    # 1. Guards win over everything.
    guard = _is_guarded(t)
    if guard:
        # A guarded term is the target audience; surface strong-intent ones as
        # keyword candidates, otherwise leave neutral.
        if _is_good_intent(t) or _is_brand(t):
            return Classification(term, "keyword", "phrase", guard, route_ad_group(t))
        return Classification(term, "neutral", reason=guard)

    # 2. Brand -> exact-match keyword, flagged for dedicated Brand campaign.
    #    (Their own brand wins over everything except the guards.)
    if _is_brand(t):
        return Classification(term, "keyword", "exact",
                              "brand term — flag for dedicated Brand campaign",
                              route_ad_group(t), brand=True)

    # 3. Junk -> negative. Checked BEFORE good-intent so a hard-exclude
    #    (competitor, wrong vehicle, foreign, visa, felony) is not rescued by an
    #    incidental hiring-intent word like "application" or "wanted".
    #    e.g. "landstar owner operator application" must stay a competitor negative.
    neg = _match_negative(t)
    if neg:
        needle, mt, reason = neg
        return Classification(term, "negative", mt, reason)

    # 4. Good-intent -> new keyword.
    if _is_good_intent(t):
        return Classification(term, "keyword", "phrase", "good hiring intent",
                              route_ad_group(t))

    # 5. Otherwise neutral.
    return Classification(term, "neutral", reason="no rule matched")
