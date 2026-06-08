# Getting Google Ads API Access (step by step)

To run this bot you need a **developer token** with at least **Basic Access**, an
**OAuth client**, a **refresh token**, and your **account IDs**. This is the part
that trips people up, so here's the whole path including the access *application*.

---

## 0. What you'll end up with

| Value | Where it comes from |
|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | your Manager (MCC) account → API Center |
| `GOOGLE_ADS_CLIENT_ID` / `GOOGLE_ADS_CLIENT_SECRET` | Google Cloud OAuth client (Desktop app) |
| `GOOGLE_ADS_REFRESH_TOKEN` | one-time browser consent (`get_refresh_token.py`) |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | your MCC ID (digits, no dashes) |
| `GOOGLE_ADS_CUSTOMER_ID` | the account you manage (digits, no dashes) |

---

## 1. Create a Manager (MCC) account

The developer token lives on a **Manager account**, not a regular one.

1. Go to [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts) and create one (free).
2. **Link the account(s) you want to manage** to this MCC (Sub-account settings →
   Link existing account → the client accepts).

## 2. Apply for a developer token (the application)

1. In the **MCC**, open **Tools & Settings → Setup → API Center**
   (API Center only appears on Manager accounts).
2. You'll see a developer token immediately, but it starts at **Test Access**
   (works only against test accounts). Apply for **Basic Access** to use it on real
   accounts.
3. Fill in the API access application. Google reviews it and often replies by email
   asking you to **clarify your business model and why you need the API**. Answer
   plainly and specifically — vague answers get rejected. What they want to see:

   - **What your business actually does** and who the end users are.
   - **Why the API is necessary** (which services/reports, and what it replaces).
   - **Read vs write**, and that any changes are gated behind human approval.
   - Rough **API call volume** vs the limit.

   A truthful template that mirrors this bot:

   > *We run paid-search optimization for our own / our clients' Google Ads
   > accounts. The API pulls reporting (campaigns, search terms, metrics) on a
   > schedule so we can analyze wasted spend and budget pacing, and — only after a
   > human approves each change in our internal tool — apply budget and
   > negative-keyword updates. It replaces hours of manual CSV exports per account.
   > Read-only by default; mutations are explicit and rare. Expected usage is a few
   > hundred operations per account per month, far below the 15,000/day Basic
   > limit. Access is used only by us, on our own infrastructure, for accounts we
   > manage with the owner's consent.*

4. **Access levels & limits:**
   - **Test** — only test accounts. **Basic** — 15,000 operations/day (plenty here).
     **Standard** — higher limits; don't apply unless you actually exceed Basic.

## 3. Create the OAuth client (Google Cloud)

1. [console.cloud.google.com](https://console.cloud.google.com) → create/select a project.
2. **APIs & Services → Library** → enable **Google Ads API**.
3. **APIs & Services → OAuth consent screen** → User type **External** → fill the
   basics → **Add yourself under "Test users"**. (While the screen is in *Testing*,
   only listed test users can authorize — otherwise you get `access_denied`.)
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Application type: Desktop app.** Download the JSON — it contains your
   `client_id` and `client_secret`.

## 4. Generate the refresh token

```bash
python get_refresh_token.py
```

It opens a browser. Approve with the Google account that has access to the MCC. If
you see **"Google hasn't verified this app"**, that's expected in Testing mode →
*Advanced → Go to … (unsafe)*. On success the refresh token is written to `.env`.

## 5. Account IDs

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` = the **MCC** ID, digits only (e.g. `123-456-7890`
  → `1234567890`).
- `GOOGLE_ADS_CUSTOMER_ID` = the **managed account** ID, digits only.
  ⚠️ This is the 10-digit ID shown top-right in the account — **not** the `ocid=`
  number in Google Ads UI URLs.

---

## Common pitfalls

- **`access_denied` on consent** → your Google account isn't a Test user on the
  consent screen. Add it.
- **`DEVELOPER_TOKEN_NOT_APPROVED`** → still on Test Access; finish the Basic Access
  application.
- **`USER_PERMISSION_DENIED`** → the authorizing account doesn't have access to that
  customer ID under the MCC.
- **Token works in the API but Change history shows nothing** → negative-keyword and
  shared-set changes aren't logged in Change history; verify in *Shared library*.

## References

- Google Ads API — [Get Started](https://developers.google.com/google-ads/api/docs/get-started/introduction)
- [Developer token / access levels](https://developers.google.com/google-ads/api/docs/access-levels)
- [OAuth desktop app flow](https://developers.google.com/google-ads/api/docs/oauth/installed-app)
