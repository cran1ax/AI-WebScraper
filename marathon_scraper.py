"""
Marathon Event Scraper for IndiaRunning.com
============================================
Scrapes upcoming marathon / running events near Navi Mumbai, Maharashtra
from https://www.indiarunning.com and returns structured event data.

Uses Playwright (Chromium, headless) with randomised delays and robust
error handling so the scraper behaves like a real user and gracefully
recovers from transient failures.

Usage
-----
    python marathon_scraper.py            # pretty-print events to stdout
    python marathon_scraper.py --json     # dump JSON to stdout

Programmatic:
    from marathon_scraper import scrape_events
    events = scrape_events()              # returns list[dict]
"""

from __future__ import annotations

import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from typing import Optional

from dateutil import parser as dateutil_parser
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Primary URL – Navi Mumbai city page (shows only Navi Mumbai events)
NAVI_MUMBAI_URL = "https://www.indiarunning.com/city/Navi-Mumbai"

# Fallback: the main events page (all cities) – we filter for Navi Mumbai ourselves
ALL_EVENTS_URL = "https://www.indiarunning.com"

# Cities we consider "near Navi Mumbai"
NEARBY_CITIES = {
    "navi mumbai",
    "kharghar",
    "vashi",
    "panvel",
    "nerul",
    "belapur",
    "airoli",
    "thane",
    "mumbai",
}

# How many times to click "Show More" to load additional events (0 = no extra)
MAX_SHOW_MORE_CLICKS = 5

# Playwright timeouts (ms)
PAGE_LOAD_TIMEOUT_MS = 60_000
EVENT_CARD_WAIT_MS = 30_000

# Randomised delay range (seconds) between actions
MIN_DELAY = 1.0
MAX_DELAY = 3.5

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("marathon_scraper")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_sleep(lo: float = MIN_DELAY, hi: float = MAX_DELAY) -> None:
    """Sleep for a random duration to mimic human browsing."""
    duration = random.uniform(lo, hi)
    log.debug("Sleeping %.2fs …", duration)
    time.sleep(duration)


def _normalise_date(raw: str) -> Optional[str]:
    """
    Try to parse a human-readable date string (e.g. "5 Apr", "22 Mar")
    into ISO format YYYY-MM-DD.  Returns None on failure.
    """
    raw = raw.strip()
    if not raw:
        return None

    # The site often shows just "5 Apr" without a year – assume current year
    # (or next year if the month has already passed).
    today = datetime.today()
    try:
        dt = dateutil_parser.parse(raw, dayfirst=True, default=today)
        # If the parsed date is in the past, push to next year
        if dt.date() < today.date():
            dt = dt.replace(year=today.year + 1)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        log.warning("Could not parse date: '%s'", raw)
        return raw  # return raw string as a fallback


def _extract_date_from_text(text: str) -> Optional[str]:
    """
    Pull a date-like pattern out of a larger string.
    Matches patterns like "5 Apr", "22 Mar", "14 Feb", "10 May" etc.
    """
    m = re.search(
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _is_near_navi_mumbai(location: str) -> bool:
    """Return True if the location string matches a nearby city."""
    if not location:
        return False
    return any(city in location.lower() for city in NEARBY_CITIES)


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def _click_show_more(page: Page, max_clicks: int = MAX_SHOW_MORE_CLICKS) -> None:
    """
    Repeatedly click the 'Show More' button to load additional event cards.
    Stops when the button disappears or max_clicks is reached.
    """
    for i in range(max_clicks):
        try:
            btn = page.locator("text=Show More").first
            if not btn.is_visible(timeout=3_000):
                log.info("'Show More' button not visible – done loading.")
                break
            _random_sleep(0.5, 1.5)
            btn.click()
            log.info("Clicked 'Show More' (%d/%d)", i + 1, max_clicks)
            # Wait for new cards to appear
            _random_sleep(1.5, 3.0)
        except PlaywrightTimeout:
            log.info("No more 'Show More' button – all events loaded.")
            break
        except Exception as exc:
            log.warning("Error clicking 'Show More': %s", exc)
            break


def _scrape_event_detail_page(context: BrowserContext, url: str) -> dict:
    """
    Open an individual event/registration page in a new tab and try to
    extract a start time and a more precise location / venue.
    Returns a dict with optional keys: 'start_time', 'location_detail'.
    """
    details: dict = {}
    page: Optional[Page] = None
    try:
        page = context.new_page()
        _random_sleep(0.8, 2.0)
        page.goto(url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
        _random_sleep(1.0, 2.5)

        body_text = page.inner_text("body")

        # ---- Start time ----
        # Look for labelled time first:  "Start Time: 5:30 AM" / "Reporting Time : 5:00 AM"
        labelled_time = re.search(
            r"(?:start\s*time|flag[- ]?off|reporting\s*time|race\s*start)"
            r"[:\s\-–]+(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))",
            body_text,
            re.IGNORECASE,
        )
        if labelled_time:
            details["start_time"] = labelled_time.group(1).strip().upper()
        else:
            # Fallback: find times in a plausible marathon range (3:00 AM – 8:00 AM)
            all_times = re.findall(
                r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))", body_text
            )
            for t in all_times:
                t_upper = t.strip().upper()
                hour = int(t_upper.split(":")[0])
                if "AM" in t_upper and 3 <= hour <= 8:
                    details["start_time"] = t_upper
                    break

        # ---- Location / venue ----
        venue_match = re.search(
            r"(?:Venue|Start\s*Point|Race\s*Venue|Event\s*Location|Address)"
            r"\s*[:\-–]\s*(.+)",
            body_text,
            re.IGNORECASE,
        )
        if venue_match:
            venue = venue_match.group(1).strip().split("\n")[0].strip()
            # Sanity: reject very short or very long captures
            if 5 < len(venue) < 200:
                details["location_detail"] = venue

    except PlaywrightTimeout:
        log.warning("Timed out loading detail page: %s", url)
    except Exception as exc:
        log.warning("Error scraping detail page %s: %s", url, exc)
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
    return details


