"""
Step 6: where did people from the Trucial Coast make their statements, and did it change in 1937?

Reads   zdanowski_annex_geo.csv   (from build_geo_table.py)
Writes  analysis/agency_by_year.csv        statements per year at each Agency (Trucial Coast residents)
        analysis/agency_by_period.csv      the same, before 1937 and from 1937, with shares
        analysis/sharjah_by_halfyear.csv   all statements taken at Sharjah, per half-year
        analysis/women_by_agency.csv       share of women among all statements at each Agency, by period
        analysis/gender_trucial.csv        Trucial Coast residents only: where women and where men
                                           made their statements, by period (the right denominator for
                                           asking whether women and men used different Agencies)
        analysis/test_results.txt          the statistical test and its robustness checks
        analysis/agency_by_year.png        chart of agency_by_year.csv

Who counts as a 'Trucial Coast resident'
  A statement whose residence was located (step 3/4) in the present-day United Arab
  Emirates (GeoNames country code AE). This is a stated, reproducible definition: no list
  of towns is typed in. It approximates the Trucial States of the 1920s-40s; places
  that were in the Trucial sphere but lie in present-day Oman (e.g. Buraimi) are excluded,
  and statements whose residence is unresolved are excluded until you resolve them.

The test
  A 2 x 2 chi-square test: Agency (Sharjah or elsewhere) against period (1921-1936 or
  1937-1942). It asks whether the share of Trucial Coast residents who went to Sharjah
  differs between the two periods by more than chance would produce. It is repeated
  (a) without the statements Zdanowski marks as repeated (+), and
  (b) with the dividing year moved to every year from 1930 to 1940, to show where the
      change is sharpest instead of assuming 1937.
"""
import csv, sys, math, collections
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "zdanowski_annex_geo.csv"
OUT = PROJECT / "analysis"
OUT.mkdir(exist_ok=True)
FIRST, LAST, SPLIT = 1921, 1942, 1937
MAIN_AGENCIES = ["Sharjah Agency", "Muscat Agency", "Bahrain Agency"]

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8"))
        if r["entry_type"] == "statement" and r["year"].isdigit() and FIRST <= int(r["year"]) <= LAST]
trucial = [r for r in rows if r.get("res_country") == "AE"]


def agency_of(r):
    return r["agency"] if r["agency"] in MAIN_AGENCIES else "other"


def write(name, header, data):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(data)


def chi2_2x2(a, b, c, d):
    """Pearson chi-square for [[a, b], [c, d]] with 1 degree of freedom; returns (chi2, p)."""
    n = a + b + c + d
    num = n * (a * d - b * c) ** 2
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        return float("nan"), float("nan")
    x = num / den
    return x, math.erfc(math.sqrt(x / 2))


def split_table(data, split):
    before = [r for r in data if int(r["year"]) < split]
    after = [r for r in data if int(r["year"]) >= split]
    a = sum(agency_of(r) == "Sharjah Agency" for r in before); b = len(before) - a
    c = sum(agency_of(r) == "Sharjah Agency" for r in after);  d = len(after) - c
    return a, b, c, d


# 1. year x agency
cols = MAIN_AGENCIES + ["other"]
by_year = collections.defaultdict(collections.Counter)
for r in trucial:
    by_year[int(r["year"])][agency_of(r)] += 1
write("agency_by_year.csv", ["year"] + cols + ["total"],
      [[y] + [by_year[y][c] for c in cols] + [sum(by_year[y].values())] for y in range(FIRST, LAST + 1)])

# 2. by period, with shares
periods = [(f"{FIRST}-{SPLIT - 1}", FIRST, SPLIT - 1), (f"{SPLIT}-{LAST}", SPLIT, LAST)]
data = []
for label, a, b in periods:
    c = collections.Counter(agency_of(r) for r in trucial if a <= int(r["year"]) <= b)
    n = sum(c.values())
    data.append([label, n] + [f"{c[x]} ({100 * c[x] / n:.0f}%)" if n else "0" for x in cols])
write("agency_by_period.csv", ["period", "statements"] + cols, data)

# 3. all statements taken at Sharjah, per half-year
half = collections.Counter()
for r in rows:
    if r["agency"] == "Sharjah Agency" and len(r["date_iso"]) >= 7:
        half[f'{r["date_iso"][:4]}-{"H1" if int(r["date_iso"][5:7]) <= 6 else "H2"}'] += 1
write("sharjah_by_halfyear.csv", ["half_year", "statements_at_sharjah"],
      [[f"{y}-{h}", half[f"{y}-{h}"]] for y in range(1925, LAST + 1) for h in ("H1", "H2")])

# 4. women's share by agency and period (all statements)
data = []
for ag in MAIN_AGENCIES:
    for label, a, b in periods:
        sel = [r for r in rows if r["agency"] == ag and a <= int(r["year"]) <= b]
        f = sum(r["gender"] == "F" for r in sel)
        data.append([ag, label, len(sel), f, f"{100 * f / len(sel):.0f}%" if sel else ""])
