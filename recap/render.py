import functools, glob, math, os, random, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from latin import deva
import config as S
W, H, FPS = S.W, S.H, S.FPS

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
    return lines + [cur]

@functools.lru_cache(None)
def _fp(): return find_font()
@functools.lru_cache(None)
def font(size): return ImageFont.truetype(_fp(), size, layout_engine=ImageFont.Layout.RAQM)
_d = ImageDraw.Draw(Image.new("RGB", (8, 8)))

def cover(img, out):
    """Fill the 16:9 frame; slightly oversize + centre-crop so any corner watermark is pushed out of view."""
    im = Image.open(img).convert("RGB"); r = max(W / im.width, H / im.height) * 1.10
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)); l, t = (im.width - W) // 2, (im.height - H) // 2
    im.crop((l, t, l + W, t + H)).save(out, quality=92)

def card(title, emotion, out):
    """Used only when an illustration could not be generated: designed title card, never a blank screen."""
    c0 = S.EMOTION_COLORS.get(emotion, (60, 30, 90)); im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H): k = y / H; d.line([(0, y), (W, y)], fill=tuple(int(c0[i] * (1 - 0.7 * k)) for i in range(3)))
    f = font(110); ls = wrap(d, title, f, 1500)[:3]; y0 = 430 - len(ls) * 70
    for i, l in enumerate(ls): d.text(((W - d.textlength(l, font=f)) / 2, y0 + i * 140), l, font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
    im.save(out, quality=90)

def panel(chip_l, chip_r, emotion, out):
    chip_l, chip_r = deva(chip_l), deva(chip_r)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for y in range(640, H):                                  # bottom shade for caption readability
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(215 * (y - 640) / (H - 640))))
    for y in range(0, 170): d.line([(0, y), (W, y)], fill=(0, 0, 0, int(140 * (1 - y / 170))))
    f = font(40); wl = int(d.textlength(chip_l, font=f)) + 50
    d.rounded_rectangle((30, 28, 30 + wl, 92), 14, fill=(200, 0, 20, 245)); d.text((55, 32), chip_l, font=f, fill=(255, 255, 255))
    col = S.EMOTION_COLORS.get(emotion, (255, 190, 0)) if chip_r != "अनुमान" else (255, 170, 0)
    wr = int(d.textlength(chip_r, font=f)) + 50
    d.rounded_rectangle((W - wr - 30, 28, W - 30, 92), 14, fill=col + (245,)); d.text((W - wr - 5, 32), chip_r, font=f, fill=(255, 255, 255))
    im.save(out)

def chunks(text, a, b):
    text = deva(text)
    ls = wrap(_d, text, font(56), 1740); groups = [ls[i:i + 2] for i in range(0, len(ls), 2)]
    tot = sum(len(" ".join(g)) for g in groups) or 1; t = a; res = []
    for g in groups:
        w = len(" ".join(g)) / tot * (b - a); res.append((g, t, t + w)); t += w
    return res

def caption(lines, out):
    im = Image.new("RGBA", (W, 230), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = font(56); y = (230 - 78 * len(lines)) // 2
    for l in lines:
        d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0)); y += 78
    im.save(out)

def clip(comp, frames, path, variant):
    N = frames
    z, x = [("min(1+0.0006*on,1.2)", "iw/2-(iw/zoom/2)"), ("max(1.2-0.0006*on,1.0)", "iw/2-(iw/zoom/2)"),
            ("1.15", f"(iw-iw/zoom)*on/{N}"), ("1.15", f"(iw-iw/zoom)*(1-on/{N})")][variant % 4]
    y = "ih/2-(ih/zoom/2)"
    vf = f"scale=2400:1350,zoompan=z='{z}':x='{x}':y='{y}':d={N}:s={W}x{H}:fps={FPS},format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", comp, "-vf", vf, "-frames:v", str(N),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-an", path], check=True)

