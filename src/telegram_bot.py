"""Component 4 — Telegram interface.

Thin wrapper over the Bot API (sync, requests-based) plus the inline-keyboard
builders for the proposal and the per-item picker. The orchestration (reacting
to taps, applying changes, dedup) lives in bot_service.py.
"""
from __future__ import annotations

import requests

import config

API = "https://api.telegram.org/bot{token}/{method}"
PER_PAGE = 8
_MAX_BTN = 32


def _call(method: str, **params) -> dict:
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    resp = requests.post(url, json=params, timeout=40).json()
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {resp}")
    return resp.get("result", {})


# ── low-level ───────────────────────────────────────────────────────────────
def send_message(text: str, reply_markup: dict | None = None,
                 chat_id: str | None = None) -> int:
    res = _call(
        "sendMessage",
        chat_id=chat_id or config.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        **({"reply_markup": reply_markup} if reply_markup else {}),
    )
    return res["message_id"]


def edit_text(message_id: int, text: str, reply_markup: dict | None = None) -> None:
    _call(
        "editMessageText",
        chat_id=config.TELEGRAM_CHAT_ID,
        message_id=message_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        **({"reply_markup": reply_markup} if reply_markup else {"reply_markup": {"inline_keyboard": []}}),
    )


def edit_markup(message_id: int, reply_markup: dict) -> None:
    _call("editMessageReplyMarkup", chat_id=config.TELEGRAM_CHAT_ID,
          message_id=message_id, reply_markup=reply_markup)


def answer_callback(callback_id: str, text: str = "") -> None:
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except RuntimeError:
        pass


def get_updates(offset: int | None, timeout: int = 30) -> list[dict]:
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method="getUpdates")
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return requests.get(url, params=params, timeout=timeout + 10).json().get("result", [])


# ── keyboards ───────────────────────────────────────────────────────────────
def proposal_keyboard() -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Approve all", "callback_data": "approve_all"},
        {"text": "✏️ Select items", "callback_data": "select"},
        {"text": "❌ Reject all", "callback_data": "reject_all"},
    ]]}


def _trim(s: str, n: int = _MAX_BTN) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def picker_keyboard(items: list, page: int) -> dict:
    """items: rows with .idx, .term, .kind, .selected. Paginated toggles."""
    pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, pages - 1))
    start = page * PER_PAGE
    rows = []
    for it in items[start:start + PER_PAGE]:
        mark = "✅" if it["selected"] else "⬜"
        tag = "neg" if it["kind"] == "negative" else "kw"
        rows.append([{
            "text": _trim(f"{mark} {it['term']} ({tag})"),
            "callback_data": f"tg:{it['idx']}",
        }])

    nav = []
    if page > 0:
        nav.append({"text": "◀", "callback_data": f"pg:{page - 1}"})
    nav.append({"text": f"{page + 1}/{pages}", "callback_data": "noop"})
    if page < pages - 1:
        nav.append({"text": "▶", "callback_data": f"pg:{page + 1}"})
    rows.append(nav)

    n_sel = sum(1 for it in items if it["selected"])
    rows.append([
        {"text": f"✔️ Apply ({n_sel})", "callback_data": "apply"},
        {"text": "✖️ Cancel", "callback_data": "cancel"},
    ])
    return {"inline_keyboard": rows}
