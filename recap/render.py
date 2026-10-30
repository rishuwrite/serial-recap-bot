import functools, glob, math, os, random, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from latin import deva
import config as S
W, H, FPS = S.W, S.H, S.FPS
VW, VH = 1080, 1920   # 9:16 vertical format for Instagram Reels & Facebook Reels

def find_font():
    for pat in ["/usr/share/fonts/**/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/**/NotoSansDevanagari*Bold*.ttf",
                "/usr/share/fonts/**/Mukta*Bold*.ttf", "/usr/share/fonts/**/*Devanagari*.ttf"]:
        f = glob.glob(pat, recursive=True)
        if f: return f[0]
    raise SystemExit("No Devanagari font found (apt install fonts-noto-core)")

def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = w
    return [x for x in (lines + [cur]) if x] or [""]

@functools.lru_cache(None)
def _fp(): return find_font()
@functools.lru_cache(None)
def font(size): return ImageFont.truetype(_fp(), size, layout_engine=ImageFont.Layout.RAQM)
_d = ImageDraw.Draw(Image.new("RGB", (8, 8)))

def cover(img, out):
    """Fill the 16:9 frame; slightly oversize + centre-crop so any corner watermark is pushed out of view."""
    im = Image.open(img).convert("RGB"); r = max(W / im.width, H / im.height) * 1.10
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)); l, t = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((l, t, l + W, t + H))
    im = ImageEnhance.Color(im).enhance(1.10)
    im = ImageEnhance.Contrast(im).enhance(1.06)
    im.save(out, quality=92)

def cover_vertical(img, out):
    """Build a 1080x1920 (9:16) vertical frame for Instagram/Facebook Reels:
    - Blurred, darkened full-height background from the scene illustration
    - Sharp, vibrant foreground card centered vertically so no characters are cropped out."""
    im = Image.open(img).convert("RGB")
    # Background: fill 1080x1920 and apply Gaussian blur + dark tint
    r_bg = max(VW / im.width, VH / im.height) * 1.12
    bg = im.resize((int(im.width * r_bg) + 1, int(im.height * r_bg) + 1))
    bl, bt = (bg.width - VW) // 2, (bg.height - VH) // 2
    bg = bg.crop((bl, bt, bl + VW, bt + VH)).filter(ImageFilter.GaussianBlur(radius=28))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)

    # Foreground: 1080x1160 center-cropped card placed at y=260..1420
    fg_w, fg_h = VW, 1160
    r_fg = max(fg_w / im.width, fg_h / im.height) * 1.06
    fg = im.resize((int(im.width * r_fg) + 1, int(im.height * r_fg) + 1))
    fl, ft = (fg.width - fg_w) // 2, (fg.height - fg_h) // 2
    fg = fg.crop((fl, ft, fl + fg_w, ft + fg_h))
    fg = ImageEnhance.Color(fg).enhance(1.12)
    fg = ImageEnhance.Contrast(fg).enhance(1.08)

    bg.paste(fg, (0, 260))
    d = ImageDraw.Draw(bg)
    d.line([(0, 260), (VW, 260)], fill=(255, 200, 0), width=4)
    d.line([(0, 1420), (VW, 1420)], fill=(255, 200, 0), width=4)
    bg.save(out, quality=92)

