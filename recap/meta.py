import re
import config as S

def hashtag(s): return "#" + re.sub(r"[^\w]", "", s)

def make_title(show, ep, date_, headline):
    base = f"{show['en']} | {date_} | Episode {ep} की कहानी".replace("Episode  ", "Episode ")
    t = f"{base} | {headline}"
    return t if len(t) <= 98 else base[:98]

def make_tags(show, ep, date_, kws, limit=480):
    en, hi = show["en"], show["hi"]
    cand = [en, hi, f"{en} {date_}", f"{en} episode {ep}", f"{en} full episode {ep}", f"{en} today episode", f"{en} episode summary",
            f"{en} story in hindi", f"{en} next episode", f"{en} kal ka episode", f"{en} update", f"{hi} आज का एपिसोड", f"{hi} कहानी",
            f"{hi} एपिसोड {ep}"] + show["alt"] + list(kws) + S.BASE_TAGS
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

def make_description(show, ep, date_, ep_url, hook, starts, prediction, kws, tags):
    d = f"{hook}\n\n📺 {show['en']} ({show['hi']}) | {date_} | एपिसोड {ep} की पूरी कहानी, 2-3 मिनट में।\n"
    ch = chapters(starts)
    if ch: d += f"\nअध्याय:\n{ch}\n"
    d += "\n⚠ कल क्या हो सकता है (सिर्फ़ अनुमान, असली एपिसोड नहीं):\n" + "\n".join(prediction) + "\n"
    d += f"\n▶ आधिकारिक पूरा एपिसोड यहाँ देखें: {ep_url}\n"
    d += f"\nखोज-शब्द: {show['en']} {date_} episode {ep} summary, {show['hi']} आज की कहानी, " + ", ".join(list(kws)[:20]) + "\n"
    d += "\n" + " ".join([hashtag(show["en"]), "#SerialSummary", "#DangalTV", "#HindiSerial", "#TodayEpisode"]) + "\n"
    d += ("\nडिस्क्लेमर: यह एक फ़ैन-निर्मित रिकैप है। शो के सभी अधिकार मूल निर्माताओं/चैनल के पास हैं। इसमें शो का कोई वीडियो, ऑडियो या संगीत इस्तेमाल नहीं हुआ। "
          "चित्र AI से बनाए गए हैं और किसी कलाकार की छवि नहीं हैं; आवाज़ AI की है।\n")
    return d[:4900]
