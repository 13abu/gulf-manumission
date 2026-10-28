"""
Parser for the annex of Zdanowski's list of slaves whose statements were
recorded at British Agencies in the Gulf (pp. 191-231).

Step 1  rebuild clean text from the PDF character layer (the PDF's word
        spaces are a private-use glyph, so ordinary extractors drop them)
Step 2  split the annex into sections (recording agency / list type)
Step 3  join wrapped lines into one string per entry (continuations are indented)
Step 4  parse each entry into fields with rules, keeping the raw text alongside

Usage:  python3 zdanowski_parser.py ZDANOWSKI_slaved_data.pdf zdanowski_annex_table
"""
import re, sys, csv, collections
import pdfplumber

SPACE_GLYPHS = {"", "†", " "}  # private-use space and the dagger used as a space


# ---------------------------------------------------------------- step 1
def page_lines(page):
    chars = page.chars
    if not chars:
        return []
    main = collections.Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
    body = [c for c in chars if c["size"] >= 0.8 * main]
    sup = [c for c in chars if c["size"] < 0.7 * main]
    # group body chars into lines by vertical position
    body.sort(key=lambda c: (round(c["top"]), c["x0"]))
    lines = []
    for c in body:
        if lines and abs(lines[-1]["top"] - c["top"]) < 2.5:
            lines[-1]["chars"].append(c)
        else:
            lines.append({"top": c["top"], "chars": [c], "plus": False})
    # superscripts: keep only '+' (repeated-statement marker), attach to nearest line
    for s in sup:
        if s["text"] == "+" and lines:
            nearest = min(lines, key=lambda l: abs(l["top"] - s["top"] - 2))
            nearest["plus"] = True
    out = []
    for l in lines:
        cs = sorted(l["chars"], key=lambda c: c["x0"])
        txt = "".join(" " if c["text"] in SPACE_GLYPHS else c["text"] for c in cs)
        txt = re.sub(r"\s+", " ", txt).strip()
        out.append({"x0": cs[0]["x0"], "text": txt, "plus": l["plus"], "size": main})
    return out


def clean(s):
    s = (s.replace("ë", "'").replace("í", "'").replace("ì", '"').replace("î", '"')
         .replace("ñ", "-"))
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- step 2/3
SECTION_RE = re.compile(r"^(Statements? recorded .*|The list of slaves who applied .*|Names of slaves released.*)$")


def collect_entries(pdf_path):
    pdf = pdfplumber.open(pdf_path)
    entries, section, in_annex, in_footnote = [], None, False, False
    pending_header = ""
    current_year = ""
    for pno, page in enumerate(pdf.pages):
        lines = page_lines(page)
        if not lines:
            continue
        left = min(l["x0"] for l in lines)
        for l in lines:
            t = clean(l["text"])
            if not in_annex:
                if t.replace(" ", "").startswith("Annex"):
                    in_annex = True
                continue
            if re.fullmatch(r"\d{3}", t):  # page number
                continue
            # footnotes start with asterisks and run to end of page block
            if t.startswith("*"):
                in_footnote = True
                continue
            if in_footnote:
                # footnotes sit at the bottom of a page, so skip everything until the page ends
                continue
            if t.replace(" ", "").startswith("wererecorded"):
                continue
            if re.fullmatch(r"(in the )?records", t) and section:
                section = section + " " + t
                continue
            # section headers (may wrap over two lines)
            if pending_header:
                section = clean(pending_header + " " + t)
                pending_header = ""
                continue
            if SECTION_RE.match(t):
                if t.startswith("The list of slaves who applied") or t.startswith("Names of slaves"):
                    if not re.search(r"(records|Bandar Abbas)$", t):
                        pending_header = t
                        continue
                section = t
                continue
            if t.startswith("Additionally, fifteen") or t.startswith("the British Consulate in Muscat"):
                entries.append({"section": section, "page": pno + 1, "text": t, "plus": False, "note": True})
                continue
            if re.fullmatch(r"(1922|1923)", t):
                current_year = t
                continue
            indented = l["x0"] - left > 6
            if indented and entries:
                entries[-1]["text"] += " " + t
                entries[-1]["plus"] |= l["plus"]
            else:
                entries.append({"section": section, "page": pno + 1, "text": t, "plus": l["plus"],
                                "list_year": current_year if section and section.startswith("Names of slaves") else ""})
        in_footnote = False
    return entries