def card(title, emotion, out):
    """Used only when an illustration could not be generated: designed title card, never a blank screen."""
    title = deva(title)
    c0 = S.EMOTION_COLORS.get(emotion, (60, 30, 90)); im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H): k = y / H; d.line([(0, y), (W, y)], fill=tuple(int(c0[i] * (1 - 0.7 * k)) for i in range(3)))
    f = font(110); ls = wrap(d, title, f, 1500)[:3]; y0 = 430 - len(ls) * 70
    for i, l in enumerate(ls): d.text(((W - d.textlength(l, font=f)) / 2, y0 + i * 140), l, font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
    im.save(out, quality=90)

def card_vertical(title, emotion, out):
    """Vertical 1080x1920 fallback title card."""
    title = deva(title)
    c0 = S.EMOTION_COLORS.get(emotion, (60, 30, 90)); im = Image.new("RGB", (VW, VH)); d = ImageDraw.Draw(im)
    for y in range(VH): k = y / VH; d.line([(0, y), (VW, y)], fill=tuple(int(c0[i] * (1 - 0.7 * k)) for i in range(3)))
    f = font(84); ls = wrap(d, title, f, 940)[:4]; y0 = 820 - len(ls) * 60
    for i, l in enumerate(ls): d.text(((VW - d.textlength(l, font=f)) / 2, y0 + i * 115), l, font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
    im.save(out, quality=90)

def panel(chip_l, chip_r, emotion, out):
    chip_l, chip_r = deva(chip_l), deva(chip_r)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(640, H):                                  # bottom shade for caption readability
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(225 * (y - 640) / (H - 640))))
    for y in range(0, 170): d.line([(0, y), (W, y)], fill=(0, 0, 0, int(145 * (1 - y / 170))))
    f = font(40); wl = int(d.textlength(chip_l, font=f)) + 50
    d.rounded_rectangle((30, 28, 30 + wl, 92), 14, fill=(200, 0, 20, 245)); d.text((55, 32), chip_l, font=f, fill=(255, 255, 255))
    col = S.EMOTION_COLORS.get(emotion, (255, 190, 0)) if chip_r != "अनुमान" else (255, 170, 0)
    wr = int(d.textlength(chip_r, font=f)) + 50
    d.rounded_rectangle((W - wr - 30, 28, W - 30, 92), 14, fill=col + (245,)); d.text((W - wr - 5, 32), chip_r, font=f, fill=(255, 255, 255))
    im.save(out)

