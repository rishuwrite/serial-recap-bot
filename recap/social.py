"""Multi-platform publishing & Google Drive storage (`recap/social.py`).

Supports:
1. Google Drive automatic Reel upload & retrieval (uses Google OAuth refresh token + Drive REST API v3):
   - Uploads vertical 9:16 Reel MP4 (`<show>_<ep_id>_reel.mp4`), vertical cover JPG, and caption metadata JSON
     into your `GDRIVE_FOLDER_ID` folder during the 12:00 AM IST run.
   - Makes the file readable via link or downloads it when publishing at the scheduled show slot.
2. Facebook Page Video / Reel native scheduling & publishing (Meta Graph API):
   - Schedules the video natively on your Facebook Page using `published=false` and `scheduled_publish_time=<unix_ts>`
     (matching the exact 9:00 AM – 4:00 PM IST slot used for YouTube!).
   - Also supports immediate publishing when `PUBLISH_NOW=true` or when triggered at slot time.
   - Performs a live anti-duplicate check against your Facebook Page videos before uploading.
3. Instagram Reels publishing (Meta Graph API):
   - Because Instagram's Content Publishing API (`/{ig-user-id}/media` -> `/{ig-user-id}/media_publish`)
     does NOT support a native `scheduled_publish_time` parameter for direct API calls, Instagram Reels are:
     a) Stored automatically in Google Drive at 12:00 AM IST alongside their caption & scheduled slot timestamp.
     b) Published automatically at the exact show slot (9:00 AM – 4:00 PM IST) when triggered by Google Apps Script
        (either directly from Google Apps Script or via `only_ig_publish=true` workflow dispatch).
   - Supports BOTH:
     * Direct Resumable Binary Upload (`upload_type=resumable` to `rupload.facebook.com/ig-api-upload/...`) — works with
       local/Google Drive files without needing any third-party CDN!
     * Public URL Container Upload (`video_url` via `INSTAGRAM_VIDEO_URL_TEMPLATE` or Google Apps Script proxy / Drive URL).
   - Performs a live anti-duplicate check against your Instagram account's recent media before publishing.
"""
import datetime as dt, json, os, subprocess, time, requests
from PIL import Image

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# ==============================================================================
# 1. CONFIGURATION & ENABLEMENT HELPERS
# ==============================================================================

def graph_version():
    v = (os.getenv("META_GRAPH_API_VERSION") or "v22.0").strip()
    if not v.startswith("v"):
        v = "v" + v
    return v

def fb_enabled():
    flag = os.getenv("FACEBOOK_ENABLED", "").strip().lower()
    if flag == "false":
        return False
    has_creds = bool(os.getenv("FACEBOOK_PAGE_ID", "").strip() and os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip())
    return has_creds and (flag in ("true", "1", "yes", ""))

def ig_enabled():
    flag = os.getenv("INSTAGRAM_ENABLED", "").strip().lower()
    if flag == "false":
        return False
    ig_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
    ig_tok = (os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    return bool(ig_id and ig_tok) and (flag in ("true", "1", "yes", ""))

def drive_enabled():
    flag = os.getenv("GDRIVE_ENABLED", "").strip().lower()
    if flag == "false":
        return False
    folder = os.getenv("GDRIVE_FOLDER_ID", "").strip()
    cid = (os.getenv("GDRIVE_CLIENT_ID") or os.getenv("YT_CLIENT_ID") or "").strip()
    csec = (os.getenv("GDRIVE_CLIENT_SECRET") or os.getenv("YT_CLIENT_SECRET") or "").strip()
    rtok = (os.getenv("GDRIVE_REFRESH_TOKEN") or os.getenv("YT_REFRESH_TOKEN") or "").strip()
    return bool(folder and cid and csec and rtok)

def should_render_vertical():
    if fb_enabled():
        return True
    rv = os.getenv("RENDER_VERTICAL", "").strip().lower()
    if rv in ("true", "1", "yes"):
        return True
    if rv in ("false", "0", "no"):
        return False
    return ig_enabled() or drive_enabled()


# ==============================================================================
# 2. GOOGLE DRIVE STORAGE (UPLOAD, METADATA, DOWNLOAD, CLEANUP)
# ==============================================================================

def _drive_token():
    cid = (os.getenv("GDRIVE_CLIENT_ID") or os.getenv("YT_CLIENT_ID") or "").strip()
    csec = (os.getenv("GDRIVE_CLIENT_SECRET") or os.getenv("YT_CLIENT_SECRET") or "").strip()
    rtok = (os.getenv("GDRIVE_REFRESH_TOKEN") or os.getenv("YT_REFRESH_TOKEN") or "").strip()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid,
        "client_secret": csec,
        "refresh_token": rtok,
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google Drive OAuth token refresh failed ({r.status_code}): {r.text[:300]}")
    return r.json()["access_token"]

def drive_find_file(filename, folder_id=None):
    """Check if a file with `filename` already exists in the configured Google Drive folder."""
    if not drive_enabled():
        return None
    folder_id = folder_id or os.getenv("GDRIVE_FOLDER_ID", "").strip()
    try:
        tok = _drive_token()
        q = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
        r = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {tok}"},
            params={"q": q, "fields": "files(id, name, size, description, webContentLink, webViewLink)", "pageSize": 5},
            timeout=30,
        )
        if r.status_code == 200:
            files = r.json().get("files", [])
            if files:
                return files[0]
    except Exception as e:
        print("   [Drive] find_file warning:", str(e)[:120])
    return None

