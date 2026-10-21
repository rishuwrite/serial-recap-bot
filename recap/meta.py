import re
import config as S

def hashtag(s): return "#" + re.sub(r"[^\w]", "", s)

def _next(ep):
    return str(int(ep) + 1) if str(ep).isdigit() else ""

def make_title(show, ep, date_, headline):
    """Package the recap as a next-day episode guess, not as a verified episode."""
    short = " ".join(date_.split()[:2]) if date_ else ""
    base = f"{show['en']} Ep {ep} | {short} | कल क्या होगा? अनुमान"
    t = f"{base} | {headline}" if headline else base
    return t if len(t) <= 98 else base[:98]

def make_tags(show, ep, date_, kws, limit=480):
    en, hi = show["en"], show["hi"]
    cand = [en, hi, f"{en} {date_}", f"{en} episode {ep}", f"{en} full episode {ep}", f"{en} today episode", f"{en} episode summary",
            f"{en} story in hindi", f"{en} next episode", f"{en} kal ka episode", f"{en} update", f"{hi} आज का एपिसोड", f"{hi} कहानी",
            f"{hi} एपिसोड {ep}"] + ([f"{en} episode {ep} prediction", f"{hi} एपिसोड {ep} अनुमान"] if str(ep).isdigit() else []) + show["alt"] + list(kws) + S.BASE_TAGS
    out, seen, total = [], set(), 0
    for t in cand:
        t = re.sub(r"[<>\"]", "", str(t)).strip(); k = t.lower()
        if not t or k in seen: continue
        cost = len(t) + 1 + (2 if " " in t else 0)
        if total + cost > limit: continue
        seen.add(k); out.append(t); total += cost
    return out

def mmss(s): return f"{int(s) // 60:02d}:{int(s) % 60:02d}"

def chapters(starts):
    """starts: [(seconds, title)]. YouTube needs a 00:00 start and >=10 s between chapters."""
    out, last = [], -99
    for t, name in starts:
        if not out or t - last >= 10: out.append((t, name)); last = t
    return "\n".join(f"{mmss(t)} {n}" for t, n in out) if len(out) >= 3 else ""

def make_description(show, ep, date_, ep_url, hook, starts, prediction, kws, tags, source_episode="?", source_date=""):
    d = (f"कल के एपिसोड की कहानी क्या मोड़ ले सकती है? इस वीडियो में पिछले उपलब्ध एपिसोड का छोटा रिकैप "
         f"और अगले एपिसोड के लिए 3 संभावित अनुमान हैं।\n\n"
         f"📺 {show['en']} ({show['hi']}) | अनुमानित तारीख: {date_} | अगले एपिसोड का नंबर: {ep}\n"
         f"📝 स्रोत: एपिसोड {source_episode}" + (f" ({source_date})" if source_date else "") + " का रिकैप।\n")
    ch = chapters(starts)
    if ch: d += f"\nअध्याय:\n{ch}\n"
    d += f"\n🔮 एपिसोड {ep} के लिए 3 संभावनाएँ (सिर्फ़ अनुमान, पुष्टि की हुई कहानी नहीं):\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(prediction[:3])) + "\n"
    d += f"\n▶ स्रोत का आधिकारिक एपिसोड यहाँ देखें: {ep_url}\n"
    d += f"\nखोज-शब्द: {show['en']} {date_} episode {ep} prediction, {show['hi']} कल की कहानी, " + ", ".join(list(kws)[:20]) + "\n"
    d += "\n" + " ".join([hashtag(show["en"]), "#NextEpisodePrediction", "#SerialSummary", "#DangalTV", "#HindiSerial"]) + "\n"
    d += ("\nडिस्क्लेमर: यह फ़ैन-निर्मित रिकैप और भविष्यवाणी है। अगले एपिसोड की घटनाएँ सत्यापित नहीं हैं। "
          "शो के सभी अधिकार मूल निर्माताओं/चैनल के पास हैं। चित्र AI से बनाए गए हैं; आवाज़ AI की है।\n")
    return d[:4900]
