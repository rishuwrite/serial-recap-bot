/**
 * 100% FREE External Cron, Multi-Platform Slot Publisher & Log-Inspecting Watchdog
 * for Serial Recap Bot (Google Apps Script)
 *
 * WHAT THIS SCRIPT DOES:
 * 1. 12:00 AM IST Midnight Trigger (`triggerNightly12AM`):
 *    - Triggers GitHub Actions `recap.yml` (`only_show=all`, `publish_now=false`).
 *    - GitHub Actions generates both the 16:9 video and 9:16 vertical Reel, natively schedules
 *      YouTube AND Facebook Page Videos for their exact 9:00 AM – 4:00 PM IST slots, and
 *      automatically saves the vertical 9:16 Reel MP4 + caption JSON into your Google Drive folder!
 *
 * 2. Hourly 9:00 AM – 4:00 PM IST Slot Trigger (`hourlySlotPublisherAndChecker`):
 *    - Because Meta's Instagram Graph API does not have a `scheduled_publish_time` field for direct API calls,
 *      this trigger fires at the top of every hour (9 AM, 10 AM, 11 AM, 12 PM, 1 PM, 2 PM, 3 PM, 4 PM IST)
 *      for the exact show scheduled for that hour:
 *        09:00 IST -> kaisi      (Kaisi Teri Dillagi)
 *        10:00 IST -> bhabhi     (Hamari Bhabhi Number 1)
 *        11:00 IST -> sohni      (Sohni Aur Nahi Koi Honi)
 *        12:00 IST -> rimjhim    (Rimjhim)
 *        13:00 IST -> mannsundar (Mann Sundar)
 *        14:00 IST -> atisundar  (Mann Atisundar)
 *        15:00 IST -> patibrahma (Pati Brahmachari)
 *        16:00 IST -> ishq       (Ishq Junooni)
 *    - It checks your Google Drive folder (`GDRIVE_FOLDER_ID`) to verify the Reel MP4 is ready,
 *      and can EITHER:
 *      (a) Publish the Reel directly from Google Drive to Instagram via Meta's Resumable Upload API
 *          (if `INSTAGRAM_USER_ID` & `INSTAGRAM_ACCESS_TOKEN` are filled in below), AND/OR
 *      (b) Dispatch GitHub Actions (`only_show=<show>`, `only_ig_publish=true`) so GitHub Actions
 *          pulls the Reel from Google Drive, publishes it to Instagram, and updates `state/<show>_status.json`!
 *    - Result: YouTube, Facebook, and Instagram ALL go live at the exact same scheduled hour!
 *
 * 3. Every-2-Hours Self-Healing Watchdog (`watchdogCheckAndRerun`):
 *    - Inspects GitHub Actions workflow runs, job conclusions, and `state/<show>_status.json` files.
 *    - If any show failed at midnight, or if any platform (YouTube, Facebook, Google Drive, or Instagram)
 *      was missed, automatically triggers a targeted rerun for ONLY that show.
 */

// ==================== REQUIRED CONFIGURATION ====================
const GITHUB_OWNER  = "YOUR_GITHUB_USERNAME";
const GITHUB_REPO   = "serial-recap-bot";
const GITHUB_PAT    = "YOUR_GITHUB_PAT_TOKEN";       // GitHub PAT with `repo` and `workflow` scopes
const WORKFLOW_FILE = "recap.yml";
const BRANCH        = "main";

// Optional: Set your Google Drive Folder ID so Apps Script can directly inspect & verify stored Reels in Drive
const GDRIVE_FOLDER_ID = "YOUR_GOOGLE_DRIVE_FOLDER_ID"; // Leave blank or fill in your Drive Folder ID

// Optional: Direct Apps Script -> Instagram Publishing (if left blank, Apps Script dispatches GitHub Actions `only_ig_publish=true` instead!)
const INSTAGRAM_USER_ID      = ""; // Optional: Your Instagram Professional Account ID (if you want Apps Script to publish directly too)
const INSTAGRAM_ACCESS_TOKEN = ""; // Optional: Your Meta/Instagram Long-Lived Access Token
const META_GRAPH_API_VERSION = "v22.0";

// Exact IST Hour -> Show Key Schedule (Matches `recap/config.py`)
const SLOT_MAP_IST = {
  9:  "kaisi",
  10: "bhabhi",
  11: "sohni",
  12: "rimjhim",
  13: "mannsundar",
  14: "atisundar",
  15: "patibrahma",
  16: "ishq"
};
const SHOW_KEYS = ["kaisi", "bhabhi", "sohni", "rimjhim", "mannsundar", "atisundar", "patibrahma", "ishq"];

