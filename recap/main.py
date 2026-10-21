import datetime as dt, json, os, shutil, sys, time, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config as S, feed, gemini, images, voice, render, meta, youtube
from PIL import Image

KEY = os.environ["SHOW_KEY"]; show = S.SHOWS[KEY]
TEST = os.getenv("TEST_MODE", "").lower() == "true"
VIDEO_ID = os.getenv("VIDEO_ID", "").strip()
event = os.getenv("EVENT_NAME", "")
publish_now = event != "schedule" and os.getenv("PUBLISH_NOW", "true").lower() != "false"
do_upload = (not TEST) and os.getenv("DO_UPLOAD", "true").lower() != "false" and youtube.enabled()
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
tmp = os.path.join(S.BASE, f"tmp_{KEY}"); out_dir = os.path.join(S.BASE, "output"); os.makedirs(tmp, exist_ok=True); os.makedirs(out_dir, exist_ok=True)

print(f"== {show['en']} | test={TEST} | upload={do_upload} | publish_now={publish_now}")
print("1/7 find episode")
ep = feed.by_id(VIDEO_ID) if VIDEO_ID else feed.find_episode(KEY)
if VIDEO_ID and feed.show_key_for(ep["title"]) != KEY: print("   this video belongs to another show; skipping"); sys.exit(0)
if not ep: print("   no new unseen full episode for this show right now"); sys.exit(0)
print("  ", ep["title"], "|", ep["url"])
EP_NO, DATE = ep["episode"] or "?", ep["date"] or dt.datetime.now(IST).strftime("%d %b %Y")
def hindi_date(d):   # on-screen text must be Devanagari (the font has no Latin letters)
    import re
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", d or "")
    mon = {k: v for k, v in zip(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], S.HI_MONTHS)}
    return f"{m.group(1)} {mon.get(m.group(2).lower(), m.group(2))} {m.group(3)}" if m else (d or "")

print("2/7 Gemini watches the episode")
data = gemini.analyze(ep["url"], show["en"], EP_NO)
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
segs.append({"tag": "pred", "lines": ["अब कल की बात, लेकिन सिर्फ़ अनुमान के तौर पर।"] + pred, "img": n, "chip": "अनुमान", "name": "कल क्या हो सकता है (अनुमान)", "emo": "tense"})
segs.append({"tag": "outro", "lines": ["पूरा एपिसोड आधिकारिक चैनल पर देखें। ऐसी कहानियों के लिए चैनल को सब्सक्राइब करें।"], "img": 0, "chip": "धन्यवाद", "name": "", "emo": "happy"})
voice.synth_all(segs, tmp)
total = sum(s["times"][-1][1] for s in segs)
print(f"   narration {total:.0f}s ({int(total // 60)}:{int(total % 60):02d})", "" if 100 <= total <= 200 else " <- outside the 2-3 min target")

print("4/7 illustrations")
seed = zlib.crc32(ep["id"].encode()) % 100000
prompts = [s["image_prompt"] for s in scenes] + [data.get("prediction_image_prompt") or scenes[-1]["image_prompt"] + ", mysterious mood, question mark in the air"]
comps = []
for i, p in enumerate(prompts):
    raw, comp = f"{tmp}/img{i}.jpg", f"{tmp}/comp{i}.jpg"
    if images.generate(p, seed, raw): render.cover(raw, comp)
    else:
        print(f"    image {i}: using title card"); render.card(scenes[min(i, n - 1)].get("title", ""), scenes[min(i, n - 1)].get("emotion", ""), comp)
    comps.append(comp)

pv = f"{out_dir}/{KEY}_{ep['id']}_preview"; os.makedirs(pv, exist_ok=True)
for i, p in enumerate(prompts):
    if os.path.exists(f"{tmp}/img{i}.jpg"): shutil.copy(f"{tmp}/img{i}.jpg", f"{pv}/image_{i + 1:02d}.jpg")
json.dump({"prompts": prompts, "narration": [s["lines"] for s in segs]}, open(f"{pv}/script_and_prompts.json", "w"), ensure_ascii=False, indent=1)
try:
    th = [Image.open(c).convert("RGB").resize((640, 360)) for c in comps]; cols = 3; rows = (len(th) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 640, rows * 360), (20, 20, 20))
    for i, t in enumerate(th): sheet.paste(t, ((i % cols) * 640, (i // cols) * 360))
    sheet.save(f"{pv}/contact_sheet.jpg", quality=85)
except Exception as e: print("   contact sheet skipped:", e)

print("5/7 render")
files, starts, t0 = [], [], 0.0
for k, s in enumerate(segs):
    f = f"{tmp}/seg_{s['tag']}.mp4"
    D = render.segment(s["tag"], f"{show['hi']} | एपिसोड {EP_NO}", s["chip"], s["emo"], s["lines"], s["times"], s["audio"], comps[s["img"]], tmp, f, t0, total, v0=k)
    files.append(f)
    if s["name"]: starts.append((t0, s["name"]))
    t0 += D; print(f"   {s['tag']}: {D:.0f}s")
name = f"{out_dir}/{KEY}_{ep['id']}"
music = render.pick_music(); print("   music:", os.path.basename(music) if music else "none (add tracks to music/)")
render.concat(files, tmp, name + ".mp4", music, t0)

print("6/7 thumbnail + metadata")
thumb = name + ".jpg"
render.thumbnail(f"{tmp}/img{hook_i}.jpg" if os.path.exists(f"{tmp}/img{hook_i}.jpg") else comps[hook_i], data.get("thumb_text") or data.get("headline") or "क्या होगा आगे?",
                  show["hi"], f"एपिसोड {EP_NO} | {hindi_date(DATE)}", thumb)
kws = [str(k) for k in data.get("keywords", [])]
title = meta.make_title(show, EP_NO, DATE, data.get("headline") or "")
tags = meta.make_tags(show, EP_NO, DATE, kws)
desc = meta.make_description(show, EP_NO, DATE, ep["url"], data.get("hook", ""), starts, pred, kws, tags)
json.dump({"title": title, "description": desc, "tags": tags, "source": ep["url"], "seconds": round(t0)}, open(name + ".json", "w"), ensure_ascii=False, indent=2)
print("   title:", title, "|", len(tags), "tags")

print("7/7 upload")
if do_upload:
    slot = None
    if not publish_now:
        now = dt.datetime.now(dt.timezone.utc)
        for d in range(2):
            day = (now.astimezone(IST) + dt.timedelta(days=d)).date(); h, m = show["slot"]
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST).astimezone(dt.timezone.utc)
            if now + dt.timedelta(minutes=8) < t < now + dt.timedelta(hours=20): slot = t; break
    print("   mode:", "publish now" if not slot else f"scheduled for {slot} UTC")
    youtube.upload_video(name + ".mp4", title, desc, tags, slot, thumb)
    feed.mark_done(KEY, ep["id"])
else:
    print("   upload skipped")
print("done", name)
