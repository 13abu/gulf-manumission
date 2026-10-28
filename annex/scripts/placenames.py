"""
Shared rules for turning a place string from the annex into something that can be
compared and looked up. Used by normalise_places.py and geocode_places.py.

Every rule here is general (it applies to all strings the same way). There is no
list of individual places in this file.
"""
import re
import unicodedata

# words that describe the kind of place, not its name
GENERIC_WORDS = {"island", "islet", "isle", "jazirat", "jazira", "village", "town", "port",
                 "oasis", "coast", "the", "of", "interior", "inside", "district"}

# Arabic article and common prefixes as they appear in English transliteration
ARTICLE = re.compile(r"\b(al|el|ar|as|ad|an|ash|az|at)[- ]", re.I)


def split_context(raw):
    """Separate the place name from the qualifying context the annex adds.

    'Jumairah (Dubai)'            -> ('Jumairah', 'Dubai')
    'Mareed near Ras al-Khaimah'  -> ('Mareed', 'Ras al-Khaimah')
    'Calicut of Malabar'          -> ('Calicut', 'Malabar')
    'Jubail in Saudi Arabia'      -> ('Jubail', 'Saudi Arabia')
    'Bahrain (originally from Qatar)' -> ('Bahrain', 'originally from Qatar')
    """
    s = raw.strip()
    s = re.sub(r"^(from|in|the)\s+", "", s, flags=re.I)
    context = ""
    m = re.search(r"\(([^)]*)\)", s)
    if m:
        context = m.group(1).strip()
        s = (s[:m.start()] + s[m.end():]).strip()
    m = re.match(r"^(.*?)\s+(?:near|of|in|under)\s+(.+)$", s, flags=re.I)
    if m and m.group(1).strip():
        s, extra = m.group(1).strip(), m.group(2).strip()
        context = f"{extra}; {context}" if context else extra
    # drop words that describe the kind of place ('islet Huwar' -> 'Huwar', 'Siri Island' -> 'Siri')
    words = [w for w in s.split() if w.lower() not in GENERIC_WORDS]
    if words:
        s = " ".join(words)
    elif context:                       # 'the interior of Oman': the name is the context
        s, context = context, ""
    return s.strip(" ,"), context


def is_island(raw):
    return bool(re.search(r"\b(island|islet|isle|jazirat|jazira)\b", raw, re.I))


def match_key(name):
    """A spelling-insensitive key for comparing transliterations.

    The steps reduce the variation that English transliteration of Arabic and
    Persian names produces: case, accents, apostrophes (for 'ayn and hamza),
    the article, doubled letters, long-vowel spellings and a few consonant
    alternations. Two spellings with the same key are treated as the same name.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = ARTICLE.sub("", s)
    s = re.sub(r"['`’ʿʾ\-]", "", s)
    words = [w for w in re.split(r"[^a-z]+", s) if w and w not in GENERIC_WORDS]
    s = "".join(words)
    # vowel and consonant alternations common in transliteration
    for a, b in [("ee", "i"), ("oo", "u"), ("ou", "u"), ("ei", "ai"), ("ay", "ai"),
                 ("ah", "a"), ("eh", "a"), ("aa", "a"), ("q", "k"), ("gh", "g"),
                 ("kh", "k"), ("dh", "d"), ("th", "t"), ("sh", "s"), ("y", "i"),
                 ("w", "u"), ("e", "a"), ("o", "u")]:
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)          # doubled letters
    return s