def segment(tag, chip_l, chip_r, emotion, lines, times, audio, comp, tmp, out, offset, total, v0=0):
    D = times[-1][1]; n = max(1, math.ceil(D / 8)); bounds = [D * k / n for k in range(n + 1)]; paths = []
    for k in range(n):
        p = f"{tmp}/{tag}_c{k}.mp4"; clip(comp, max(round(bounds[k + 1] * FPS) - round(bounds[k] * FPS), 2), p, v0 + k); paths.append(p)
    open(f"{tmp}/{tag}_c.txt", "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in paths))
    bg = f"{tmp}/{tag}_bg.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{tmp}/{tag}_c.txt", "-c", "copy", bg], check=True)
    panel(chip_l, chip_r, emotion, f"{tmp}/{tag}_panel.png")
    bar = f"{tmp}/bar.png"
    if not os.path.exists(bar): Image.new("RGBA", (W, 12), (255, 200, 0, 245)).save(bar)
    ins = ["-i", bg, "-i", audio, "-i", f"{tmp}/{tag}_panel.png", "-i", bar]; flt = "[0:v][2:v]overlay=0:0[v0];"; n_ov = 0
    for li, (ln, (a, b)) in enumerate(zip(lines, times)):
        for gi, (g, ta, tb) in enumerate(chunks(ln, a, b)):
            cp = f"{tmp}/{tag}_cap{li}_{gi}.png"; caption(g, cp); ins += ["-i", cp]
            flt += f"[v{n_ov}][{4 + n_ov}:v]overlay=0:830:enable='between(t,{ta:.3f},{tb:.3f})'[v{n_ov + 1}];"; n_ov += 1
    flt += f"[v{n_ov}][3:v]overlay=x='-{W}+{W}*(t+{offset:.3f})/{total:.3f}':y={H - 12}[outv]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", flt, "-map", "[outv]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "5000k", "-bufsize", "10000k", "-r", str(FPS), "-g", str(FPS * 2),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k", "-t", f"{D:.3f}", out], check=True)
    for p in paths + [bg]: os.remove(p)
    return D

def concat(files, tmp, out, music=None, total=0):
    open(f"{tmp}/final.txt", "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in files))
    raw = out if not music else out + ".nomusic.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{tmp}/final.txt", "-c", "copy", "-movflags", "+faststart", raw], check=True)
    if music:  # optional background music (your own royalty-free tracks in serial/music/), low volume, fades out
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-stream_loop", "-1", "-i", music, "-filter_complex",
                        f"[1:a]volume=0.10,afade=t=in:d=1.5,afade=t=out:st={max(total - 2.5, 0):.2f}:d=2.5[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)
        os.remove(raw)

def thumbnail(img, hook, tag_text, bottom_text, out):
    hook, tag_text, bottom_text = deva(hook), deva(tag_text), deva(bottom_text)
    im = Image.open(img).convert("RGB"); r = max(1280 / im.width, 720 / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1)); l, t = (im.width - 1280) // 2, (im.height - 720) // 2
    im = im.crop((l, t, l + 1280, t + 720)).filter(ImageFilter.GaussianBlur(0)); d = ImageDraw.Draw(im, "RGBA")
    for y in range(300, 720): d.line([(0, y), (1280, y)], fill=(0, 0, 0, int(230 * (y - 300) / 420)))
    f = font(120); ls = wrap(d, hook, f, 1200)[:2]; y0 = 560 - len(ls) * 130
    for i, l in enumerate(ls): d.text((40, y0 + i * 130), l, font=f, fill=(255, 225, 0), stroke_width=7, stroke_fill=(0, 0, 0))
    f2 = font(54); w = int(d.textlength(tag_text, font=f2)) + 50
    d.rounded_rectangle((30, 28, 30 + w, 100), 16, fill=(200, 0, 20, 245)); d.text((55, 30), tag_text, font=f2, fill=(255, 255, 255))
    f3 = font(48); w3 = int(d.textlength(bottom_text, font=f3)) + 40
    d.rounded_rectangle((1280 - w3 - 30, 650, 1250, 705), 12, fill=(255, 255, 255, 235)); d.text((1280 - w3 - 10, 648), bottom_text, font=f3, fill=(20, 20, 20))
    im.convert("RGB").save(out, quality=88)

def pick_music():
    tr = glob.glob(os.path.join(S.BASE, "music", "*.mp3")) + glob.glob(os.path.join(S.BASE, "music", "*.m4a"))
    return random.choice(tr) if tr else None
