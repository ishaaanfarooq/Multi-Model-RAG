"""
One-time Gmail OAuth consent. Run from the `backend` directory:

    source venv/bin/activate
    python -m actions.authorize

Prerequisite: `credentials.json` (an OAuth *Desktop app* client, downloaded from
Google Cloud Console) must sit in this directory. This opens a browser, asks you to
grant access, and writes `token.json`, which the app then refreshes on its own.

Both files are gitignored — they are credentials, never commit them.
"""

import os
import sys

from actions.gmail_client import SCOPES

CREDENTIALS = "credentials.json"
TOKEN = "token.json"


def main():
    if not os.path.exists(CREDENTIALS):
        print(f"ERROR: '{CREDENTIALS}' not found in {os.getcwd()}\n")
        print("Get it from Google Cloud Console:")
        print("  1. https://console.cloud.google.com/  -> create/select a project")
        print("  2. APIs & Services -> Library -> enable 'Gmail API'")
        print("  3. APIs & Services -> OAuth consent screen -> External -> add yourself")
        print("     under 'Test users' (otherwise Google blocks the login)")
        print("  4. Credentials -> Create credentials -> OAuth client ID")
        print("     -> Application type: 'Desktop app'")
        print(f"  5. Download the JSON, save it here as {CREDENTIALS}")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN, "w") as f:
        f.write(creds.to_json())

    from actions.gmail_client import GmailClient

    client = GmailClient()
    if client.available:
        print(f"\nAuthorized. Gmail connected as: {client.email_address}")
        print(f"Token written to {TOKEN}. You can now send and read mail from the app.")
    else:
        print("\nToken written, but the client still could not connect. Check the logs.")


if __name__ == "__main__":
    main()