/**
 * Run `setupTriggers()` ONCE in the Google Apps Script editor to install all 3 automated triggers.
 */
function setupTriggers() {
  // Remove any old duplicate triggers first
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // 1. Exact 12:00 AM IST (Midnight) Nightly Trigger -> Renders all 8 shows, schedules YT & FB, uploads Reels to Drive
  ScriptApp.newTrigger("triggerNightly12AM")
    .timeBased()
    .atHour(0)
    .nearMinute(1)
    .everyDays(1)
    .inTimezone("Asia/Kolkata")
    .create();

  // 2. Hourly Trigger -> Fires every hour to publish the scheduled show's Instagram Reel at 9 AM - 4 PM IST sharp
  ScriptApp.newTrigger("hourlySlotPublisherAndChecker")
    .timeBased()
    .everyHours(1)
    .create();

  // 3. Watchdog Log-Inspector & Auto-Rerunner -> Checks every 2 hours to catch & heal any failed job
  ScriptApp.newTrigger("watchdogCheckAndRerun")
    .timeBased()
    .everyHours(2)
    .create();

  Logger.log("Installed: (1) 12:00 AM IST Nightly Trigger, (2) Hourly 9 AM-4 PM IST Slot Publisher, (3) 2-Hour Watchdog!");
}

/**
 * 1. Fires at 12:00 AM IST every night to generate & schedule all 8 videos for 9 AM - 4 PM IST.
 */
function triggerNightly12AM() {
  dispatchWorkflow("all", false, false);
}

/**
 * 2. Fires every hour. During 9:00 AM – 4:00 PM IST, identifies the show scheduled for this hour:
 *    - Checks `state/<show>_status.json` in GitHub and/or the Google Drive folder.
 *    - Publishes the pre-rendered Reel to Instagram so YouTube, Facebook, and Instagram go live simultaneously!
 */
function hourlySlotPublisherAndChecker() {
  const nowIst = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const hourIst = nowIst.getHours();
  const showKey = SLOT_MAP_IST[hourIst];

  if (!showKey) {
    Logger.log(`Current IST hour (${hourIst}:00) is not a 9 AM - 4 PM show slot; skipping slot publish.`);
    return;
  }

  Logger.log(`=== [SLOT ${hourIst}:00 IST] Processing scheduled slot for show '${showKey}' ===`);

  // Check show status in GitHub repo `state/<showKey>_status.json`
  const st = fetchShowStatusFromGitHub(showKey);
  const todayStr = Utilities.formatDate(new Date(), "Asia/Kolkata", "yyyy-MM-dd");

  if (st && st.date_ist === todayStr && st.instagram_media_id) {
    Logger.log(`[${showKey}] Instagram Reel already published today (ig_media_id=${st.instagram_media_id}). All 3 platforms live!`);
    return;
  }

  // Optional: If GDRIVE_FOLDER_ID is configured in Apps Script, check the Drive folder for today's Reel
  const driveReel = findLatestReelInDrive(showKey);
  if (driveReel) {
    Logger.log(`[${showKey}] Found pre-rendered Reel in Google Drive: ${driveReel.name} (fileId=${driveReel.id})`);
    // If direct Instagram credentials are set in Apps Script, try direct publish from Drive first
    if (INSTAGRAM_USER_ID && INSTAGRAM_ACCESS_TOKEN) {
      const igId = publishDriveReelDirectlyToInstagram(driveReel);
      if (igId) {
        Logger.log(`[${showKey}] Published Reel directly from Apps Script to Instagram! ig_media_id=${igId}`);
      }
    }
  } else {
    Logger.log(`[${showKey}] No Drive check or file not yet in Drive; dispatching GitHub workflow to handle IG publish / recovery.`);
  }

  // Always dispatch `only_ig_publish=true` on GitHub Actions so `state/<show>_status.json` is verified & updated
  // (If Apps Script already published it above, `social.ig_already_uploaded()` in Python detects it in 2 seconds and records the ID without duplicating!)
  dispatchWorkflow(showKey, true, true);
}

/**
 * 3. Watchdog Log-Inspector & Auto-Rerunner (runs every 2 hours).
 */
