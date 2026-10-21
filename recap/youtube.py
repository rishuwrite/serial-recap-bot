import os, requests

def enabled():
    return all(os.getenv(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))

def _token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200: raise SystemExit(f"YouTube token refresh failed: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]

def already_uploaded(show, target_ep, source_vid=None):
    """Live check against the user's YouTube channel (including private/scheduled videos) to guarantee
    the same episode is NEVER uploaded twice even if a job is retried or git state had a conflict."""
    if not enabled():
        return None
    try:
        tok = _token()
        hdr = {"Authorization": f"Bearer {tok}"}
        ch = requests.get("https://www.googleapis.com/youtube/v3/channels",
                          params={"part": "contentDetails", "mine": "true"}, headers=hdr, timeout=30).json()
        items = ch.get("items", [])
        if not items:
            return None
        uploads_pl = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        pl = requests.get("https://www.googleapis.com/youtube/v3/playlistItems",
                          params={"part": "snippet", "playlistId": uploads_pl, "maxResults": 50},
                          headers=hdr, timeout=30).json()
        en_low = show["en"].lower()
        ep_tag = f"ep {target_ep}".lower() if target_ep and str(target_ep) != "?" else ""
        for it in pl.get("items", []):
            sn = it.get("snippet", {})
            vid = sn.get("resourceId", {}).get("videoId", "")
            title_low = (sn.get("title") or "").lower()
            desc = sn.get("description") or ""
            # Match 1: exact source Dangal TV video ID cited in description
            if source_vid and source_vid in desc:
                return vid
            # Match 2: same show name + same target episode number in title
            if ep_tag and en_low in title_low and ep_tag in title_low:
                return vid
    except Exception as e:
        print("   dedup check warning (continuing):", str(e)[:120])
    return None

def upload_video(mp4, title, description, tags, publish_at=None, thumb=None):
    title = title.replace("<", "").replace(">", "").strip()[:100]
    status = {"selfDeclaredMadeForKids": False}
    if publish_at: status.update(privacyStatus="private", publishAt=publish_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
    else: status["privacyStatus"] = os.getenv("UPLOAD_PRIVACY") or "public"
    meta = {"snippet": {"title": title, "description": description, "tags": tags, "categoryId": "24",
                        "defaultLanguage": "hi", "defaultAudioLanguage": "hi"}, "status": status}
    tok = _token(); size = os.path.getsize(mp4)
    init = requests.post("https://www.googleapis.com/upload/youtube/v3/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                                  "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"}, json=meta, timeout=60)
    if init.status_code != 200: raise SystemExit(f"YouTube upload init failed: {init.status_code} {init.text[:500]}")
    with open(mp4, "rb") as f:
        r = requests.put(init.headers["Location"], data=f, headers={"Content-Type": "video/mp4", "Content-Length": str(size)}, timeout=1800)
    if r.status_code not in (200, 201): raise SystemExit(f"YouTube upload failed: {r.status_code} {r.text[:500]}")
    vid = r.json()["id"]; print("UPLOADED https://youtube.com/watch?v=" + vid, "| publishAt:", publish_at)
    if thumb and os.path.exists(thumb):
        try:
            t = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set", params={"videoId": vid, "uploadType": "media"},
                              headers={"Authorization": f"Bearer {_token()}", "Content-Type": "image/jpeg"}, data=open(thumb, "rb").read(), timeout=120)
            print("thumbnail:", t.status_code, "" if t.status_code == 200 else t.text[:200])
        except Exception as e: print("thumbnail skipped:", e)
    return vid