def panel_vertical(chip_l, chip_r, emotion, out):
    chip_l, chip_r = deva(chip_l), deva(chip_r)
    im = Image.new("RGBA", (VW, VH), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(1320, VH):
        d.line([(0, y), (VW, y)], fill=(0, 0, 0, int(235 * (y - 1320) / (VH - 1320))))
    for y in range(0, 260):
        d.line([(0, y), (VW, y)], fill=(0, 0, 0, int(185 * (1 - y / 260))))
    f = font(38); wl = min(int(d.textlength(chip_l, font=f)) + 48, VW - 60)
    d.rounded_rectangle((30, 70, 30 + wl, 134), 14, fill=(200, 0, 20, 245)); d.text((54, 74), chip_l, font=f, fill=(255, 255, 255))
    col = S.EMOTION_COLORS.get(emotion, (255, 190, 0)) if chip_r != "अनुमान" else (255, 170, 0)
    wr = int(d.textlength(chip_r, font=f)) + 48
    d.rounded_rectangle((30, 148, 30 + wr, 210), 14, fill=col + (245,)); d.text((54, 151), chip_r, font=f, fill=(255, 255, 255))
    im.save(out)

def chunks(text, a, b, exact_words=None, group_size=8):
    """Return short caption groups with word index and timings: (group_words, active_idx, start_s, end_s).
    Uses exact WordBoundary events from edge-tts when present, falling back to character-weighted timings."""
    words = deva(text).split()
    if not words: return []
    if exact_words and len(exact_words) == len(words):
        result = []
        for g_start in range(0, len(words), group_size):
            group = words[g_start:g_start + group_size]
            g_exact = exact_words[g_start:g_start + group_size]
            for idx in range(len(group)):
                ws = g_exact[idx][1]
                we = g_exact[idx + 1][1] if idx + 1 < len(g_exact) else max(g_exact[idx][2], b)
                if idx == 0 and g_start == 0:
                    ws = a
                if we > ws:
                    result.append((group, idx, ws, we))
        if result:
            return result

    groups = [words[i:i + group_size] for i in range(0, len(words), group_size)]
    weights = [sum(max(1, len(w.strip("।,!?:;"))) for w in g) for g in groups]
    total = sum(weights) or 1; cursor = a; result = []
    for group, weight in zip(groups, weights):
        end = cursor + (b - a) * weight / total
        gw = [max(1, len(w.strip("।,!?:;"))) for w in group]; gtotal = sum(gw) or 1
        wc = cursor
        for idx, (word, ww) in enumerate(zip(group, gw)):
            we = wc + (end - cursor) * ww / gtotal
            result.append((group, idx, wc, we))
            wc = we
        cursor = end
    return result

def caption(words, active_idx, out):
    """Draw the short phrase and highlight ONLY the word at `active_idx` in yellow (fixes duplicate word bug)."""
    im = Image.new("RGBA", (W, 230), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = font(56)
    widths = [d.textlength(w + (" " if i < len(words) - 1 else ""), font=f) for i, w in enumerate(words)]
    x = (W - sum(widths)) / 2; y = 76
    for i, word in enumerate(words):
        is_active = (i == active_idx)
        color = (255, 222, 45, 255) if is_active else (255, 255, 255, 255)
        d.text((x + 3, y + 4), word, font=f, fill=(0, 0, 0, 210), stroke_width=4, stroke_fill=(0, 0, 0, 210))
        d.text((x, y), word, font=f, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 255))
        x += widths[i]
    im.save(out)

def caption_vertical(words, active_idx, out):
    """Draw 5-word phrase centered for 1080px vertical Reel width."""
    im = Image.new("RGBA", (VW, 240), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = font(54)
    widths = [d.textlength(w + (" " if i < len(words) - 1 else ""), font=f) for i, w in enumerate(words)]
    if sum(widths) > VW - 60:
        f = font(44)
        widths = [d.textlength(w + (" " if i < len(words) - 1 else ""), font=f) for i, w in enumerate(words)]
    x = (VW - sum(widths)) / 2; y = 70
    for i, word in enumerate(words):
        is_active = (i == active_idx)
        color = (255, 222, 45, 255) if is_active else (255, 255, 255, 255)
        d.text((x + 3, y + 4), word, font=f, fill=(0, 0, 0, 215), stroke_width=4, stroke_fill=(0, 0, 0, 215))
        d.text((x, y), word, font=f, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 255))
        x += widths[i]
    im.save(out)

def clip(comp, frames, path, variant):
    N = frames; y = "ih/2-(ih/zoom/2)"
    zin, zout = f"1+0.13*on/{N}", f"1.13-0.13*on/{N}"
    z, x, y = [(zin, "iw/2-(iw/zoom/2)", y), (zout, "iw/2-(iw/zoom/2)", y),
               ("1.14", f"(iw-iw/zoom)*on/{N}", y), ("1.14", f"(iw-iw/zoom)*(1-on/{N})", y),
               (zin, "0", "0"), (zin, "iw-iw/zoom", "ih-ih/zoom")][variant % 6]
    vf = f"scale=2400:1350,zoompan=z='{z}':x='{x}':y='{y}':d={N}:s={W}x{H}:fps={FPS},format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", comp, "-vf", vf, "-frames:v", str(N),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-an", path], check=True)

def clip_vertical(comp, frames, path, variant):
    N = frames; y = "ih/2-(ih/zoom/2)"
    zin, zout = f"1+0.08*on/{N}", f"1.08-0.08*on/{N}"
    z, x, y = [(zin, "iw/2-(iw/zoom/2)", y), (zout, "iw/2-(iw/zoom/2)", y),
               ("1.08", f"(iw-iw/zoom)*on/{N}", y), ("1.08", f"(iw-iw/zoom)*(1-on/{N})", y)][variant % 4]
    vf = f"scale=1200:2134,zoompan=z='{z}':x='{x}':y='{y}':d={N}:s={VW}x{VH}:fps={FPS},format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", comp, "-vf", vf, "-frames:v", str(N),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-an", path], check=True)

def segment(tag, chip_l, chip_r, emotion, lines, times, audio, comps, tmp, out, offset, total, v0=0, word_times=None):
    D = times[-1][1]; n = max(1, round(D / S.CUT_SECONDS)); bounds = [D * k / n for k in range(n + 1)]; paths = []
    for k in range(n):
        p = f"{tmp}/{tag}_c{k}.mp4"; clip(comps[k % len(comps)], max(round(bounds[k + 1] * FPS) - round(bounds[k] * FPS), 2), p, v0 * 2 + k); paths.append(p)
    open(f"{tmp}/{tag}_c.txt", "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in paths))
    bg = f"{tmp}/{tag}_bg.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{tmp}/{tag}_c.txt", "-c", "copy", bg], check=True)
    panel(chip_l, chip_r, emotion, f"{tmp}/{tag}_panel.png")
    bar = f"{tmp}/bar.png"
    if not os.path.exists(bar): Image.new("RGBA", (W, 12), (255, 200, 0, 245)).save(bar)
    ins = ["-i", bg, "-i", audio, "-i", f"{tmp}/{tag}_panel.png", "-i", bar]; flt = "[0:v][2:v]overlay=0:0[v0];"; n_ov = 0
    wt_list = word_times if word_times and len(word_times) == len(lines) else [None] * len(lines)
    for li, (ln, (a, b), exact_w) in enumerate(zip(lines, times, wt_list)):
        for gi, (words, active_idx, ta, tb) in enumerate(chunks(ln, a, b, exact_words=exact_w, group_size=8)):
            cp = f"{tmp}/{tag}_cap{li}_{gi}.png"
            caption(words, active_idx, cp); ins += ["-i", cp]
            flt += f"[v{n_ov}][{4 + n_ov}:v]overlay=0:830:enable='between(t,{ta:.3f},{tb:.3f})'[v{n_ov + 1}];"; n_ov += 1
    flt += f"[v{n_ov}][3:v]overlay=x='-{W}+{W}*(t+{offset:.3f})/{total:.3f}':y={H - 12}[outv]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", flt, "-map", "[outv]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "5000k", "-bufsize", "10000k", "-r", str(FPS), "-g", str(FPS * 2),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k", "-t", f"{D:.3f}", out], check=True)
    for p in paths + [bg]: os.remove(p)
    return D

