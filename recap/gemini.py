import json, os, time, requests
BASE = "https://generativelanguage.googleapis.com/v1beta"

def list_models(key):
    """Stable flash models first; preview/omni models often have 0 free quota (429), so they go last."""
    names = [os.getenv("GEMINI_MODEL") or "", "gemini-flash-latest"]
    try:
        r = requests.get(f"{BASE}/models", params={"key": key, "pageSize": 200}, timeout=30).json()
        ok = [m["name"].split("/")[-1] for m in r.get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
              and not any(x in m["name"] for x in ("image", "tts", "live", "audio", "robotics", "computer", "omni", "exp"))]
        names += sorted([n for n in ok if "preview" not in n and "lite" not in n], reverse=True)
        names += sorted([n for n in ok if "preview" not in n and "lite" in n], reverse=True)
        names += sorted([n for n in ok if "preview" in n], reverse=True)
    except Exception:
        pass
    names.append("gemini-2.5-flash")
    seen = []
    for n in names:
        if n and n not in seen: seen.append(n)
    return seen

PROMPT = """आप एक हिंदी टीवी-सीरियल रिकैप राइटर हैं। यह वीडियो एक पूरा सीरियल-एपिसोड है। इसे ध्यान से देखें-सुनें और 2-3 मिनट के \"मोशन कॉमिक\" रिकैप वीडियो की स्क्रिप्ट बनाएँ।
नियम:
- सारा हिंदी टेक्स्ट सिर्फ़ देवनागरी में (अंग्रेज़ी शब्द/संक्षेप भी देवनागरी में, जैसे "डीएनए"); सिर्फ़ image_prompt अंग्रेज़ी में।
- सिर्फ़ वही लिखें जो एपिसोड में सचमुच हुआ/कहा गया। पात्रों के नाम वही रखें जो संवादों में बोले गए हों; पक्का न हो तो \"बहू\", \"दादी\" जैसे रिश्ते लिखें। कलाकारों/अभिनेताओं के असली नाम कभी न लिखें।
- संवादों की नक़ल न करें; घटनाओं का सार अपने शब्दों में, सरल बोलचाल की हिंदी में।
- 8 या 9 दृश्य, हर दृश्य की narration 26-34 शब्द। कुल narration (hook, दृश्य, cliffhanger, prediction) लगभग 330-380 शब्द।
- \"hook\": 1 रोचक सवाल (15-22 शब्द), \"cliffhanger\": एपिसोड का अंत 1-2 वाक्य में।
- \"prediction\": 2 वाक्य जिनमें अंत के आधार पर अनुमान हो कि आगे क्या हो सकता है; यह साफ़ अनुमान की भाषा में हो (\"शायद\", \"हो सकता है\"), तथ्य की तरह नहीं।
- चित्रों के लिए: \"characters\" में हर मुख्य पात्र का अंग्रेज़ी visual विवरण (उम्र, बाल, कपड़ों के रंग, पहचान की एक चीज़) - यह किसी असली व्यक्ति से मेल न खाए, सामान्य रखें। हर दृश्य के \"image_prompt\" में दृश्य का क्षण, जगह, भाव और उसमें मौजूद हर पात्र का visual विवरण शब्दशः लिखें (अंग्रेज़ी, 40-70 शब्द)। ख़ून/हिंसा/नग्नता न माँगें; बच्चों को ख़तरे में न दिखाएँ।
- \"keywords\": इस एपिसोड की कहानी और शो से जुड़े 20 प्रासंगिक खोज-शब्द (हिंदी + अंग्रेज़ी), कोई असंबंधित शो/व्यक्ति का नाम नहीं।
केवल JSON:
{"characters":[{"key":"c1","name":"...","visual":"..."}],
 "hook":"...","headline":"<=8 शब्द","thumb_text":"<=5 शब्द का सवाल/हुक","hook_scene":0,
 "scenes":[{"title":"<=5 शब्द","narration":"...","emotion":"tense|sad|happy|angry|romantic|shock","image_prompt":"..."}],
 "cliffhanger":"...","prediction":["...","..."],"prediction_image_prompt":"...","keywords":["..."]}
"""

def analyze(video_url, show_name, episode):
    key = os.environ["GEMINI_API_KEY"]; models = list_models(key)[:8]; last = None
    base_cfg = {"responseMimeType": "application/json", "temperature": 0.5}
    for rnd, wait in enumerate([0, 30, 60, 120]):
        if wait: print(f"  all models busy, retrying in {wait}s"); time.sleep(wait)
        for m in models:
            for cfg in ({**base_cfg, "mediaResolution": "MEDIA_RESOLUTION_LOW"}, base_cfg):
                payload = {"contents": [{"parts": [{"file_data": {"file_uri": video_url}},
                                                   {"text": PROMPT + f"\nशो: {show_name} | एपिसोड: {episode}"}]}], "generationConfig": cfg}
                try: r = requests.post(f"{BASE}/models/{m}:generateContent", params={"key": key}, json=payload, timeout=900)
                except Exception as e: last = f"{m}: {type(e).__name__}"; break
                if r.status_code == 200:
                    try:
                        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        txt = txt.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                        print("  analysed with", m); return json.loads(txt)
                    except Exception as e: last = f"{m}: bad response ({e})"; print(" ", last); break
                last = f"{m}: {r.status_code} {r.text[:160]}"; print("  failed ->", m, r.status_code)
                if r.status_code != 400: break          # only 400 can mean 'mediaResolution unsupported' -> retry once without it
    raise SystemExit("Gemini could not analyse the video. Last error: " + str(last))
