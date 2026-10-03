"""
ONE-TIME Gmail login. Run this on your own computer (it opens a browser):

    cd backend
    python scripts/gmail_auth.py

It reads `credentials.json` (downloaded from Google Cloud Console) and writes
`token.json`. Both files are git-ignored - never commit them.

For Render, copy the printed single-line JSON into the GOOGLE_TOKEN_JSON
environment variable (or upload token.json as a Render Secret File).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from config.settings import settings  # noqa: E402
from services.gmail_service import SCOPES  # noqa: E402


def main() -> int:
    credentials_file = Path(settings.GOOGLE_CREDENTIALS_FILE)
    if not credentials_file.is_file():
        print(f"ERROR: credentials file not found: {credentials_file}")
        print("Download an OAuth 'Desktop app' client from Google Cloud Console")
        print("(APIs & Services > Credentials) and save it as backend/credentials.json")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    creds = flow.run_local_server(port=0)

    token_file = Path(settings.GOOGLE_TOKEN_FILE)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())

    print(f"\nSaved token to {token_file}")
    print("\nFor Render, set this environment variable (keep it secret!):\n")
    print("GOOGLE_TOKEN_JSON=" + json.dumps(json.loads(creds.to_json())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
