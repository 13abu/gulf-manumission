"""
Step 7: basic descriptive analysis of the annex (who, from where, born where, why, and names).

Reads   zdanowski_annex_geo.csv   (from build_geo_table.py)
Writes  analysis/descriptive/*.csv          one table per question (listed below)
        analysis/descriptive/report.txt     the key figures in plain language
        analysis/descriptive/*.png          two charts

Only statements are used (the supplementary lists in the annex have no statement).
Every percentage is printed with its count, so small groups are visible as small.

What each table answers
  A  overview.csv                  How many statements, at which Agency, when, men and women?
     missing_fields.csv            How complete is each field, by Agency? (what the clerks recorded)
  B  birth_country_by_period.csv   Where were applicants born, and did that change over time?
     birth_country_by_agency.csv   ... and by Agency.
     birthplaces_top.csv           The most frequent birthplaces as written, with their country.
     born_where_lived.csv          Share born in the same place / country as they lived (born
                                   locally, i.e. born into slavery in the Gulf, vs brought in).
     ethnicity_by_birth_country.csv  The ethnic label in the annex (Zdanowski: taken from the agents'
                                   notes where available) against the birthplace: does 'African'
                                   or 'Baluchi' track origin? A mismatch shows the label is not a
                                   birthplace; what it does record needs the original documents.
  C  kidnapping_summary.csv        How many statements mention kidnapping, by period and Agency,
                                   and where those people were born, against everyone else.
     kidnapping_entries.csv        Every such entry in full, for close reading.
  D  reasons_by_agency_period.csv  Share of each stated reason (keyword codes) by Agency and period.
     reasons_by_gender.csv         ... by gender.
     reason_wording.csv            The most common exact wordings of the reason in Zdanowski's annex,
                                   by Agency and period, and how much of the annex's entries those
                                   few wordings account for. NB the annex gives Zdanowski's summary
                                   of each statement, not the Agency's wording: a high share shows
                                   uniform summaries in the annex; whether the Agency's statements
                                   were themselves formulaic must be checked against the originals.
  E  age_heaping.csv               Whipple's index of age heaping by Agency (100 = no rounding,
                                   500 = every age ends in 0 or 5), for ages as given in the annex
                                   (estimates, 'about 30', presumably carried over from the statements).
     age_by_gender.csv             Age bands by gender.
  F  occupation_by_gender.csv      Recorded occupation by gender.
  G  father_names.csv              Fathers' names, with spellings grouped.
     given_names.csv               Applicants' own names, with spellings grouped.
     names_by_agency.csv           By Agency and period: share 'father unknown', share 'bin Abdullah'
                                   (a common convention for an unknown or non-Muslim father),
                                   share held by the ten commonest fathers' names, and how many
                                   different fathers' names per 100 statements.
     father_in_given_pool.csv      Share of fathers' names that are themselves among the names
                                   applicants carried, by Agency: fathers named within the same
                                   pool of names as the enslaved.

Coding rules (stated, not judged case by case)
  - Reasons and kidnapping come from the keyword flags made in step 1 (zdanowski_parser.py).
  - Names: spellings are grouped with the same transliteration key as places (placenames.py).
  - 'Born locally' compares the grouped birthplace with the grouped residence.
  - Countries are present-day ISO codes from the gazetteer; regions such as Makran are filed
    under the country GeoNames gives them (Makran -> IR), which should be stated as a limitation.
"""
import csv, re, sys, collections
from pathlib import Path
from placenames import match_key

PROJECT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "zdanowski_annex_geo.csv"
OUT = PROJECT / "analysis" / "descriptive"
OUT.mkdir(parents=True, exist_ok=True)

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8")) if r["entry_type"] == "statement"]
MAIN = ["Sharjah Agency", "Muscat Agency", "Bahrain Agency"]
REASONS = ["ill_treated", "beaten", "chains_or_confinement", "fear_of_sale", "not_paid_or_advance",
           "kidnapped", "re_enslavement", "family_separation_or_search", "duplicate_certificate"]
report = []


def agency(r):
    return r["agency"] if r["agency"] in MAIN else "other"


