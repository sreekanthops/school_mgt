"""Language filter for the anonymous idea board.

Server-side only (the browser merely previews it). It rejects profanity, sexual wording, slurs, threats and
personal contact details (phone numbers, e-mail, links). A word list can never catch everything, so the
board also lets authors delete their own note and lets school moderators delete any note."""
import re

# Whole-word matches only, so innocent words that merely contain a bad string (e.g. "class", "assess") pass.
BLOCKED_WORDS = {
    # profanity and insults
    "fuck", "fucker", "fucking", "fck", "fuk", "shit", "shitty", "bullshit", "bitch", "bastard", "asshole", "arse",
    "arsehole", "dick", "dickhead", "cock", "prick", "twat", "wanker", "bollocks", "crap", "piss", "slut", "whore",
    "hoe", "douche", "douchebag", "moron", "idiot", "stupid", "dumbass", "jackass", "retard", "retarded", "loser",
    "scumbag", "damn", "goddamn", "hell",
    # sexual wording
    "sex", "sexy", "sexual", "porn", "porno", "nude", "nudes", "naked", "boobs", "boob", "tits", "titties", "pussy",
    "vagina", "penis", "dildo", "orgasm", "masturbate", "masturbation", "erotic", "horny", "rape", "raped", "rapist",
    "molest", "molested", "blowjob", "handjob", "cum", "cumshot", "anal", "fetish", "stripper", "xxx",
    # slurs and hate
    "nigger", "nigga", "faggot", "fag", "dyke", "tranny", "chink", "paki", "kike", "spic", "coon", "negro",
    # common abusive words in Hindi/Telugu written in English letters
    "madarchod", "behenchod", "bhenchod", "chutiya", "chutiye", "gandu", "harami", "haramzada", "bhosdi", "bhosdike",
    "randi", "lavda", "lund", "saala", "kutta", "kamina", "lanjakodaka", "lanja", "dengey", "dengu", "puku", "gudda",
    "modda", "pooku", "dengesey", "sulli",
}
BLOCKED_PHRASES = [
    "kill yourself", "kill urself", "go die", "hang yourself", "i will kill", "ill kill", "i will hurt", "shoot up",
    "bomb threat", "blow up the school", "suicide", "hate you all", "shut up",
]

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "+": "t"})
_PHONE = re.compile(r"(?:\+?\d[\s\-().]?){8,}")
_EMAIL = re.compile(r"[\w.+-]+\s*(?:@|\[at\]|\(at\))\s*[\w-]+\s*(?:\.|\[dot\]|\(dot\))\s*\w+", re.I)
_LINK = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|net|org|in|io|co|xyz|me)\b", re.I)
REASON = "That note contains words or details that are not allowed on the school board. Please rephrase it."


def _variants(token: str) -> set[str]:
    """The token plus versions with stretched letters squeezed: 'fuuuck' -> 'fuck', 'assss' -> 'ass'."""
    return {token, re.sub(r"(.)\1{2,}", r"\1", token), re.sub(r"(.)\1{2,}", r"\1\1", token)}


def _tokens(text: str) -> list[str]:
    plain = re.findall(r"[a-z]+", text.lower())
    mapped = re.findall(r"[a-z]+", text.lower().translate(_LEET))
    # letters spaced out to dodge the filter: "f u c k" -> "fuck"
    joined, run = [], []
    for t in mapped + [""]:
        if len(t) == 1:
            run.append(t)
            continue
        if len(run) >= 3:
            joined.append("".join(run))
        run = []
    return plain + mapped + joined


def problem(text: str) -> str | None:
    """None if the text is fine, otherwise a short generic reason (never echoes the offending word)."""
    flat = " ".join(text.lower().translate(_LEET).split())
    if _PHONE.search(text) or _EMAIL.search(text) or _LINK.search(text):
        return REASON
    if any(p in flat for p in BLOCKED_PHRASES):
        return REASON
    for tok in _tokens(text):
        if _variants(tok) & BLOCKED_WORDS:
            return REASON
    return None
