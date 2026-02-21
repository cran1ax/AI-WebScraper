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
git clone https://github.com/<your-username>/AI-WebScraper.git
cd AI-WebScraper
pip install -r requirements.txt
playwright install chromium
```

### 2. Set up Google Calendar API

Follow the detailed guide in **[GOOGLE_CALENDAR_SETUP.md](GOOGLE_CALENDAR_SETUP.md)** to:
1. Create a Google Cloud project
2. Enable the Google Calendar API
3. Download `credentials.json` and place it in the project root

### 3. Run

```bash
# Preview events only (no calendar changes)
python main.py --dry-run

# Full pipeline: scrape + add to Google Calendar
python main.py
```

## 🛠️ CLI Options

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
