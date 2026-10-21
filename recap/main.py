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
SOURCE_EP_NO, SOURCE_DATE = ep["episode"] or "?", ep["date"] or dt.datetime.now(IST).strftime("%d %b %Y")
# The video is framed as a next-day prediction: metadata/on-screen target date and episode are +1.
def next_target(source_ep, source_date):
    target_ep = str(int(source_ep) + 1) if str(source_ep).isdigit() else source_ep
    parsed = None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try: parsed = dt.datetime.strptime(source_date, fmt); break
        except ValueError: pass
    target_date = (parsed + dt.timedelta(days=1)).strftime("%d %b %Y") if parsed else (dt.datetime.now(IST) + dt.timedelta(days=1)).strftime("%d %b %Y")
    return target_ep, target_date
EP_NO, DATE = next_target(SOURCE_EP_NO, SOURCE_DATE)
print(f"  source episode/date: {SOURCE_EP_NO} / {SOURCE_DATE}; next-day target: {EP_NO} / {DATE}")
def hindi_date(d):   # on-screen text must be Devanagari (the font has no Latin letters)
    import re
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", d or "")
    mon = {k: v for k, v in zip(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], S.HI_MONTHS)}
    return f"{m.group(1)} {mon.get(m.group(2).lower(), m.group(2))} {m.group(3)}" if m else (d or "")

print("2/7 Gemini watches the episode")
data = gemini.analyze(ep["url"], show["en"], SOURCE_EP_NO)
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
comps = {i: [] for i in range(n + 1)}; raws = {}
for k, (i, label, p) in enumerate(jobs):
    raw, comp = f"{tmp}/img{i}_{label}.jpg", f"{tmp}/comp{i}_{label}.jpg"
    if images.generate(p, seed + (7 if label == "close" else 0), raw): render.cover(raw, comp); raws[(i, label)] = raw
    elif comps[i]: print(f"    image {i} {label}: failed, reusing the scene's other image"); continue
    else:
        print(f"    image {i} {label}: using title card"); render.card(scenes[min(i, n - 1)].get("title", ""), scenes[min(i, n - 1)].get("emotion", ""), comp)
    comps[i].append(comp)

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

print("5/7 render")
files, starts, t0 = [], [], 0.0
for k, s in enumerate(segs):
    f = f"{tmp}/seg_{s['tag']}.mp4"
    D = render.segment(s["tag"], f"{show['hi']} | कल का एपिसोड {EP_NO}", s["chip"], s["emo"], s["lines"], s["times"], s["audio"], comps[s["img"]], tmp, f, t0, total, v0=k)
    files.append(f)
    if s["name"]: starts.append((t0, s["name"]))
    t0 += D; print(f"   {s['tag']}: {D:.0f}s")
name = f"{out_dir}/{KEY}_{ep['id']}"
main_emo = (scenes[hook_i].get("emotion") if scenes else "tense") or "tense"
music = render.auto_music(tmp, t0, emotion=main_emo)
print(f"   music: automatic background music ({main_emo}) -> {os.path.basename(music)}")
render.concat(files, tmp, name + ".mp4", music, t0, emotion=main_emo)

print("6/7 thumbnail + metadata")
thumb = name + ".jpg"
render.thumbnail(raws.get((hook_i, "close")) or raws.get((hook_i, "wide")) or comps[hook_i][0], data.get("thumb_text") or data.get("headline") or "क्या होगा आगे?",
                  show["hi"], f"एपिसोड {EP_NO} | {hindi_date(DATE)}", thumb)
kws = [str(k) for k in data.get("keywords", [])]
title = meta.make_title(show, EP_NO, DATE, data.get("headline") or "", source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
tags = meta.make_tags(show, EP_NO, DATE, kws)
desc = meta.make_description(show, EP_NO, DATE, ep["url"], data.get("hook", ""), starts, pred, kws, tags, source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
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