write("women_by_agency.csv", ["agency", "period", "statements", "women", "share_women"], data)

# 4b. Trucial Coast residents only: did women and men use different Agencies?
data = []
for label, a0, b0 in periods:
    for g, lab in [("F", "women"), ("M", "men")]:
        sel = [r for r in trucial if r["gender"] == g and a0 <= int(r["year"]) <= b0]
        c = collections.Counter(agency_of(r) for r in sel)
        data.append([label, lab, len(sel)] + [f"{c[x]} ({100 * c[x] / len(sel):.0f}%)" if sel else "0" for x in cols])
write("gender_trucial.csv", ["period", "gender", "Trucial Coast statements"] + cols, data)

# 5. tests
lines = [f"Source: {SRC.name}",
         f"Statements {FIRST}-{LAST} with a year: {len(rows)}",
         f"  of which residence located in present-day UAE (res_country AE): {len(trucial)}",
         ""]
a, b, c, d = split_table(trucial, SPLIT)
x, p = chi2_2x2(a, b, c, d)
lines += [f"Main test, split at {SPLIT}: Trucial Coast residents, Sharjah vs elsewhere",
          f"  {FIRST}-{SPLIT - 1}: Sharjah {a}, elsewhere {b}  -> {100 * a / (a + b):.0f}% at Sharjah",
          f"  {SPLIT}-{LAST}: Sharjah {c}, elsewhere {d}  -> {100 * c / (c + d):.0f}% at Sharjah",
          f"  chi-square = {x:.1f}, p = {p:.2g}", ""]
no_rep = [r for r in trucial if not r["repeated_marker"]]
a2, b2, c2, d2 = split_table(no_rep, SPLIT)
x2, p2 = chi2_2x2(a2, b2, c2, d2)
lines += [f"Robustness (a): without statements marked + (repeated): n = {len(no_rep)}",
          f"  {100 * a2 / (a2 + b2):.0f}% at Sharjah before, {100 * c2 / (c2 + d2):.0f}% from {SPLIT};"
          f" chi-square = {x2:.1f}, p = {p2:.2g}", "",
          "Robustness (b): moving the dividing year (larger chi-square = sharper change)"]
for s in range(1930, 1941):
    a3, b3, c3, d3 = split_table(trucial, s)
    x3, p3 = chi2_2x2(a3, b3, c3, d3)
    lines.append(f"  split {s}: before {100 * a3 / max(a3 + b3, 1):.0f}% Sharjah (n={a3 + b3}), "
                 f"after {100 * c3 / max(c3 + d3, 1):.0f}% (n={c3 + d3}); chi-square {x3:.1f}")
pre = [r for r in trucial if int(r["year"]) < SPLIT and r["gender"] in ("F", "M")]
fw = [r for r in pre if r["gender"] == "F"]; mw = [r for r in pre if r["gender"] == "M"]
a4 = sum(agency_of(r) == "Sharjah Agency" for r in fw); c4 = sum(agency_of(r) == "Sharjah Agency" for r in mw)
x4, p4 = chi2_2x2(a4, len(fw) - a4, c4, len(mw) - c4)
lines += ["", f"Gender, Trucial Coast residents, {FIRST}-{SPLIT - 1}: share who made their statement at Sharjah",
          f"  women {a4} of {len(fw)} ({100 * a4 / max(len(fw), 1):.0f}%), men {c4} of {len(mw)} "
          f"({100 * c4 / max(len(mw), 1):.0f}%); chi-square = {x4:.1f}, p = {p4:.2g}",
          "  (a difference shows women and men used different Agencies; it does not show why)"]
lines += ["", "Caveat: counts depend on which statements Zdanowski found and transcribed; see the",
          "file-coverage check (IOR/R/15/1/208-212) in the methods chapter."]
(OUT / "test_results.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))

# 6. chart
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    years = list(range(FIRST, LAST + 1))
    colours = {"Sharjah Agency": "#c0392b", "Muscat Agency": "#1e8449", "Bahrain Agency": "#2471a3", "other": "#aaaaaa"}
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bottom = [0] * len(years)
    for c in cols:
        vals = [by_year[y][c] for y in years]
        ax.bar(years, vals, bottom=bottom, color=colours[c], label=c.replace(" Agency", ""))
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.axvline(SPLIT - 0.5, color="black", lw=1, ls="--")
    ax.set_title("Statements by residents of the Trucial Coast (present-day UAE), by Agency and year")
    ax.set_ylabel("statements"); ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 0.01, "Source: Zdanowski (2008), annex; residences located via GeoNames.", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "agency_by_year.png", dpi=200)
    print(f"\nchart saved to {OUT / 'agency_by_year.png'}")
except ImportError:
    print("\n(matplotlib not installed: run  pip install matplotlib  to get the chart)")
