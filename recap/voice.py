import asyncio, os, re, subprocess, time
import config as S

def sanitize(t):
    t = t.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace("\u2014", ", ").replace("\u2013", ", ").replace("\u2026", ".")
    t = re.sub(r"[^\u0900-\u097F\x20-\x7E\u0964]", " ", t)       # keep Devanagari, ASCII, danda
    return re.sub(r"\s+", " ", t).strip()

def _edge(text, path):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, S.VOICE, rate="+3%").save(path))

def _gtts(text, path):                 # last-resort free fallback (robotic voice)
    from gtts import gTTS
    gTTS(text=text, lang="hi", tld="co.in").save(path)

def _try(fn, text, path, tries):
    for i in range(tries):
        try:
            if os.path.exists(path): os.remove(path)
            fn(text, path)
            if os.path.getsize(path) > 1000: return True
        except Exception as e:
            print(f"    {fn.__name__} try {i + 1}/{tries}: {type(e).__name__}: {str(e)[:90]}")
        time.sleep(1.5 * (i + 1))
    return False

def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode())

def _one(lines, outdir, tag, fn, tries):
    paths = []
    for i, ln in enumerate(lines):
        p = f"{outdir}/{tag}_{i}.mp3"
        if not _try(fn, sanitize(ln), p, tries): return None
        paths.append(p)
    times, t = [], 0.0
    for p in paths:
        d = dur(p); times.append((t, t + d)); t += d
    lst = f"{outdir}/{tag}_a.txt"; open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in paths))
    out = f"{outdir}/{tag}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libmp3lame", "-b:a", "160k", out], check=True)
    return out, times

def synth_all(segments, outdir):
    """segments: [{'tag','lines'}]. One voice engine for the whole video; falls back for ALL segments if one fails."""
    for name, fn, tries in (("edge-tts", _edge, 4), ("gtts", _gtts, 3)):
        res, ok = [], True
        for s in segments:
            r = _one(s["lines"], outdir, s["tag"], fn, tries)
            if r is None: print(f"  {name} failed on {s['tag']}; switching engine for the whole video"); ok = False; break
            res.append(r)
        if ok:
            print("  voice:", name, "|", S.VOICE if name == "edge-tts" else "gTTS")
            for s, (a, t) in zip(segments, res): s["audio"], s["times"] = a, t
            return
    raise SystemExit("All voice engines failed")
