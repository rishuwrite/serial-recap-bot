import re
# Noto Sans Devanagari has no Latin glyphs: any Latin letters in captions would show as empty boxes.
_L = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", ["ए", "बी", "सी", "डी", "ई", "एफ", "जी", "एच", "आई", "जे", "के", "एल", "एम", "एन", "ओ", "पी", "क्यू", "आर", "एस", "टी", "यू", "वी", "डब्ल्यू", "एक्स", "वाई", "ज़ेड"]))

def deva(text):
    """Spell ALL-CAPS acronyms in Devanagari (BJP -> बीजेपी). Other Latin words should already be written in Devanagari by the script prompt."""
    return re.sub(r"\b[A-Z]{2,7}\b", lambda m: "".join(_L[c] for c in m.group()), text or "")
