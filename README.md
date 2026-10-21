# Serial recap bot (Dangal TV serials -> 2-3 min "motion comic" recaps), standalone repo

## Daily Publish Schedule (9:00 AM – 4:00 PM IST)
The bot runs at **12:00 AM IST (Midnight)** via an external cron trigger and schedules the 8 daily recap videos on YouTube at hourly slots from **9:00 AM to 4:00 PM IST**:

| Show Key | Serial Name | Scheduled YouTube Publish Time (IST) |
| :--- | :--- | :--- |
| `kaisi` | Kaisi Teri Dillagi (कैसी तेरी दिल्लगी) | **09:00 AM IST** |
| `bhabhi` | Hamari Bhabhi Number 1 (हमारी भाभी नंबर 1) | **10:00 AM IST** |
| `sohni` | Sohni Aur Nahi Koi Honi (सोहनी और नहीं कोई होनी) | **11:00 AM IST** |
| `rimjhim` | Rimjhim (रिमझिम) | **12:00 PM IST** |
| `mannsundar` | Mann Sundar (मन सुंदर) | **01:00 PM IST** |
| `atisundar` | Mann Atisundar (मन अतिसुंदर) | **02:00 PM IST** |
| `patibrahma` | Pati Brahmachari (पति ब्रह्मचारी) | **03:00 PM IST** |
| `ishq` | Ishq Junooni (इश्क़ जुनूनी) | **04:00 PM IST** |

## Why We Don't Use GitHub's Built-In Cron (And How to Trigger at 12:00 AM IST Sharp for Free)
GitHub's internal `schedule:` cron frequently delays runs by 30–90 minutes or drops them during peak hours. Instead, this repo uses **external `workflow_dispatch` / `repository_dispatch`** triggered at **12:00 AM IST sharp** using any of the 100% free external schedulers included in `/scheduler`:

1. **Option A — Google Apps Script (`scheduler/google_apps_script.gs`, Recommended & 100% Free)**:
   - Open [script.google.com](https://script.google.com), create a project, and paste `scheduler/google_apps_script.gs`.
   - Set `GITHUB_OWNER`, `GITHUB_REPO`, and `GITHUB_PAT` (a GitHub Personal Access Token with `repo` and `workflow` permissions).
   - Run `setupTriggers()` once. It installs an exact **12:00 AM IST (`Asia/Kolkata`)** daily trigger plus a **2-hour Watchdog Log-Inspector** that checks GitHub run logs and automatically re-triggers any failed show.
2. **Option B — Cloudflare Worker (`scheduler/cloudflare_worker.js`, 100% Free)**:
   - Deploy `scheduler/cloudflare_worker.js` on Cloudflare Workers Free Tier with cron `30 18 * * *` (12:00 AM IST) and `30 20,22,0,2 * * *` (watchdog checks).
3. **Option C — cron-job.org (100% Free Web Cron)**:
   - Create a free job at [cron-job.org](https://cron-job.org) set to **00:00 Asia/Kolkata (12:00 AM IST)**.
   - Method: `POST` to `https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/recap.yml/dispatches`
   - Headers: `Authorization: Bearer <YOUR_GITHUB_PAT>`, `Accept: application/vnd.github+json`
   - Body: `{"ref":"main","inputs":{"only_show":"all","test_mode":"false","upload":"true","publish_now":"false"}}`

## 3-Layer Self-Healing Log Watchdog & Zero-Duplicate Protection
1. **In-Job Log Capture & Auto-Retry (`recap.yml` & `main.py`)**:
   - Every show job streams its logs into `state/<show>_status.json`. If Attempt 1 fails (e.g., temporary Gemini 503 or network timeout), the job reads the status log, cleans up temp files, waits 45 seconds, and retries automatically inside the same run.
2. **Post-Run Watchdog Supervisor (`recap/watchdog.py`)**:
   - After the matrix finishes (and whenever triggered with `only_show=watchdog`), `watchdog.py` inspects the GitHub Actions job logs, reads `state/<show>_status.json`, and checks Dangal TV's live feed. If any show failed, timed out, or has an unprocessed new episode, it automatically dispatches a targeted rerun for **only that show** (up to 4 self-healing attempts per day).
3. **Triple Anti-Duplicate Lock (Never Uploads an Episode Twice)**:
   - **Video ID + Episode Number State (`state/<show>.json`)**: Stores both the source YouTube video ID (`JNdlYnNneKE`) and the episode number (`ep:452`, `target_ep:453`). Even if Dangal TV re-uploads the same episode with a new video ID, it is never processed twice.
   - **Live YouTube Channel Pre-Check (`youtube.already_uploaded()`)**: Before generating a video AND again right before uploading, the bot queries your YouTube channel's uploads list (including private/scheduled videos). If an episode is already uploaded or scheduled on your channel, it syncs `state/<show>.json` and skips immediately.
