"""
Link the file 212 statements (statements_zschema.csv) to Zdanowski's annex and compare them field by field.

Usage   python link_annex.py
Reads   statements_zschema.csv                                  (from 212_zschema.py)
        ../annex/zdanowski_annex_table.csv           (from annex/, run that pipeline first)
        ../annex/scripts/placenames.py               (the shared spelling key)
Writes  link_212.csv                 one row per statement: its annex match (if any), how it matched,
                                     and the comparison of each shared field
        annex_unmatched_212.csv      annex entries recorded at Sharjah within the dates covered by the
                                     212 statements that no statement links to
        link_report.txt              counts, and the cases to review (contains names: keep private)
        results/link_summary.txt     counts only, no names (safe to share)

How a statement is matched (rules applied in this order; each annex entry is used once,
except that a statement flagged as a copy of another links to the same entry)
  linked             same given name and father's name (spelling key), dates within 3 days
  date_differs       same given name and father's name, dates further apart. Listed for review:
                     either the annex misdates the statement or these are two different people.
                     'same_day_month' marks pairs with the same day and month in a different year,
                     the pattern of a misprinted year.
  probable_spelling  same given name, dates within 3 days, father's name differs (check spelling)
  none               no annex entry meets any rule
The spelling key is placenames.match_key, the same transliteration rule used for places.

Fields compared for linked statements: gender, father's name, birthplace, residence, age, date,
and the reason flags. Each comparison is 'same', 'differs', or blank when either side is empty.
Places are compared by name only (a trailing clause and the annex's added context are dropped),
and a pair whose spelling keys are at least 75% similar is marked 'spelling', not 'differs'.
Nothing here decides which side is right; the differences are listed for checking against the images.
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

ZPROJ = Path("../annex")
sys.path.insert(0, str(ZPROJ / "scripts"))
from placenames import match_key, split_context  # noqa: E402
import difflib  # noqa: E402

DAYS = 3
FLAGS = ["ill_treated", "beaten", "chains_or_confinement", "fear_of_sale", "not_paid_or_advance",
         "kidnapped", "re_enslavement", "family_separation_or_search", "duplicate_certificate"]


def to_date(s):
    try:
        return date.fromisoformat(s) if len(s or "") == 10 else None
    except ValueError:
        return None


def name_keys(name, father=""):
    n = re.sub(r"\(.*?\)|\[.*?\]", "", name or "")
    n = re.sub(r"^(?:the\s+)?(?:slave\s+)?", "", n.strip(), flags=re.I)
    parts = re.split(r"\b(?:bin|bint|ibn|int|binti|s/o|d/o)\b", n, maxsplit=1, flags=re.I)
    given = match_key(parts[0].strip().split(" ")[0]) if parts[0].strip() else ""
    fth = father if father and father != "unknown" else (parts[1] if len(parts) > 1 else "")
    fth = re.split(r"[,(]|\bof\b|\bbearer\b|\bdated\b", fth or "")[0].strip()
    fkey = match_key(fth.split(" ")[0]) if fth else ""
    return given, fkey


def cmp(a, b, key=lambda x: x.strip().lower()):
    if not (a or "").strip() or not (b or "").strip():
        return ""
    return "same" if key(a) == key(b) else "differs"


def place_key(p):
    """The place name only: drop a trailing clause ('Abu Dhabi in the house of my master ...'), then
    the context the annex adds ('Khan (Dubai)' -> 'Khan'), then reduce to the spelling key."""
    p = re.split(r"\s+(?:in the house|who|where|and)\b|,", p or "", maxsplit=1)[0]
    return match_key(split_context(p)[0])


def cmp_place(a, b):
    """'same' (equal spelling key), 'spelling' (keys at least 75% similar: Debai/Dubai, Zua'b/Za'ab),
    'differs' (a different place), or blank when either side is empty."""
    if not (a or "").strip() or not (b or "").strip():
        return ""
    ka, kb = place_key(a), place_key(b)
    if ka == kb:
        return "same"
    return "spelling" if difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.75 else "differs"


S = list(csv.DictReader(open("statements_zschema.csv", encoding="utf-8-sig")))
A = [a for a in csv.DictReader(open(ZPROJ / "zdanowski_annex_table.csv", encoding="utf-8"))
     if a["entry_type"] == "statement"]
for a in A:
    a["_d"] = to_date(a["date_iso"])
    a["_g"], a["_f"] = name_keys(a["name"], a["father_name"])
for s in S:
    s["_d"] = to_date(s["date_iso"])
    s["_g"], s["_f"] = name_keys(s["name"], s["father_name"])

used, link = set(), {}
dups = {}
src = list(csv.DictReader(open("statements.csv", encoding="utf-8-sig"))) if Path("statements.csv").exists() else []
for r in src:
    if r.get("possible_duplicate_of"):
        dups[r["statement_id"]] = r["possible_duplicate_of"]


def find(s, rule):
    out = []
    for i, a in enumerate(A):
        if i in used or not s["_g"] or a["_g"] != s["_g"]:
            continue
        close = s["_d"] and a["_d"] and abs((a["_d"] - s["_d"]).days) <= DAYS
        same_f = s["_f"] and a["_f"] == s["_f"]
        if rule == "linked" and same_f and close:
            out.append(i)
        elif rule == "date_differs" and same_f and not close:
            out.append(i)
        elif rule == "probable_spelling" and close and not same_f:
            out.append(i)
    if s["_d"]:
        out.sort(key=lambda i: abs((A[i]["_d"] - s["_d"]).days) if A[i]["_d"] else 99999)
    return out


for rule in ("linked", "date_differs", "probable_spelling"):
    for s in S:
        if s["statement_id"] in link or s["statement_id"] in dups:
            continue
        hits = find(s, rule)
        if hits:
            used.add(hits[0])
            link[s["statement_id"]] = (rule, hits[0])
for sid, orig in dups.items():                      # copies link to the same annex entry as the original
    if orig in link:
        link[sid] = (link[orig][0] + " (copy of " + orig + ")", link[orig][1])

rows = []
for s in S:
    rule, i = link.get(s["statement_id"], ("none", None))
    a = A[i] if i is not None else {}
    gap = (a["_d"] - s["_d"]).days if (a and a.get("_d") and s["_d"]) else ""
    sdm = (a and a.get("_d") and s["_d"] and a["_d"].year != s["_d"].year
           and (a["_d"].month, a["_d"].day) == (s["_d"].month, s["_d"].day))
    r = {"statement_id": s["statement_id"], "statement_name": s["name"], "statement_date": s["date_iso"],
         "link": rule, "annex_id": a.get("id", ""), "annex_name": a.get("name", ""),
         "annex_book_page": a.get("book_page", ""), "annex_date": a.get("date_iso", ""),
         "days_apart": gap, "same_day_month": "Y" if sdm else "",
         "gender": cmp(s["gender"], a.get("gender", "")),
         "father_name": cmp(s["father_name"], a.get("father_name", ""), key=lambda x: match_key(x.split(" ")[0])),
         "birthplace": cmp_place(s["birthplace"], a.get("birthplace", "")),
         "residence": cmp_place(s["residence"], a.get("residence", "")),
         "age": cmp(s["age_years"], a.get("age_years", "")),
         "statement_birthplace": s["birthplace"], "annex_birthplace": a.get("birthplace", ""),
         "statement_residence": s["residence"], "annex_residence": a.get("residence", ""),
         "statement_age": s["age_years"], "annex_age": a.get("age_years", ""),
         "statement_reason": s["reason_or_circumstance"], "annex_reason": a.get("reason_or_circumstance", ""),
         "counts_as_application": s.get("counts_as_application", "")}
    for f in FLAGS:
        r[f"flag_{f}"] = ("same" if s.get(f, "") == a.get(f, "") else "differs") if a else ""
    rows.append(r)

with open("link_212.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

dates = sorted(s["_d"] for s in S if s["_d"])
lo, hi = dates[0], dates[-1]
linked_ids = {A[i]["id"] for _, i in link.values()}
un = [a for a in A if a["recorded_at"] == "British Agency in Sharjah" and a["_d"] and lo <= a["_d"] <= hi
      and a["id"] not in linked_ids]
with open("annex_unmatched_212.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["annex_id", "name", "date_iso", "book_page", "residence", "birthplace", "reason"])
    w.writerows([[a["id"], a["name"], a["date_iso"], a["book_page"], a["residence"], a["birthplace"],
                  a["reason_or_circumstance"]] for a in sorted(un, key=lambda a: a["_d"])])

from collections import Counter  # noqa: E402
c = Counter(r["link"].split(" (")[0] for r in rows)
lk = [r for r in rows if r["link"].startswith("linked")]
L = [f"statements in 212: {len(S)}",
     f"  linked: {c['linked']}; date differs: {c['date_differs']}; probable spelling: {c['probable_spelling']}; "
     f"no annex entry: {c['none']}",
     f"annex entries recorded at Sharjah between {lo} and {hi}: "
     f"{sum(1 for a in A if a['recorded_at'] == 'British Agency in Sharjah' and a['_d'] and lo <= a['_d'] <= hi)}; "
     f"not linked to any 212 statement: {len(un)} (see annex_unmatched_212.csv; 212 lacks subjects 15-23)", "",
     "Field agreement among linked statements (same / differs):"]
for fld in ("gender", "father_name", "age"):
    cc = Counter(r[fld] for r in lk)
    L.append(f"  {fld:12} {cc['same']} / {cc['differs']}")
for fld in ("birthplace", "residence"):
    cc = Counter(r[fld] for r in lk)
    L.append(f"  {fld:12} {cc['same']} / {cc['differs']}   (plus {cc['spelling']} spelling variants, counted as same place)")
L += ["", "Real differences in place or age (check against the image):"]
for fld in ("birthplace", "residence", "age"):
    L += [f"  {r['statement_id']} {fld}: statement {r['statement_' + fld]!r:32} annex {r['annex_' + fld]!r}"
          for r in lk if r[fld] == "differs"]
for f in FLAGS:
    cc = Counter(r[f'flag_{f}'] for r in lk)
    L.append(f"  flag {f:28} {cc['same']} / {cc['differs']}")
L += ["", "Date differs (check: misdated in the annex, or a different person):"]
L += [f"  {r['statement_id']} {r['statement_name'][:30]:30} statement {r['statement_date']}  annex {r['annex_date']} "
      f"(p. {r['annex_book_page']}){'  SAME DAY AND MONTH' if r['same_day_month'] else ''}"
      for r in rows if r["link"].startswith("date_differs")]
L += ["", "Probable spelling matches (check the father's name):"]
L += [f"  {r['statement_id']} {r['statement_name'][:30]:30} ~ {r['annex_name']} (p. {r['annex_book_page']})"
      for r in rows if r["link"].startswith("probable_spelling")]
L += ["", "No annex entry (code counts_as_application before calling any of these an omission):"]
L += [f"  {r['statement_id']} {r['statement_name'][:40]:40} {r['statement_date']}" for r in rows if r["link"] == "none"]
Path("link_report.txt").write_text("\n".join(L), encoding="utf-8")

# counts only, no names: safe to share (results/link_summary.txt)
Ls = L[:3] + ["", "Field agreement among linked statements (same / differs):"]
for fld in ("gender", "father_name", "age", "birthplace", "residence"):
    cc = Counter(r[fld] for r in lk)
    Ls.append(f"  {fld:12} {cc['same']} / {cc['differs']}" + (f"   (plus {cc['spelling']} spelling variants)" if fld in ("birthplace", "residence") else ""))
for f in FLAGS:
    cc = Counter(r[f'flag_{f}'] for r in lk)
    Ls.append(f"  flag {f:28} {cc['same']} / {cc['differs']}")
dd = [r for r in rows if r["link"].startswith("date_differs")]
Ls += ["", f"date differs: {len(dd)}, of which same day and month in a different year (misprinted year): "
       f"{sum(1 for r in dd if r['same_day_month'])}"]
Path("results").mkdir(exist_ok=True)
Path("results/link_summary.txt").write_text("\n".join(Ls), encoding="utf-8")
print("\n".join(L))
