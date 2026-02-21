# 🏃 AI Marathon WebScraper → Google Calendar

Automatically scrapes upcoming marathon & running events near **Navi Mumbai, Maharashtra** from [IndiaRunning.com](https://www.indiarunning.com) and adds them to your **Google Calendar** — with duplicate detection, smart scheduling, and clean summaries.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Chromium-green?logo=google-chrome&logoColor=white)
![Google Calendar](https://img.shields.io/badge/Google%20Calendar-API%20v3-red?logo=google-calendar&logoColor=white)

---

## ✨ Features

- **Web Scraping** — Playwright-based headless browser scrapes event cards from IndiaRunning.com
- **Smart Parsing** — Extracts event name, date, start time, location, and registration link
- **Anti-blocking** — Randomised delays, stealth browser fingerprint, realistic viewport
- **Google Calendar Integration** — OAuth 2.0 authentication with token caching
- **Duplicate Detection** — Queries your calendar before adding; never creates duplicates
- **Batch Processing** — Scrapes & adds all upcoming events in one run
- **CLI Flags** — `--dry-run`, `--fast`, `--headed` for flexible usage

## 📁 Project Structure

```
AI WebScraper/
├── main.py                    # Main pipeline: scrape → deduplicate → add → summary
├── marathon_scraper.py        # Playwright scraper for IndiaRunning.com
├── calendar_integration.py    # Google Calendar API v3 authentication & event creation
├── GOOGLE_CALENDAR_SETUP.md   # Step-by-step guide to get credentials.json
├── requirements.txt           # Python dependencies
├── .gitignore                 # Protects credentials.json & token.json
└── README.md
```

## 🚀 Quick Start

### 1. Clone & install dependencies

```bash
git clone https://github.com/cran1ax/AI-WebScraper.git
cd AI-WebScraper
pip install -r requirements.txt
playwright install chromium
```

### 2. Set up Google Calendar API

Follow the detailed guide in **[GOOGLE_CALENDAR_SETUP.md](GOOGLE_CALENDAR_SETUP.md)**. In short:

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a new project
2. **Enable** the **Google Calendar API** (APIs & Services → Library → search "Google Calendar API" → Enable)
3. **Configure OAuth consent screen** (APIs & Services → OAuth consent screen)
   - Choose **External** → Create
   - App name: `Marathon Scraper`, add your email
   - Add scope: `https://www.googleapis.com/auth/calendar`
   - Add yourself as a **Test User**
4. **Create credentials** (APIs & Services → Credentials → + Create Credentials → OAuth client ID)
   - Application type: **Desktop app**
   - Click **Create** → **Download JSON**
5. Rename the downloaded file to `credentials.json` and place it in the project root:
   ```
   AI-WebScraper/
   ├── credentials.json   ← here
   ├── main.py
   ├── ...
   ```

### 3. Run the project

```bash
# Full pipeline: scrape events + add to Google Calendar
python main.py
```

On the **first run**, a browser window will open asking you to sign in to Google and grant calendar access. After that, a `token.json` is saved and future runs are fully automatic.

---

## ▶️ How to Run — All Options

### Full pipeline (scrape + add to calendar)

```bash
python main.py
```

This will:
1. Launch a headless Chromium browser
2. Scrape all upcoming running events near Navi Mumbai from IndiaRunning.com
3. Authenticate with Google Calendar (browser popup on first run only)
4. Check each event against your calendar to avoid duplicates
5. Add new events with date, time, location, reminders, and registration link
6. Print a summary of what was added / skipped

### Preview only (don't touch the calendar)

```bash
python main.py --dry-run
```

Scrapes and displays all found events in a table, but **does not** authenticate or modify Google Calendar. Great for testing.

### Fast mode (skip detail pages)

```bash
python main.py --fast
```

Skips visiting each event's individual registration page. This is **~3× faster** but won't extract start times or detailed venue addresses.

### See the browser while scraping

```bash
python main.py --headed
```

Opens a visible Chromium window so you can watch the scraper navigate the website. Useful for debugging.

### Combine flags

```bash
# Fast preview
python main.py --dry-run --fast

# Headed + full pipeline
python main.py --headed

# Add to a specific calendar
python main.py --calendar-id "your_calendar_id@group.calendar.google.com"
```

### Run individual modules

```bash
# Scraper only (no calendar)
python marathon_scraper.py            # pretty-print to console
python marathon_scraper.py --json     # output raw JSON

# Test calendar authentication
python calendar_integration.py        # adds a sample event to verify setup
```

## 🛠️ CLI Reference

| Flag | Description |
|------|-------------|
| `--dry-run` | Scrape & display events without touching Google Calendar |
| `--fast` | Skip detail-page visits (faster, but no start-time data) |
| `--headed` | Show the browser window while scraping |
| `--calendar-id ID` | Target a specific Google Calendar (default: `primary`) |

## 🔒 Security

> **Never commit** `credentials.json` or `token.json` to version control.

Both files are listed in `.gitignore`. If you accidentally expose them:
1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Delete the compromised OAuth client
3. Create a new one and download fresh `credentials.json`

## 📄 License

MIT
