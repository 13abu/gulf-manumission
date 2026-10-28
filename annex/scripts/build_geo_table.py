"""
Step 4: combine the automatic lookup with your own decisions and add coordinates to the table.

Reads   zdanowski_annex_table.csv
        places/place_variants.csv     (step 2)
        places/gazetteer_auto.csv     (step 3)
        places/gazetteer_manual.csv   (your decisions; created on first run, see below)
Writes  gazetteer.csv                 one row per place, with where its coordinate came from
        zdanowski_annex_geo.csv       the table with residence, birthplace and Agency locations added

gazetteer_manual.csv
  On the first run this file is created with one row for every place the lookup marked
  'ambiguous' or 'none', and one for every 'probable' match for you to confirm. For each row, fill in lat and lon (or leave them blank if the place
  cannot be identified), and write in 'source' and 'citation' where the identification comes
  from, e.g. source 'Lorimer' and citation 'Gazetteer of the Persian Gulf, vol. II, p. 1234'.
  Rows are sorted by how many statements mention the place, so work from the top.
  For a 'probable' row the automatic choice is already used; check it, and either write
  'confirmed' in 'certainty' (coordinates can stay blank) or enter the correct coordinates.
  For a region with no single point (e.g. 'Swahil', the Swahili coast) you may leave lat/lon
  blank and fill in 'country' only, writing 'region' in 'certainty'.
  'country' is the present-day ISO code (AE, OM, QA, BH, SA, IR ...) of the place you identify.
  You can also add a row for any place where you want to override the automatic choice.
  A row in this file always takes priority over the automatic result. Later runs never
  overwrite your entries; they only add rows for newly unresolved places.
"""
import csv, re, sys, collections
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PLACES = PROJECT / "places"
TABLE = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "zdanowski_annex_table.csv"
MANUAL = PLACES / "gazetteer_manual.csv"
MANUAL_FIELDS = ["place", "role", "n_rows", "lat", "lon", "country", "certainty", "source", "citation",
                 "note", "auto_certainty", "auto_choice"]

variant_rows = list(csv.DictReader(open(PLACES / "place_variants.csv", encoding="utf-8")))
variants = {v["original_string"]: v["canonical_name"] for v in variant_rows}
place_roles = collections.defaultdict(set)
for v in variant_rows:
    place_roles[v["canonical_name"]].update(v["role"].split("+"))
auto = {a["place"]: a for a in csv.DictReader(open(PLACES / "gazetteer_auto.csv", encoding="utf-8"))}

# create or extend the manual file
manual = {}
if MANUAL.exists():
    # utf-8-sig: Excel and Numbers may add an invisible marker at the start of the file
    manual = {m["place"]: m for m in csv.DictReader(open(MANUAL, encoding="utf-8-sig"))}
added = 0
for name, a in auto.items():
    if a["certainty"] in ("ambiguous", "none", "probable") and name not in manual:
        manual[name] = {"place": name, "role": "", "n_rows": "", "lat": "", "lon": "", "country": "",
                        "certainty": "", "source": "",
                        "citation": "", "note": "", "auto_certainty": a["certainty"],
                        "auto_choice": f'{a["gn_name"]} ({a["country"]}, {a["lat"]}, {a["lon"]})' if a["lat"] else ""}
        added += 1
for name, m in manual.items():          # keep role and frequency current, so you can work top-down
    m["role"] = "+".join(sorted(place_roles.get(name, [])))
    m["n_rows"] = auto[name]["n_rows"] if name in auto else ""
ordered = sorted(manual.values(), key=lambda m: -int(m["n_rows"] or 0))
with open(MANUAL, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=MANUAL_FIELDS, restval="", extrasaction="ignore")
    w.writeheader(); w.writerows(ordered)