def _parse_event_cards(page: Page, context: BrowserContext) -> list[dict]:
    """
    Parse all visible event cards on the current page and return a list of
    event dicts.  Each card on IndiaRunning typically lives inside an <a>
    tag pointing to the registration URL and contains structured text:
        Line structure (from inner_text):
            "Register"  /  "Discounted Price"   (header noise)
            "<day>"                              e.g. "5"
            "<month>"                            e.g. "Apr"
            "<Event Name>"                       e.g. "Kharghar Half Marathon"
            "<distance tags>"                    e.g. "3K", "5K", "10K", "HM"
            "<rating>"                           e.g. "4.7"
            "Running"
            "Registrations …"  or  "Registrations closing on …"
            "₹ 695 onwards"
            "<City>"                             e.g. "Navi Mumbai"
    """
    events: list[dict] = []

    # The event cards are <a> tags whose href points to registrations site.
    # Skip banner-only links (they have empty inner text).
    card_links = page.locator('a[href^="https://registrations.indiarunning.com/"]')
    count = card_links.count()
    log.info("Found %d event card link(s) on page.", count)

    for i in range(count):
        try:
            card = card_links.nth(i)
            href = card.get_attribute("href") or ""
            card_text = card.inner_text(timeout=5_000).strip()

            # Skip banner / image-only links with no meaningful text
            if not card_text or len(card_text) < 10:
                continue

            # -- Registration link --
            reg_link = href.strip()

            # Split into non-empty lines for structured parsing
            lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]

            # -- Location (city) --
            # The city is the LAST meaningful line in the card text
            location = ""
            for ln in reversed(lines):
                # Skip noise lines that can appear at the end
                if ln.lower().startswith(("this is a virtual", "₹")):
                    continue
                # The city line is a short string that is NOT a number/price/keyword
                if (
                    not re.match(r"^[\d₹.]+", ln)
                    and not ln.lower().startswith("registration")
                    and len(ln) < 60
                ):
                    location = ln
                    break

            # -- Filter: only keep events near Navi Mumbai --
            if not _is_near_navi_mumbai(location):
                continue

            # -- Date --
            # The date is split across two lines: "<day>" then "<month>"
            # e.g. lines like ["Register", "5", "Apr", "Event Name", ...]
            event_date = None
            raw_date_str = None
            for j, ln in enumerate(lines):
                if re.match(r"^\d{1,2}$", ln) and j + 1 < len(lines):
                    month_candidate = lines[j + 1]
                    if re.match(
                        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                        month_candidate,
                        re.I,
                    ):
                        raw_date_str = f"{ln} {month_candidate}"
                        break
            # Fallback: look for inline "5 Apr" style
            if not raw_date_str:
                raw_date_str = _extract_date_from_text(card_text)
            if raw_date_str:
                event_date = _normalise_date(raw_date_str)

            # -- Event name --
            # The event name is the first "long-ish" line after the date/month
            # that is not a distance tag, number, price, or keyword.
            NOISE = {
                "register", "discounted price", "running", "running-icon",
                "location-icon", "event-type-icon",
            }
            MONTH_NAMES = {
                "jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec",
            }
            event_name = ""
            passed_date = raw_date_str is None  # if no date found, start looking immediately
            for ln in lines:
                low = ln.lower()
                # Skip known noise
                if low in NOISE:
                    continue
                # Skip bare numbers (day, rating)
                if re.match(r"^[\d.]+$", ln):
                    continue
                # Skip month names (standalone)
                if low[:3] in MONTH_NAMES and len(ln) <= 3:
                    if not passed_date:
                        passed_date = True
                    continue
                # Skip distance tags like "3K", "5K", "10K", "21.1K", "HM"
                if re.match(r"^(\d+(\.\d+)?K|HM|FM|M|U)$", ln, re.I):
                    continue
                # Skip prices
                if ln.startswith("₹"):
                    continue
                # Skip registration status lines
                if low.startswith("registration"):
                    continue
                # Skip city (already captured)
                if ln == location:
                    continue
                if not passed_date:
                    continue
                # This is likely the event name – take the first match
                event_name = ln
                break

            if not event_name:
                # Fallback: derive a name from the registration URL slug
                slug = reg_link.rstrip("/").rsplit("/", 1)[-1]
                # Remove trailing numeric IDs e.g. "_24658" or "-24658"
                slug = re.sub(r"[-_]\d{4,}$", "", slug)
                event_name = slug.replace("_", " ").replace("-", " ").strip().title()
                if not event_name:
                    event_name = "Unknown Event"

            # -- Build base event dict --
            event = {
                "event_name": event_name,
                "date": event_date,
                "start_time": None,
                "location": location,
                "registration_link": reg_link,
            }

            # -- Optionally visit the detail / registration page for start time --
            if reg_link:
                log.info(
                    "Fetching detail page for '%s' …", event_name
                )
                details = _scrape_event_detail_page(context, reg_link)
                if details.get("start_time"):
                    event["start_time"] = details["start_time"]
                if details.get("location_detail"):
                    event["location"] = (
                        f"{details['location_detail']} ({location})"
                        if location
                        else details["location_detail"]
                    )

            events.append(event)
            log.info(
                "✔  %s | %s | %s",
                event["event_name"],
                event["date"],
                event["location"],
            )

        except PlaywrightTimeout:
            log.warning("Timed out reading event card #%d – skipping.", i)
        except Exception as exc:
            log.warning("Error parsing event card #%d: %s", i, exc)

    return events