def segment_vertical(tag, chip_l, chip_r, emotion, lines, times, audio, vcomps, tmp, out, offset, total, v0=0, word_times=None):
    """Render a vertical 1080x1920 (9:16) Reel segment with Hindi captions & progress bar."""
    D = times[-1][1]; n = max(1, round(D / S.CUT_SECONDS)); bounds = [D * k / n for k in range(n + 1)]; paths = []
    for k in range(n):
        p = f"{tmp}/v_{tag}_c{k}.mp4"; clip_vertical(vcomps[k % len(vcomps)], max(round(bounds[k + 1] * FPS) - round(bounds[k] * FPS), 2), p, v0 * 2 + k); paths.append(p)
    open(f"{tmp}/v_{tag}_c.txt", "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in paths))
    bg = f"{tmp}/v_{tag}_bg.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{tmp}/v_{tag}_c.txt", "-c", "copy", bg], check=True)
    panel_vertical(chip_l, chip_r, emotion, f"{tmp}/v_{tag}_panel.png")
    bar = f"{tmp}/v_bar.png"
    if not os.path.exists(bar): Image.new("RGBA", (VW, 12), (255, 200, 0, 245)).save(bar)
    ins = ["-i", bg, "-i", audio, "-i", f"{tmp}/v_{tag}_panel.png", "-i", bar]; flt = "[0:v][2:v]overlay=0:0[v0];"; n_ov = 0
    wt_list = word_times if word_times and len(word_times) == len(lines) else [None] * len(lines)
    for li, (ln, (a, b), exact_w) in enumerate(zip(lines, times, wt_list)):
        for gi, (words, active_idx, ta, tb) in enumerate(chunks(ln, a, b, exact_words=exact_w, group_size=5)):
            cp = f"{tmp}/v_{tag}_cap{li}_{gi}.png"
            caption_vertical(words, active_idx, cp); ins += ["-i", cp]
            flt += f"[v{n_ov}][{4 + n_ov}:v]overlay=0:1460:enable='between(t,{ta:.3f},{tb:.3f})'[v{n_ov + 1}];"; n_ov += 1
    flt += f"[v{n_ov}][3:v]overlay=x='-{VW}+{VW}*(t+{offset:.3f})/{total:.3f}':y={VH - 12}[outv]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", flt, "-map", "[outv]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "4500k", "-bufsize", "9000k", "-r", str(FPS), "-g", str(FPS * 2),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k", "-t", f"{D:.3f}", out], check=True)
    for p in paths + [bg]: os.remove(p)
    return D