def year(r):
    return int(r["year"]) if r["year"].isdigit() and 1900 < int(r["year"]) < 1960 else None


def period(r):
    y = year(r)
    if y is None:
        return "no date"
    return "before 1930" if y < 1930 else ("1930-1936" if y < 1937 else ("1937-1942" if y <= 1942 else "after 1942"))


PERIODS = ["before 1930", "1930-1936", "1937-1942", "after 1942"]


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else ""


def write(name, header, data):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(data)


def crosstab(name, key_row, key_col, cols, sel=rows, top=None, row_label="row"):
    t = collections.defaultdict(collections.Counter)
    for r in sel:
        t[key_row(r)][key_col(r)] += 1
    order = sorted(t, key=lambda k: -sum(t[k].values()))
    if top:
        order = order[:top]
    data = []
    for k in order:
        n = sum(t[k].values())
        data.append([k, n] + [f"{t[k][c]} ({pct(t[k][c], n)})" for c in cols])
    write(name, [row_label, "total"] + cols, data)
    return t


# ---------------------------------------------------------------- A overview
G = ["M", "F", ""]
data = []
for ag in MAIN + ["other"]:
    for p in PERIODS:
        sel = [r for r in rows if agency(r) == ag and period(r) == p]
        if sel:
            c = collections.Counter(r["gender"] for r in sel)
            data.append([ag, p, len(sel), c["M"], c["F"], c[""], pct(c["F"], len(sel))])
write("overview.csv", ["agency", "period", "statements", "men", "women", "gender not given", "share women"], data)
fields = ["residence", "birthplace", "ethnicity_as_recorded", "age_years", "occupation",
          "father_name", "reason_or_circumstance", "date_iso"]
data = []
for ag in MAIN + ["other"]:
    sel = [r for r in rows if agency(r) == ag]
    data.append([ag, len(sel)] + [pct(sum(1 for r in sel if r[f]), len(sel)) for f in fields])
write("missing_fields.csv", ["agency", "statements"] + [f"{f} recorded" for f in fields], data)
fem = sum(r["gender"] == "F" for r in rows)
report += [f"A. {len(rows)} statements; {fem} women ({pct(fem, len(rows))}).",
           "   Field completeness by Agency is in missing_fields.csv.", ""]

# ---------------------------------------------------------------- B origins
def bc(r):
    return r["birth_country"] or ("unresolved" if r["birth_place"] else "not given")


countries = [c for c, _ in collections.Counter(bc(r) for r in rows).most_common()]
crosstab("birth_country_by_period.csv", bc, period, PERIODS, row_label="birth country")
crosstab("birth_country_by_agency.csv", bc, agency, MAIN + ["other"], row_label="birth country")
t = collections.Counter((r["birth_place"], r["birth_country"]) for r in rows if r["birth_place"])
write("birthplaces_top.csv", ["birthplace (grouped)", "country", "statements"],
      [[p, c, n] for (p, c), n in t.most_common(60)])

data = []
for ag in MAIN + ["other"]:
    for p in PERIODS:
        sel = [r for r in rows if agency(r) == ag and period(r) == p and r["birth_place"] and r["residence_place"]]
        if not sel:
            continue
        same_place = sum(r["birth_place"] == r["residence_place"] for r in sel)
        both = [r for r in sel if r["birth_country"] and r["res_country"]]
        same_c = sum(r["birth_country"] == r["res_country"] for r in both)
        data.append([ag, p, len(sel), same_place, pct(same_place, len(sel)), len(both), same_c, pct(same_c, len(both))])
write("born_where_lived.csv", ["agency", "period", "with birthplace and residence", "born in same place",
                               "share", "both countries known", "born in same country", "share"], data)
sel = [r for r in rows if r["birth_place"] and r["residence_place"]]
same = sum(r["birth_place"] == r["residence_place"] for r in sel)
report += [f"B. Of {len(sel)} statements giving both birthplace and residence, {same} ({pct(same, len(sel))})",
           "   were born in the place where they lived (born_where_lived.csv; by Agency and period).", ""]

