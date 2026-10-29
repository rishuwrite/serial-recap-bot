import datetime as dt, io, json, os, shutil, sys, time, traceback, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config as S, feed, gemini, images, voice, render, meta, youtube, social
from PIL import Image

# Capture console logs in memory so any failure writes its exact log tail to state/<show>_status.json
_LOG_BUF = io.StringIO()
class _Tee:
    def __init__(self, orig): self.orig = orig
    def write(self, s):
        self.orig.write(s)
        _LOG_BUF.write(s)
    def flush(self): self.orig.flush()
sys.stdout = _Tee(sys.stdout)
sys.stderr = _Tee(sys.stderr)

KEY = os.environ["SHOW_KEY"]; show = S.SHOWS[KEY]
TEST = os.getenv("TEST_MODE", "").lower() == "true"
VIDEO_ID = os.getenv("VIDEO_ID", "").strip()
event = os.getenv("EVENT_NAME", "")
publish_now = os.getenv("PUBLISH_NOW", "false").lower() == "true"
only_ig_publish = os.getenv("ONLY_IG_PUBLISH", "false").lower() == "true"
do_upload = (not TEST) and os.getenv("DO_UPLOAD", "true").lower() != "false"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
tmp = os.path.join(S.BASE, f"tmp_{KEY}"); out_dir = os.path.join(S.BASE, "output"); os.makedirs(tmp, exist_ok=True); os.makedirs(out_dir, exist_ok=True)

SOURCE_EP_NO, EP_NO, ep = "", "", None

# ==============================================================================
# FAST PATH: ONLY_IG_PUBLISH=true (Triggered by Google Apps Script at exact show slot 9 AM - 4 PM IST)
# Fetches the pre-rendered vertical Reel MP4 from Google Drive and publishes to Instagram Reels immediately!
# ==============================================================================
if only_ig_publish:
    try:
        st = feed.get_status(KEY)
        vid = st.get("source_video_id", "")
        src_ep = st.get("source_episode", "")
        target_ep = st.get("target_episode", "")
        drive_id = st.get("gdrive_file_id", "")
        existing_ig = st.get("instagram_media_id", "")
        print(f"== [IG-SLOT-PUBLISH] {show['en']} | source_vid={vid} | target_ep={target_ep} | drive_id={drive_id} ==")

        if not social.ig_enabled():
            print("   Instagram is not enabled or missing credentials; skipping.")
            sys.exit(0)

        if existing_ig:
            print(f"   Already published to Instagram (ig_media_id={existing_ig}); skipping.")
            sys.exit(0)

        live_ig = social.ig_already_uploaded(show, target_ep, source_vid=vid)
        if live_ig:
            print(f"   Live check found Reel already on Instagram ({live_ig}); updating state.")
            feed.record_status(KEY, "success", vid=vid, episode=src_ep, target_ep=target_ep, ig_id=live_ig, log_tail=_LOG_BUF.getvalue())
            sys.exit(0)

        if not drive_id and social.drive_enabled() and vid:
            found = social.drive_find_file(f"{KEY}_{vid}_ep{target_ep}_reel.mp4")
            if found:
                drive_id = found["id"]

        if not drive_id:
            print("   No pre-rendered Reel found in Google Drive for today; falling through to full pipeline with PUBLISH_NOW=true...")
            publish_now = True
        else:
            reel_mp4 = os.path.join(tmp, f"{KEY}_{vid}_reel.mp4")
            print(f"   Downloading Reel from Google Drive (file_id={drive_id})...")
            social.drive_download_file(drive_id, reel_mp4)

            caption = f"🔥 {show['hi']} ({show['en']}) | Ep {target_ep} महा-ट्विस्ट! #DangalTV #HindiSerial #ReelsIndia"
            sidecar = social.drive_find_file(f"{KEY}_{vid}_ep{target_ep}_reel.json")
            if sidecar and sidecar.get("id"):
                try:
                    sc_path = os.path.join(tmp, "sidecar.json")
                    social.drive_download_file(sidecar["id"], sc_path)
                    sc_data = json.load(open(sc_path))
                    caption = sc_data.get("caption") or caption
                except Exception as e:
                    print("   sidecar read warning:", e)

            ig_id = social.publish_instagram_reel(reel_mp4, caption)
            social.drive_mark_ig_published(drive_id, ig_id)
            feed.record_status(KEY, "success", vid=vid, episode=src_ep, target_ep=target_ep, ig_id=ig_id, drive_id=drive_id, log_tail=_LOG_BUF.getvalue())
            print(f"== [IG-SLOT-PUBLISH] Done! ig_media_id={ig_id} ==")
            sys.exit(0)
    except SystemExit:
        raise
    except Exception as ex:
        tb = traceback.format_exc()
        print("IG SLOT PUBLISH ERROR:\n", tb)
        feed.record_status(KEY, "failed", error=f"IG_PUBLISH: {type(ex).__name__}: {ex}", log_tail=_LOG_BUF.getvalue())
        raise SystemExit(1)

