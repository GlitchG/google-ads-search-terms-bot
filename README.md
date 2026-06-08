# Google Ads Search-Terms Bot

A self-hosted **Telegram bot** that reviews your Google Ads search terms twice a
week, proposes **negative keywords** (to stop wasted spend) and **new keywords**
(to capture missed intent), and writes the approved ones to your account — all
from a chat, **one tap at a time**.

> Search-terms report → classified by your rules → proposal in Telegram →
> approve all / reject all / pick item-by-item → applied to the account.
> **Nothing is written without an explicit approval tap.**

```
🔎 Account — Search Terms Review
Jun 02 – Jun 05

📊 Clicks: 287  ·  Cost: $412
📝 Form opens: 41  ·  ✅ Real submits: 6

➖ Negatives (23)
  • competitor brand — broad — competitor
  • "free course" — phrase — informational / non-buyer
➕ New keywords (4)
  • online application — phrase → Applications

[✅ Approve all]   [✏️ Select items]   [❌ Reject all]
```

## Why it's not a dumb keyword dumper

Hand-managing the search-terms report is slow and error-prone; naive automation
makes expensive mistakes. This bot encodes the judgment:

- **False-positive guards win over everything.** Your best-converting terms are
  protected — they're never added as negatives, even if they look like junk.
- **Hard-excludes beat intent.** A competitor or wrong-product term isn't rescued
  by a stray "apply" / "buy" word.
- **Plural-tolerant, word-boundary matching.** Catches `car haulers` from
  `car hauler`, never blocks a bare word that would clip a real keyword.
- **Broad vs phrase match types** chosen per rule, so a negative can't quietly
  nuke a profitable query.
- **Idempotent + deduped.** Existing list entries are skipped; once you review a
  term it never comes back.
- **Human-in-the-loop.** Approve everything, reject everything, or page through and
  pick individual items. Self-alerts to Telegram on API/auth failures.

## Does it use AI?

**No LLM at runtime.** The bot is deterministic Python — it queries the Google Ads
API and classifies terms with fixed, auditable rules you control in `src/rules.py`.
No model decides what to add or block. Fully standalone — no external agent or
service required.

## How it works

```
[twice-weekly schedule] ─▶ pull search-terms report (since last run)
                       ─▶ classify each term (your rules: negative / keyword / keep)
                       ─▶ post proposal to Telegram with buttons
                       ─▶ on approval: write negatives → shared list, keywords → ad group
                       ─▶ SQLite: dedup + full audit log
```

---

## Quick start

```bash
git clone https://github.com/GlitchG/google-ads-search-terms-bot
cd google-ads-search-terms-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill it in (see below)
python get_refresh_token.py   # one-time OAuth → writes refresh token to .env
python get_chat_id.py         # prints your Telegram chat ID → put in .env
# edit src/rules.py for your vertical (it ships with a worked example)

pytest -q                     # the guard tests are your safety net
python main.py --dry-sample   # offline: see a proposal with no API/Telegram
python bot_service.py         # run it; send /run or /ping in your chat
```

## Getting Google Ads API access

You need a **developer token**, an **OAuth client**, a **refresh token**, and your
**account IDs**. Full step-by-step including the access *application* (what to write
so it gets approved): **[docs/GOOGLE_ADS_API_ACCESS.md](docs/GOOGLE_ADS_API_ACCESS.md)**.

1. **Developer token** — in your **Manager (MCC) account**: *Tools & Settings →
   API Center*. New tokens may need a short Basic Access application.
2. **OAuth client** — [Google Cloud Console](https://console.cloud.google.com):
   create a project → enable **Google Ads API** → *OAuth consent screen* (External,
   add yourself as a **Test user**) → *Credentials → OAuth client ID → Desktop app*.
   This gives `GOOGLE_ADS_CLIENT_ID` and `GOOGLE_ADS_CLIENT_SECRET`.
3. **Refresh token** — `python get_refresh_token.py`, approve in the browser; it
   writes `GOOGLE_ADS_REFRESH_TOKEN` to `.env`.
4. **Account IDs** — `GOOGLE_ADS_LOGIN_CUSTOMER_ID` = MCC; `GOOGLE_ADS_CUSTOMER_ID`
   = the client account (digits only, no dashes).

Plus a **shared negative keyword list** in the account (its `sharedSetId` goes in
`.env`) and your **ad-group names** for routing new keywords.

## Telegram setup

1. **@BotFather** → `/newbot` → token into `TELEGRAM_BOT_TOKEN`.
2. Create a chat/group, add the bot, send a message, run `python get_chat_id.py`,
   put the ID (negative for groups) into `TELEGRAM_CHAT_ID`.

## Adapting the rules (`src/rules.py`)

This is the only file with real per-account logic. It ships with a worked example
(driver recruitment) to show the engine handling real nuance. For your account,
edit:

- **Guards** — terms to always protect (your converters / brand-adjacent)
- **Negatives** — junk lists by reason (competitors, wrong product, informational,
  foreign language…) with a default match type
- **Good-intent** — signals that mean a real buyer/applicant → new keyword
- **Routing** — which ad group a new keyword goes to

Classification priority: **guards → brand → negatives → good-intent → neutral.**
Add your account's must-never-negate terms to `tests/test_rules.py` and keep
`pytest` green before going live.

## Commands

- `/run` — build & post a proposal now
- `/ping` — health check

## Deployment

```bash
sudo cp google-ads-search-terms-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now google-ads-search-terms-bot
```

## Project structure

```
config.py             settings (.env) + Google Ads client config
bot_service.py        scheduler + Telegram loop + approval handling
src/ads_client.py     read: search-terms report, ad groups, existing criteria
src/rules.py          classification rules + false-positive guards  ← edit this
src/proposal.py       builds the proposal + Telegram formatting
src/ads_write.py      write: negatives → shared list, keywords → ad group (idempotent)
src/telegram_bot.py   Telegram API + inline keyboards (per-item picker)
src/state.py          SQLite dedup + audit log
tests/test_rules.py   guard + classification tests
```

## Safety

- Writes only after an explicit Telegram tap.
- Idempotent: re-runs never create duplicate negatives/keywords.
- Full SQLite audit log of proposals and decisions.
- Note: Google Ads **Change history does not show negative-list changes** — verify
  in *Shared library → Negative keyword lists*.

## Tech

Python · [google-ads](https://pypi.org/project/google-ads/) · APScheduler ·
Telegram Bot API · SQLite.

## License

MIT — see [LICENSE](LICENSE).