def pick_music(emotion=None):
    """Find background music tracks in /music or the project root directory."""
    tr = (glob.glob(os.path.join(S.BASE, "music", "*.mp3")) +
          glob.glob(os.path.join(S.BASE, "music", "*.m4a")) +
          glob.glob(os.path.join(S.BASE, "music", "*.wav")))
    if not tr:
        tr = (glob.glob(os.path.join(S.BASE, "*.mp3")) +
              glob.glob(os.path.join(S.BASE, "*.m4a")) +
              glob.glob(os.path.join(S.BASE, "*.wav")))
    if tr and emotion:
        matched = [f for f in tr if emotion.lower() in os.path.basename(f).lower()]
        if matched: return random.choice(matched)
    return random.choice(tr) if tr else None

def generate_original_music(out, total, emotion="tense"):
    """Synthesize a mood-matched Indian TV serial dramatic score with rhythmic pulse & harmony pads via FFmpeg."""
    total = max(float(total), 8.0)
    chords = {
        "tense":    [(110.0, 0.40), (130.81, 0.30), (155.56, 0.25), (220.0, 0.25)],
        "sad":      [(110.0, 0.45), (130.81, 0.35), (164.81, 0.30), (220.0, 0.20)],
        "happy":    [(130.81, 0.40), (164.81, 0.35), (196.00, 0.30), (261.63, 0.25)],
        "romantic": [(146.83, 0.40), (185.00, 0.35), (220.00, 0.30), (293.66, 0.20)],
        "shock":    [(110.0, 0.42), (116.54, 0.35), (155.56, 0.30), (207.65, 0.25)],
        "angry":    [(110.0, 0.45), (123.47, 0.35), (155.56, 0.30), (220.00, 0.25)],
    }
    emo_key = (emotion or "tense").lower()
    notes = chords.get(emo_key, chords["tense"])
    pulse_hz = 2.0 if emo_key in ("shock", "angry", "tense") else (1.1 if emo_key == "sad" else 1.5)

    inputs = []
    for freq, _ in notes:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=44100:duration={total:.3f}"]
    inputs += ["-f", "lavfi", "-i", f"sine=frequency=65.41:sample_rate=44100:duration={total:.3f}"]
    inputs += ["-f", "lavfi", "-i", f"anoisesrc=sample_rate=44100:duration={total:.3f}:amplitude=0.012:color=pink"]

    filters = []
    for i, (_, vol) in enumerate(notes):
        filters.append(f"[{i}:a]volume={vol:.2f},lowpass=f={450 + i * 150},tremolo=f={0.4 + i * 0.15}:d=0.25[a{i}]")
    p_idx = len(notes)
    n_idx = len(notes) + 1
    filters.append(f"[{p_idx}:a]volume=0.38,lowpass=f=140,tremolo=f={pulse_hz}:d=0.85[ap]")
    filters.append(f"[{n_idx}:a]bandpass=f=700:width_type=h:w=250,volume=0.12[an]")

    mix_ins = "".join(f"[a{i}]" for i in range(len(notes))) + "[ap][an]"
    filters.append(f"{mix_ins}amix=inputs={len(notes) + 2}:normalize=0,chorus=0.7:0.9:55:0.4:0.25:2,"
                   f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(total - 2.5, 0):.3f}:d=2.5,alimiter=limit=0.9[out]")

    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex", ";".join(filters),
           "-map", "[out]", "-ac", "2", "-b:a", "160k", out]
    subprocess.run(cmd, check=True)
    return out