labels = [l for l, _ in collections.Counter(r["ethnicity_as_recorded"] or "none" for r in rows).most_common(8)]
crosstab("ethnicity_by_birth_country.csv", bc, lambda r: r["ethnicity_as_recorded"] or "none",
         labels, row_label="birth country")
afr = [r for r in rows if r["ethnicity_as_recorded"] == "African" and r["birth_country"]]
afc = collections.Counter(r["birth_country"] for r in afr)
report += [f"   Statements labelled 'African' with a known birth country: {len(afr)}; born in "
           + ", ".join(f"{c} {n}" for c, n in afc.most_common(8)),
           "   (ethnicity_by_birth_country.csv: the label against the birthplace).", ""]

# ---------------------------------------------------------------- C kidnapping
kid = [r for r in rows if r["kidnapped"] == "Y"]
data = []
for p in PERIODS:
    for ag in MAIN + ["other"]:
        sel = [r for r in rows if period(r) == p and agency(r) == ag]
        k = sum(r["kidnapped"] == "Y" for r in sel)
        if sel:
            data.append([p, ag, len(sel), k, pct(k, len(sel))])
data.append([])
data.append(["birth country", "", "kidnapped", "", "all others"])
kc = collections.Counter(bc(r) for r in kid)
oc = collections.Counter(bc(r) for r in rows if r["kidnapped"] != "Y")
for c in countries:
    data.append([c, "", f"{kc[c]} ({pct(kc[c], len(kid))})", "", f"{oc[c]} ({pct(oc[c], len(rows) - len(kid))})"])
write("kidnapping_summary.csv", ["period", "agency", "statements", "mention kidnapping", "share"], data)
write("kidnapping_entries.csv", ["date", "agency", "residence", "birthplace", "birth country", "gender", "raw"],
      [[r["date_iso"], r["agency"], r["residence"], r["birthplace"], r["birth_country"], r["gender"], r["raw"]]
       for r in sorted(kid, key=lambda r: r["date_iso"])])
report += [f"C. {len(kid)} statements mention kidnapping. Birth countries of those people: "
           + ", ".join(f"{c} {n}" for c, n in kc.most_common(6)) + ".",
           "   kidnapping_entries.csv lists each in full; note that some are relatives asking",
           "   for a kidnapped person, not the kidnapped person speaking.", ""]

# ---------------------------------------------------------------- D reasons
data = []
for ag in MAIN:
    for p in PERIODS:
        sel = [r for r in rows if agency(r) == ag and period(r) == p]
        if sel:
            data.append([ag, p, len(sel)] + [pct(sum(r[k] == "Y" for r in sel), len(sel)) for k in REASONS])
write("reasons_by_agency_period.csv", ["agency", "period", "statements"] + REASONS, data)
data = []
for g, lab in [("M", "men"), ("F", "women")]:
    sel = [r for r in rows if r["gender"] == g]
    data.append([lab, len(sel)] + [pct(sum(r[k] == "Y" for r in sel), len(sel)) for k in REASONS])
write("reasons_by_gender.csv", ["gender", "statements"] + REASONS, data)


def wording(r):
    return re.sub(r"\s+", " ", r["reason_or_circumstance"].lower()).strip(" .,")


data = []
for ag in MAIN:
    for p in PERIODS:
        sel = [wording(r) for r in rows if agency(r) == ag and period(r) == p and r["reason_or_circumstance"]]
        if len(sel) < 5:
            continue
        c = collections.Counter(sel)
        top = c.most_common(3)
        share = sum(n for _, n in top)
        data.append([ag, p, len(sel), len(c), pct(share, len(sel))] + [f"{w} ({n})" for w, n in top])
write("reason_wording.csv", ["agency", "period", "statements with a reason", "distinct wordings",
                             "share in 3 commonest wordings", "1st", "2nd", "3rd"], data)
f_m = [r for r in rows if r["gender"] == "M"]; f_f = [r for r in rows if r["gender"] == "F"]
report += ["D. Fear of sale: men " + pct(sum(r["fear_of_sale"] == "Y" for r in f_m), len(f_m))
           + ", women " + pct(sum(r["fear_of_sale"] == "Y" for r in f_f), len(f_f))
           + "; ill-treatment: men " + pct(sum(r["ill_treated"] == "Y" for r in f_m), len(f_m))
           + ", women " + pct(sum(r["ill_treated"] == "Y" for r in f_f), len(f_f)) + ".",
           "   reason_wording.csv: how uniform the annex's summaries of reasons are, by Agency and period",
           "   (Zdanowski's wording; compare with original statements before attributing it to the Agency).", ""]

