# Complete Setup Guide: Synchronized YouTube + Facebook + Instagram Reels + Google Drive + Google Apps Script

## 1. How Simultaneous Scheduling Works Across All 3 Platforms

| Platform | Native API Scheduling Supported? | How This Bot Schedules & Publishes It at the Exact Same Slot (9:00 AM – 4:00 PM IST) |
| :--- | :--- | :--- |
| **YouTube** | **Yes** (`status.publishAt` ISO-8601 UTC + `privacyStatus="private"`) | Uploaded at **12:00 AM IST** and scheduled natively on YouTube for the show's exact hourly slot (`09:00` to `16:00 IST`). |
| **Facebook Page** | **Yes** (`published=false` + `scheduled_publish_time=<unix_timestamp>`) | Uploaded at **12:00 AM IST** via Meta's 3-phase Resumable Video API (`graph-video.facebook.com/{ver}/{page_id}/videos`) and scheduled natively on Facebook with the **exact same Unix timestamp** as YouTube! |
| **Instagram Reels** | **No** (Meta's `/media` & `/media_publish` endpoints publish immediately and do **not** accept `scheduled_publish_time`) | At **12:00 AM IST**, the bot renders the 9:16 vertical Reel (`<show>_<vid>_ep<N>_reel.mp4`) and automatically uploads it + its Hindi caption JSON to your **Google Drive folder** (`GDRIVE_FOLDER_ID`). Then, at the exact show hour (**9:00 AM – 4:00 PM IST**), **Google Apps Script** (`hourlySlotPublisherAndChecker`) triggers the Instagram Reel publish from Google Drive so **Instagram, Facebook, and YouTube all go live at the exact same time!** |

### Hourly Show Slot Schedule (9:00 AM – 4:00 PM IST)

| Show Key | Serial Name | Scheduled Publish Time (YouTube + Facebook + Instagram) |
| :--- | :--- | :--- |
| `kaisi` | Kaisi Teri Dillagi (कैसी तेरी दिल्लगी) | **09:00 AM IST** |
| `bhabhi` | Hamari Bhabhi Number 1 (हमारी भाभी नंबर 1) | **10:00 AM IST** |
| `sohni` | Sohni Aur Nahi Koi Honi (सोहनी और नहीं कोई होनी) | **11:00 AM IST** |
| `rimjhim` | Rimjhim (रिमझिम) | **12:00 PM IST** |
| `mannsundar` | Mann Sundar (मन सुंदर) | **01:00 PM IST** |
| `atisundar` | Mann Atisundar (मन अतिसुंदर) | **02:00 PM IST** |
| `patibrahma` | Pati Brahmachari (पति ब्रह्मचारी) | **03:00 PM IST** |
| `ishq` | Ishq Junooni (इश्क़ जुनूनी) | **04:00 PM IST** |

---

## 2. All Required GitHub Actions Secrets & Variables

Go to your GitHub repository → **Settings → Secrets and variables → Actions**.

### A. Repository Secrets (`New repository secret`)

| Secret Name | Required For | What Value to Put |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | AI Script & Scene Analysis | Your Google AI Studio Gemini API Key |
| `YT_CLIENT_ID` | YouTube + Google Drive | OAuth 2.0 Web Client ID from Google Cloud Console |
| `YT_CLIENT_SECRET` | YouTube + Google Drive | OAuth 2.0 Web Client Secret from Google Cloud Console |
| `YT_REFRESH_TOKEN` | YouTube + Google Drive | OAuth Refresh Token authorized with **both** `youtube` and `drive.file` (or `drive`) scopes (see Step 3 below) |
| `GDRIVE_FOLDER_ID` | Google Drive Reel Storage | The Folder ID from your Google Drive folder URL (`https://drive.google.com/drive/folders/<FOLDER_ID>`) |
| `FACEBOOK_PAGE_ID` | Facebook Page Publishing | Your numeric Facebook Page ID (e.g. `102938475610293`) |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook Page Publishing | Long-lived / Never-expiring Facebook Page Access Token with `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` |
| `INSTAGRAM_USER_ID` | Instagram Reels Publishing | Your numeric Instagram Professional (Business/Creator) Account ID (e.g. `17841405500208338`) |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Reels Publishing | Long-lived Token with `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` (can be the same token as `FACEBOOK_PAGE_ACCESS_TOKEN` if your IG Business account is linked to your FB Page!) |
| `GH_PAT` | Self-Healing Watchdog | GitHub Personal Access Token (`repo` + `workflow` scopes) so the watchdog can dispatch targeted reruns |
| `CF_ACCOUNT_ID` *(Optional)* | Fast Image Generation | Cloudflare Account ID (falls back to free Pollinations if unset) |
| `CF_API_TOKEN` *(Optional)* | Fast Image Generation | Cloudflare Workers AI Token |

*(Note: If you want Google Drive to use a separate Google account from YouTube, you can optionally add `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET`, and `GDRIVE_REFRESH_TOKEN`. Otherwise, the bot automatically reuses `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, and `YT_REFRESH_TOKEN`!)*

### B. Repository Variables (`Variables` tab → `New repository variable`)

| Variable Name | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `FACEBOOK_ENABLED` | `true` | Enables Facebook Page video upload & native slot scheduling (`published=false` + `scheduled_publish_time`) |
| `INSTAGRAM_ENABLED` | `true` | Enables 9:16 vertical Reel rendering and Instagram Reels publishing |
| `GDRIVE_ENABLED` | `true` | Automatically stores rendered 9:16 vertical Reels + captions in your Google Drive folder |
| `META_GRAPH_API_VERSION` | `v22.0` | Meta Graph API version (`v22.0` or `v25.0`) |
| `FACEBOOK_REELS_MODE` | `false` (or `true`) | `false` uploads the full 16:9 video to Facebook Page Videos; `true` uploads the 9:16 vertical Reel video to your Facebook Page |
| `IG_MAX_REEL_SECONDS` | `115` | Caps the vertical Instagram Reel at 115 seconds so it never triggers Meta's >120s API processing error |
| `IG_PUBLISH_WITH_NIGHTLY` | `false` | Keep `false` so Instagram Reels wait in Google Drive and publish at the exact 9 AM – 4 PM IST show slot via Google Apps Script. Set `true` only if you want IG Reels to publish immediately at midnight |
| `GDRIVE_DELETE_AFTER_PUBLISH` | `false` | Set `true` if you want the bot to automatically delete the Reel MP4 from Google Drive after it is published on Instagram (saves Drive space) |
| `UPLOAD_PRIVACY` | `public` | Privacy status when `publish_now=true` |
| `SERIAL_CHANNEL_NAME` | `सीरियल की कहानी` | Channel branding text |
| `SERIAL_VOICE` | `hi-IN-SwaraNeural` | Primary Hindi neural TTS voice |
| `MUSIC_VOLUME` | `0.15` | Background music volume relative to narration |

---

## 3. Step-by-Step Setup Instructions

### Step 1: Enable Google Drive API & Add Drive Scope to Your Refresh Token (2 Minutes)
1. Open [Google Cloud Console](https://console.cloud.google.com/) and select the same project you used for YouTube (`SETUP_YOUTUBE.md`).
2. Go to **APIs & Services → Library**, search for **Google Drive API**, and click **Enable**.
3. Open [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground):
   - Click the ⚙️ (Gear icon) in the top-right → check **"Use your own OAuth credentials"** → paste your `YT_CLIENT_ID` and `YT_CLIENT_SECRET`.
   - In Step 1 (*Select & authorize APIs*), paste **both** scopes separated by a space:
     ```text
     https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/drive
     ```
   - Click **Authorize APIs**, sign in with your Google account, and click **Exchange authorization code for tokens**.
   - Copy the new **Refresh token** and update your `YT_REFRESH_TOKEN` secret in GitHub (or save it as `GDRIVE_REFRESH_TOKEN`).
4. Create a folder in your Google Drive (e.g., `Serial_Recap_Reels`), open it in your browser, and copy the Folder ID from the URL:
   `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j...` → save that ID as `GDRIVE_FOLDER_ID` in GitHub Secrets/Variables.

### Step 2: Get Your Facebook Page & Instagram Business Tokens (5 Minutes)
1. Make sure your Instagram account is switched to a **Professional (Business)** account and is **linked to your Facebook Page** (in Facebook Page Settings → Linked Accounts → Instagram).
2. Open [Meta for Developers](https://developers.facebook.com/) → **My Apps → Create App** → choose **Business** type.
3. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/):
   - Select your Meta App in the top-right dropdown.
   - Under **User or Page**, select **Get User Access Token**.
   - Add these 6 permissions:
     - `pages_show_list`
     - `pages_read_engagement`
     - `pages_manage_posts`
     - `pages_manage_engagement`
     - `instagram_basic`
     - `instagram_content_publish`
   - Click **Generate Access Token** and approve your Facebook Page and linked Instagram account.
4. Extend the token so it doesn't expire in 1 hour:
   - Paste that short-lived User Token into Meta's [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/) → click **Extend Access Token** at the bottom to get a **60-day Long-Lived User Token**.
   - Now in Graph API Explorer, paste that Long-Lived User Token and run:
     ```text
     GET /me/accounts?fields=id,name,access_token,instagram_business_account
     ```
   - From the JSON response:
     - Copy `id` → save as `FACEBOOK_PAGE_ID` in GitHub Secrets.
     - Copy `access_token` (this Page token derived from a long-lived user token **never expires**!) → save as **both** `FACEBOOK_PAGE_ACCESS_TOKEN` and `INSTAGRAM_ACCESS_TOKEN` in GitHub Secrets.
     - Copy `instagram_business_account.id` → save as `INSTAGRAM_USER_ID` in GitHub Secrets.

### Step 3: Install the Google Apps Script Scheduler & Slot Publisher (2 Minutes)
1. Open [script.google.com](https://script.google.com) → click **New Project**.
2. Replace `Code.gs` with the full contents of `scheduler/google_apps_script.gs`.
3. Fill in the top constants in `Code.gs`:
   - `GITHUB_OWNER`: Your GitHub username
   - `GITHUB_REPO`: `serial-recap-bot`
   - `GITHUB_PAT`: Your GitHub Personal Access Token (`repo` and `workflow` permissions)
   - `GDRIVE_FOLDER_ID`: Your Google Drive folder ID
   - *(Optional)* `INSTAGRAM_USER_ID` & `INSTAGRAM_ACCESS_TOKEN`: If filled in, Apps Script will also push the Reel directly from Google Drive to Instagram at slot time before calling the GitHub verification job.
4. Select `setupTriggers` in the top toolbar dropdown and click **Run** once (grant permissions when prompted).
   - It automatically installs:
     1. **`triggerNightly12AM` (Daily at 12:00 AM IST)**: Generates all 8 shows, schedules YouTube & Facebook for 9 AM – 4 PM IST, and uploads all 8 vertical Reels to Google Drive.
     2. **`hourlySlotPublisherAndChecker` (Every 1 Hour at 9 AM – 4 PM IST)**: Publishes that hour's show Reel from Google Drive to Instagram so Instagram goes live at the exact same time as YouTube and Facebook!
     3. **`watchdogCheckAndRerun` (Every 2 Hours)**: Checks GitHub logs & `state/<show>_status.json` and automatically re-runs any failed or missed show/platform.