try:
    render_vert = social.should_render_vertical()
    print(f"== {show['en']} | slot={show['slot'][0]:02d}:{show['slot'][1]:02d} IST | test={TEST} | upload={do_upload} | publish_now={publish_now} | vertical_reel={render_vert} ==")
    feed.record_status(KEY, "running", log_tail=_LOG_BUF.getvalue())

    print("1/7 find episode")
    ep = feed.by_id(VIDEO_ID) if VIDEO_ID else feed.find_episode(KEY)
    if VIDEO_ID and ep and feed.show_key_for(ep["title"]) != KEY:
        print("   this video belongs to another show; skipping")
        feed.record_status(KEY, "skipped_other_show", vid=VIDEO_ID, log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    if not ep:
        print("   no new unseen full episode for this show right now")
        feed.record_status(KEY, "no_new_episode", log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    print("  ", ep["title"], "|", ep["url"])
    SOURCE_EP_NO, SOURCE_DATE = ep["episode"] or "?", ep["date"] or dt.datetime.now(IST).strftime("%d %b %Y")

    # The video is framed as a two-day-ahead prediction: metadata/on-screen target date and episode are +2.
    def next_target(source_ep, source_date):
        target_ep = str(int(source_ep) + 2) if str(source_ep).isdigit() else source_ep
        parsed = None
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try: parsed = dt.datetime.strptime(source_date, fmt); break
            except ValueError: pass
        target_date = (parsed + dt.timedelta(days=2)).strftime("%d %b %Y") if parsed else (dt.datetime.now(IST) + dt.timedelta(days=2)).strftime("%d %b %Y")
        return target_ep, target_date

    EP_NO, DATE = next_target(SOURCE_EP_NO, SOURCE_DATE)
    print(f"  source episode/date: {SOURCE_EP_NO} / {SOURCE_DATE}; two-day target: {EP_NO} / {DATE}")

    # Check existing platform states so retries only run missing destinations
    st_prev = feed.get_status(KEY)
    same_ep = (st_prev.get("source_video_id") == ep["id"])
    yt_done_id = st_prev.get("youtube_video_id", "") if same_ep else ""
    fb_done_id = st_prev.get("facebook_video_id", "") if same_ep else ""
    ig_done_id = st_prev.get("instagram_media_id", "") if same_ep else ""
    drive_done_id = st_prev.get("gdrive_file_id", "") if same_ep else ""

    if do_upload and youtube.enabled() and not yt_done_id:
        yt_done_id = youtube.already_uploaded(show, EP_NO, source_vid=ep["id"]) or ""
    if do_upload and social.fb_enabled() and not fb_done_id:
        fb_done_id = social.fb_already_uploaded(show, EP_NO, source_vid=ep["id"]) or ""
    if do_upload and social.ig_enabled() and not ig_done_id:
        ig_done_id = social.ig_already_uploaded(show, EP_NO, source_vid=ep["id"]) or ""
    if do_upload and social.drive_enabled() and not drive_done_id:
        f_drv = social.drive_find_file(f"{KEY}_{ep['id']}_ep{EP_NO}_reel.mp4")
        if f_drv:
            drive_done_id = f_drv.get("id", "")

    need_yt = do_upload and youtube.enabled() and not yt_done_id
    need_fb = do_upload and social.fb_enabled() and not fb_done_id
    need_drive = do_upload and social.drive_enabled() and not drive_done_id
    need_ig_now = do_upload and social.ig_enabled() and publish_now and not ig_done_id

    # If all enabled platforms are already done/scheduled, mark state done and exit cleanly
    if not VIDEO_ID and feed.is_done(KEY, ep["id"], SOURCE_EP_NO) and not (need_yt or need_fb or need_drive or need_ig_now):
        print(f"   episode {SOURCE_EP_NO} ({ep['id']}) already uploaded/scheduled across all enabled platforms; skipping")
        feed.record_status(KEY, "already_uploaded", vid=ep["id"], episode=SOURCE_EP_NO, target_ep=EP_NO,
                           yt_id=yt_done_id, fb_id=fb_done_id, ig_id=ig_done_id, drive_id=drive_done_id, log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    if do_upload and not (need_yt or need_fb or need_drive or need_ig_now) and (yt_done_id or fb_done_id or drive_done_id):
        print(f"   all enabled platforms already have episode {EP_NO} (yt={yt_done_id}, fb={fb_done_id}, drive={drive_done_id}); syncing state and skipping")
        feed.mark_done(KEY, ep["id"], episode_no=SOURCE_EP_NO, target_ep=EP_NO,
                       yt_id=yt_done_id, fb_id=fb_done_id, ig_id=ig_done_id, drive_id=drive_done_id)
        sys.exit(0)

    def hindi_date(d):   # on-screen text must be Devanagari (the font has no Latin letters)
        import re
        m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", d or "")
        mon = {k: v for k, v in zip(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], S.HI_MONTHS)}
        return f"{m.group(1)} {mon.get(m.group(2).lower(), m.group(2))} {m.group(3)}" if m else (d or "")

    print("2/7 Gemini watches the episode")
    data = gemini.analyze(ep["url"], show["en"], SOURCE_EP_NO)
    thumbnail_reference = ""
    try:
        thumbnail_reference = gemini.describe_thumbnail(ep["id"])
    except gemini.ThumbnailAnalysisError as exc:
        print("   source thumbnail analysis unavailable; using episode scene prompts:", str(exc)[:240])
    scenes = [s for s in data.get("scenes", []) if s.get("narration")]
    if TEST: scenes = scenes[:3]
    if len(scenes) < 4 and not TEST: raise SystemExit(f"Gemini returned too few scenes ({len(scenes)})")
    n = len(scenes); hook_i = min(max(int(data.get("hook_scene", 0) or 0), 0), n - 1)
    pred = [str(x) for x in data.get("prediction", [])][:2] or ["शायद आगे कहानी में नया मोड़ आएगा।"]

    print("3/7 voice")
    segs = [{"tag": "hook", "lines": [data.get("hook") or scenes[0]["narration"]], "img": hook_i, "chip": "आज की कहानी", "name": "शुरुआत", "emo": scenes[hook_i].get("emotion", "tense")}]
    for i, s in enumerate(scenes):
        segs.append({"tag": f"s{i}", "lines": [s["narration"]], "img": i, "chip": f"दृश्य {i + 1}/{n}", "name": s.get("title") or f"दृश्य {i + 1}", "emo": s.get("emotion", "tense")})
    segs.append({"tag": "cliff", "lines": [data.get("cliffhanger") or scenes[-1]["narration"]], "img": n - 1, "chip": "एपिसोड का अंत", "name": "एपिसोड का अंत", "emo": "shock"})
    segs.append({"tag": "pred", "lines": ["अब परसों की बात, लेकिन सिर्फ़ अनुमान के तौर पर।"] + pred, "img": n, "chip": "अनुमान", "name": "परसों क्या हो सकता है (अनुमान)", "emo": "tense"})
    segs.append({"tag": "outro", "lines": ["पूरा एपिसोड आधिकारिक चैनल पर उपलब्ध है।", S.OUTRO_LINE], "img": 0, "chip": "धन्यवाद", "name": "", "emo": "happy"})
    voice.synth_all(segs, tmp)
    total = sum(s["times"][-1][1] for s in segs)
    print(f"   narration {total:.0f}s ({int(total // 60)}:{int(total % 60):02d})", "" if 100 <= total <= 200 else " <- outside the 2-3 min target")

    print("4/7 illustrations")
    seed = zlib.crc32(ep["id"].encode()) % 100000
    jobs = []   # (scene index, label, prompt)
    for i, sc in enumerate(scenes):
        jobs.append((i, "wide", sc["image_prompt"]))
        if S.IMAGES_PER_SCENE >= 2 and sc.get("closeup_prompt"): jobs.append((i, "close", sc["closeup_prompt"]))
    jobs.append((n, "wide", data.get("prediction_image_prompt") or scenes[-1]["image_prompt"] + ", mysterious mood, question mark in the air"))
    comps = {i: [] for i in range(n + 1)}; vcomps = {i: [] for i in range(n + 1)}; raws = {}
    for k, (i, label, p) in enumerate(jobs):
        raw, comp, vcomp = f"{tmp}/img{i}_{label}.jpg", f"{tmp}/comp{i}_{label}.jpg", f"{tmp}/vcomp{i}_{label}.jpg"
        if images.generate(p, seed + (7 if label == "close" else 0), raw):
            render.cover(raw, comp)
            if render_vert: render.cover_vertical(raw, vcomp)
            raws[(i, label)] = raw
        elif comps[i]:
            print(f"    image {i} {label}: failed, reusing the scene's other image"); continue
        else:
            print(f"    image {i} {label}: using title card")
            sc_title = scenes[min(i, n - 1)].get("title", "")
            sc_emo = scenes[min(i, n - 1)].get("emotion", "")
            render.card(sc_title, sc_emo, comp)
            if render_vert: render.card_vertical(sc_title, sc_emo, vcomp)
        comps[i].append(comp)
        if render_vert: vcomps[i].append(vcomp)

    pv = f"{out_dir}/{KEY}_{ep['id']}_preview"; os.makedirs(pv, exist_ok=True)
    for (i, label), raw in raws.items(): shutil.copy(raw, f"{pv}/image_{i + 1:02d}_{label}.jpg")
    json.dump({"prompts": [{"scene": i + 1, "type": lb, "prompt": p} for i, lb, p in jobs], "narration": [s["lines"] for s in segs]}, open(f"{pv}/script_and_prompts.json", "w"), ensure_ascii=False, indent=1)
    try:
        allc = [c for i in range(n + 1) for c in comps[i]]
        th = [Image.open(c).convert("RGB").resize((640, 360)) for c in allc]; cols = 3; rows = (len(th) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 640, rows * 360), (20, 20, 20))
        for i, t in enumerate(th): sheet.paste(t, ((i % cols) * 640, (i // cols) * 360))
        sheet.save(f"{pv}/contact_sheet.jpg", quality=85)
    except Exception as e: print("   contact sheet skipped:", e)

    print("5/7 render (landscape 16:9" + (" + vertical 9:16 Reel)" if render_vert else ")"))
    files, vfiles, starts, t0 = [], [], [], 0.0
    for k, s in enumerate(segs):
        f = f"{tmp}/seg_{s['tag']}.mp4"
        D = render.segment(s["tag"], f"{show['hi']} | परसों का एपिसोड {EP_NO}", s["chip"], s["emo"], s["lines"], s["times"], s["audio"], comps[s["img"]], tmp, f, t0, total, v0=k, word_times=s.get("word_times"))
        files.append(f)
        if render_vert:
            vf = f"{tmp}/vseg_{s['tag']}.mp4"
            render.segment_vertical(s["tag"], f"{show['hi']} | एपिसोड {EP_NO}", s["chip"], s["emo"], s["lines"], s["times"], s["audio"], vcomps[s["img"]], tmp, vf, t0, total, v0=k, word_times=s.get("word_times"))
            vfiles.append(vf)
        if s["name"]: starts.append((t0, s["name"]))
        t0 += D; print(f"   {s['tag']}: {D:.0f}s")
    name = f"{out_dir}/{KEY}_{ep['id']}"
    reel_mp4 = name + "_reel.mp4"
    main_emo = (scenes[hook_i].get("emotion") if scenes else "tense") or "tense"
    music = render.auto_music(tmp, t0, emotion=main_emo)
    print(f"   music: automatic background music ({main_emo}) -> {os.path.basename(music)}")
    render.concat(files, tmp, name + ".mp4", music, t0, emotion=main_emo)
    if render_vert:
        # Cap Instagram Reel duration to IG_MAX_REEL_SECONDS (default 115s so it never hits Meta's >120s API processing bug)
        ig_max_s = float(os.getenv("IG_MAX_REEL_SECONDS") or 115)
        render.concat(vfiles, tmp, reel_mp4, music, t0, emotion=main_emo, max_seconds=ig_max_s)
        print(f"   vertical Reel rendered -> {os.path.basename(reel_mp4)} (capped at <= {ig_max_s:.0f}s for Instagram Reels API)")

    print("6/7 thumbnail + metadata")
    thumb = name + ".jpg"
    thumbnail_prompt = (
        "Create a dramatic, polished 16:9 YouTube recap thumbnail illustration. "
        f"Episode moment: {scenes[hook_i].get('image_prompt', '')}. "
        f"Emotional hook: {data.get('hook', '')}. "
        "Use expressive original fictional faces, strong separation between foreground and background, "
        "bright cinematic lighting, and clear space across the lower third for added Hindi title text. "
        "Do not draw any text, letters, logos, or watermarks."
    )
    if thumbnail_reference:
        thumbnail_prompt += (
            " Use only the broad composition and color balance from this episode-thumbnail description; "
            "do not reproduce its people, text, logo, or exact artwork: " + thumbnail_reference[:700]
        )
    thumbnail_art = f"{tmp}/thumbnail_art.jpg"
    if not images.generate_thumbnail(thumbnail_prompt, seed + 1001, thumbnail_art):
        print("   generated thumbnail art unavailable; using the existing episode illustration")
        thumbnail_art = raws.get((hook_i, "close")) or raws.get((hook_i, "wide")) or comps[hook_i][0]
    render.thumbnail(thumbnail_art, data.get("thumb_text") or data.get("headline") or "क्या होगा आगे?",
                      show["hi"], f"एपिसोड {EP_NO} | {hindi_date(DATE)}", thumb)
    kws = [str(k) for k in data.get("keywords", [])]
    title = meta.make_title(show, EP_NO, DATE, data.get("headline") or "", source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
    tags = meta.make_tags(show, EP_NO, DATE, kws)
    desc = meta.make_description(show, EP_NO, DATE, ep["url"], data.get("hook", ""), starts, pred, kws, tags, source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
    social_caption = meta.make_social_caption(show, EP_NO, DATE, ep["url"], data.get("hook", ""), pred, headline=data.get("headline") or "", source_ep=SOURCE_EP_NO, source_vid=ep["id"])
    json.dump({"title": title, "description": desc, "social_caption": social_caption, "tags": tags, "source": ep["url"], "seconds": round(t0)}, open(name + ".json", "w"), ensure_ascii=False, indent=2)
    print("   title:", title, "|", len(tags), "tags")

    print("7/7 upload & schedule (YouTube + Facebook + Google Drive + Instagram)")
    if do_upload:
        slot = None
        if not publish_now:
            now = dt.datetime.now(dt.timezone.utc)
            # Search next 3 days within a 30-hour window so 12 AM IST runs reliably schedule 9 AM - 4 PM IST slots
            for d in range(3):
                day = (now.astimezone(IST) + dt.timedelta(days=d)).date(); h, m = show["slot"]
                t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST).astimezone(dt.timezone.utc)
                if now + dt.timedelta(minutes=12) < t < now + dt.timedelta(hours=30):
                    slot = t; break
        slot_ist_str = slot.astimezone(IST).strftime("%Y-%m-%d %I:%M %p IST") if slot else "IMMEDIATE"
        print("   schedule mode:", "publish now" if not slot else f"scheduled for {slot_ist_str} ({slot.strftime('%H:%M UTC')})")

        # 7A. YouTube Upload & Native Schedule
        if youtube.enabled() and not yt_done_id:
            dup_yt = youtube.already_uploaded(show, EP_NO, source_vid=ep["id"])
            if dup_yt:
                print(f"   [YouTube] duplicate prevented right before upload (already on YouTube: {dup_yt})")
                yt_done_id = dup_yt
            else:
                yt_done_id = youtube.upload_video(name + ".mp4", title, desc, tags, slot, thumb)

        # 7B. Facebook Page Video Upload & Native Schedule (exact same `slot` as YouTube!)
        if social.fb_enabled() and not fb_done_id:
            dup_fb = social.fb_already_uploaded(show, EP_NO, source_vid=ep["id"])
            if dup_fb:
                print(f"   [Facebook] duplicate prevented right before upload (already on Facebook: {dup_fb})")
                fb_done_id = dup_fb
            else:
                fb_mp4 = reel_mp4 if (os.getenv("FACEBOOK_REELS_MODE", "").lower() == "true" and os.path.exists(reel_mp4)) else (name + ".mp4")
                fb_done_id = social.upload_facebook_video(fb_mp4, title, social_caption, publish_at=slot, thumb_path=thumb)

        # 7C. Google Drive Automatic Reel Storage (so Reel is backed up in Drive & ready for scheduled IG slot)
        if social.drive_enabled() and os.path.exists(reel_mp4) and not drive_done_id:
            drive_done_id = social.drive_upload_reel(reel_mp4, KEY, ep["id"], EP_NO, title, social_caption, scheduled_slot_utc=slot, thumb_path=thumb)

        # 7D. Instagram Reels Publishing
        # Note: Meta's Instagram Content Publishing API does NOT support a `scheduled_publish_time` parameter.
        # - If `publish_now=true` (or slot is immediate, or `IG_PUBLISH_WITH_NIGHTLY=true`), publish to Instagram right now.
        # - Otherwise, the Reel is stored in Google Drive and Google Apps Script triggers `ONLY_IG_PUBLISH=true`
        #   (or publishes directly from Apps Script) at the show's exact 9 AM - 4 PM IST slot so IG goes live at the exact same time as YT & FB!
        ig_with_nightly = os.getenv("IG_PUBLISH_WITH_NIGHTLY", "false").lower() == "true"
        if social.ig_enabled() and os.path.exists(reel_mp4) and not ig_done_id:
            if (not slot) or publish_now or ig_with_nightly:
                dup_ig = social.ig_already_uploaded(show, EP_NO, source_vid=ep["id"])
                if dup_ig:
                    print(f"   [Instagram] duplicate prevented right before publish (already on Instagram: {dup_ig})")
                    ig_done_id = dup_ig
                else:
                    ig_done_id = social.publish_instagram_reel(reel_mp4, social_caption)
                    if drive_done_id:
                        social.drive_mark_ig_published(drive_done_id, ig_done_id)
            else:
                print(f"   [Instagram] Reel stored in Google Drive (id={drive_done_id or 'local'}); will be published at {slot_ist_str} by Google Apps Script slot trigger!")

        feed.mark_done(
            KEY, ep["id"],
            episode_no=SOURCE_EP_NO, target_ep=EP_NO,
            yt_id=yt_done_id, fb_id=fb_done_id, ig_id=ig_done_id, drive_id=drive_done_id,
            scheduled_slot_ist=slot_ist_str,
        )
    else:
        print("   upload skipped")
        feed.record_status(KEY, "rendered_no_upload", vid=ep["id"], episode=SOURCE_EP_NO, target_ep=EP_NO, log_tail=_LOG_BUF.getvalue())
    print("done", name)

except SystemExit as se:
    if se.code not in (0, None):
        err_msg = str(se)
        print("FAILED:", err_msg)
        feed.record_status(
            KEY, "failed",
            vid=ep["id"] if ep else VIDEO_ID,
            episode=SOURCE_EP_NO,
            target_ep=EP_NO,
            error=err_msg,
            log_tail=_LOG_BUF.getvalue(),
        )
    raise
except Exception as ex:
    tb = traceback.format_exc()
    print("UNHANDLED ERROR:\n", tb)
    feed.record_status(
        KEY, "failed",
        vid=ep["id"] if ep else VIDEO_ID,
        episode=SOURCE_EP_NO,
        target_ep=EP_NO,
        error=f"{type(ex).__name__}: {ex}",
        log_tail=_LOG_BUF.getvalue(),
    )
    raise SystemExit(1)
