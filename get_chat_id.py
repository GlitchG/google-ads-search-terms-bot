"""One-time helper: find your Telegram chat ID.

1. Open Telegram, find your bot, press Start, send any message.
2. Run:  python get_chat_id.py
3. Paste the printed ID into .env as TELEGRAM_CHAT_ID.
"""
import requests

import config


def main() -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    resp = requests.get(url, timeout=30).json()
    if not resp.get("ok"):
        print("Telegram API error:", resp)
        return
    results = resp.get("result", [])
    if not results:
        print("No messages yet. Send a message to the bot first, then re-run.")
        return
    seen = {}
    for upd in results:
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            seen[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name", "")
    print("Found chat(s):")
    for cid, name in seen.items():
        print(f"  TELEGRAM_CHAT_ID={cid}   ({name})")


if __name__ == "__main__":
    main()