def drive_upload_reel(mp4_path, show_key, ep_id, target_ep, title, caption, scheduled_slot_utc=None, thumb_path=None):
    """Upload the vertical Reel MP4 (and metadata JSON) to Google Drive folder so Google Apps Script
    or scheduled jobs can reliably verify and publish it at the show's exact slot."""
    if not drive_enabled():
        return None
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()
    filename = f"{show_key}_{ep_id}_ep{target_ep}_reel.mp4"

    existing = drive_find_file(filename, folder_id)
    if existing and existing.get("id"):
        print(f"   [Drive] Reel already exists in Google Drive: {filename} (id={existing['id']})")
        return existing["id"]

    tok = _drive_token()
    size = os.path.getsize(mp4_path)
    slot_iso = scheduled_slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if scheduled_slot_utc else ""
    slot_ist = scheduled_slot_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M IST") if scheduled_slot_utc else ""

    meta_summary = json.dumps({
        "show": show_key,
        "source_vid": ep_id,
        "target_ep": str(target_ep),
        "scheduled_utc": slot_iso,
        "scheduled_ist": slot_ist,
        "title": title[:120],
    }, ensure_ascii=False)

    init_Meta = {
        "name": filename,
        "parents": [folder_id],
        "description": meta_summary,
        "appProperties": {
            "show_key": show_key,
            "source_vid": ep_id,
            "target_ep": str(target_ep),
            "scheduled_utc": slot_iso,
            "ig_published": "false",
        },
    }

    init = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        json=init_Meta,
        timeout=60,
    )
    if init.status_code not in (200, 201):
        raise RuntimeError(f"Google Drive resumable init failed ({init.status_code}): {init.text[:300]}")

    upload_url = init.headers["Location"]
    with open(mp4_path, "rb") as f:
        up = requests.put(
            upload_url,
            data=f,
            headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
            timeout=1200,
        )
    if up.status_code not in (200, 201):
        raise RuntimeError(f"Google Drive video upload failed ({up.status_code}): {up.text[:300]}")

    file_id = up.json()["id"]
    print(f"   [Drive] Uploaded Reel MP4 -> https://drive.google.com/file/d/{file_id}/view ({filename})")

    # Share file as "anyone with link can read" so public URL / Apps Script proxy can read it seamlessly
    try:
        requests.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"role": "reader", "type": "anyone"},
            timeout=30,
        )
    except Exception as e:
        print("   [Drive] permission warning:", str(e)[:100])

    # Also upload companion sidecar JSON with full caption & tags for Google Apps Script / scheduled IG publisher
    sidecar_name = f"{show_key}_{ep_id}_ep{target_ep}_reel.json"
    sidecar_payload = {
        "show": show_key,
        "source_vid": ep_id,
        "target_ep": str(target_ep),
        "drive_video_id": file_id,
        "video_filename": filename,
        "title": title,
        "caption": caption,
        "scheduled_utc": slot_iso,
        "scheduled_ist": slot_ist,
        "ig_published": False,
    }
    try:
        if not drive_find_file(sidecar_name, folder_id):
            s_bytes = json.dumps(sidecar_payload, ensure_ascii=False, indent=2).encode("utf-8")
            s_init = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
                headers={
                    "Authorization": f"Bearer {tok}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "application/json",
                    "X-Upload-Content-Length": str(len(s_bytes)),
                },
                json={"name": sidecar_name, "parents": [folder_id]},
                timeout=30,
            )
            if s_init.status_code in (200, 201) and "Location" in s_init.headers:
                requests.put(s_init.headers["Location"], data=s_bytes, headers={"Content-Type": "application/json"}, timeout=60)
    except Exception as e:
        print("   [Drive] sidecar json warning:", str(e)[:100])

    return file_id