# ---------------------------------------------------------------- E age
def whipple(ages):
    a = [x for x in ages if 23 <= x <= 62]
    return round(500 * sum(x % 5 == 0 for x in a) / len(a)) if a else ""


data = []
for ag in MAIN + ["other"]:
    for p in PERIODS + ["all"]:
        ages = [int(r["age_years"]) for r in rows if r["age_years"].isdigit() and agency(r) == ag
                and (p == "all" or period(r) == p)]
        if len([x for x in ages if 23 <= x <= 62]) >= 10:
            data.append([ag, p, len(ages), whipple(ages)])
write("age_heaping.csv", ["agency", "period", "ages recorded", "Whipple index (100 = none, 500 = all on 0/5)"], data)
bands = ["0-14", "15-24", "25-34", "35-44", "45-54", "55+"]


def band(x):
    return bands[min(5, 0 if x < 15 else (x - 5) // 10)]


data = []
for g, lab in [("M", "men"), ("F", "women")]:
    ages = [int(r["age_years"]) for r in rows if r["age_years"].isdigit() and r["gender"] == g]
    c = collections.Counter(band(x) for x in ages)
    data.append([lab, len(ages)] + [f"{c[b]} ({pct(c[b], len(ages))})" for b in bands]
                + [sorted(ages)[len(ages) // 2] if ages else ""])
write("age_by_gender.csv", ["gender", "ages recorded"] + bands + ["median"], data)
allages = [int(r["age_years"]) for r in rows if r["age_years"].isdigit()]
report += [f"E. Whipple's index for all recorded ages: {whipple(allages)} (100 = no rounding; 500 = all on 0 or 5).",
           "   Ages are estimates; use bands, not single years (age_heaping.csv by Agency).", ""]

# ---------------------------------------------------------------- F occupation
occs = [o for o, _ in collections.Counter(r["occupation"].lower() or "not given" for r in rows).most_common(7)]
crosstab("occupation_by_gender.csv", lambda r: {"M": "men", "F": "women"}.get(r["gender"], "not given"),
         lambda r: r["occupation"].lower() or "not given", occs, row_label="gender")

# ---------------------------------------------------------------- G names
UNKNOWN = re.compile(r"unknown|uknown|not known", re.I)


def given(name):
    n = re.sub(r"\(.*?\)", "", name)
    n = re.split(r"\b(?:bin|bint|ibn|int|bib|s/o|d/o|son of|and)\b", n, flags=re.I)[0]
    n = re.split(r"\balias\b", n, flags=re.I)[0]
    return n.strip(" ,")


def father(r):
    f = r["father_name"].strip()
    if not f or UNKNOWN.search(f) or UNKNOWN.search(r["name"]):
        return "unknown"
    f = re.sub(r"\(.*?\)", "", f)
    return re.split(r"\b(?:bin|bint|ibn|al|of|alias)\b|,", f)[0].strip()   # first element only


def grouped(values):
    """Count names grouped by transliteration key; label each group by its commonest spelling."""
    by_key = collections.defaultdict(collections.Counter)
    for v in values:
        if v and v != "unknown":
            by_key[match_key(v)][v] += 1
    return {k: (c.most_common(1)[0][0], sum(c.values()), sorted(c)) for k, c in by_key.items()}


fg = grouped(father(r) for r in rows)
gg = grouped(given(r["name"]) for r in rows)
write("father_names.csv", ["father's name", "statements", "spellings in the annex"],
      [[lab, n, " | ".join(sp)] for lab, n, sp in sorted(fg.values(), key=lambda x: -x[1])])
write("given_names.csv", ["name", "statements", "spellings in the annex"],
      [[lab, n, " | ".join(sp)] for lab, n, sp in sorted(gg.values(), key=lambda x: -x[1])])

abd = match_key("Abdullah")
data = []
for ag in MAIN + ["other"]:
    for p in PERIODS + ["all"]:
        sel = [r for r in rows if agency(r) == ag and (p == "all" or period(r) == p)]
        if len(sel) < 10:
            continue
        fs = [father(r) for r in sel]
        known = [match_key(f) for f in fs if f != "unknown" and f]
        c = collections.Counter(known)
        top10 = sum(n for _, n in c.most_common(10))
        data.append([ag, p, len(sel), pct(fs.count("unknown"), len(sel)), pct(c[abd], len(known)),
                     pct(top10, len(known)), round(100 * len(c) / len(known)) if known else ""])
write("names_by_agency.csv", ["agency", "period", "statements", "father unknown", "father 'Abdullah'",
                              "share of 10 commonest fathers' names", "distinct fathers' names per 100"], data)

given_keys = set(gg)
data = []
for ag in MAIN + ["other"]:
    known = [match_key(father(r)) for r in rows if agency(r) == ag and father(r) not in ("unknown", "")]
    inpool = sum(k in given_keys for k in known)
    data.append([ag, len(known), inpool, pct(inpool, len(known))])
write("father_in_given_pool.csv", ["agency", "fathers' names known", "also a name an applicant carried", "share"], data)
tf = sorted(fg.values(), key=lambda x: -x[1])[:5]
unk = sum(father(r) == "unknown" for r in rows)
report += [f"G. Father's name unknown in {unk} statements ({pct(unk, len(rows))}).",
           "   Commonest fathers' names: " + ", ".join(f"{lab} {n}" for lab, n, _ in tf) + ".",
           "   Repetition alone does not show invention by the Agency: owners gave the enslaved",
           "   a small pool of names (Mubarak, Faraj, Bilal, Khamis), and fathers were often enslaved",
           "   too. The comparisons that can point to clerical practice are between Agencies and",
           "   periods (names_by_agency.csv): a jump in 'unknown' or 'Abdullah', or in concentration,",
           "   at one Agency or under one officer.", ""]

(OUT / "report.txt").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))

# ---------------------------------------------------------------- charts
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top = [c for c in countries if c not in ("not given", "unresolved")][:7]
    cols = top + ["other", "unresolved"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    left = [0] * len(PERIODS)
    for c in cols:
        vals = []
        for p in PERIODS:
            sel = [r for r in rows if period(r) == p and r["birth_place"]]
            k = sum((bc(r) == c) if c != "other" else (bc(r) not in top + ["unresolved", "not given"]) for r in sel)
            vals.append(100 * k / len(sel) if sel else 0)
        ax.barh(PERIODS, vals, left=left, label=c)
        left = [a + b for a, b in zip(left, vals)]
    ax.set_xlabel("% of statements giving a birthplace"); ax.invert_yaxis()
    ax.set_title("Birth country of applicants, by period"); ax.legend(ncol=5, fontsize=8, frameon=False,
                                                                       loc="upper center", bbox_to_anchor=(0.5, -0.15))
    ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    fig.savefig(OUT / "birth_country_by_period.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4))
    show = ["ill_treated", "beaten", "fear_of_sale", "not_paid_or_advance", "kidnapped", "family_separation_or_search"]
    x = range(len(show)); w = 0.4
    for i, (g, lab) in enumerate([("M", "men"), ("F", "women")]):
        sel = [r for r in rows if r["gender"] == g]
        ax.bar([j + (i - 0.5) * w for j in x], [100 * sum(r[k] == "Y" for r in sel) / len(sel) for k in show],
               width=w, label=f"{lab} (n={len(sel)})")
    ax.set_xticks(list(x)); ax.set_xticklabels([s.replace("_", " ") for s in show], fontsize=8, rotation=15)
    ax.set_ylabel("% of statements"); ax.set_title("Stated reasons, by gender"); ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False); fig.tight_layout()
    fig.savefig(OUT / "reasons_by_gender.png", dpi=200); plt.close(fig)
    print(f"charts saved in {OUT}")
except ImportError:
    print("(matplotlib not installed: pip install matplotlib for the charts)")
