# Serial Recap Bot (Dangal TV -> YouTube + Facebook + Instagram Reels + Google Drive + Google Apps Script)

## Daily Synchronized Publish Schedule (9:00 AM – 4:00 PM IST)
The bot runs at **12:00 AM IST (Midnight)** via Google Apps Script (`scheduler/google_apps_script.gs`) and publishes all 8 daily recap videos across **YouTube**, **Facebook Page**, and **Instagram Reels** at the exact same hourly slots from **9:00 AM to 4:00 PM IST**:

| Show Key | Serial Name | YouTube Schedule | Facebook Page Schedule | Google Drive + Instagram Reel Slot |
| :--- | :--- | :--- | :--- | :--- |
| `kaisi` | Kaisi Teri Dillagi (कैसी तेरी दिल्लगी) | **09:00 AM IST** (`publishAt`) | **09:00 AM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **09:00 AM IST** |
| `bhabhi` | Hamari Bhabhi Number 1 (हमारी भाभी नंबर 1) | **10:00 AM IST** (`publishAt`) | **10:00 AM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **10:00 AM IST** |
| `sohni` | Sohni Aur Nahi Koi Honi (सोहनी और नहीं कोई होनी) | **11:00 AM IST** (`publishAt`) | **11:00 AM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **11:00 AM IST** |
| `rimjhim` | Rimjhim Choti Umar Bada Safar (रिमझिम छोटी उम्र बड़ा सफर) | **12:00 PM IST** (`publishAt`) | **12:00 PM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **12:00 PM IST** |
| `mannsundar` | Mann Sundar (मन सुंदर) | **01:00 PM IST** (`publishAt`) | **01:00 PM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **01:00 PM IST** |
| `atisundar` | Mann Atisundar (मन अतिसुंदर) | **02:00 PM IST** (`publishAt`) | **02:00 PM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **02:00 PM IST** |
| `patibrahma` | Pati Brahmachari (पति ब्रह्मचारी) | **03:00 PM IST** (`publishAt`) | **03:00 PM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **03:00 PM IST** |
| `ishq` | Ishq Junooni (इश्क़ जुनूनी) | **04:00 PM IST** (`publishAt`) | **04:00 PM IST** (`scheduled_publish_time`) | Stored in Drive at 12 AM → Published **04:00 PM IST** |

Video descriptions include dynamic show, episode, and date details, Hindi/English search phrases, hashtags, recap/prediction copy, and the official source episode link. Search terms include general show phrases plus varied +1-day/+1-episode and +2-day/+2-episode combinations; source-day search terms are excluded. [Example description](./examples/mann_atisundar_MZLmmpAv87Q_description.txt).

---

## Why Facebook & YouTube Schedule Natively, While Instagram Uses Google Drive + Apps Script

1. **YouTube (`recap/youtube.py`)**: Supports native server-side scheduling via `status.publishAt` (ISO-8601 UTC timestamp) with `privacyStatus="private"`.
2. **Facebook Page Videos (`recap/social.py`)**: Always uploads the rendered 9:16 vertical video with its matching custom cover and verifies the video dimensions before upload. It supports native server-side scheduling via Meta's Graph Video API (`POST /{page-id}/videos`) using `published=false` and `scheduled_publish_time=<unix_timestamp>` (must be at least 10 minutes in the future). At 12:00 AM IST, the bot passes the **exact same `slot` timestamp** to both YouTube and Facebook so they go live simultaneously!
3. **Instagram Reels (`recap/social.py` + `scheduler/google_apps_script.gs`)**: Meta's official Instagram Graph API (`/{ig-user-id}/media` and `/{ig-user-id}/media_publish`) **does not support a `scheduled_publish_time` parameter** for direct API calls (calling `media_publish` publishes the Reel immediately).
   - **Our Solution**:
     - At **12:00 AM IST**, the bot renders the 9:16 vertical Reel (`<show>_<vid>_ep<N>_reel.mp4`) and automatically uploads it (along with a `<show>_<vid>_ep<N>_reel.json` caption file) into your **Google Drive folder** (`GDRIVE_FOLDER_ID`).
     - Every hour from **9:00 AM to 4:00 PM IST**, **Google Apps Script** (`hourlySlotPublisherAndChecker`) wakes up, verifies the show's Reel in Google Drive / `state/<show>_status.json`, and triggers `only_ig_publish=true` (or publishes directly from Drive via Meta's Resumable Upload API `rupload.facebook.com` without needing any external hosting server!).
     - As a result, **Instagram, Facebook, and YouTube all publish at the exact same scheduled hour**.

---

## Required GitHub Secrets & Variables

See **[`SETUP_META_AND_DRIVE.md`](SETUP_META_AND_DRIVE.md)** for the full step-by-step setup guide.

### GitHub Actions Secrets (`Settings → Secrets and variables → Actions → Secrets`)

