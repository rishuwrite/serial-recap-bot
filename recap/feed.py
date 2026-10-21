import json, os, re, time, calendar, requests, feedparser
import config as S
UA = {"User-Agent": "Mozilla/5.0 (compatible; SerialRecapBot/1.0)"}

def _state(key): return os.path.join(S.BASE, "state", f"{key}.json")
def done_ids(key):
    try: return set(json.load(open(_state(key))))
    except Exception: return set()
def mark_done(key, vid):
    os.makedirs(os.path.join(S.BASE, "state"), exist_ok=True)
    ids = sorted(done_ids(key) | {vid}); json.dump(ids[-60:], open(_state(key), "w"))

def recent_uploads():
    """Latest uploads of the channel. Uses the Data API (50 items) when YT_API_KEY is set, else the RSS feed (15 items)."""
    out = []
    key = os.getenv("YT_API_KEY")
    if key:
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", timeout=30,
                             params={"part": "snippet", "playlistId": S.UPLOADS_PLAYLIST, "maxResults": 50, "key": key}).json()
            for it in r.get("items", []):
                sn = it["snippet"]
                out.append({"id": sn["resourceId"]["videoId"], "title": sn["title"], "published": sn["publishedAt"]})
            print(f"   uploads via API: {len(out)}")
        except Exception as e: print("   API failed:", str(e)[:100])
    if not out:
        feed = feedparser.parse(requests.get(S.FEED, headers=UA, timeout=30).content)
        for e in feed.entries:
            out.append({"id": e.get("yt_videoid") or e.link.split("v=")[-1], "title": e.title, "published": e.get("published", "")})
        print(f"   uploads via RSS: {len(out)}")
    return out

def parse_title(title):
    ep = re.search(r"Episode\s*(\d+)", title, re.I); dt_ = re.search(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", title)
    return (ep.group(1) if ep else ""), (dt_.group(1) if dt_ else "")

def find_episode(key, max_age_h=72):
    show = S.SHOWS[key]; done = done_ids(key)
    now = time.time()
    for v in recent_uploads():
        t = v["title"].lower()
        if show["match"] not in t or "full episode" not in t or v["id"] in done: continue
        # reject if a longer/other show name matches (e.g. 'mann sundar' inside another title)
        if key == "mannsundar" and "atisundar" in t: continue
        try:
            import datetime as dt
            pub = dt.datetime.fromisoformat(v["published"].replace("Z", "+00:00")).timestamp()
            if now - pub > max_age_h * 3600: continue
        except Exception: pass
        ep, date_ = parse_title(v["title"])
        return {"id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}", "title": v["title"], "episode": ep, "date": date_}
    return None

def by_id(video_id):
    """Manual override: build the episode record from a video id using YouTube's oEmbed (title only)."""
    title = requests.get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                         headers=UA, timeout=20).json().get("title", "")
    ep, date_ = parse_title(title)
    return {"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "title": title, "episode": ep, "date": date_}

def show_key_for(title):
    t = title.lower()
    for k, s in S.SHOWS.items():
        if s["match"] in t and not (k == "mannsundar" and "atisundar" in t): return k
    return None
