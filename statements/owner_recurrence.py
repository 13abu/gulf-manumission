"""
Do owners and intermediaries recur across the file 212 statements? (The test that decides whether
ownership can be traced across statements, or only within each one.)

Usage   python owner_recurrence.py
Reads   extractions/212/*.json              raw replies from 212_zschema.py (names and roles kept apart)
        statements_zschema.csv              statement dates
        ../annex/scripts/placenames.py   the shared spelling key
Writes  mentions_212.csv                    one row per person mentioned as owner, seller, buyer,
                                            heir, kidnapper or intermediary
        people_212.csv                      one row per person after grouping mentions
        recurrence_report.txt               the counts, and the recurring people (contains names: keep private)
        results/recurrence_summary.txt      counts only, no names (safe to share)

Rules
  1. A mention is cleaned of titles (Shaikh, Sayid, Khan Bahadur, Ruler of ...) and of a trailing
     'of <place>', which is kept as the person's place.
  2. A name is linkable only if it has a given name AND at least one 'bin/bint' element. A bare
     given name ('Abdullah', 'Said of Batinah') or a group ('Bedouins') is too common to link and is
     counted as unlinkable.
  3. Two mentions are the same person if their given name and father's name have the same spelling
     key, and any further element they both have (grandfather, family name 'al ...') also matches.
     'Muhamad bin Ahmad Dalmuk' and 'Muhamad bin Ahmad bin Dalmuk' therefore group together.
  4. A person 'recurs' if they appear in statements recorded more than 3 days apart, i.e. in
     separate applications, not just in the statements of one household recorded together.
Grouping by name cannot prove identity: two different men can share a name. The people_212.csv
rows with recurrence are candidates to confirm from the statements' context (place, kin, dates).
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path("../annex/scripts")))
from placenames import match_key  # noqa: E402

TITLES = re.compile(r"\b(?:shaikh|sheikh|shaikha|sayid|sayyid|saiyid|khan bahadur|khan sahib|haji|hajji|"
                    r"the late|late|nakhuda)\b\.?", re.I)
RULER = re.compile(r",?\s*(?:the\s+)?ruler of .*$", re.I)
GROUPS = re.compile(r"\b(?:bedouins?|unknown|a man|some|people|men|another|my master|his master|"
                    r"her master|two sons|sons of|family of|heirs?)\b", re.I)
LINK = re.compile(r"\s+\b(?:bin|bint|ibn|binti)\b\s+", re.I)
DAYS = 3


def parse(name):
    """-> (given, [lineage...], family, place) or None if not linkable."""
    n = re.sub(r"\s+", " ", name or "").strip(" ,.")
    if not n or GROUPS.search(n):
        return None
    n = RULER.sub("", n)
    place = ""
    m = re.search(r"\s+of\s+([A-Z][\w' -]+)$", n)
    if m:
        place, n = m.group(1).strip(), n[:m.start()]
    n = TITLES.sub("", n).strip(" ,.")
    family = ""
    m = re.search(r"\s+(?:al|el)[\s-]+([\w'-]+)$", n, re.I)
    if m:
        family, n = m.group(1), n[:m.start()]
    parts = [p.strip() for p in LINK.split(n) if p.strip()]
    if len(parts) < 2:
        return None
    given, lineage = parts[0].split(" ")[0], parts[1:]
    # 'Muhamad bin Ahmad Dalmuk': a second word in the last element is a family name
    last = lineage[-1].split(" ")
    if len(last) > 1 and not family:
        lineage[-1], family = last[0], " ".join(last[1:])
    return given, lineage, family, place


def key(p):
    given, lineage, family, _ = p
    return match_key(given), [match_key(x.split(" ")[0]) for x in lineage], match_key(family) if family else ""


def same(k1, k2):
    if k1[0] != k2[0] or not k1[1] or not k2[1] or k1[1][0] != k2[1][0]:
        return False
    rest1, rest2 = k1[1][1:] + ([k1[2]] if k1[2] else []), k2[1][1:] + ([k2[2]] if k2[2] else [])
    # any further element present on both sides must agree (in order)
    for a, b in zip(rest1, rest2):
        if a != b:
            return False
    return True


S = {r["statement_id"]: r for r in csv.DictReader(open("statements_zschema.csv", encoding="utf-8-sig"))}
mentions = []
for f in sorted(Path("extractions/212").glob("S*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    sid, rep = d["statement_id"], d.get("reply") or {}
    if sid not in S:
        continue
    for t in rep.get("transfers") or []:
        mode = t.get("mode") or ""
        if t.get("from"):
            mentions.append((sid, t["from"], f"transfer from ({mode})"))
        if t.get("to"):
            mentions.append((sid, t["to"], f"transfer to ({mode})"))
    co = (rep.get("current_owner") or {}).get("value")
    if co:
        mentions.append((sid, co, "current owner"))
    kd = (rep.get("kidnapper") or {}).get("value")
    if kd:
        mentions.append((sid, kd, "kidnapper"))
    for it in rep.get("intermediaries") or []:
        if it.get("name"):
            mentions.append((sid, it["name"], f"intermediary ({it.get('role') or ''})"))

# one row per (statement, person string): the same person named twice in one statement counts once
seen, rows = set(), []
for sid, name, role in mentions:
    nm = re.sub(r"\s+", " ", name).strip()
    if (sid, nm) in seen:
        for r in rows:
            if r["statement_id"] == sid and r["name"] == nm and role not in r["roles"]:
                r["roles"] += "; " + role
        continue
    seen.add((sid, nm))
    p = parse(nm)
    rows.append({"statement_id": sid, "date": S[sid]["date_iso"], "name": nm, "roles": role,
                 "linkable": "Y" if p else "", "place": p[3] if p else "", "_key": key(p) if p else None})

# group linkable mentions
people = []
for r in rows:
    if not r["_key"]:
        continue
    for g in people:
        if any(same(r["_key"], m["_key"]) for m in g):
            g.append(r)
            break
    else:
        people.append([r])
for i, g in enumerate(people, 1):
    for r in g:
        r["person_id"] = f"P{i:03d}"


def recurs(g):
    ds = sorted({date.fromisoformat(r["date"]) for r in g if len(r["date"]) == 10})
    return len({r["statement_id"] for r in g}) > 1 and len(ds) > 1 and (ds[-1] - ds[0]).days > DAYS


with open("mentions_212.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["statement_id", "date", "name", "roles", "linkable", "place", "person_id"],
                       extrasaction="ignore", restval="")
    w.writeheader(); w.writerows(rows)
prow = []
for g in people:
    prow.append({"person_id": g[0]["person_id"], "spellings": " | ".join(sorted({r["name"] for r in g})),
                 "roles": " | ".join(sorted({x for r in g for x in r["roles"].split("; ")})),
                 "places": " | ".join(sorted({r["place"] for r in g if r["place"]})),
                 "n_statements": len({r["statement_id"] for r in g}),
                 "n_dates": len({r["date"] for r in g if r["date"]}),
                 "recurs_across_applications": "Y" if recurs(g) else "",
                 "statements": " ".join(sorted({r["statement_id"] for r in g}))})
prow.sort(key=lambda p: (-p["n_statements"], p["person_id"]))
with open("people_212.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(prow[0].keys())); w.writeheader(); w.writerows(prow)

lk = [r for r in rows if r["linkable"]]
multi = [p for p in prow if p["n_statements"] > 1]
rec = [p for p in prow if p["recurs_across_applications"]]
rec_ids = {p["person_id"] for p in rec}
st_with = {r["statement_id"] for r in rows if r.get("person_id") in rec_ids}
L = [f"person mentions (owners, sellers, buyers, heirs, kidnappers, intermediaries): {len(rows)} "
     f"in {len({r['statement_id'] for r in rows})} statements",
     f"  linkable (given name + at least one bin/bint): {len(lk)}; unlinkable (bare name or group): {len(rows) - len(lk)}",
     f"distinct people after grouping: {len(prow)}",
     f"  appearing in more than one statement: {len(multi)}",
     f"  recurring across separate applications (dates more than {DAYS} days apart): {len(rec)}",
     f"statements containing at least one recurring person: {len(st_with)} of {len(S)}", "",
     "Recurring people (candidates: confirm identity from place, kin and dates):"]
for p in rec:
    L.append(f"  {p['person_id']} {p['spellings'][:70]}")
    L.append(f"        roles: {p['roles'][:90]}; places: {p['places'] or '-'}; statements: {p['statements']}")
L += ["", "In more than one statement but only on the same dates (one household or one case):"]
L += [f"  {p['person_id']} {p['spellings'][:60]}  ({p['statements']})" for p in multi if not p["recurs_across_applications"]]
Path("recurrence_report.txt").write_text("\n".join(L), encoding="utf-8")
Path("results").mkdir(exist_ok=True)
Path("results/recurrence_summary.txt").write_text("\n".join(L[:6]), encoding="utf-8")   # counts only, no names
print("\n".join(L))