| Secret | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio Gemini API Key |
| `YT_CLIENT_ID` | Google Cloud OAuth 2.0 Client ID (used for YouTube & Google Drive) |
| `YT_CLIENT_SECRET` | Google Cloud OAuth 2.0 Client Secret |
| `YT_REFRESH_TOKEN` | Google OAuth Refresh Token with `youtube` + `drive` scopes |
| `GDRIVE_FOLDER_ID` | Google Drive Folder ID where 9:16 Reels & captions are stored automatically |
| `FACEBOOK_PAGE_ID` | Numeric ID of your Facebook Page |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Never-expiring Page Access Token (`pages_manage_posts`, `pages_read_engagement`, `pages_show_list`) |
| `INSTAGRAM_USER_ID` | Numeric ID of your Instagram Professional (Business/Creator) Account |
| `INSTAGRAM_ACCESS_TOKEN` | Long-lived Meta Access Token with `instagram_basic` and `instagram_content_publish` |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID for Workers AI image generation |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI API token for primary image generation |

### GitHub Actions Variables (`Settings → Secrets and variables → Actions → Variables`)

| Variable | Recommended Value | Description |
| :--- | :--- | :--- |
| `FACEBOOK_ENABLED` | `true` | Enable Facebook Page upload & native scheduling |
| `INSTAGRAM_ENABLED` | `true` | Enable 9:16 vertical Reel rendering & Instagram Reels publishing |
| `GDRIVE_ENABLED` | `true` | Enable automatic Google Drive Reel upload & slot retrieval |
| `META_GRAPH_API_VERSION` | `v22.0` | Meta Graph API version |
| `REEL_MAX_SECONDS` | `115` | Caps Facebook/Instagram 9:16 video length at 115s; Facebook uploads always use the vertical video |
| `IG_PUBLISH_WITH_NIGHTLY` | `false` | `false` = publish IG Reel at exact 9 AM–4 PM IST slot via Apps Script; `true` = publish IG immediately at 12 AM |
| `GDRIVE_DELETE_AFTER_PUBLISH` | `false` | `true` = automatically delete Reel from Google Drive after Instagram publish succeeds |
| `HF_FLUX_SPACE` | Public FLUX.1-schnell Space | First image fallback if Cloudflare is unavailable or its quota is exhausted |

### Episode-aware thumbnail artwork

For each episode, the bot asks Gemini to describe the source video's public YouTube thumbnail and uses only its broad composition and color balance as guidance. It generates fresh episode art with Cloudflare Workers AI FLUX.1-schnell first, then falls back to the Hugging Face FLUX Space and Pollinations. YouTube receives the existing 1280 × 720 thumbnail, while Facebook receives a separate 1080 × 1920 cover composed for its 9:16 video. Both use the bot's Hindi hook, show, and episode/date overlays. If individual scene generation fails, the nearest successfully generated scene art is reused; title cards are used only if all image providers fail for the episode.

`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are read from GitHub Actions secrets (legacy `CF_ACCOUNT_ID` and `CF_API_TOKEN` names are also accepted). Cloudflare is the primary image provider and uses the Workers AI FLUX.1-schnell endpoint; if it is unavailable or its quota is exhausted, generation tries the configured/default Hugging Face FLUX Space, then Pollinations. `gradio_client` is installed from `requirements.txt`; `HF_FLUX_SPACE` can override the default public Space URL. A ZeroGPU quota or HTTP 402 is a provider limit, not a DNS error; the exhausted provider is skipped so the next provider can run. Transient errors such as HTTP 503 are retried.

---

## Reliability, Self-Healing Watchdog & Zero-Duplicate Protection
1. **In-Job Log Capture & Auto-Retry (`recap.yml` & `main.py`)**:
   - Every show job streams its logs into `state/<show>_status.json` (tracking `youtube_video_id`, `facebook_video_id`, `instagram_media_id`, `gdrive_file_id`, and `scheduled_slot_ist`). If Attempt 1 fails, it cleans up temporary files, waits 45s, and retries automatically. Only platforms that haven't succeeded yet are run on retry.
2. **Google Apps Script Scheduler + Hourly Slot Publisher + Single 2-Hour Watchdog (`scheduler/google_apps_script.gs`)**:
   - **`triggerNightly12AM`**: Starts the midnight generation and scheduling run at 12:00 AM IST sharp.
   - **`hourlySlotPublisherAndChecker`**: Runs every hour at 9 AM – 4 PM IST to publish that hour's Instagram Reel from Google Drive and verify that YouTube, Facebook, and Instagram are all live.
   - **`watchdogCheckAndRerun`**: The only scheduled watchdog; runs every 2 hours and dispatches targeted reruns for failed or missed work.
3. **Live Anti-Duplicate Locks Across All 3 Platforms**:
   - Before uploading to YouTube (`youtube.already_uploaded()`), Facebook (`social.fb_already_uploaded()`), Google Drive (`social.drive_find_file()`), or Instagram (`social.ig_already_uploaded()`), the bot queries the live API of each platform to guarantee the same episode is **never** uploaded twice.
