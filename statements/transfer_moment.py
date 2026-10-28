"""
Did people seek manumission when their ownership was about to change? (file 212)

Usage   python transfer_moment.py
Reads   statements_zschema.csv, evidence.csv, transfers.csv     (from 212_zschema.py)
        statements.csv                                          (possible_duplicate_of)
        ../annex/zdanowski_annex_table.csv          (for the comparison with the annex)
Writes  transfer_moment_212.csv     one row per statement: each trigger, with the words it rests on
        results/transfer_moment_report.txt  counts, by gender, and against the annex for the same months

Triggers (a statement can have several)
  sale_threat     the model marked sale_feared_or_planned = Y AND its quotation was found in the text
  master_death    the statement text says the master or mistress died (rule below), or a transfer of
                  mode 'inherited' is recorded
  other_transfer  a transfer of mode 'married_off', 'gifted' or 'pledged' is recorded
  any_transfer_moment   any of the three above
  Other grounds are given for comparison, from the reason flags: ill_treated, beaten, not_paid_or_advance.

Rule for master_death (applied to the statement text, case-insensitive):
  '(master|mistress|owner) ... died' within 8 words, 'death of my/his/her master|mistress|owner',
  'after (his|her) death', or 'heirs of'.

Caution for interpretation: fear of sale was a ground the Agency accepted. Its share measures what
applicants said to Agency staff, which may reflect what they knew would succeed as well as what
prompted them to leave. master_death and inheritance are less open to that reading.
Copies of the same statement (possible_duplicate_of) are counted once.
"""
import csv
import re
from collections import Counter
from pathlib import Path

DEATH = re.compile(r"\b(?:master|mistress|owner)\b(?:\W+\w+){0,8}?\W+died\b"
                   r"|\bdeath of (?:my|his|her|our) (?:master|mistress|owner)\b"
                   r"|\bafter (?:his|her) death\b|\bheirs of\b", re.I)

S = list(csv.DictReader(open("statements_zschema.csv", encoding="utf-8-sig")))
dup = {r["statement_id"]: r["possible_duplicate_of"]
       for r in csv.DictReader(open("statements.csv", encoding="utf-8-sig")) if r.get("possible_duplicate_of")}
ev = {(e["statement_id"], e["field"]): e for e in csv.DictReader(open("evidence.csv", encoding="utf-8-sig"))}
tr = {}
for t in csv.DictReader(open("transfers.csv", encoding="utf-8-sig")):
    tr.setdefault(t["statement_id"], []).append(t)

rows = []
for s in S:
    sid = s["statement_id"]
    if sid in dup:
        continue
    e = ev.get((sid, "sale_feared_or_planned"))
    sale = s["sale_feared_or_planned"] == "Y" and e is not None and e["quote_check"] in ("exact", "approx")
    m = DEATH.search(s["text_clean"])
    modes = [t["mode"] for t in tr.get(sid, [])]
    death = bool(m) or "inherited" in modes
    other = any(x in modes for x in ("married_off", "gifted", "pledged"))
    rows.append({"statement_id": sid, "gender": s["gender"], "date_iso": s["date_iso"],
                 "sale_threat": "Y" if sale else "", "sale_quote": e["quote"] if sale else "",
                 "master_death": "Y" if death else "",
                 "death_words": m.group(0) if m else ("transfer: inherited" if death else ""),
                 "other_transfer": "Y" if other else "",
                 "any_transfer_moment": "Y" if (sale or death or other) else "",
                 "ill_treated": s["ill_treated"], "beaten": s["beaten"],
                 "not_paid_or_advance": s["not_paid_or_advance"],
                 "counts_as_application": s.get("counts_as_application", "")})

with open("transfer_moment_212.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def pct(n, d):
    return f"{n} of {d} ({100 * n / d:.0f}%)" if d else "0"


L = [f"statements (copies counted once): {len(rows)}", ""]
for lab, sel in [("all", rows), ("women", [r for r in rows if r["gender"] == "F"]),
                 ("men", [r for r in rows if r["gender"] == "M"])]:
    L.append(f"{lab}:")
    for k in ("any_transfer_moment", "sale_threat", "master_death", "other_transfer",
              "ill_treated", "beaten", "not_paid_or_advance"):
        L.append(f"  {k:22} {pct(sum(r[k] == 'Y' for r in sel), len(sel))}")
only_moment = sum(1 for r in rows if r["any_transfer_moment"] == "Y"
                  and not any(r[k] == "Y" for k in ("ill_treated", "beaten", "not_paid_or_advance")))
L += ["", f"transfer moment as the only ground given (no ill-treatment, beating or pay): {pct(only_moment, len(rows))}"]

# the annex for the same months, recorded at Sharjah
dates = sorted(r["date_iso"] for r in rows if len(r["date_iso"]) == 10)
lo, hi = dates[0], dates[-1]
A = [a for a in csv.DictReader(open("../annex/zdanowski_annex_table.csv", encoding="utf-8"))
     if a["entry_type"] == "statement" and a["recorded_at"] == "British Agency in Sharjah"
     and len(a["date_iso"]) == 10 and lo <= a["date_iso"] <= hi]
L += ["", f"Zdanowski's annex, Sharjah, {lo} to {hi} ({len(A)} entries):",
      f"  fear_of_sale           {pct(sum(a['fear_of_sale'] == 'Y' for a in A), len(A))}",
      f"  re_enslavement         {pct(sum(a['re_enslavement'] == 'Y' for a in A), len(A))}",
      "  (the annex has no field for a master's death; compare sale threat with fear_of_sale)"]
Path("results").mkdir(exist_ok=True)
Path("results/transfer_moment_report.txt").write_text("\n".join(L), encoding="utf-8")   # counts only
print("\n".join(L))