function watchdogCheckAndRerun() {
  const nowIst = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const hourIst = nowIst.getHours();
  // Run active recovery checks between 2:00 AM IST and 6:00 PM IST
  if (hourIst < 2 || hourIst > 18) {
    Logger.log("Outside recovery window (02:00 - 18:00 IST); skipping.");
    return;
  }

  const runsUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=10`;
  const resp = UrlFetchApp.fetch(runsUrl, { headers: ghHeaders(), muteHttpExceptions: true });
  if (resp.getResponseCode() !== 200) {
    Logger.log("Failed to fetch runs: " + resp.getContentText());
    return;
  }

  const runs = JSON.parse(resp.getContentText()).workflow_runs || [];
  const todayStr = Utilities.formatDate(new Date(), "Asia/Kolkata", "yyyy-MM-dd");

  // Check if any run is currently in_progress or queued
  const activeRun = runs.find(r => r.status === "in_progress" || r.status === "queued");
  if (activeRun) {
    Logger.log("A workflow run is currently active (ID: " + activeRun.id + "); waiting for it to finish.");
    return;
  }

  // Filter runs from today (IST)
  const todayRuns = runs.filter(r => {
    const runDateIst = Utilities.formatDate(new Date(r.created_at), "Asia/Kolkata", "yyyy-MM-dd");
    return runDateIst === todayStr;
  });

  if (todayRuns.length === 0) {
    Logger.log("No workflow run found for today (" + todayStr + ")! Triggering full nightly run now...");
    dispatchWorkflow("all", false, false);
    return;
  }

  // Inspect jobs of the latest run today to see if any show failed
  const latestRun = todayRuns[0];
  const jobsUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runs/${latestRun.id}/jobs?per_page=50`;
  const jobsResp = UrlFetchApp.fetch(jobsUrl, { headers: ghHeaders(), muteHttpExceptions: true });
  if (jobsResp.getResponseCode() === 200) {
    const jobs = JSON.parse(jobsResp.getContentText()).jobs || [];
    for (const job of jobs) {
      const name = (job.name || "").toLowerCase();
      const conclusion = (job.conclusion || "").toLowerCase();
      if (conclusion === "failure" || conclusion === "timed_out" || conclusion === "cancelled") {
        for (const showKey of SHOW_KEYS) {
          if (name.includes(showKey)) {
            Logger.log(`Detected failed job for show '${showKey}' (${conclusion}). Dispatched targeted rerun!`);
            dispatchWorkflow(showKey, false, false);
            Utilities.sleep(2000);
          }
        }
      }
    }
  }

  // Also run the repo's internal multi-platform watchdog check at 4-5 AM IST and 5-6 PM IST
  if (hourIst === 4 || hourIst === 5 || hourIst === 17) {
    dispatchWorkflow("watchdog", false, false);
  }
}

/**
 * Helper: Dispatch GitHub Actions `recap.yml` workflow.
 */