# ---------------------------------------------------------------- step 4
MONTHS = "January|February|Febr\\.|March|April|May|June|July|August|September|Sept|October|November|December"
DATE_RE = re.compile(
    rf"(?:(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+)?(?:of\s+)?({MONTHS}),?\s*(\d{{3,4}})"
    rf"|({MONTHS})\s*-\s*({MONTHS})\s+(\d{{4}})"
    rf"|(?:in\s+)?({MONTHS}),?\s+(\d{{4}})"
    rf"|(\d{{1,2}})\.(\d{{1,2}})\.(\d{{4}})"
    rf"|\b(19[0-4]\d)\b(?:\s*\(\?\))?)", re.I)
ETHNIC = ["half-Arab, half-African", "half-Baluchi, half-African", "half-African, half-Baluchi",
          "half-Arab, half-Baluchi", "father African, mother Baluchi", "African of East Africa origins",
          "African (from Nubia)", "African (?)", "Abyssinian (Walamo)", "Baluchi \"but very negroid\"",
          "African", "Africa", "Arican", "Baluchi", "Abyssinian", "Somali", "Sudanese", "Sudani", "Nubian",
          "Yemeni", "Arab", "Zanzibari", "Persian", "Indian", "Hindu", "Omani", "Makrani", "Najdi",
          "Sawahili"]
OCCUPATIONS = ["pearl diver", "diver", "servant", "domestic", "housemaid", "labourer", "sailor", "gardener",
               "coolie in the oil fields", "coolie with the oil company", "coolie", "oil company worker",
               "clerk", "mason", "cameleer", "fisherman", "goldsmith", "builder", "buttermilk seller",
               "police man", "caretaker of a tower", "hauler", "driven", "soldier"]
MONTH_NUM = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], 1)}


def month_num(m):
    m = m.lower().rstrip(".")
    for k, v in MONTH_NUM.items():
        if k.startswith(m[:3]):
            return v
    return None


def parse_date(seg):
    m = DATE_RE.search(seg)
    if not m:
        return None, None
    g = m.groups()
    if g[0]:
        iso = f"{int(g[2]):04d}-{month_num(g[1]):02d}-{int(g[0]):02d}"
    elif g[3]:
        iso = f"{g[5]}-{month_num(g[3]):02d}"
    elif g[6]:
        iso = f"{g[7]}-{month_num(g[6]):02d}"
    elif g[8]:
        iso = f"{g[10]}-{int(g[9]):02d}-{int(g[8]):02d}"
    else:
        iso = g[11]
    return iso, m


def split_name(name):
    """Name, gender, father's name."""
    gender = ""
    father = ""
    m = re.search(r"\b(bin|bint|ibn|int|bib|s/o|d/o|son of)\b\s+(.*)", name, re.I)
    if m:
        gender = "F" if m.group(1).lower() in ("bint", "int", "d/o") else "M"
        father = m.group(2)
        father = re.sub(r"\s*\(.*?\)\s*", " ", father).strip()
    if re.search(r"wife of", name):
        gender = "F"
    if re.search(r"(her|his|her|) ?fat?h(er|re)'?s name", name):
        father = "unknown"
        gender = "F" if "her father" in name else gender
    return gender, father


