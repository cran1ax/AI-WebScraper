"""
Marathon Scraper — FastAPI REST API
====================================
Wraps the scraping + Google Calendar pipeline into a single
``POST /sync-marathons`` endpoint.

Run locally:
    uvicorn app:app --reload --port 8000

Then hit the endpoint:
    curl -X POST http://localhost:8000/sync-marathons
    curl -X POST "http://localhost:8000/sync-marathons?fast=true&dry_run=true"

Interactive docs:
    http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from googleapiclient.errors import HttpError

from marathon_scraper import scrape_events
from calendar_integration import (
    authenticate_google,
    add_marathon_to_calendar,
    EVENT_TIMEZONE,
)

# Re-use the duplicate-checker from main.py
from main import _event_already_exists

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class EventStatus(str, Enum):
    created = "created"
    duplicate = "duplicate"
    skipped = "skipped"
    error = "error"


class EventResult(BaseModel):
    event_name: str
    date: Optional[str] = None
    start_time: Optional[str] = None
    location: Optional[str] = None
    registration_link: Optional[str] = None
    status: EventStatus
    calendar_link: Optional[str] = None
    reason: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    message: str
    duration_seconds: float
    total_scraped: int
    total_upcoming: int
    added: int
    duplicates: int
    skipped: int
    errors: int
    events: list[EventResult]


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="🏃 Marathon Scraper API",
    description=(
        "Scrapes upcoming marathon events near Navi Mumbai from IndiaRunning.com "
        "and syncs them to Google Calendar."
    ),
    version="1.0.0",
)


@app.get("/", tags=["Health"])
async def health_check():
    """Health check — verify the API is running."""
    return {
        "status": "ok",
        "service": "Marathon Scraper API",
        "timestamp": datetime.now().isoformat(),
    }


@app.post(
    "/sync-marathons",
    response_model=SyncResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Sync"],
    summary="Scrape marathon events and sync to Google Calendar",
)
async def sync_marathons(
    fast: bool = Query(
        False,
        description="Skip detail-page visits (faster but no start-time data).",
    ),
    dry_run: bool = Query(
        False,
        description="Scrape only — do not authenticate or modify Google Calendar.",
    ),
    calendar_id: str = Query(
        "primary",
        description="Google Calendar ID to add events to.",
    ),
) -> SyncResponse:
    """
    **POST /sync-marathons**

    Triggers the full pipeline:

    1. Scrapes upcoming running events near Navi Mumbai from IndiaRunning.com
    2. Authenticates with Google Calendar (requires `token.json` / `credentials.json`)
    3. Checks each event for duplicates on the calendar
    4. Adds only new events
    5. Returns a JSON summary

    **Query parameters:**
    - `fast=true` — skip individual event pages (3× faster, no start times)
    - `dry_run=true` — scrape only, don't touch the calendar
    - `calendar_id=<id>` — target a specific Google Calendar
    """
    start_time = time.time()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ── Step 1: Scrape ────────────────────────────────────────────────────
    log.info("API: Starting scrape (fast=%s) …", fast)
    try:
        all_events = scrape_events(headless=True, visit_details=not fast)
    except Exception as exc:
        log.exception("Scraping failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {exc}",
        )

    if not all_events:
        elapsed = round(time.time() - start_time, 2)
        return SyncResponse(
            success=True,
            message="No events found. The website may be down or the page structure changed.",
            duration_seconds=elapsed,
            total_scraped=0,
            total_upcoming=0,
            added=0,
            duplicates=0,
            skipped=0,
            errors=0,
            events=[],
        )

    # Filter to upcoming only
    upcoming = [ev for ev in all_events if ev.get("date") and ev["date"] >= today_str]
    past_skipped = len(all_events) - len(upcoming)

    log.info("Scraped %d events, %d upcoming, %d past.", len(all_events), len(upcoming), past_skipped)

    # ── Dry-run: return scraped data without calendar ops ─────────────────
    if dry_run:
        elapsed = round(time.time() - start_time, 2)
        event_results = [
            EventResult(
                event_name=ev.get("event_name", "Unknown"),
                date=ev.get("date"),
                start_time=ev.get("start_time"),
                location=ev.get("location"),
                registration_link=ev.get("registration_link"),
                status=EventStatus.skipped,
                reason="dry_run mode — calendar not modified",
            )
            for ev in upcoming
        ]
        return SyncResponse(
            success=True,
            message=f"Dry run: scraped {len(upcoming)} upcoming events (calendar not touched).",
            duration_seconds=elapsed,
            total_scraped=len(all_events),
            total_upcoming=len(upcoming),
            added=0,
            duplicates=0,
            skipped=len(upcoming),
            errors=0,
            events=event_results,
        )

    # ── Step 2: Authenticate ──────────────────────────────────────────────
    log.info("API: Authenticating with Google Calendar …")
    try:
        service = authenticate_google()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        log.exception("Authentication failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Google Calendar authentication failed: {exc}",
        )

    # ── Step 3: De-duplicate and add ──────────────────────────────────────
    log.info("API: Processing %d upcoming events …", len(upcoming))
    event_results: list[EventResult] = []

    for ev in upcoming:
        name = ev.get("event_name", "Unknown")
        date = ev.get("date")
        result = EventResult(
            event_name=name,
            date=date,
            start_time=ev.get("start_time"),
            location=ev.get("location"),
            registration_link=ev.get("registration_link"),
            status=EventStatus.skipped,
        )

        # Skip events without a date
        if not date:
            result.status = EventStatus.skipped
            result.reason = "No date available"
            event_results.append(result)
            continue

        # Check for duplicate
        if _event_already_exists(service, name, date, calendar_id):
            result.status = EventStatus.duplicate
            result.reason = "Already exists on calendar"
            log.info("  ⏭  Duplicate: '%s' on %s", name, date)
        else:
            # Add to calendar
            try:
                link = add_marathon_to_calendar(service, ev, calendar_id)
                result.status = EventStatus.created
                result.calendar_link = link
                log.info("  ✅  Added: '%s' on %s", name, date)
            except (ValueError, HttpError) as exc:
                result.status = EventStatus.error
                result.reason = str(exc)
                log.error("  ✖  Error adding '%s': %s", name, exc)

        event_results.append(result)

    # ── Build summary ─────────────────────────────────────────────────────
    added = sum(1 for r in event_results if r.status == EventStatus.created)
    dupes = sum(1 for r in event_results if r.status == EventStatus.duplicate)
    skipped = sum(1 for r in event_results if r.status == EventStatus.skipped)
    errs = sum(1 for r in event_results if r.status == EventStatus.error)
    elapsed = round(time.time() - start_time, 2)

    message = f"Sync complete: {added} added, {dupes} duplicates, {skipped} skipped, {errs} errors."
    log.info("API: %s (%.1fs)", message, elapsed)

    return SyncResponse(
        success=errs == 0,
        message=message,
        duration_seconds=elapsed,
        total_scraped=len(all_events),
        total_upcoming=len(upcoming),
        added=added,
        duplicates=dupes,
        skipped=skipped,
        errors=errs,
        events=event_results,
    )