# final gazetteer: manual entry if it has coordinates or says 'unidentified', else automatic
gaz = {}
for name, a in auto.items():
    m = manual.get(name)
    if m and m.get("certainty", "").strip().lower() == "confirmed" and not m["lat"]:
        # you confirmed the automatic choice: keep its coordinates, record your source
        gaz[name] = {"place": name, "lat": a["lat"], "lon": a["lon"], "country": a["country"],
                     "certainty": "confirmed", "source": m["source"] or "GeoNames",
                     "citation": m["citation"] or f'geonameid {a["geonameid"]} ({a["gn_name"]})',
                     "geonameid": a["geonameid"], "note": m["note"]}
    elif m and (m["lat"] or m["certainty"]):
        gaz[name] = {"place": name, "lat": m["lat"], "lon": m["lon"],
                     "country": m.get("country") or (a["country"] if not m["lat"] else ""),
                     "certainty": m["certainty"] or ("manual" if m["lat"] else "unidentified"),
                     "source": m["source"], "citation": m["citation"], "geonameid": "", "note": m["note"]}
    elif a["certainty"] in ("high", "region", "probable"):
        gaz[name] = {"place": name, "lat": a["lat"], "lon": a["lon"], "country": a["country"],
                     "certainty": a["certainty"],
                     "source": "GeoNames", "citation": f'geonameid {a["geonameid"]} ({a["gn_name"]})',
                     "geonameid": a["geonameid"], "note": ""}
    else:   # unresolved: keep out of the analysis until decided
        gaz[name] = {"place": name, "lat": "", "lon": "", "country": "", "certainty": "unresolved",
                     "source": "", "citation": "", "geonameid": "", "note": "see gazetteer_manual.csv"}

with open(PROJECT / "gazetteer.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["place", "lat", "lon", "country", "certainty", "source", "citation",
                                      "geonameid", "note"])
    w.writeheader(); w.writerows(gaz.values())


def agency_place(recorded_at):
    if recorded_at.startswith("HMS") or " and " in recorded_at:
        return ""
    m = re.search(r"\b(?:in|at)\s+(.+)$", recorded_at)
    return m.group(1) if m else recorded_at


rows = list(csv.DictReader(open(TABLE, encoding="utf-8")))
for r in rows:
    place = variants.get(r["residence"], "") if r["residence"] else ""
    g = gaz.get(place, {})
    r["residence_place"] = place
    r["res_lat"], r["res_lon"] = g.get("lat", ""), g.get("lon", "")
    r["res_certainty"] = g.get("certainty", "")
    r["res_country"] = g.get("country", "")   # present-day country code from GeoNames (AE, OM, QA ...)
    ap = variants.get(agency_place(r["recorded_at"]), "")
    ga = gaz.get(ap, {})
    r["agency"] = f"{ap} Agency" if ap else r["recorded_at"]
    r["ag_lat"], r["ag_lon"] = ga.get("lat", ""), ga.get("lon", "")
    bp = variants.get(r.get("birthplace", ""), "") if r.get("birthplace") else ""
    gb = gaz.get(bp, {})
    r["birth_place"] = bp
    r["birth_lat"], r["birth_lon"] = gb.get("lat", ""), gb.get("lon", "")
    r["birth_country"], r["birth_certainty"] = gb.get("country", ""), gb.get("certainty", "")

with open(PROJECT / "zdanowski_annex_geo.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

c = collections.Counter(g["certainty"] for g in gaz.values())
st = [r for r in rows if r["entry_type"] == "statement" and r["residence_place"]]
print(f"gazetteer.csv: {len(gaz)} places {dict(c)}")
print(f"{sum(1 for r in st if r['res_lat'])} of {len(st)} statements with a residence now have coordinates")
sb = [r for r in rows if r["entry_type"] == "statement" and r["birth_place"]]
print(f"{sum(1 for r in sb if r['birth_country'])} of {len(sb)} statements with a birthplace now have a country")
if added:
    print(f"{added} places added to places/gazetteer_manual.csv for your decision")