def auto_music(tmp, total, emotion="tense"):
    """Automatically find or synthesize background music without requiring any user-provided files."""
    music = pick_music(emotion)
    if not music:
        out_bed = os.path.join(tmp, f"auto_ambient_{emotion or 'tense'}.m4a")
        music = generate_original_music(out_bed, total, emotion=emotion)
    return music

def concat(files, tmp, out, music=None, total=0, emotion="tense", max_seconds=None):
    list_file = f"{tmp}/final_{os.path.basename(out)}.txt"
    open(list_file, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in files))
    if not music:
        music = auto_music(tmp, total, emotion=emotion)
    raw = out + ".nomusic.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", "-movflags", "+faststart", raw], check=True)
    vol = getattr(S, "MUSIC_VOLUME", 0.16)
    eff_total = min(total, max_seconds) if max_seconds else total
    fade_out_st = max(eff_total - 2.5, 0)
    dur_args = ["-t", f"{max_seconds:.2f}"] if (max_seconds and total > max_seconds) else []
    duck_flt = (f"[0:a]asplit=2[vo][sc];"
                f"[1:a]volume={vol * 1.35:.2f},afade=t=in:d=1.5,afade=t=out:st={fade_out_st:.2f}:d=2.5[m_raw];"
                f"[m_raw][sc]sidechaincompress=threshold=0.03:ratio=4:attack=50:release=400[m_duck];"
                f"[vo][m_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    res = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-stream_loop", "-1", "-i", music, "-filter_complex",
                          duck_flt, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k"] + dur_args + ["-movflags", "+faststart", out])
    if res.returncode != 0:
        basic_flt = (f"[1:a]volume={vol:.2f},afade=t=in:d=1.5,afade=t=out:st={fade_out_st:.2f}:d=2.5[m];"
                     f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-stream_loop", "-1", "-i", music, "-filter_complex",
                        basic_flt, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k"] + dur_args + ["-movflags", "+faststart", out], check=True)
    os.remove(raw)

def thumbnail(img, hook, tag_text, bottom_text, out):
    hook, tag_text, bottom_text = deva(hook), deva(tag_text), deva(bottom_text)
    im = Image.open(img).convert("RGB"); r = max(1280 / im.width, 720 / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)); l, t = (im.width - 1280) // 2, (im.height - 720) // 2
    im = im.crop((l, t, l + 1280, t + 720))
    im = ImageEnhance.Color(im).enhance(1.25)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    im = ImageEnhance.Sharpness(im).enhance(1.15)
    d = ImageDraw.Draw(im, "RGBA")
    for y in range(280, 720): d.line([(0, y), (1280, y)], fill=(0, 0, 0, int(235 * (y - 280) / 440)))
    for y in range(0, 120): d.line([(0, y), (1280, y)], fill=(0, 0, 0, int(130 * (1 - y / 120))))
    f = font(118); ls = wrap(d, hook, f, 1200)[:2]; y0 = 555 - len(ls) * 128
    for i, line in enumerate(ls):
        yy = y0 + i * 128
        d.text((44, yy + 5), line, font=f, fill=(0, 0, 0, 230), stroke_width=8, stroke_fill=(0, 0, 0, 230))
        d.text((40, yy), line, font=f, fill=(255, 228, 0), stroke_width=7, stroke_fill=(0, 0, 0))
    f2 = font(52); w = int(d.textlength(tag_text, font=f2)) + 50
    d.rounded_rectangle((30, 26, 30 + w, 98), 16, fill=(210, 0, 20, 248)); d.text((55, 29), tag_text, font=f2, fill=(255, 255, 255))
    twist_txt = "महा-ट्विस्ट!"
    wt = int(d.textlength(twist_txt, font=f2)) + 46
    d.rounded_rectangle((1280 - wt - 30, 26, 1250, 98), 16, fill=(255, 195, 0, 248))
    d.text((1280 - wt - 7, 29), twist_txt, font=f2, fill=(15, 15, 15))
    f3 = font(46); w3 = int(d.textlength(bottom_text, font=f3)) + 40
    d.rounded_rectangle((1280 - w3 - 30, 648, 1250, 704), 12, fill=(255, 255, 255, 240)); d.text((1280 - w3 - 10, 647), bottom_text, font=f3, fill=(20, 20, 20))
    im.convert("RGB").save(out, quality=90)

def thumbnail_vertical(img, hook, tag_text, bottom_text, out):
    """Create a custom 1080x1920 Facebook Reel cover using the same episode artwork."""
    hook, tag_text, bottom_text = deva(hook), deva(tag_text), deva(bottom_text)
    source = Image.open(img).convert("RGB")

    scale = max(VW / source.width, VH / source.height)
    bg = source.resize((int(source.width * scale) + 1, int(source.height * scale) + 1))
    left, top = (bg.width - VW) // 2, (bg.height - VH) // 2
    bg = bg.crop((left, top, left + VW, top + VH)).filter(ImageFilter.GaussianBlur(radius=32))
    bg = ImageEnhance.Brightness(bg).enhance(0.38)
    im = bg
    draw = ImageDraw.Draw(im, "RGBA")
    for y in range(1080, VH):
        draw.line([(0, y), (VW, y)], fill=(0, 0, 0, int(230 * (y - 1080) / (VH - 1080))))

    max_w, max_h = VW - 80, 760
    scale = min(max_w / source.width, max_h / source.height)
    foreground = source.resize((int(source.width * scale), int(source.height * scale)))
    x, y = (VW - foreground.width) // 2, 510 + (max_h - foreground.height) // 2
    draw.rectangle((x - 5, y - 5, x + foreground.width + 4, y + foreground.height + 4), fill=(255, 195, 0, 255))
    im.paste(foreground, (x, y))

    tag_font = font(48)
    tag_lines = wrap(draw, tag_text, tag_font, VW - 80)[:2]
    tag_h = 74 + max(0, len(tag_lines) - 1) * 58
    draw.rounded_rectangle((30, 34, VW - 30, 34 + tag_h), 18, fill=(180, 0, 20, 245))
    for i, line in enumerate(tag_lines):
        draw.text((VW / 2, 46 + i * 58), line, font=tag_font, anchor="ma", fill=(255, 255, 255))

    hook_font = font(88)
    hook_lines = wrap(draw, hook, hook_font, VW - 100)[:3]
    hook_y = 1400 - len(hook_lines) * 104
    for i, line in enumerate(hook_lines):
        draw.text(
            (VW / 2, hook_y + i * 104), line, font=hook_font, anchor="mm",
            fill=(255, 228, 0), stroke_width=7, stroke_fill=(0, 0, 0),
        )

    footer_font = font(48)
    footer_lines = wrap(draw, bottom_text, footer_font, VW - 100)[:2]
    for i, line in enumerate(footer_lines):
        draw.text((VW / 2, 1760 + i * 58), line, font=footer_font, anchor="mm", fill=(255, 255, 255))
    im.save(out, quality=90)
