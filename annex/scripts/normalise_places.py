"""
Step 2: collect every place string in the table (residences, birthplaces and the places
of the Agencies) and group spellings of the same place.

Reads   zdanowski_annex_table.csv
        places/merge_decisions.csv   (optional; your yes/no decisions on suggested merges)
Writes  places/place_variants.csv    one row per original string, with its group
        places/merge_suggestions.csv near-identical groups for you to decide on

How grouping works
  0. Birthplaces given as 'unknown' or 'not known' are skipped.
  1. Each string is split into a name and its context, using the rules in placenames.py
     ('Jumairah (Dubai)' -> name 'Jumairah', context 'Dubai').
  2. Each name gets a spelling-insensitive key ('Shandaqah' and 'Shandaghah' -> same key).
     Strings with the same key are grouped automatically.
  3. Groups whose keys are similar but not identical are only suggested, in
     merge_suggestions.csv. Type yes in the 'accept' column for the pairs that are the
     same place, then run this script again. Nothing is merged without your decision.
"""
import csv, sys, collections, difflib, re
from pathlib import Path
from placenames import split_context, match_key, is_island

PROJECT = Path(__file__).resolve().parent.parent
TABLE = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "zdanowski_annex_table.csv"
OUT = PROJECT / "places"
OUT.mkdir(exist_ok=True)
SIMILARITY = 0.9   # threshold for suggesting a merge (difflib ratio between keys)


def agency_place(recorded_at):
    """'British Agency in Sharjah' -> 'Sharjah'; ships have no place."""
    if recorded_at.startswith("HMS") or " and " in recorded_at:
        return ""   # ships, and lists that combine two Agencies, have no single place
    m = re.search(r"\b(?:in|at)\s+(.+)$", recorded_at)
    return m.group(1) if m else recorded_at


UNKNOWN = re.compile(r"unknown|uknown|not known|not indicated", re.I)   # 'place unknown' is not a place

rows = list(csv.DictReader(open(TABLE, encoding="utf-8")))
strings = collections.Counter()
roles = collections.defaultdict(set)
recorded_at = collections.defaultdict(collections.Counter)   # where each residence's statements were taken
for r in rows:
    if r["residence"]:
        strings[r["residence"]] += 1
        roles[r["residence"]].add("residence")
        a = agency_place(r["recorded_at"])
        if a:
            recorded_at[r["residence"]][a] += 1
    a = agency_place(r["recorded_at"])
    if a:
        strings[a] += 0
        roles[a].add("agency")
    b = r.get("birthplace", "").strip()
    if b and not UNKNOWN.search(b):
        strings[b] += 1
        roles[b].add("birthplace")

# 1-2. split and key
info = {}
for s in strings:
    name, context = split_context(s)
    info[s] = {"name": name, "context": context, "key": match_key(name), "island": is_island(s)}

# 3. read your earlier decisions on suggested merges
decisions = {}
dec_file = OUT / "merge_decisions.csv"
if dec_file.exists():
    for d in csv.DictReader(open(dec_file, encoding="utf-8-sig")):
        if d.get("accept", "").strip().lower() in ("yes", "y", "no", "n"):
            decisions[(d["key_a"], d["key_b"])] = d["accept"].strip().lower().startswith("y")

# union-find over keys, merging only pairs you accepted
parent = {}
def find(k):
    parent.setdefault(k, k)
    while parent[k] != k:
        k = parent[k]
    return k
for (a, b), yes in decisions.items():
    if yes:
        parent[find(a)] = find(b)

keys = sorted({v["key"] for v in info.values()})
for k in keys:
    find(k)

# canonical name for each group = most frequent name form in the annex
group_names = collections.defaultdict(collections.Counter)
for s, v in info.items():
    group_names[find(v["key"])][v["name"]] += max(strings[s], 1)
canonical = {g: c.most_common(1)[0][0] for g, c in group_names.items()}

with open(OUT / "place_variants.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["original_string", "role", "name", "context", "island", "match_key", "group",
                "canonical_name", "n_rows", "recorded_at"])
    for s, v in sorted(info.items(), key=lambda x: (-strings[x[0]], x[0])):
        g = find(v["key"])
        w.writerow([s, "+".join(sorted(roles[s])), v["name"], v["context"], v["island"], v["key"], g,
                    canonical[g], strings[s],
                    "; ".join(f"{a}:{n}" for a, n in recorded_at[s].most_common())])

# suggestions: similar keys in different groups, not yet decided
groups = sorted(set(find(k) for k in keys))
sugg = []
for i, a in enumerate(groups):
    for b in groups[i + 1:]:
        if (a, b) in decisions or (b, a) in decisions:
            continue
        r = difflib.SequenceMatcher(None, a, b).ratio()
        if r >= SIMILARITY and min(len(a), len(b)) >= 4:
            sugg.append((round(r, 2), a, canonical[a], b, canonical[b]))
with open(OUT / "merge_suggestions.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["similarity", "key_a", "name_a", "key_b", "name_b", "accept"])
    for row in sorted(sugg, reverse=True):
        w.writerow(list(row) + [""])

n_groups = len(groups)
print(f"{len(strings)} place strings -> {n_groups} places")
print(f"{len(sugg)} possible merges written to places/merge_suggestions.csv")
print("To decide them: copy that file to places/merge_decisions.csv, type yes or no in 'accept', run again.")