def parse_entry(e):
    raw = clean(e["text"]).rstrip("+").strip()
    rec = {"section": e["section"], "page": e["page"], "pdf_page": e["page"],
           "repeated_marker": "+" if e["plus"] or e["text"].rstrip().endswith("+") else "",
           "raw": raw}
    # agency from section header
    sec = e["section"] or ""
    m = re.search(
        r"(?:recorded|at|in|on) (?:the )?(?:British |Political )*(Agency|Consulate|Consular Agency|Residency)?\s*(?:at|in)?\s*(.+)$",
        sec)
    if sec.startswith("Statement"):
        rec["recorded_at"] = re.sub(r"^Statements? recorded (?:at|in|on) (?:the )?", "", sec).rstrip("*")
    else:
        m5 = re.search(r"in (Bandar Abbas|Sharjah|Bahrain and Muscat)", sec)
        rec["recorded_at"] = m5.group(1) if m5 else ""

    parts = [p.strip() for p in re.split(r",(?![^()]*\))", raw)]
    merged = []
    for p in parts:
        if merged and (re.match(r"^half-", p) and re.match(r"^half-", merged[-1])
                       or re.match(r"^near\s", p) and re.match(r"^(born|from)", merged[-1])
                       or re.match(r"^mother\s", p) and merged[-1].startswith("father")):
            merged[-1] += ", " + p
        else:
            merged.append(p)
    parts = merged
    name = parts[0]
    rest = parts[1:]
    rec["name"] = name
    rec["gender"], rec["father_name"] = split_name(name)
    if re.search(r"\b(her|she|wife|mistress who ill-treated her)\b", raw) and not rec["gender"]:
        rec["gender"] = "F"

    resid = birth = eth = age = date_iso = date_txt = ""
    used = set()
    for i, p in enumerate(rest):
        pl = p.lower()
        if not resid and re.match(r"^(from|of)\s", pl) and "father" not in pl:
            resid = re.sub(r"^(from|of)\s+(from\s+)?", "", p)
            # "from X, born in Y" vs "from Bahrain (originally from Qatar)"
            used.add(i);
            continue
        if not birth and re.match(r"^(born|bron|birth[- ]place|place of birth|place of residence)", pl):
            birth = re.sub(r"^(born|bron)\s+(in|on|at|near)?\s*", "", p).strip()
            used.add(i);
            continue
        if not eth:
            hit = next((x for x in ETHNIC if p == x or pl == x.lower()), None)
            if hit or re.fullmatch(r"(half-\w+, )?half-\w+|father .*mother .*|Baluchi .*negroid.*", p):
                eth = p;
                used.add(i);
                continue
        if not age:
            if re.fullmatch(r"(aged )?(about )?\d{1,2}( years?( old)?)?", pl) or re.fullmatch(
                    r"(age (not indicated|unknown|uknown)|\(age (unknown|uknown)\)|no data about age)", pl):
                age = p;
                used.add(i);
                continue
        if not date_iso:
            d, dm = parse_date(p)
            if d:
                date_iso, date_txt = d, p
                used.add(i)
                continue
    # dates may also be split across a comma ("December 1945" fine) or inside the name part
    if not date_iso:
        d, dm = parse_date(raw)
        if d:
            date_iso, date_txt = d, dm.group(0)
    tail = [p for i, p in enumerate(rest) if i not in used]
    # occupation: last tail item that matches an occupation
    occ = ""
    for p in reversed(tail):
        pl = p.lower().rstrip(".")
        if any(re.search(rf"\b{re.escape(o)}\b", pl) for o in OCCUPATIONS) and len(pl) < 45:
            occ = p.rstrip(".");
            tail.remove(p)
            m2 = re.match(r"^(ill-treated|beaten)\s+(.*)$", occ)
            if m2:
                tail.append(m2.group(1));
                occ = m2.group(2)
            break
    reason = ", ".join(tail).strip(" ,.")

    age_num = ""
    am = re.search(r"\d{1,2}", age)
    if am:
        age_num = am.group(0)
    rec.update({
        "residence": resid, "birthplace": birth, "ethnicity_as_recorded": eth,
        "age_as_recorded": age, "age_years": age_num,
        "date_as_recorded": date_txt, "date_iso": date_iso,
        "year": date_iso[:4] if date_iso else "",
        "reason_or_circumstance": reason, "occupation": occ,
    })
    rl = (reason + " " + raw).lower()
    flags = {
        "ill_treated": bool(re.search(
            r"ill-?treated|ill-treatment|maltreatment|badly treated|cruel|harsh|oppress|tortur|troubled|molested", rl)),
        "beaten": "beat" in rl or "baeten" in rl,
        "chains_or_confinement": bool(re.search(r"chain|irons|orons|prison|custody|confinement|imprisoned", rl)),
        "fear_of_sale": bool(re.search(
            r"afraid of being (sold|bartered)|fear\w* of being sold|threatened to be sold|afraid .* will be sold|going to be sold",
            rl)),
        "not_paid_or_advance": bool(re.search(r"not paid|advance|earnings|deprived", rl)),
        "kidnapped": "kidnap" in rl,
        "re_enslavement": bool(
            re.search(r"re-?enslav|re-esclaved|enslaved by his heirs|claimed by his heirs|enslaved again", rl)),
        "family_separation_or_search": bool(re.search(
            r"separat|daughter|son\b|sons|children|wife|husband|relatives|brother|sister|family|mother|father who",
            rl)),
        "duplicate_certificate": bool(re.search(r"duplicate|copy|lost it|stolen certificate", rl)),
    }
    rec.update({k: "Y" if v else "" for k, v in flags.items()})

    rec["book_page"] = int(e["page"]) + 183
    el = eth.lower()
    rec["ethnicity_group"] = (
        "Mixed" if ("half-" in el or "mother" in el) else
        "African" if re.search(r"afric|arican|sawahili|zanzibari|nubian|sudan", el) else
        "Abyssinian" if "abyssin" in el else
        "Baluchi" if re.search(r"baluchi|makrani", el) else
        eth.split(" (")[0] if eth else "")
    if sec.startswith("Statement"):
        rec["entry_type"] = "statement"
    elif sec.startswith("Names of slaves"):
        rec["entry_type"] = "released_repatriated_bandar_abbas"
        rec["date_iso"] = rec["year"] = e.get("list_year", "")
        rec["date_as_recorded"] = ""
        last = rest[-1] if rest else ""
        rec["occupation"] = ""
        rec["reason_or_circumstance"] = last
    else:
        rec["entry_type"] = "applied_statement_not_found"
        # 1937-38 Sharjah list: application, Bahrain communication, authorisation dates
        ds = re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", raw)
        iso = lambda d: "{2}-{1:0>2}-{0:0>2}".format(*d.split("."))
        if len(ds) == 3:
            rec["date_applied"], rec["date_bahrain_communication"], rec["date_authorised"] = map(iso, ds)
            rec["date_iso"] = iso(ds[0]);
            rec["year"] = rec["date_iso"][:4]
            rec["date_as_recorded"] = ""
            rec["reason_or_circumstance"] = ""
            rec["name"] = re.split(r",\s*(?:\d|date of)", raw)[0]
            rec["gender"], rec["father_name"] = split_name(rec["name"])
        m3 = re.search(r"manumitted (?:in (\w+) )?on (\d{1,2}\.\d{1,2}\.\d{4})", raw)
        if m3:
            rec["manumitted_at"] = m3.group(1) or ""
            rec["date_iso"] = iso(m3.group(2));
            rec["year"] = rec["date_iso"][:4]
            rec["date_as_recorded"] = m3.group(0)
        m4 = re.search(r"taken to ([^,]+)", raw)
        if m4:
            rec["taken_to"] = m4.group(1)
        if m3 or m4:
            rec["reason_or_circumstance"] = ""
    return rec


