"""One-time helper: generate a Google Ads API refresh token via OAuth.

Run once:  python get_refresh_token.py
It opens a browser; sign in with the Google account that has access to your
Google Ads manager (MCC). On success it writes GOOGLE_ADS_REFRESH_TOKEN into .env.

NOTE: while your OAuth consent screen is in "Testing" mode, the Google account you
approve with must be added as a Test User on that consent screen.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

ENV = Path(__file__).parent / ".env"
load_dotenv(ENV)
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def _write_env(token: str) -> None:
    lines, found = [], False
    for line in ENV.read_text().splitlines():
        if line.startswith("GOOGLE_ADS_REFRESH_TOKEN="):
            lines.append(f"GOOGLE_ADS_REFRESH_TOKEN={token}")
            found = True
        else:
            lines.append(line)
    if not found:
        lines.append(f"GOOGLE_ADS_REFRESH_TOKEN={token}")
    ENV.write_text("\n".join(lines) + "\n")


def main() -> None:
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit("Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env first.")

    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }},
        SCOPES,
    )
    creds = flow.run_local_server(port=0, prompt="consent")
    if not creds.refresh_token:
        raise SystemExit("No refresh token returned — re-run and fully approve the consent screen.")
    _write_env(creds.refresh_token)
    print("\n✅ Success — GOOGLE_ADS_REFRESH_TOKEN written to .env")


if __name__ == "__main__":
    main()
