import base64, io, os, time, urllib.parse, requests
from PIL import Image
import config as S
_last = [0.0]

def _cloudflare(prompt, seed):
    acc, tok = os.getenv("CF_ACCOUNT_ID"), os.getenv("CF_API_TOKEN")
    if not (acc and tok): return None
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                      headers={"Authorization": f"Bearer {tok}"}, json={"prompt": prompt[:2000], "steps": 6}, timeout=120)
    r.raise_for_status()
    return Image.open(io.BytesIO(base64.b64decode(r.json()["result"]["image"]))).convert("RGB")

def _pollinations(prompt, seed):
    wait = 17 - (time.time() - _last[0])                       # anonymous tier: ~1 request / 15 s
    if wait > 0: time.sleep(wait)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1500]) +
           f"?width=1280&height=720&seed={seed}&model=flux&nologo=true")
    hdr = {"User-Agent": "SerialRecapBot/1.0"}
    if os.getenv("POLLINATIONS_TOKEN"): hdr["Authorization"] = "Bearer " + os.getenv("POLLINATIONS_TOKEN")
    r = requests.get(url, headers=hdr, timeout=180); _last[0] = time.time()
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"): raise ValueError("not an image")
    return Image.open(io.BytesIO(r.content)).convert("RGB")

def generate(prompt, seed, out):
    """Make one illustration. Tries Cloudflare (if configured) then Pollinations, with retries. Returns True on success."""
    full = f"{prompt}. Style: {S.STYLE}"
    for name, fn in (("cloudflare", _cloudflare), ("pollinations", _pollinations)):
        for attempt in range(3):
            try:
                im = fn(full, seed)
                if im is None: break
                if im.width < 400 or im.height < 300: raise ValueError("tiny")
                im.save(out, quality=92); print(f"    image ok via {name}"); return True
            except Exception as e:
                print(f"    {name} try {attempt + 1}/3: {type(e).__name__}: {str(e)[:80]}"); time.sleep(8 * (attempt + 1))
    return False
