"""
Google Calendar Integration for Marathon Scraper
=================================================
Authenticates with Google Calendar API v3 using OAuth 2.0 and
creates calendar events from the scraped marathon event data.

Prerequisites
-------------
1. A ``credentials.json`` file obtained from Google Cloud Console
   (see GOOGLE_CALENDAR_SETUP.md for step-by-step instructions).
2. Python packages:
       pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

Usage
-----
Programmatic:
    from calendar_integration import authenticate_google, add_marathon_to_calendar

    service = authenticate_google()          # opens browser on first run
    event_dict = {
        "event_name": "Kharghar Half Marathon",
        "date": "2026-04-05",
        "start_time": "5:30 AM",
        "location": "Navi Mumbai",
        "registration_link": "https://registrations.indiarunning.com/..."
    }
    link = add_marathon_to_calendar(service, event_dict)
    print(f"Created: {link}")

CLI (standalone test):
    python calendar_integration.py           # adds a sample event
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# If you modify SCOPES, delete token.json so the user can re-authorise.
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]

# Default paths – relative to this file's directory
_BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE: Path = _BASE_DIR / "credentials.json"
TOKEN_FILE: Path = _BASE_DIR / "token.json"

# Timezone for marathon events (IST)
EVENT_TIMEZONE = "Asia/Kolkata"

# Default event duration when only a start time is known (hours)
DEFAULT_EVENT_DURATION_HOURS = 4

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("calendar_integration")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate_google(
    credentials_path: str | Path = CREDENTIALS_FILE,
    token_path: str | Path = TOKEN_FILE,
) -> Any:
    """
    Authenticate with Google Calendar API v3 using OAuth 2.0.

    On the **first run** this opens a browser window asking the user to
    grant calendar access.  The resulting token is saved to ``token.json``
    so subsequent runs are non-interactive.

    Parameters
    ----------
    credentials_path : str | Path
        Path to the ``credentials.json`` downloaded from Google Cloud Console.
    token_path : str | Path
        Path where the refresh/access token will be cached.

    Returns
    -------
    googleapiclient.discovery.Resource
        An authorised Google Calendar API service object.

    Raises
    ------
    FileNotFoundError
        If ``credentials.json`` is missing.
    """
    credentials_path = Path(credentials_path)
    token_path = Path(token_path)

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"credentials.json not found at '{credentials_path}'.\n"
            "Please follow the instructions in GOOGLE_CALENDAR_SETUP.md to "
            "download it from the Google Cloud Console."
        )

    creds: Optional[Credentials] = None

    # ---- Load existing token if available --------------------------------
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            log.info("Loaded cached credentials from %s", token_path.name)
        except Exception as exc:
            log.warning("Could not load token.json (%s) – will re-authenticate.", exc)
            creds = None

    # ---- Refresh or create credentials -----------------------------------
    if creds and creds.valid:
        log.info("Credentials are valid.")
    elif creds and creds.expired and creds.refresh_token:
        log.info("Refreshing expired credentials …")
        try:
            creds.refresh(Request())
            log.info("Credentials refreshed successfully.")
        except Exception as exc:
            log.warning("Token refresh failed (%s) – re-authenticating.", exc)
            creds = None

    if not creds or not creds.valid:
        log.info("Starting OAuth 2.0 authorization flow …")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), SCOPES
        )
        creds = flow.run_local_server(
            port=0,              # pick any free port
            prompt="consent",    # always show consent screen
            access_type="offline",
        )
        log.info("Authorization successful.")

        # Save for next time
        token_path.write_text(creds.to_json(), encoding="utf-8")
        log.info("Token saved to %s", token_path.name)

    # ---- Build the API service -------------------------------------------
    service = build("calendar", "v3", credentials=creds)
    log.info("Google Calendar API service created.")
    return service


# ---------------------------------------------------------------------------
# Event creation helpers
# ---------------------------------------------------------------------------

def _parse_start_datetime(date_str: str | None, time_str: str | None) -> datetime:
    """
    Combine a date (``YYYY-MM-DD``) and an optional time (``5:30 AM``)
    into a single ``datetime``.  Falls back to 06:00 AM if time is missing.
    """
    if not date_str:
        raise ValueError("Event date is required but was None / empty.")

    dt = datetime.strptime(date_str, "%Y-%m-%d")

    if time_str:
        time_str = time_str.strip().upper()
        for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
            try:
                t = datetime.strptime(time_str, fmt)
                dt = dt.replace(hour=t.hour, minute=t.minute)
                return dt
            except ValueError:
                continue
        log.warning("Could not parse time '%s' – defaulting to 06:00 AM.", time_str)
        dt = dt.replace(hour=6, minute=0)
    else:
        # Sensible default for a marathon start
        dt = dt.replace(hour=6, minute=0)

    return dt


def _build_event_body(event_dict: dict) -> dict:
    """
    Transform a scraped event dictionary into a Google Calendar API event
    resource body.

    Expected keys in *event_dict*:
        event_name        – str
        date              – str  (YYYY-MM-DD)
        start_time        – str | None  (e.g. "5:30 AM")
        location          – str | None
        registration_link – str | None
    """
    start_dt = _parse_start_datetime(
        event_dict.get("date"), event_dict.get("start_time")
    )
    end_dt = start_dt + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)

    summary = event_dict.get("event_name", "Marathon Event")
    location = event_dict.get("location", "")
    reg_link = event_dict.get("registration_link", "")

    # Build a rich description
    description_parts: list[str] = []
    description_parts.append(f"🏃 {summary}")
    if location:
        description_parts.append(f"📍 Location: {location}")
    if event_dict.get("start_time"):
        description_parts.append(f"⏰ Start Time: {event_dict['start_time']}")
    if reg_link:
        description_parts.append(f"🔗 Registration: {reg_link}")
    description_parts.append("\n— Added automatically by Marathon Scraper 🤖")

    body: dict[str, Any] = {
        "summary": f"🏃 {summary}",
        "location": location,
        "description": "\n".join(description_parts),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": EVENT_TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": EVENT_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 1440},    # 1 day before
                {"method": "popup", "minutes": 120},     # 2 hours before
            ],
        },
        "source": {
            "title": "IndiaRunning.com",
            "url": reg_link or "https://www.indiarunning.com",
        },
    }

    # Colour-code: use a distinct event colour (banana = "5")
    body["colorId"] = "5"

    return body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_marathon_to_calendar(
    service: Any,
    event_dict: dict,
    calendar_id: str = "primary",
) -> str:
    """
    Create a single marathon event on Google Calendar.

    Parameters
    ----------
    service : googleapiclient.discovery.Resource
        Authorised Calendar API service (from ``authenticate_google()``).
    event_dict : dict
        Scraped event data with keys: ``event_name``, ``date``,
        ``start_time``, ``location``, ``registration_link``.
    calendar_id : str
        Which calendar to add the event to.  ``"primary"`` = the user's
        default calendar.

    Returns
    -------
    str
        The URL of the created Google Calendar event.

    Raises
    ------
    ValueError
        If required fields (event_name, date) are missing.
    HttpError
        If the Google API request fails.
    """
    if not event_dict.get("event_name"):
        raise ValueError("event_dict must contain a non-empty 'event_name'.")
    if not event_dict.get("date"):
        raise ValueError("event_dict must contain a non-empty 'date'.")

    body = _build_event_body(event_dict)

    try:
        created = (
            service.events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )
        html_link = created.get("htmlLink", "")
        log.info(
            "✔  Created: '%s' on %s → %s",
            event_dict["event_name"],
            event_dict["date"],
            html_link,
        )
        return html_link

    except HttpError as exc:
        log.error(
            "Google API error creating '%s': %s",
            event_dict["event_name"],
            exc,
        )
        raise


def add_all_marathons_to_calendar(
    service: Any,
    events: list[dict],
    calendar_id: str = "primary",
    skip_past: bool = True,
) -> list[dict]:
    """
    Batch-add multiple scraped events to Google Calendar.

    Parameters
    ----------
    service : googleapiclient.discovery.Resource
        Authorised Calendar API service.
    events : list[dict]
        List of scraped event dicts (same format as ``add_marathon_to_calendar``).
    calendar_id : str
        Target calendar ID.
    skip_past : bool
        If True, silently skip events whose date is in the past.

    Returns
    -------
    list[dict]
        A list of result dicts, one per event:
        ``{"event_name": str, "status": "created"|"skipped"|"error", "link": str|None, "reason": str|None}``
    """
    results: list[dict] = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for ev in events:
        name = ev.get("event_name", "Unknown")

        # Skip past events
        if skip_past and ev.get("date") and ev["date"] < today_str:
            log.info("⏭  Skipping past event: '%s' (%s)", name, ev["date"])
            results.append({
                "event_name": name,
                "status": "skipped",
                "link": None,
                "reason": f"Event date {ev['date']} is in the past",
            })
            continue

        # Skip events without a date
        if not ev.get("date"):
            log.warning("⏭  Skipping '%s' – no date available.", name)
            results.append({
                "event_name": name,
                "status": "skipped",
                "link": None,
                "reason": "No date available",
            })
            continue

        try:
            link = add_marathon_to_calendar(service, ev, calendar_id)
            results.append({
                "event_name": name,
                "status": "created",
                "link": link,
                "reason": None,
            })
        except (ValueError, HttpError) as exc:
            log.error("✖  Failed to add '%s': %s", name, exc)
            results.append({
                "event_name": name,
                "status": "error",
                "link": None,
                "reason": str(exc),
            })

    created = sum(1 for r in results if r["status"] == "created")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    log.info(
        "Batch complete: %d created, %d skipped, %d errors (of %d total).",
        created, skipped, errors, len(events),
    )
    return results


# ---------------------------------------------------------------------------
# CLI – standalone test
# ---------------------------------------------------------------------------

def main() -> None:
    """Quick test: authenticate and add a single sample event."""
    print("=" * 60)
    print("  Google Calendar Integration – Test Run")
    print("=" * 60)

    service = authenticate_google()

    sample_event = {
        "event_name": "Test Marathon – AI WebScraper",
        "date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "start_time": "6:00 AM",
        "location": "Navi Mumbai, Maharashtra",
        "registration_link": "https://www.indiarunning.com",
    }

    print(f"\nAdding sample event: {sample_event['event_name']}")
    print(f"  Date: {sample_event['date']}")
    print(f"  Time: {sample_event['start_time']}")
    print(f"  Location: {sample_event['location']}\n")

    link = add_marathon_to_calendar(service, sample_event)
    print(f"\n✅  Event created successfully!")
    print(f"    View it here: {link}\n")
    print("You can delete this test event from your Google Calendar.")
    print("=" * 60)


if __name__ == "__main__":
    main()