def drive_download_file(file_id, dest_path):
    """Download a Reel MP4 from Google Drive by file_id into `dest_path`."""
    tok = _drive_token()
    with requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers={"Authorization": f"Bearer {tok}"},
        stream=True,
        timeout=600,
    ) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Google Drive download failed for {file_id} ({r.status_code}): {r.text[:200]}")
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return dest_path

def drive_mark_ig_published(file_id, ig_media_id):
    """Update the Google Drive file's appProperties after Instagram Reel is published."""
    if not (drive_enabled() and file_id):
        return
    try:
        tok = _drive_token()
        requests.patch(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"appProperties": {"ig_published": "true", "ig_media_id": str(ig_media_id)}},
            timeout=30,
        )
        if os.getenv("GDRIVE_DELETE_AFTER_PUBLISH", "false").strip().lower() == "true":
            requests.delete(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=30,
            )
            print(f"   [Drive] Cleaned up published Reel file {file_id} from Drive")
    except Exception as e:
        print("   [Drive] mark published warning:", str(e)[:100])


# ==============================================================================
# 3. FACEBOOK PAGE VIDEO / REEL SCHEDULING & PUBLISHING
# ==============================================================================

def _validate_vertical_video(mp4_path):
    """Reject Facebook uploads unless the encoded video is in a 9:16 portrait format."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", mp4_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        streams = json.loads(result.stdout).get("streams", [])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not verify Facebook video dimensions with ffprobe: {exc}") from exc

    if not streams or not streams[0].get("width") or not streams[0].get("height"):
        raise RuntimeError(f"Could not determine Facebook video dimensions: {mp4_path}")
    width, height = int(streams[0]["width"]), int(streams[0]["height"])
    if abs(width / height - 9 / 16) > 0.01:
        raise ValueError(
            f"Facebook uploads must be 9:16 vertical video; got {width}x{height} for {mp4_path}"
        )

def _validate_vertical_thumbnail(thumb_path):
    """Require a readable 9:16 custom cover for every Facebook upload."""
    if not thumb_path or not os.path.isfile(thumb_path):
        raise ValueError("Facebook uploads require a generated 9:16 custom thumbnail")
    try:
        with Image.open(thumb_path) as thumbnail:
            width, height = thumbnail.size
    except OSError as exc:
        raise RuntimeError(f"Could not verify Facebook thumbnail: {exc}") from exc
    if not height or abs(width / height - 9 / 16) > 0.01:
        raise ValueError(
            f"Facebook thumbnails must be 9:16; got {width}x{height} for {thumb_path}"
        )

def fb_already_uploaded(show, target_ep, source_vid=None):
    """Check recent videos on the Facebook Page (including scheduled/unpublished videos)
    to prevent duplicate Facebook uploads."""
    if not fb_enabled():
        return None
    page_id = os.environ["FACEBOOK_PAGE_ID"].strip()
    token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"].strip()
    ver = graph_version()
    en_low = show["en"].lower()
    ep_tag = f"ep {target_ep}".lower() if target_ep and str(target_ep) != "?" else ""

    try:
        r = requests.get(
            f"https://graph.facebook.com/{ver}/{page_id}/videos",
            params={"fields": "id,title,description,published,scheduled_publish_time", "limit": 50, "access_token": token},
            timeout=30,
        )
        if r.status_code == 200:
            for item in r.json().get("data", []):
                vid = item.get("id", "")
                title_low = (item.get("title") or "").lower()
                desc = item.get("description") or ""
                if source_vid and source_vid in desc:
                    return vid
                if ep_tag and en_low in title_low and ep_tag in title_low:
                    return vid
    except Exception as e:
        print("   [Facebook] dedup check warning (continuing):", str(e)[:120])
    return None

def upload_facebook_video(mp4_path, title, description, publish_at=None, thumb_path=None):
    """Upload and schedule (or immediately publish) a video to a Facebook Page via the
    3-phase Resumable Upload API (`start` -> `transfer` -> `finish`) on `graph-video.facebook.com`.

    When `publish_at` (UTC datetime) is provided and is at least 11 minutes in the future,
    the video is scheduled natively on Facebook with `published=false` and `scheduled_publish_time=<unix_ts>`,
    so it goes live at the exact same minute as YouTube!
    """
    if not fb_enabled():
        return None

    _validate_vertical_video(mp4_path)
    _validate_vertical_thumbnail(thumb_path)
    page_id = os.environ["FACEBOOK_PAGE_ID"].strip()
    token = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"].strip()
    ver = graph_version()
    size = os.path.getsize(mp4_path)
    base_url = f"https://graph-video.facebook.com/{ver}/{page_id}/videos"

    # Phase 1: Start resumable upload session
    r_start = requests.post(
        base_url,
        data={
            "upload_phase": "start",
            "file_size": str(size),
            "access_token": token,
        },
        timeout=60,
    )
    if r_start.status_code != 200:
        raise RuntimeError(f"Facebook upload start failed ({r_start.status_code}): {r_start.text[:400]}")
    start_data = r_start.json()
    session_id = start_data["upload_session_id"]
    video_id = start_data["video_id"]
    start_offset = int(start_data.get("start_offset", 0))
    end_offset = int(start_data.get("end_offset", size))

    # Phase 2: Transfer binary chunks
    with open(mp4_path, "rb") as f:
        while start_offset < end_offset:
            f.seek(start_offset)
            chunk = f.read(end_offset - start_offset)
            r_tr = requests.post(
                base_url,
                data={
                    "upload_phase": "transfer",
                    "upload_session_id": session_id,
                    "start_offset": str(start_offset),
                    "access_token": token,
                },
                files={"video_file_chunk": ("chunk.mp4", chunk, "application/octet-stream")},
                timeout=600,
            )
            if r_tr.status_code != 200:
                raise RuntimeError(f"Facebook upload transfer failed ({r_tr.status_code}): {r_tr.text[:400]}")
            tr_data = r_tr.json()
            start_offset = int(tr_data.get("start_offset", size))
            end_offset = int(tr_data.get("end_offset", size))

    # Phase 3: Finish and set schedule or immediate publish
    custom_cap = os.getenv("FACEBOOK_CAPTION", "").strip()
    final_desc = custom_cap if custom_cap else description
    finish_data = {
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "title": title[:250],
        "description": final_desc,
        "access_token": token,
    }

    now_utc = dt.datetime.now(dt.timezone.utc)
    # Meta requires scheduled_publish_time to be at least 10 minutes in the future (we enforce 11m buffer)
    if publish_at and publish_at > now_utc + dt.timedelta(minutes=11):
        unix_ts = int(publish_at.timestamp())
        finish_data["published"] = "false"
        finish_data["scheduled_publish_time"] = str(unix_ts)
        sched_label = f"scheduled for {publish_at.astimezone(IST).strftime('%Y-%m-%d %I:%M %p IST')} (unix={unix_ts})"
    else:
        finish_data["published"] = "true"
        sched_label = "published immediately"

    files_finish = {}
    thumb_fh = None
    if thumb_path and os.path.exists(thumb_path):
        thumb_fh = open(thumb_path, "rb")
        files_finish["thumb"] = ("thumb.jpg", thumb_fh, "image/jpeg")

    try:
        r_fin = requests.post(
            base_url,
            data=finish_data,
            files=files_finish if files_finish else None,
            timeout=120,
        )
    finally:
        if thumb_fh:
            thumb_fh.close()

    if r_fin.status_code != 200:
        raise RuntimeError(f"Facebook upload finish failed ({r_fin.status_code}): {r_fin.text[:400]}")

    print(f"   [Facebook] UPLOADED video_id={video_id} | {sched_label}")
    return str(video_id)


# ==============================================================================
# 4. INSTAGRAM REELS PUBLISHING (RESUMABLE BINARY + PUBLIC URL SUPPORT)
# ==============================================================================

def ig_already_uploaded(show, target_ep, source_vid=None):
    """Check the Instagram Professional account's recent media to ensure the same Reel
    is never published twice."""
    if not ig_enabled():
        return None
    ig_id = os.environ["INSTAGRAM_USER_ID"].strip()
    token = (os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    ver = graph_version()
    en_low = show["en"].lower()
    ep_tag = f"ep {target_ep}".lower() if target_ep and str(target_ep) != "?" else ""

    try:
        r = requests.get(
            f"https://graph.facebook.com/{ver}/{ig_id}/media",
            params={"fields": "id,caption,media_type,permalink,timestamp", "limit": 35, "access_token": token},
            timeout=30,
        )
        if r.status_code == 200:
            for item in r.json().get("data", []):
                mid = item.get("id", "")
                cap = item.get("caption") or ""
                cap_low = cap.lower()
                if source_vid and source_vid in cap:
                    return mid
                if ep_tag and en_low in cap_low and ep_tag in cap_low:
                    return mid
    except Exception as e:
        print("   [Instagram] dedup check warning (continuing):", str(e)[:120])
    return None

def _poll_ig_container(container_id, token, ver, timeout_s=420):
    """Poll `GET /{container_id}?fields=status_code,status` until `FINISHED`."""
    deadline = time.time() + timeout_s
    last_status = "IN_PROGRESS"
    while time.time() < deadline:
        time.sleep(12)
        r = requests.get(
            f"https://graph.facebook.com/{ver}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        if r.status_code == 200:
            d = r.json()
            sc = (d.get("status_code") or "").upper()
            last_status = f"{sc} ({d.get('status', '')})"
            print(f"   [Instagram] container {container_id} status: {last_status}")
            if sc in ("FINISHED", "PUBLISHED"):
                return True
            if sc in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram container {container_id} failed with {last_status}: {d}")
    raise RuntimeError(f"Instagram container {container_id} timed out after {timeout_s}s (last={last_status})")

def publish_instagram_reel(mp4_path, caption, share_to_feed=True, thumb_offset_ms=2000, video_url=None):
    """Publish a vertical 9:16 MP4 as an Instagram Reel.

    Tries:
    1. If `video_url` or `INSTAGRAM_VIDEO_URL_TEMPLATE` is provided, creates a standard `video_url` Reel container.
    2. Otherwise (or if URL container fails), uses Meta's Resumable Binary Upload protocol (`upload_type=resumable`
       + binary POST to `https://rupload.facebook.com/ig-api-upload/{ver}/{container_id}`), which uploads the MP4
       bytes directly from GitHub Actions / Google Drive without needing any external web server!
    """
    if not ig_enabled():
        return None

    ig_id = os.environ["INSTAGRAM_USER_ID"].strip()
    token = (os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    ver = graph_version()
    custom_cap = os.getenv("INSTAGRAM_CAPTION", "").strip()
    final_caption = (custom_cap if custom_cap else caption)[:2150]

    url_tmpl = os.getenv("INSTAGRAM_VIDEO_URL_TEMPLATE", "").strip()
    if not video_url and url_tmpl and mp4_path:
        video_url = url_tmpl.replace("{filename}", os.path.basename(mp4_path))

    container_id = None

    # Method A: Public HTTPS URL container (if configured)
    if video_url:
        print(f"   [Instagram] creating Reel container via video_url: {video_url[:80]}...")
        r_cont = requests.post(
            f"https://graph.facebook.com/{ver}/{ig_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": final_caption,
                "share_to_feed": "true" if share_to_feed else "false",
                "thumb_offset": str(thumb_offset_ms),
                "access_token": token,
            },
            timeout=60,
        )
        if r_cont.status_code == 200 and r_cont.json().get("id"):
            container_id = r_cont.json()["id"]
            try:
                _poll_ig_container(container_id, token, ver)
            except Exception as e:
                print(f"   [Instagram] video_url container failed ({e}); falling back to direct resumable binary upload...")
                container_id = None
        else:
            print(f"   [Instagram] video_url init failed ({r_cont.status_code}: {r_cont.text[:200]}); falling back to resumable upload...")

    # Method B: Direct Resumable Binary Upload (No external hosting server required)
    if not container_id:
        if not (mp4_path and os.path.exists(mp4_path)):
            raise RuntimeError("Instagram Reel publish requires either a valid local/Drive MP4 file or a reachable video_url")
        size = os.path.getsize(mp4_path)
        print(f"   [Instagram] initializing resumable Reel container ({size} bytes)...")
        r_init = requests.post(
            f"https://graph.facebook.com/{ver}/{ig_id}/media",
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": final_caption,
                "share_to_feed": "true" if share_to_feed else "false",
                "thumb_offset": str(thumb_offset_ms),
                "access_token": token,
            },
            timeout=60,
        )
        if r_init.status_code != 200:
            raise RuntimeError(f"Instagram resumable container init failed ({r_init.status_code}): {r_init.text[:400]}")
        init_json = r_init.json()
        container_id = init_json["id"]
        rupload_uri = init_json.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{ver}/{container_id}"

        with open(mp4_path, "rb") as f:
            video_bytes = f.read()

        r_up = requests.post(
            rupload_uri,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            data=video_bytes,
            timeout=900,
        )
        if r_up.status_code != 200:
            raise RuntimeError(f"Instagram binary rupload failed ({r_up.status_code}): {r_up.text[:400]}")

        _poll_ig_container(container_id, token, ver)

    # Step 3: Publish the finished container
    r_pub = requests.post(
        f"https://graph.facebook.com/{ver}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    if r_pub.status_code != 200:
        raise RuntimeError(f"Instagram media_publish failed ({r_pub.status_code}): {r_pub.text[:400]}")

    ig_media_id = str(r_pub.json().get("id", ""))
    print(f"   [Instagram] PUBLISHED Reel! ig_media_id={ig_media_id}")
    return ig_media_id