function dispatchWorkflow(onlyShow, publishNow, onlyIgPublish) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const payload = {
    ref: BRANCH,
    inputs: {
      only_show: onlyShow,
      video_id: "",
      test_mode: "false",
      upload: "true",
      publish_now: publishNow ? "true" : "false",
      only_ig_publish: onlyIgPublish ? "true" : "false",
      render_vertical: "true"
    }
  };
  const res = UrlFetchApp.fetch(url, {
    method: "post",
    headers: ghHeaders(),
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  Logger.log(`Dispatched workflow (only_show=${onlyShow}, publish_now=${publishNow}, only_ig_publish=${onlyIgPublish}): HTTP ${res.getResponseCode()}`);
}

/**
 * Helper: Read `state/<showKey>_status.json` from the GitHub repository via REST API.
 */
function fetchShowStatusFromGitHub(showKey) {
  try {
    const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/state/${showKey}_status.json?ref=${BRANCH}`;
    const res = UrlFetchApp.fetch(url, { headers: ghHeaders(), muteHttpExceptions: true });
    if (res.getResponseCode() === 200) {
      const contentB64 = (JSON.parse(res.getContentText()).content || "").replace(/\s/g, "");
      const jsonStr = Utilities.newBlob(Utilities.base64Decode(contentB64)).getDataAsString("UTF-8");
      return JSON.parse(jsonStr);
    }
  } catch (e) {
    Logger.log(`Status read warning for ${showKey}: ${e}`);
  }
  return null;
}

/**
 * Helper: Inspect Google Drive folder (`GDRIVE_FOLDER_ID`) for the newest unpublished Reel MP4 & sidecar JSON for `showKey`.
 */
function findLatestReelInDrive(showKey) {
  if (!GDRIVE_FOLDER_ID || GDRIVE_FOLDER_ID === "YOUR_GOOGLE_DRIVE_FOLDER_ID") {
    return null;
  }
  try {
    const folder = DriveApp.getFolderById(GDRIVE_FOLDER_ID);
    const files = folder.getFiles();
    let newestMp4 = null;
    let newestTime = 0;
    while (files.hasNext()) {
      const f = files.next();
      const name = f.getName();
      if (name.indexOf(showKey + "_") === 0 && name.indexOf("_reel.mp4") !== -1) {
        const t = f.getDateCreated().getTime();
        if (t > newestTime) {
          newestTime = t;
          newestMp4 = f;
        }
      }
    }
    if (!newestMp4) return null;

    // Look for companion .json sidecar with full Hindi caption
    let caption = `🔥 ${showKey.toUpperCase()} महा-ट्विस्ट! #DangalTV #HindiSerial #ReelsIndia`;
    const jsonName = newestMp4.getName().replace("_reel.mp4", "_reel.json");
    const jsonFiles = folder.getFilesByName(jsonName);
    if (jsonFiles.hasNext()) {
      const metaObj = JSON.parse(jsonFiles.next().getBlob().getDataAsString("UTF-8"));
      if (metaObj.caption) caption = metaObj.caption;
    }
    return {
      id: newestMp4.getId(),
      name: newestMp4.getName(),
      file: newestMp4,
      caption: caption
    };
  } catch (e) {
    Logger.log(`Drive lookup warning for ${showKey}: ${e}`);
    return null;
  }
}

/**
 * Optional Helper: Directly upload Reel bytes from Google Drive to Instagram Graph API (`rupload.facebook.com`)
 * inside Google Apps Script.
 */
function publishDriveReelDirectlyToInstagram(driveReel) {
  try {
    const blob = driveReel.file.getBlob();
    const bytes = blob.getBytes();
    const size = bytes.length;

    // 1. Initialize Resumable Reel Container
    const initUrl = `https://graph.facebook.com/${META_GRAPH_API_VERSION}/${INSTAGRAM_USER_ID}/media`;
    const initRes = UrlFetchApp.fetch(initUrl, {
      method: "post",
      payload: {
        media_type: "REELS",
        upload_type: "resumable",
        caption: driveReel.caption,
        share_to_feed: "true",
        thumb_offset: "2000",
        access_token: INSTAGRAM_ACCESS_TOKEN
      },
      muteHttpExceptions: true
    });
    if (initRes.getResponseCode() !== 200) {
      Logger.log("IG direct init failed: " + initRes.getContentText());
      return null;
    }
    const initData = JSON.parse(initRes.getContentText());
    const containerId = initData.id;
    const ruploadUri = initData.uri || `https://rupload.facebook.com/ig-api-upload/${META_GRAPH_API_VERSION}/${containerId}`;

    // 2. Upload Binary Bytes to rupload.facebook.com
    const upRes = UrlFetchApp.fetch(ruploadUri, {
      method: "post",
      headers: {
        "Authorization": "OAuth " + INSTAGRAM_ACCESS_TOKEN,
        "offset": "0",
        "file_size": String(size)
      },
      contentType: "application/octet-stream",
      payload: bytes,
      muteHttpExceptions: true
    });
    if (upRes.getResponseCode() !== 200) {
      Logger.log("IG direct binary upload failed: " + upRes.getContentText());
      return null;
    }

    // 3. Poll Container until FINISHED (up to ~3.5 minutes inside Apps Script's 6-minute execution limit)
    for (let i = 0; i < 18; i++) {
      Utilities.sleep(12000);
      const stRes = UrlFetchApp.fetch(
        `https://graph.facebook.com/${META_GRAPH_API_VERSION}/${containerId}?fields=status_code,status&access_token=${encodeURIComponent(INSTAGRAM_ACCESS_TOKEN)}`,
        { muteHttpExceptions: true }
      );
      if (stRes.getResponseCode() === 200) {
        const stData = JSON.parse(stRes.getContentText());
        const code = (stData.status_code || "").toUpperCase();
        Logger.log(`IG container ${containerId} status: ${code}`);
        if (code === "FINISHED") break;
        if (code === "ERROR" || code === "EXPIRED") return null;
      }
    }

    // 4. Publish Container
    const pubRes = UrlFetchApp.fetch(`https://graph.facebook.com/${META_GRAPH_API_VERSION}/${INSTAGRAM_USER_ID}/media_publish`, {
      method: "post",
      payload: {
        creation_id: containerId,
        access_token: INSTAGRAM_ACCESS_TOKEN
      },
      muteHttpExceptions: true
    });
    if (pubRes.getResponseCode() === 200) {
      return JSON.parse(pubRes.getContentText()).id;
    }
    Logger.log("IG media_publish failed: " + pubRes.getContentText());
  } catch (e) {
    Logger.log("Direct IG publish exception: " + e);
  }
  return null;
}

function ghHeaders() {
  return {
    "Authorization": "Bearer " + GITHUB_PAT,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
  };
}
