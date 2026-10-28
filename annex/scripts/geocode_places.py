"""
Step 3: look up each place in GeoNames and record how the match was made.

Reads   places/place_variants.csv            (from normalise_places.py)
        geonames/XX.txt                       (GeoNames country files; downloaded on first run)
Writes  places/geocode_candidates.csv         every candidate found, ranked, with its score
        places/gazetteer_auto.csv             the chosen candidate per place, with its certainty
        geonames/SOURCE.txt                   which files were used and when they were downloaded

Source: GeoNames (https://www.geonames.org), licensed CC BY 4.0. Cite as
'GeoNames geographical database, country extracts downloaded <date>'.

How a place is matched
  1. Candidates. The place name and every GeoNames name (main, ASCII and alternate) are
     reduced to the same spelling-insensitive key (placenames.match_key). Equal keys are
     candidates. Only settlements (P), land features such as islands (T), administrative
     areas (A) and regions (L) are used.

  2. Anchor. A candidate is judged by its distance from an anchor point taken from the
     annex itself:
       - the context the annex gives ('Jumairah (Dubai)' -> Dubai), if any;
       - otherwise, for residences only, the Agency where the statements of people from
         that place were taken (someone from 'Kuwait' recorded at Bahrain -> anchor Bahrain).
         Birthplaces have no Agency anchor, since people were often born far away; a
         birthplace without context is 'high' only if it is a major place.
     The Agencies are located first, by the same matching, choosing the most important
     place of that name (capital, provincial centre, country, largest population).

  3. Score (lower is better) = an importance penalty by GeoNames feature type
                               + a penalty if only an alternate name matched
                               - a bonus for population (main-name matches only)
                               + distance: in full km from an annex context that is a town,
                                 or 1 point per 20 km from the recording Agency.
     A context that is a country or region ('Saudi Arabia', 'Oman') restricts the
     candidates to that country instead of measuring distance from its centre.

  4. Certainty is computed from the result, not judged:
       high       a clear best candidate that is a major place (capital, provincial centre),
                  or lies within CONTEXT_KM of an annex context, or within NEAR_AGENCY_KM
                  of the recording Agency
      probable   a clear best candidate, but either a minor place NEAR_AGENCY_KM-AGENCY_KM
                  from the Agency, or (with no anchor) a large town below provincial-capital
                  rank: used in the analysis, and listed for you to confirm
       region     the best match is a country, administrative area or region
     A major place (country, province, capital) is only ever challenged by another
     major place: a village named Yemen does not compete with the country Yemen.
       ambiguous  another candidate in a different location scores almost as well,
                  or the best candidate is too far from its anchor
       none       no candidate at all
     'ambiguous' and 'none' are passed to you in places/gazetteer_manual.csv (step 4).
"""
import csv, math, re, sys, zipfile, urllib.request, datetime, collections
from pathlib import Path
from placenames import split_context, match_key

PROJECT = Path(__file__).resolve().parent.parent
PLACES = PROJECT / "places"
GN = PROJECT / "geonames"
GN.mkdir(exist_ok=True)

# Countries searched: the Gulf, Persia and Makran, Arabia, the Red Sea and East African
# coasts, and India (origins of a few applicants).
COUNTRIES = ["AE", "OM", "QA", "BH", "SA", "KW", "IR", "IQ", "PK", "YE", "IN", "TZ", "KE", "ET", "SD", "SO", "DJ", "ER"]
KEEP_CLASSES = {"P", "T", "A", "L"}

# --- the numbers in the rule -------------------------------------------------------
IMPORTANCE = {"PCLI": 0, "PCLD": 0, "PCLIX": 0, "PPLC": 0, "ADM1": 5, "PPLA": 5,
              "PPLA2": 15, "RGN": 15, "ISL": 20, "ISLS": 20, "PPLA3": 25, "ADM2": 25,
              "PPL": 40, "PPLL": 45, "PPLX": 45}
