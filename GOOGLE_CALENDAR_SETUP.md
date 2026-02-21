# 🔑 Google Calendar API – Setup Guide

> Step-by-step instructions to obtain the `credentials.json` file needed by
> `calendar_integration.py`.  
> Estimated time: **5–10 minutes**.

---

## 1. Create (or select) a Google Cloud Project

1. Go to the **Google Cloud Console**:  
   👉 <https://console.cloud.google.com/>

2. Sign in with the **same Google account** whose calendar you want to add events to.

3. In the top navigation bar, click the **project selector** (drop-down next to "Google Cloud").

4. Click **"New Project"**.
   - **Project name:** `Marathon Scraper` (or anything you like)
   - **Organization:** leave as default
   - Click **Create**.

5. Make sure the new project is **selected** in the project selector.

---

## 2. Enable the Google Calendar API

1. In the left sidebar, go to **APIs & Services → Library**  
   (or visit <https://console.cloud.google.com/apis/library>).

2. Search for **"Google Calendar API"**.

3. Click the **Google Calendar API** card.

4. Click **"Enable"**.

---

## 3. Configure the OAuth Consent Screen

> This step is required before you can create OAuth credentials.

1. Go to **APIs & Services → OAuth consent screen**  
   (or visit <https://console.cloud.google.com/apis/credentials/consent>).

2. Select **User Type → External**, then click **Create**.

3. Fill in the required fields:
   | Field               | Value                              |
   |---------------------|------------------------------------|
   | App name            | `Marathon Scraper`                 |
   | User support email  | *your email*                       |
   | Developer contact   | *your email*                       |

4. Click **Save and Continue**.

5. **Scopes** screen → Click **"Add or Remove Scopes"**.
   - In the filter box search for `Google Calendar API`.
   - Check the scope:
     ```
     https://www.googleapis.com/auth/calendar
     ```
     *(This is the full read/write scope that lets us create events.)*
   - Click **Update**, then **Save and Continue**.

6. **Test users** screen → Click **"+ Add Users"**.
   - Enter **your own Gmail / Google Workspace email address**.
   - Click **Add**, then **Save and Continue**.

7. Review the summary and click **Back to Dashboard**.

> **Note:** While the app is in "Testing" status the consent screen will
> show a "This app isn't verified" warning.  That's perfectly fine for
> personal use — just click **Continue** when prompted.

---

## 4. Create OAuth 2.0 Client ID Credentials

1. Go to **APIs & Services → Credentials**  
   (or visit <https://console.cloud.google.com/apis/credentials>).

2. Click **"+ Create Credentials" → "OAuth client ID"**.

3. Fill in:
   | Field             | Value                |
   |-------------------|----------------------|
   | Application type  | **Desktop app**      |
   | Name              | `Marathon Scraper`   |

4. Click **Create**.

5. A dialog will appear showing your **Client ID** and **Client Secret**.  
   Click **"Download JSON"** (the ⬇ button).

6. **Rename** the downloaded file to:
   ```
   credentials.json
   ```

7. **Move** `credentials.json` into the project directory:
   ```
   AI WebScraper/
   ├── marathon_scraper.py
   ├── calendar_integration.py
   ├── credentials.json          ← place it here
   ├── requirements.txt
   └── ...
   ```

---

## 5. First-Run Authorization

1. Run the calendar integration test:
   ```bash
   python calendar_integration.py
   ```

2. A **browser window** will open asking you to sign in and grant
   calendar access to "Marathon Scraper".

3. You may see a **"This app isn't verified"** warning:
   - Click **Advanced** → **Go to Marathon Scraper (unsafe)**
   - This is expected for apps in "Testing" status.

4. Grant the requested permission:
   - **"See, edit, share, and permanently delete all the calendars you
     can access using Google Calendar"** → Click **Allow**.

5. The browser will say *"The authentication flow has completed."*  
   You can close the tab.

6. Back in the terminal you should see:
   ```
   ✅  Event created successfully!
       View it here: https://www.google.com/calendar/event?eid=...
   ```

7. A `token.json` file is now saved in the project directory.  
   **Future runs will not open the browser** — they use the cached token.

---

## 6. Required Scope Reference

| Scope                                              | Why we need it                            |
|----------------------------------------------------|-------------------------------------------|
| `https://www.googleapis.com/auth/calendar`         | Create, read, and update calendar events  |

> We use the full `calendar` scope (not `calendar.events` or
> `calendar.readonly`) because we need to **insert new events**.  
> If you only wanted to read events, `calendar.readonly` would suffice.

---

## 7. Security Notes

| File               | Contains                | Commit to Git? |
|--------------------|-------------------------|----------------|
| `credentials.json` | OAuth client ID/secret  | **❌ NO**       |
| `token.json`       | User access/refresh token | **❌ NO**     |

Add both to your `.gitignore`:
```gitignore
credentials.json
token.json
```

- **Never share** `credentials.json` or `token.json` publicly.
- If either file is compromised, go to the Google Cloud Console →
  Credentials → delete the OAuth client, and create a new one.
- The `token.json` auto-refreshes.  If you ever see auth errors,
  delete `token.json` and re-run to trigger a fresh login.

---

## 8. Troubleshooting

| Problem | Fix |
|---------|-----|
| `FileNotFoundError: credentials.json not found` | Download it from Cloud Console (Step 4) and place it in the project root. |
| Browser never opens | Make sure you're running on a machine with a desktop browser. On a headless server use `flow.run_console()` instead. |
| `Access blocked: This app's request is invalid` | You probably chose "Web application" instead of **"Desktop app"** in Step 4. Re-create the credential. |
| `Error 403: access_denied` | Your email is not listed as a **Test User** (Step 3.6). |
| `Token has been expired or revoked` | Delete `token.json` and re-run. |
| Events appear at wrong time | Ensure `EVENT_TIMEZONE` in `calendar_integration.py` is `"Asia/Kolkata"`. |

---

*Guide last updated: February 2026*