FIELDS = ["id", "entry_type", "section", "recorded_at", "book_page", "pdf_page", "name", "gender", "father_name",
          "residence", "birthplace",
          "ethnicity_as_recorded", "ethnicity_group", "age_as_recorded", "age_years", "date_as_recorded", "date_iso",
          "year",
          "occupation", "reason_or_circumstance", "ill_treated", "beaten", "chains_or_confinement",
          "fear_of_sale", "not_paid_or_advance", "kidnapped", "re_enslavement",
          "family_separation_or_search", "duplicate_certificate", "repeated_marker",
          "taken_to", "manumitted_at", "date_applied", "date_bahrain_communication", "date_authorised", "raw"]


def main(pdf_path, out_prefix):
    entries = collect_entries(pdf_path)
    rows = []
    for e in entries:
        if e.get("note") or e.get("year"):
            continue
        rows.append(parse_entry(e))
    for i, r in enumerate(rows, 1):
        r["id"] = i
    with open(out_prefix + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader();
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    from pathlib import Path

    # The project folder is one level above this script, so paths work whether you
    # press Run in PyCharm or type the command in Terminal.
    PROJECT = Path(__file__).resolve().parent.parent

    pdf = sys.argv[1] if len(sys.argv) > 1 else PROJECT / "data" / "ZDANOWSKI_slaved_data.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else str(PROJECT / "zdanowski_annex_table")
    rows = main(str(pdf), out)
    print("wrote", out + ".csv")
    print(len(rows), "rows")
    print(collections.Counter(r["section"] for r in rows))