OTHER_IMPORTANCE = 60          # any other feature type
ALT_NAME_PENALTY = 25          # matched only through an alternate name (alternate names are noisy)
POP_BONUS_MAX = 50             # population bonus, reached at 1,000,000 people (main-name matches only)
AGENCY_KM_PER_POINT = 20       # with an Agency anchor, 20 km of distance costs 1 point
SAME_PLACE_KM = 50             # candidates closer than this count as the same location
SAME_NAME_AREA_KM = 200        # an area and a settlement of the same name this close are one place
RIVAL_MARGIN = 15              # a different location scoring within this margin is a rival
CONTEXT_KM = 150               # how far from an annex context a 'high' match may lie
AGENCY_KM = 700                # beyond this from the Agency, only a major place counts as 'high'
MAJOR = 15                     # importance at or below which a place counts as major
MAJOR_POP = 100_000            # ... or a settlement with at least this population
SHORT_KEY = 3                  # keys this short match main names only (short names collide easily)
NEAR_AGENCY_KM = 150           # a minor place this close to the Agency is 'high'; further away it is 'probable'
ANCHOR_MAX_IMPORTANCE = 25     # a context is used only if it resolves to a place at least this important
# -------------------------------------------------------------------------------------


def download(cc):
    txt = GN / f"{cc}.txt"
    if txt.exists():
        return txt
    url = f"https://download.geonames.org/export/dump/{cc}.zip"
    print(f"  downloading {url}")
    zpath = GN / f"{cc}.zip"
    try:
        urllib.request.urlretrieve(url, zpath)
    except Exception as e:
        sys.exit(f"Could not download {url} ({e}).\nDownload it in your browser, put the .zip in the "
                 f"'geonames' folder, unzip it there, and run this script again.")
    with zipfile.ZipFile(zpath) as z:
        z.extract(f"{cc}.txt", GN)
    with open(GN / "SOURCE.txt", "a") as f:
        f.write(f"{cc}.zip from {url}, downloaded {datetime.date.today().isoformat()}\n")
    return txt


def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = (math.sin((la2 - la1) * p / 2) ** 2 +
         math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def context_name(part):
    """'under Ras al-Khaimah' -> 'Ras al-Khaimah'; 'originally from Qatar' -> 'Qatar'."""
    part = re.sub(r"^(originally from|under|near|from|in|of)\s+", "", part.strip(), flags=re.I)
    return split_context(part)[0]


# ---- 1. what we need to look up ---------------------------------------------------------
variants = list(csv.DictReader(open(PLACES / "place_variants.csv", encoding="utf-8")))
canon_of = {v["original_string"]: v["canonical_name"] for v in variants}
places = {}
for v in variants:
    p = places.setdefault(v["canonical_name"], {"keys": set(), "contexts": collections.Counter(),
                                                 "island": False, "n": 0, "agency": False,
                                                 "residence": False,
                                                 "recorded_at": collections.Counter()})
    if v["context"]:
        for part in v["context"].split(";"):
            if context_name(part):
                p["contexts"][context_name(part)] += max(int(v["n_rows"]), 1)
    p["keys"].add(v["match_key"])
    p["island"] |= v["island"] == "True"
    p["n"] += int(v["n_rows"])
    p["agency"] |= "agency" in v["role"]
    p["residence"] |= "residence" in v["role"]
    for item in filter(None, v.get("recorded_at", "").split("; ")):
        a, n = item.rsplit(":", 1)
        p["recorded_at"][canon_of.get(a, a)] += int(n)

wanted = set().union(*(p["keys"] for p in places.values()))
for p in places.values():
    wanted |= {match_key(c) for c in p["contexts"]}

# ---- 2. index GeoNames by key (only keys we need) ----------------------------------------
index = collections.defaultdict(list)
for cc in COUNTRIES:
    path = download(cc)
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) < 15 or c[6] not in KEEP_CLASSES:
                continue
            main = {match_key(c[1]), match_key(c[2])}
            alts = {match_key(a) for a in c[3].split(",") if a and a.isascii()}
            alts = {a for a in alts if len(a) > SHORT_KEY}
            for k in (main | alts) & wanted:
                index[k].append({"geonameid": c[0], "gn_name": c[1], "lat": float(c[4]),
                                 "lon": float(c[5]), "fclass": c[6], "fcode": c[7], "country": c[8],
                                 "population": int(c[14] or 0), "alt_only": k not in main})
    print(f"  indexed {cc}")


