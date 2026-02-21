"""
Marathon → Google Calendar  —  Main Pipeline
=============================================
Ties together the web scraper (marathon_scraper.py) and the
Google Calendar integration (calendar_integration.py) into a
single end-to-end workflow:

    1. Scrape upcoming running events near Navi Mumbai
    2. Authenticate with Google Calendar
    3. For each event, check if it already exists on the calendar
    4. Add only new events; skip duplicates
    5. Print a clean summary

Usage
-----
    python main.py                 # default: headless, visits detail pages
    python main.py --fast          # skip detail-page scraping (faster)
    python main.py --headed        # show the browser while scraping
    python main.py --dry-run       # scrape only – don't touch the calendar
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Any

from googleapiclient.errors import HttpError

from marathon_scraper import scrape_events
from calendar_integration import (
    authenticate_google,
    add_marathon_to_calendar,
    EVENT_TIMEZONE,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _event_already_exists(
    service: Any,
    event_name: str,
    event_date: str,
    calendar_id: str = "primary",
) -> bool:
    """
    Query Google Calendar to check whether an event with a matching name
    already exists on the given date.

    We search a 24-hour window around ``event_date`` and compare summaries
    case-insensitively.  This catches events that were previously added by
    this script (or manually) and prevents duplicates.

    Parameters
    ----------
    service : googleapiclient.discovery.Resource
        Authorised Calendar API service.
    event_name : str
        The event name to look for (matched case-insensitively).
    event_date : str
        ISO date string ``YYYY-MM-DD``.
    calendar_id : str
        Calendar to search in.

    Returns
    -------
    bool
        True if a matching event already exists.
    """
    try:
        dt = datetime.strptime(event_date, "%Y-%m-%d")
        time_min = dt.isoformat() + "T00:00:00+05:30"   # IST start of day
        time_max = (dt + timedelta(days=1)).isoformat() + "T00:00:00+05:30"

        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                q=event_name,           # free-text search narrows results
                maxResults=50,
            )
            .execute()
        )

        existing_events = result.get("items", [])
        target = event_name.strip().lower()

        for item in existing_events:
            summary = (item.get("summary") or "").strip().lower()
            # Match the exact name or the name with our 🏃 prefix
            if target in summary or summary in target:
                log.info(
                    "  ↳ Duplicate found: '%s' on %s – skipping.",
                    item.get("summary"),
                    event_date,
                )
                return True

        return False

    except HttpError as exc:
        log.warning(
            "  ↳ Could not check for duplicates (%s) – will attempt to add.",
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    headless: bool = True,
    fast: bool = False,
    dry_run: bool = False,
    calendar_id: str = "primary",
) -> None:
    """
    End-to-end: scrape → de-duplicate → add to Google Calendar → summarise.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── Step 1: Scrape events ─────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  🏃  Marathon Event Scraper → Google Calendar Pipeline")
    print("=" * 70)
    print()
    print("▸ Step 1/4 — Scraping upcoming events near Navi Mumbai …")
    print()

    events = scrape_events(headless=headless, visit_details=not fast)

    if not events:
        print("\n  ⚠  No events found. The website may be down or the")
        print("     page structure may have changed.\n")
        return

    # Filter out past events
    upcoming = [
        ev for ev in events
        if ev.get("date") and ev["date"] >= today_str
    ]
    past_count = len(events) - len(upcoming)

    print(f"\n  ✔  Scraped {len(events)} event(s), {len(upcoming)} upcoming"
          f"{f', {past_count} past (skipped)' if past_count else ''}.\n")

    if not upcoming:
        print("  ⚠  No upcoming events to add.\n")
        return

    # ── Show what was found ───────────────────────────────────────────────
    print("-" * 70)
    print(f"  {'#':<4} {'Date':<13} {'Event Name':<45} {'City'}")
    print("-" * 70)
    for i, ev in enumerate(upcoming, 1):
        name = ev["event_name"][:43]
        loc = (ev.get("location") or "N/A")[:20]
        print(f"  {i:<4} {ev['date']:<13} {name:<45} {loc}")
    print("-" * 70)
    print()

    if dry_run:
        print("  ℹ  --dry-run flag set. Skipping calendar integration.\n")
        return

    # ── Step 2: Authenticate ──────────────────────────────────────────────
    print("▸ Step 2/4 — Authenticating with Google Calendar …\n")

    try:
        service = authenticate_google()
    except FileNotFoundError as exc:
        print(f"\n  ✖  {exc}\n")
        return
    except Exception as exc:
        print(f"\n  ✖  Authentication failed: {exc}\n")
        return

    print()

    # ── Step 3: De-duplicate and add ──────────────────────────────────────
    print("▸ Step 3/4 — Checking for duplicates & adding new events …\n")

    results: list[dict] = []

    for ev in upcoming:
        name = ev["event_name"]
        date = ev["date"]
        status = "unknown"
        link = None
        reason = None

        print(f"  [{date}]  {name}")

        # Check for duplicate
        if _event_already_exists(service, name, date, calendar_id):
            status = "duplicate"
            reason = "Already on calendar"
            print(f"           → ⏭  Skipped (already exists)\n")
        else:
            # Add to calendar
            try:
                link = add_marathon_to_calendar(service, ev, calendar_id)
                status = "created"
                print(f"           → ✅  Added to calendar\n")
            except (ValueError, HttpError) as exc:
                status = "error"
                reason = str(exc)
                print(f"           → ✖  Error: {exc}\n")

        results.append({
            "event_name": name,
            "date": date,
            "location": ev.get("location", ""),
            "start_time": ev.get("start_time"),
            "status": status,
            "link": link,
            "reason": reason,
        })

    # ── Step 4: Summary ──────────────────────────────────────────────────
    created  = [r for r in results if r["status"] == "created"]
    dupes    = [r for r in results if r["status"] == "duplicate"]
    errors   = [r for r in results if r["status"] == "error"]

    print()
    print("=" * 70)
    print("  📋  Summary")
    print("=" * 70)
    print()
    print(f"    Total upcoming events scraped : {len(upcoming)}")
    print(f"    ✅  Added to calendar          : {len(created)}")
    print(f"    ⏭   Already existed (skipped)  : {len(dupes)}")
    print(f"    ✖   Errors                     : {len(errors)}")
    print()

    if created:
        print("  ── New events added ──────────────────────────────────────")
        for r in created:
            time_str = r["start_time"] or "TBA"
            loc = r["location"][:35] if r["location"] else "N/A"
            print(f"    🏃 {r['event_name']}")
            print(f"       📅 {r['date']}  ⏰ {time_str}  📍 {loc}")
            if r["link"]:
                print(f"       🔗 {r['link']}")
            print()

    if dupes:
        print("  ── Skipped (duplicates) ──────────────────────────────────")
        for r in dupes:
            print(f"    ⏭  {r['event_name']}  ({r['date']})")
        print()

    if errors:
        print("  ── Errors ────────────────────────────────────────────────")
        for r in errors:
            print(f"    ✖  {r['event_name']}  ({r['date']})")
            print(f"       Reason: {r['reason']}")
        print()

    print("=" * 70)
    print("  Done! Open Google Calendar to see your marathon events. 🎉")
    print("=" * 70)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape marathon events near Navi Mumbai and add them to Google Calendar.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip visiting individual event pages (faster but no start-time data).",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window while scraping (useful for debugging).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape events and display them, but do NOT add to Google Calendar.",
    )
    parser.add_argument(
        "--calendar-id",
        default="primary",
        help="Google Calendar ID to add events to (default: 'primary').",
    )
    args = parser.parse_args()

    run_pipeline(
        headless=not args.headed,
        fast=args.fast,
        dry_run=args.dry_run,
        calendar_id=args.calendar_id,
    )


if __name__ == "__main__":
    main()
