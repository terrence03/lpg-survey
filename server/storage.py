"""Append rows to Google Sheets, falling back to local CSV like the original app."""

import csv
import json
import logging
import os
import threading
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

log = logging.getLogger("storage")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
_lock = threading.Lock()
_session: AuthorizedSession | None = None


def get_timestamp() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def _load_secrets() -> dict:
    """Read the old .streamlit/secrets.toml format if present, else env vars."""
    path = Path(os.environ.get("SECRETS_FILE", ".streamlit/secrets.toml"))
    if path.is_file():
        with path.open("rb") as f:
            return tomllib.load(f)
    s: dict = {"spreadsheet": {
        "check_in": os.environ.get("SPREADSHEET_CHECKIN", ""),
        "response": os.environ.get("SPREADSHEET_RESPONSE", ""),
    }}
    if os.environ.get("GCP_SERVICE_ACCOUNT_JSON"):
        s["gcp_service_account"] = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
    return s


SECRETS = _load_secrets()


def _get_session() -> AuthorizedSession:
    global _session
    if _session is None:
        info = SECRETS.get("gcp_service_account")
        if info:
            creds = service_account.Credentials.from_service_account_info(dict(info), scopes=SCOPES)
        else:  # e.g. Cloud Run with an attached service account
            creds, _ = google.auth.default(scopes=SCOPES)
        _session = AuthorizedSession(creds)
    return _session


def _append_sheet(spreadsheet_id: str, rows: list) -> None:
    if not spreadsheet_id:
        raise RuntimeError("spreadsheet id not configured")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/A1:append"
    r = _get_session().post(
        url,
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": rows},
        timeout=15,
    )
    r.raise_for_status()
    log.info("%s cells appended", r.json().get("updates", {}).get("updatedCells"))


def _write_csv(name: str, headers: list, rows: list) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    with _lock:
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(headers)
            w.writerows(rows)


def append(kind: str, headers: list, rows: list) -> str:
    """kind is 'check_in' or 'response'. Returns 'sheets' or 'csv'."""
    try:
        _append_sheet(SECRETS["spreadsheet"].get(kind, ""), rows)
        return "sheets"
    except Exception as e:  # noqa: BLE001 - any failure falls back to CSV
        # Also log the rows: on Cloud Run the CSV disk is temporary, but logs are kept.
        log.warning("Sheets append failed (%s); writing %s to CSV: %s", e, kind, json.dumps(rows, ensure_ascii=False))
        _write_csv("checkin.csv" if kind == "check_in" else "survey.csv", headers, rows)
        return "csv"