def candidates(keys):
    if isinstance(keys, str):
        keys = [keys]
    seen, out = set(), []
    for c in (c for k in keys for c in index.get(k, [])):
        if c["geonameid"] not in seen:
            seen.add(c["geonameid"]); out.append(dict(c))
    return out


def importance(c):
    return IMPORTANCE.get(c["fcode"], OTHER_IMPORTANCE)


def conventional(c):
    """Countries, provinces and regions: their alternate names are conventional names."""
    return c["fcode"].startswith("PCL") or c["fcode"] in ("ADM1", "RGN")


def base_score(c):
    if c["alt_only"] and not conventional(c):
        return importance(c) + ALT_NAME_PENALTY
    bonus = POP_BONUS_MAX * min(c["population"], 1_000_000) / 1_000_000 if c["fclass"] == "P" else 0
    return importance(c) - bonus


def is_major(c):
    """Capitals, provincial centres, countries, first-level provinces and named regions.
    For countries and provinces an alternate-name match is accepted (GeoNames' alternate
    names for these are conventional names: Yemen, Abyssinia, Dhofar); for towns it is not."""
    if c["alt_only"] and not conventional(c):
        return False
    return importance(c) <= MAJOR or (c["fclass"] == "P" and c["population"] >= MAJOR_POP)


TOP_TIER = ("PPLC", "PPLA", "ADM1", "RGN")   # accepted outright even without an anchor


def top_tier(c):
    return c["fcode"].startswith("PCL") or c["fcode"] in TOP_TIER


def is_area(c):
    return c["fclass"] in ("A", "L") or c["fcode"].startswith("PCL")


def most_important(keys):
    """Locate a name with no anchor (Agencies, contexts): the most important place of that name."""
    cands = candidates(keys)
    for c in cands:
        c["score"] = base_score(c)
    cands.sort(key=lambda c: c["score"])
    return cands


def judge(cands, anchor, anchor_type, country=None):
    """Rank candidates and compute certainty."""
    if country and any(c["country"] == country for c in cands):
        cands[:] = [c for c in cands if c["country"] == country]
    for c in cands:
        d = round(km((c["lat"], c["lon"]), anchor)) if anchor else ""
        c["dist_anchor_km"] = d
        if anchor_type == "context":
            c["score"] = round(base_score(c) + d, 1)
        elif anchor_type == "agency":
            c["score"] = round(base_score(c) + d / AGENCY_KM_PER_POINT, 1)
        else:
            c["score"] = round(base_score(c), 1)
    cands.sort(key=lambda c: c["score"])
    if not cands:
        return "none"
    # a name that matches a country means the country ('the Sudan', 'Yemen', 'Persia')
    countries = [c for c in cands if c["fcode"].startswith("PCL")]
    if countries:
        cands.remove(countries[0]); cands.insert(0, countries[0])
        return "region"
    best = cands[0]
    # a residence is a town: if the best match is a district or municipality and a
    # settlement of the same name lies within it, take the settlement
    if is_area(best) and not best["fcode"].startswith("PCL"):
        towns = [c for c in cands if c["fclass"] == "P" and not c["alt_only"]
                 and km((c["lat"], c["lon"]), (best["lat"], best["lon"])) <= SAME_NAME_AREA_KM]
        if towns:
            cands.remove(towns[0]); cands.insert(0, towns[0]); best = towns[0]
    bp = (best["lat"], best["lon"])

    def same_place(c):
        d = km((c["lat"], c["lon"]), bp)
        # an area and a settlement of the same name close together are one place
        return d <= SAME_PLACE_KM or (d <= SAME_NAME_AREA_KM and (is_area(c) or is_area(best)))

    rivals = [c for c in cands[1:] if not same_place(c) and c["score"] <= best["score"] + RIVAL_MARGIN
              and (is_major(c) or not is_major(best))]   # a hamlet does not compete with a country
    if rivals:
        return "ambiguous"
    kind = "region" if is_area(best) else "high"
    major = is_major(best)
    if anchor_type == "context" and best["dist_anchor_km"] <= CONTEXT_KM:
        return kind
    if anchor_type == "agency":
        if major or best["dist_anchor_km"] <= NEAR_AGENCY_KM:
            return kind
        if best["dist_anchor_km"] <= AGENCY_KM:
            return "probable"
    if anchor_type == "none" and major:
        # with nothing in the annex to check it against, only a country, province, region,
        # capital or provincial capital is accepted outright; other matches await confirmation
        return kind if top_tier(best) else "probable"
    return "ambiguous"