def scrape_events(
    headless: bool = True,
    visit_details: bool = True,
) -> list[dict]:
    """
    Main entry point.  Launches a Playwright Chromium browser, navigates to
    IndiaRunning.com, and scrapes upcoming running events near Navi Mumbai.

    Parameters
    ----------
    headless : bool
        Run the browser in headless mode (default True).
    visit_details : bool
        Whether to open each event's registration page to grab the start
        time and detailed venue (slower but more data).  Default True.

    Returns
    -------
    list[dict]
        Each dict has keys:
            event_name        – str
            date              – str (YYYY-MM-DD) or None
            start_time        – str (e.g. "6:00 AM") or None
            location          – str
            registration_link – str (URL)
    """
    events: list[dict] = []

    pw: Optional[Playwright] = None
    browser: Optional[Browser] = None

    try:
        pw = sync_playwright().start()
        log.info("Launching Chromium (headless=%s) …", headless)

        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        # Stealth: remove the navigator.webdriver flag
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined})"
        )

        page = context.new_page()

        # ---- Try city-specific page first --------------------------------
        target_url = NAVI_MUMBAI_URL
        log.info("Navigating to %s …", target_url)
        try:
            page.goto(target_url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            log.warning("City page timed out – falling back to main page.")
            target_url = ALL_EVENTS_URL
            page.goto(target_url, timeout=PAGE_LOAD_TIMEOUT_MS, wait_until="domcontentloaded")

        _random_sleep(2.0, 4.0)

        # Wait for at least one event card link to appear
        try:
            page.wait_for_selector(
                'a[href^="https://registrations.indiarunning.com/"]',
                timeout=EVENT_CARD_WAIT_MS,
            )
        except PlaywrightTimeout:
            log.error("No event cards found after waiting – page may have changed.")
            return events

        _random_sleep()

        # ---- Click "Show More" to load all events -------------------------
        _click_show_more(page)
        _random_sleep()

        # ---- Parse event cards -------------------------------------------
        if visit_details:
            events = _parse_event_cards(page, context)
        else:
            events = _parse_event_cards(page, context)

        log.info(
            "Scraping complete – %d event(s) near Navi Mumbai found.", len(events)
        )

    except PlaywrightTimeout as exc:
        log.error("Global timeout: %s", exc)
    except Exception as exc:
        log.exception("Unexpected error during scraping: %s", exc)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return events


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _pretty_print(events: list[dict]) -> None:
    """Print events in a human-readable table format."""
    if not events:
        print("\n  No upcoming events found near Navi Mumbai.\n")
        return

    print(f"\n{'=' * 90}")
    print(f"  🏃  Upcoming Marathon / Running Events near Navi Mumbai  ({len(events)} found)")
    print(f"{'=' * 90}\n")

    for idx, ev in enumerate(events, start=1):
        print(f"  [{idx}] {ev['event_name']}")
        print(f"      📅  Date       : {ev['date'] or 'TBA'}")
        print(f"      ⏰  Start Time : {ev['start_time'] or 'TBA'}")
        print(f"      📍  Location   : {ev['location'] or 'N/A'}")
        print(f"      🔗  Register   : {ev['registration_link']}")
        print()

    print(f"{'=' * 90}\n")


def main() -> None:
    use_json = "--json" in sys.argv
    headless = "--headed" not in sys.argv
    skip_details = "--fast" in sys.argv

    events = scrape_events(headless=headless, visit_details=not skip_details)

    if use_json:
        print(json.dumps(events, indent=2, ensure_ascii=False))
    else:
        _pretty_print(events)


if __name__ == "__main__":
    main()
