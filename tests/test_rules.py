"""Unit tests for the analysis rules — with special focus on the false-positive
guards required by the acceptance criteria.
"""
import pytest

from src.rules import classify, route_ad_group


# ── Acceptance criteria: these must NEVER be proposed as negatives ──────────
GUARDED_TERMS = [
    "dry van owner operator",
    "driver work",
    "truck work",
    "owner operator loads",
    "owner operator with own truck",
    "long haul owner operator",
    "otr owner operator",
    "dry van",
]


@pytest.mark.parametrize("term", GUARDED_TERMS)
def test_guards_never_negative(term):
    assert classify(term).kind != "negative", f"{term!r} was wrongly negated"


# ── Junk that SHOULD become negatives ───────────────────────────────────────
NEGATIVE_TERMS = [
    "landstar",
    "box truck driver",
    "cdl school near me",
    "load board",
    "dispatcher jobs",
    "how to start a trucking business",
    "trabajo de chofer",
    "class b driver",
    "tow truck driver",
    "h2b visa sponsorship",
]


@pytest.mark.parametrize("term", NEGATIVE_TERMS)
def test_junk_is_negative(term):
    assert classify(term).kind == "negative", f"{term!r} should be a negative"


# ── Match-type traps ────────────────────────────────────────────────────────
def test_load_board_is_phrase():
    assert classify("load board").match_type == "phrase"


def test_competitor_is_broad():
    assert classify("schneider").match_type == "broad"


def test_bare_van_not_negative():
    # bare "van" must never block (it would clip "dry van owner operator")
    assert classify("dry van owner operator").kind != "negative"


def test_how_to_broker_is_phrase_negative():
    c = classify("how to broker freight")
    assert c.kind == "negative" and c.match_type == "phrase"


# ── Hard-exclude beats hiring intent (regression) ───────────────────────────
def test_competitor_with_intent_stays_negative():
    # hiring-intent word "application" must not rescue a competitor term
    c = classify("landstar owner operator application")
    assert c.kind == "negative" and c.reason == "competitor brand"


def test_wrong_vehicle_with_intent_stays_negative():
    c = classify("owner operator car haulers wanted")
    assert c.kind == "negative" and c.reason == "wrong vehicle"


# ── Good intent -> new keyword ──────────────────────────────────────────────
GOOD_INTENT = [
    ("apply to be a truck driver", "OTR Jobs"),
    ("owner operators needed", "Owner Operator Jobs"),
    ("cdl a owner operator application", "Owner Operator Jobs"),
    ("truck driver recruitment", "OTR Jobs"),
]


@pytest.mark.parametrize("term,ad_group", GOOD_INTENT)
def test_good_intent_keyword(term, ad_group):
    c = classify(term)
    assert c.kind == "keyword", f"{term!r} should be a keyword"
    assert c.ad_group == ad_group


# ── Brand ───────────────────────────────────────────────────────────────────
def test_brand_is_exact_keyword_flagged():
    c = classify("acme logistics")
    assert c.kind == "keyword"
    assert c.match_type == "exact"
    assert c.brand is True


# ── Ad-group routing ────────────────────────────────────────────────────────
def test_routing():
    assert route_ad_group("long haul owner operator") == "Owner Operator Jobs"
    assert route_ad_group("lease purchase truck") == "Owner Operator Jobs"
    assert route_ad_group("cdl a driver") == "CDL A Jobs"
    assert route_ad_group("otr semi driver") == "OTR Jobs"