# ---- 3. locate the Agencies first (they anchor everything else) --------------------------
anchors = {}
for name, p in places.items():
    if p["agency"]:
        c = most_important(p["keys"])
        if c:
            anchors[name] = (c[0]["lat"], c[0]["lon"])

# ---- 4. locate every place -------------------------------------------------------------
out_cands, out_auto = [], []
for name, p in sorted(places.items(), key=lambda x: -x[1]["n"]):
    anchor, anchor_type, anchor_name, country = None, "none", "", None
    for ctx, _ in p["contexts"].most_common():
        loc = [c for c in most_important(match_key(ctx))
               if is_major(c) or (importance(c) <= ANCHOR_MAX_IMPORTANCE and not c["alt_only"])]
        if not loc:
            continue                      # context not recognised as a significant place: ignore it
        if is_area(loc[0]) and not conventional(loc[0]):
            continue                      # a district or municipality is too vague to anchor on
        if is_area(loc[0]):
            country = loc[0]["country"]   # 'Saudi Arabia', 'Oman', 'Batinah': restrict to that country
            anchor_name = ctx
        else:
            anchor, anchor_type, anchor_name = (loc[0]["lat"], loc[0]["lon"]), "context", ctx
        break
    # the Agency anchor applies to residences only: people were born far from where they applied
    if anchor is None and p["residence"] and p["recorded_at"]:
        ag = p["recorded_at"].most_common(1)[0][0]
        if ag in anchors:
            anchor, anchor_type = anchors[ag], "agency"
            anchor_name = f"{anchor_name} / Agency {ag}" if anchor_name else ag
    if p["agency"] and anchor is None:
        cands = most_important(p["keys"])
        cert = judge(cands, None, "none", country)
    else:
        cands = candidates(p["keys"])
        cert = judge(cands, anchor, anchor_type, country)
    best = cands[0] if cands else None

    for rank, c in enumerate(cands[:8], 1):
        out_cands.append({"place": name, "rank": rank, **{k: c.get(k, "") for k in (
            "geonameid", "gn_name", "lat", "lon", "country", "fclass", "fcode", "population",
            "alt_only", "dist_anchor_km", "score")}})
    out_auto.append({"place": name, "n_rows": p["n"],
                     "context": "; ".join(p["contexts"]), "anchor_type": anchor_type, "anchor": anchor_name,
                     "lat": best["lat"] if best else "", "lon": best["lon"] if best else "",
                     "geonameid": best["geonameid"] if best else "", "gn_name": best["gn_name"] if best else "",
                     "country": best["country"] if best else "",
                     "feature": f'{best["fclass"]}.{best["fcode"]}' if best else "",
                     "dist_anchor_km": best.get("dist_anchor_km", "") if best else "",
                     "n_candidates": len(cands), "certainty": cert, "source": "GeoNames" if best else ""})

for fname, data in [("geocode_candidates.csv", out_cands), ("gazetteer_auto.csv", out_auto)]:
    with open(PLACES / fname, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        w.writeheader(); w.writerows(data)

cert = collections.Counter(a["certainty"] for a in out_auto)
rows_by = collections.Counter()
for a in out_auto:
    rows_by[a["certainty"]] += a["n_rows"]
print(f"{len(out_auto)} places: {dict(cert)}")
print(f"rows covered: {dict(rows_by)}")
print("Next: run build_geo_table.py, then review places/gazetteer_manual.csv")