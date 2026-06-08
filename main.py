"""Orchestrator for one run (steps 1-3, dry-run — NO writes to Google Ads).

Flow:
    1. Pull the search terms report (Component 1)
    2. Classify + build a proposal (Components 2-3)
    3. Send to Telegram, capture approve/reject (Component 4)
    4. Log the decision. (Write path = Component 5, added later.)

Usage:
    python main.py                # live: pull from API + send to Telegram
    python main.py --dry-sample   # offline: use sample rows, print proposal only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import config
from src.proposal import SearchTermRow, build_proposal, format_for_telegram

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _period_label(days: int) -> str:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    return f"{start:%b %d} – {today:%b %d, %Y}"


def _sample_rows() -> list[SearchTermRow]:
    """A few hand-picked rows incl. the guard cases, for offline verification."""
    return [
        SearchTermRow("landstar owner operator", clicks=3, cost_micros=4_200_000),
        SearchTermRow("dry van owner operator", clicks=5, cost_micros=7_600_000,
                      conversions=1, conversion_action_name="Submit lead form"),
        SearchTermRow("driver work", clicks=40, cost_micros=12_000_000),
        SearchTermRow("how to start a trucking business", clicks=2, cost_micros=1_500_000),
        SearchTermRow("cdl a owner operator application", clicks=1, cost_micros=900_000),
        SearchTermRow("box truck driver near me", clicks=4, cost_micros=2_100_000),
        SearchTermRow("find loads for owner operator", clicks=1, cost_micros=500_000),
    ]


def run(dry_sample: bool = False) -> None:
    period = _period_label(config.LOOKBACK_DAYS)

    if dry_sample:
        rows = _sample_rows()
    else:
        from src import ads_client
        print(f"Pulling search terms (last ~{config.LOOKBACK_DAYS} days)…")
        rows = ads_client.pull_search_terms()
        print(f"  {len(rows)} rows.")

    proposal = build_proposal(rows, period=period)

    # Persist the proposal for the audit trail.
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DATA_DIR / f"proposal_{stamp}.json"
    out.write_text(json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False))
    print(f"Proposal saved → {out}")

    msg = format_for_telegram(proposal)

    if dry_sample:
        print("\n" + "─" * 60)
        print(msg.replace("<b>", "").replace("</b>", "")
                 .replace("<i>", "").replace("</i>", "")
                 .replace("<code>", "").replace("</code>", ""))
        print("─" * 60)
        return

    from src import telegram_bot
    print("Sending proposal to Telegram…")
    message_id = telegram_bot.send_proposal(msg)
    print("Waiting for approval… (dry-run — nothing will be written)")
    result = telegram_bot.wait_for_decision(message_id)
    print(f"Decision: {result.decision}")

    # Log the decision alongside the proposal.
    log = DATA_DIR / f"decision_{stamp}.json"
    log.write_text(json.dumps(
        {"period": period, "decision": result.decision,
         "negatives": len(proposal.negatives),
         "new_keywords": len(proposal.new_keywords)},
        indent=2,
    ))
    print(f"Decision logged → {log}")
    print("NOTE: write path not wired yet — no changes were made to Google Ads.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-sample", action="store_true",
                    help="Use built-in sample rows, print proposal, no API/Telegram.")
    args = ap.parse_args()
    run(dry_sample=args.dry_sample)
