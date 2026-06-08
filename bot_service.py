"""Google Ads search-terms bot — long-running service.

Run:  python bot_service.py

Two concurrent jobs:
  1. Scheduler — fires twice a week, builds a proposal for the period since the
     last run, posts it to the Telegram chat.
  2. Poll loop — handles button taps: approve all / reject all / per-item select
     / apply selected. Applying writes to Google Ads (negatives + keywords).

Manual control in the chat:
  /run   — build & post a proposal right now
  /ping  — health check
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from apscheduler.schedulers.background import BackgroundScheduler

import config
from src import ads_client, ads_write, state, telegram_bot
from src.proposal import build_proposal, format_for_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("search-terms-bot")

SCHEDULE_TZ = config.SCHEDULE_TZ


# ── proposal generation ─────────────────────────────────────────────────────
def run_proposal() -> None:
    conn = state.connect()
    run_id = uuid.uuid4().hex[:12]

    end = ads_client.account_today()
    last = state.last_run_date(conn)
    start = last if last else end - dt.timedelta(days=config.LOOKBACK_DAYS)
    if start >= end:
        start = end - dt.timedelta(days=1)
    period = f"{start:%b %d} – {end:%b %d, %Y}"

    log.info("Run %s — pulling %s..%s", run_id, start, end)
    rows = ads_client.pull_search_terms(start=start, end=end)

    skip = state.processed_terms(conn)
    proposal = build_proposal(rows, period=period, skip_terms=skip)

    if not proposal.negatives and not proposal.new_keywords:
        telegram_bot.send_message(
            f"🔎 <b>{config.ACCOUNT_NAME}</b> — {period}\nNo new terms to review this period. ✅"
        )
        state.record_run(conn, run_id, period, 0, 0)
        state.finalize_run(conn, run_id, "empty", 0)
        return

    text = format_for_telegram(proposal)
    msg_id = telegram_bot.send_message(text, reply_markup=telegram_bot.proposal_keyboard())

    items = (
        [{"term": n["term"], "kind": "negative", "match_type": n["match_type"],
          "reason": n["reason"], "target": None} for n in proposal.negatives]
        + [{"term": k["term"], "kind": "keyword", "match_type": k["match_type"],
            "reason": "", "target": k["ad_group"]} for k in proposal.new_keywords]
    )
    state.record_run(conn, run_id, period, len(proposal.negatives), len(proposal.new_keywords))
    state.open_session(conn, run_id, config.TELEGRAM_CHAT_ID, msg_id, items, text)
    log.info("Run %s posted: %d neg, %d kw", run_id, len(proposal.negatives), len(proposal.new_keywords))


# ── apply helpers ───────────────────────────────────────────────────────────
def _split(items) -> tuple[list[dict], list[dict]]:
    negs = [{"term": it["term"], "match_type": it["match_type"], "reason": it["reason"]}
            for it in items if it["kind"] == "negative"]
    kws = [{"term": it["term"], "match_type": it["match_type"], "ad_group": it["target"]}
           for it in items if it["kind"] == "keyword"]
    return negs, kws


def _apply_and_record(conn, run_id, selected_items, all_items, decision) -> str:
    negs, kws = _split(selected_items)
    res = ads_write.apply_changes(negs, kws)

    # Mark every reviewed term processed so it never reappears.
    selected_terms = {it["term"].lower() for it in selected_items}
    for it in all_items:
        d = "applied" if it["term"].lower() in selected_terms else "rejected"
        state.mark_processed(conn, it["term"], it["kind"], d, run_id)
    for it in selected_items:
        state.record_applied(conn, run_id, it["term"], it["kind"],
                             it["match_type"], it["target"] or config.NEGATIVE_LIST_NAME)
    state.finalize_run(conn, run_id, decision, res.negatives_added + res.keywords_added)
    return res.summary()


# ── callback handling ───────────────────────────────────────────────────────
def _handle_callback(conn, cb) -> None:
    data = cb.get("data", "")
    cb_id = cb["id"]
    msg = cb.get("message") or {}
    message_id = msg.get("message_id")
    sess = state.get_session_by_message(conn, message_id)

    if data == "noop":
        telegram_bot.answer_callback(cb_id)
        return
    if not sess or sess["status"] != "open":
        telegram_bot.answer_callback(cb_id, "This proposal is closed.")
        return

    run_id = sess["run_id"]
    items = [dict(r) for r in state.session_items(conn, run_id)]

    if data == "approve_all":
        telegram_bot.answer_callback(cb_id, "Applying all…")
        summary = _apply_and_record(conn, run_id, items, items, "approve_all")
        state.close_session(conn, run_id)
        telegram_bot.edit_text(message_id, sess["proposal_text"] + f"\n\n✅ <b>APPROVED ALL</b> — {summary}")

    elif data == "reject_all":
        telegram_bot.answer_callback(cb_id, "Rejected.")
        for it in items:
            state.mark_processed(conn, it["term"], it["kind"], "rejected", run_id)
        state.finalize_run(conn, run_id, "reject_all", 0)
        state.close_session(conn, run_id)
        telegram_bot.edit_text(message_id, sess["proposal_text"] + "\n\n❌ <b>REJECTED ALL</b> — nothing written.")

    elif data == "select":
        telegram_bot.answer_callback(cb_id)
        _render_picker(conn, sess, message_id)

    elif data.startswith("tg:"):
        state.toggle_item(conn, run_id, int(data[3:]))
        telegram_bot.answer_callback(cb_id)
        _render_picker(conn, state.get_session(conn, run_id), message_id, edit_markup_only=True)

    elif data.startswith("pg:"):
        state.set_page(conn, run_id, int(data[3:]))
        telegram_bot.answer_callback(cb_id)
        _render_picker(conn, state.get_session(conn, run_id), message_id, edit_markup_only=True)

    elif data == "apply":
        telegram_bot.answer_callback(cb_id, "Applying selected…")
        selected = [it for it in items if it["selected"]]
        summary = _apply_and_record(conn, run_id, selected, items, "select")
        state.close_session(conn, run_id)
        telegram_bot.edit_text(
            message_id,
            sess["proposal_text"] + f"\n\n✔️ <b>APPLIED {len(selected)} SELECTED</b> — {summary}",
        )

    elif data == "cancel":
        telegram_bot.answer_callback(cb_id, "Back to summary.")
        telegram_bot.edit_text(message_id, sess["proposal_text"],
                               reply_markup=telegram_bot.proposal_keyboard())


def _picker_header(sess) -> str:
    return (sess["proposal_text"].split("\n")[0]
            + "\n<b>✏️ Select items to apply</b> — tap to toggle, then ✔️ Apply.")


def _render_picker(conn, sess, message_id, edit_markup_only: bool = False) -> None:
    run_id = sess["run_id"]
    items = [dict(r) for r in state.session_items(conn, run_id)]
    kb = telegram_bot.picker_keyboard(items, sess["page"])
    if edit_markup_only:
        telegram_bot.edit_markup(message_id, kb)
    else:
        telegram_bot.edit_text(message_id, _picker_header(sess), reply_markup=kb)


# ── poll loop ───────────────────────────────────────────────────────────────
def poll_loop() -> None:
    conn = state.connect()
    offset = None
    log.info("Poll loop started.")
    while True:
        try:
            for upd in telegram_bot.get_updates(offset, timeout=30):
                offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    _handle_callback(conn, upd["callback_query"])
                elif "message" in upd:
                    _handle_message(conn, upd["message"])
        except Exception:  # noqa: BLE001 — keep the loop alive
            log.exception("poll loop error")


def safe_run_proposal() -> None:
    """run_proposal wrapped with a Telegram alert on failure (auth/API/etc.)."""
    try:
        run_proposal()
    except Exception as e:  # noqa: BLE001
        log.exception("run_proposal failed")
        msg = str(e)
        auth = any(k in msg.upper() for k in ("AUTHENTICATION", "REFRESH", "INVALID_GRANT",
                                              "PERMISSION_DENIED", "UNAUTHENTICATED"))
        hint = ("\n🔑 Auth/refresh token problem — shared token, ALL bots affected!"
                if auth else "")
        telegram_bot.send_message(f"⚠️ <b>Run failed</b>\n<code>{msg[:300]}</code>{hint}")


def _handle_message(conn, message) -> None:
    text = (message.get("text") or "").strip()
    if text.startswith("/run"):
        telegram_bot.send_message("⏳ Building a proposal now…")
        safe_run_proposal()
    elif text.startswith("/ping"):
        telegram_bot.send_message("🟢 Bot is alive.")


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    state.connect()  # ensure schema
    scheduler = BackgroundScheduler(timezone=SCHEDULE_TZ)
    scheduler.add_job(safe_run_proposal, "cron", day_of_week=config.SCHEDULE_DAYS,
                      hour=config.SCHEDULE_HOUR, minute=config.SCHEDULE_MINUTE,
                      id="biweekly", misfire_grace_time=3600)
    scheduler.start()
    nxt = scheduler.get_job("biweekly").next_run_time
    log.info("Scheduler started. Next run: %s", nxt)
    telegram_bot.send_message(
        f"🟢 {config.ACCOUNT_NAME} search-terms bot online. Next run: "
        f"<b>{nxt:%a %d %b, %H:%M}</b> ({config.SCHEDULE_TZ}).\nSend /run to try now."
    )
    poll_loop()


if __name__ == "__main__":
    main()
