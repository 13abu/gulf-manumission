"""
Rebuild the file 212 statements in Zdanowski's annex schema, and add the fields his annex leaves out.

Usage   python 212_zschema.py              extract every statement not yet extracted, then build the tables
        python 212_zschema.py --limit 5    extract at most 5 new statements (try this first)
        python 212_zschema.py --dry-run    no API calls: write one example prompt, build tables from what is cached

Reads   statements.csv                         from 212_extract_statements.py (one row per statement)
Writes  extractions/212/<id>_<hash>.json       the model's raw reply for each statement (kept; reruns skip it)
        statements_zschema.csv                 one row per statement: Zdanowski's fields, then the extra fields
        transfers.csv                          one row per change of owner reported in a statement
        evidence.csv                           one row per model-extracted value, with its quotation and check
        zschema_report.txt                     counts, and every value whose quotation was not found

Where each value comes from (the 'source' column in evidence.csv)
  copied  read from the statement heading by 212_extract_statements.py: name, age, date, birthplace,
          father's name status, thumb impression
  rule    derived here by a stated rule: gender (bin/bint), father's name (the word after bin/bint),
          recorded_at ('Recorded at X'), date_iso (parsed from the heading date), the reason flags
  model   extracted by Gemini from the statement text. The model must return, for every value, the
          exact words of the statement it rests on. This script then looks for those words in the
          statement: 'exact' (found), 'approx' (found with small differences, e.g. spacing or a
          [struck: ...] mark), or 'not_found'. Values marked not_found stay in the table but are
          listed in zschema_report.txt; check them against the image before using them.

Blind extraction: the model sees only the statement text, never Zdanowski's annex, so the comparison
with the annex (a later step) is a real test.

Comparability with the annex
  - Column names match zdanowski_annex_table.csv so the two can be joined field by field.
  - reason_or_circumstance is a short summary in the annex's style; the reason flags are computed
    from that summary with the same keyword rules as zdanowski_parser.py, not from the whole
    statement (the annex flags were computed from Zdanowski's short entries).
  - ethnicity_as_recorded is filled only when the statement itself states a label. Zdanowski took
    labels from the Agency's notes on attached documents, so most will be blank here by design.
"""
import argparse
import csv
import difflib
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

SOURCE_FILE = "IOR/R/15/1/212"
STATEMENTS_CSV = Path("statements.csv")
CACHE = Path("extractions/212")
MODEL = "gemini-3.5-flash-lite"
PROMPT_VERSION = "z1"          # change this whenever PROMPT changes; older replies are then re-extracted
REQUESTS_PER_MINUTE = 12
MAX_RETRIES = 3

# ---------------------------------------------------------------- cleaning the statement text
# Lines that are the transcription process, not the document: the model's refusals on faded pages,
# its section headers, and marginalia that leaked into the body when pages were joined.
NOISE = [
    re.compile(r"^.*\bI (?:cannot|can't|am unable to|could not) (?:provide|produce|transcribe|fulfil+)\b.*$", re.I | re.M),
    re.compile(r"^.*\bI'm sorry\b.*$", re.I | re.M),
    re.compile(r"^\s*(?:MAIN(?: BODY)? )?(?:TRANSCRIPTION|TEXT)\b[^\n]*:?\s*$|^\s*BODY TEXT\b[^\n]*$", re.I | re.M),
    re.compile(r"^\W*MARGINALIA\b[^\n]*$", re.I | re.M),
]


def clean(text):
    removed = 0
    for pat in NOISE:
        text, n = pat.subn("", text)
        removed += n
    return re.sub(r"\n{3,}", "\n\n", text).strip(), removed


# ---------------------------------------------------------------- the prompt
PROMPT = """You are extracting information from one manumission statement recorded at a British Agency
in the Persian Gulf (1939-1941). The statement is given below between <statement> tags.

Return ONE JSON object with exactly these keys. For every value you give, also give "quote": the exact,
continuous words of the statement that the value rests on, copied character for character (same
spelling, same punctuation). If the statement does not say it, use null for the value and the quote.
Do not infer, do not use outside knowledge, do not correct spellings of names or places.

{
  "residence":        {"value": place where the person lived or was held when they ran away, "quote": ...},
  "occupation":       {"value": work the person did, in the statement's words (e.g. "diving"), "quote": ...},
  "ethnicity_stated": {"value": an ethnic or origin label the statement applies to the person (e.g. "Baluchi"), "quote": ...},
  "reason_summary":   {"value": why they sought release, as a short phrase in this style:
                        "ill-treated and beaten, afraid of being sold", "not paid", "kidnapped and escaped",
                       "quote": the sentence(s) giving the reason},
  "origin_of_enslavement": {"value": one of "born_into_slavery", "kidnapped", "sold_by_relative",
                        "pledged_or_debt", "other", "not_stated", "quote": ...},
  "kidnap_place":     {"value": where they were kidnapped from, "quote": ...},
  "kidnapper":        {"value": name or description of the kidnapper, "quote": ...},
  "current_owner":    {"value": the master at the time of the statement, name as written, "quote": ...},
  "transfers": [      one item per change of owner or holder, in the order they happened:
                      {"from": name or null, "to": name or null,
                       "mode": one of "born_in_house", "kidnapped", "sold", "bought", "inherited",
                               "gifted", "married_off", "pledged", "hired_out", "other",
                       "price": amount as written or null, "place": place as written or null,
                       "when": time as written or null, "quote": ...}],
  "intermediaries": [ people who stood between the person and the owner: boat captains (nakhuda),
                      brokers (dallal), creditors, employers. {"name": ..., "role": ..., "quote": ...}],
  "money": [          every sum of money mentioned. {"amount": as written, "what": what it was for, "quote": ...}],
  "earnings_withheld":     {"value": true, false or null, "quote": ...},
  "sale_feared_or_planned":{"value": true, false or null, "quote": ...},
  "fled_from":        {"value": place, "quote": ...},
  "fled_to":          {"value": place, "quote": ...},
  "family": [         relatives mentioned. {"relation": e.g. "wife", "name": name or null, "quote": ...}]
}

Use [] for an empty list. Return only the JSON object.

<statement>
{text}
</statement>
"""

# ---------------------------------------------------------------- rule-based fields
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}

# Same keyword rules as zdanowski_parser.py, applied to the reason summary (see docstring).
FLAGS = {
    "ill_treated": r"ill-?treated|ill-treatment|maltreatment|badly treated|cruel|harsh|oppress|tortur|troubled|molested",
    "beaten": r"beat|baeten",
    "chains_or_confinement": r"chain|irons|prison|custody|confinement|imprisoned",
    "fear_of_sale": r"afraid of being (?:sold|bartered)|fear\w* of being sold|threatened to be sold|afraid .* will be sold|going to be sold",
    "not_paid_or_advance": r"not paid|advance|earnings|deprived",
    "kidnapped": r"kidnap",
    "re_enslavement": r"re-?enslav|enslaved by his heirs|claimed by his heirs|enslaved again",
    "family_separation_or_search": r"separat|daughter|\bson\b|sons|children|wife|husband|relatives|brother|sister|family|mother",
    "duplicate_certificate": r"duplicate|copy|lost it|stolen certificate",
}


def date_iso(raw):
    m = re.search(r"(\d{1,2})\w*\s+(?:day\s+)?(?:of\s+)?([A-Za-z]{3})[a-z]*\.?,?\s+(19\d\d)", raw or "")
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(19\d\d)\b", raw or "")
    return m.group(1) if m else ""


def father_name(name_raw, status):
    if status == "unknown":
        return "unknown"
    m = re.search(r"\b(?:bin|bint|ibn|binti)\s+([^,()]+)", name_raw, re.I)
    return m.group(1).strip() if m else ""


def recorded_at(text):
    m = re.search(r"Recorded\s+at\s+([A-Z][A-Za-z' -]+?)(?:\s+on\b|[,.])", text)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------- checking quotations
def norm(s):
    s = re.sub(r"\[struck:[^\]]*\]", "", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("_", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def check_quote(quote, text):
    """'exact' if the quotation is in the text, 'approx' if a passage of the text matches it closely
    (similarity >= 0.9, e.g. spacing or struck-through words), otherwise 'not_found'."""
    q, t = norm(quote), norm(text)
    if not q:
        return ""
    if q in t:
        return "exact"
    n = len(q)
    step = max(1, n // 4)
    best = 0.0
    for i in range(0, max(1, len(t) - n + 1), step):
        best = max(best, difflib.SequenceMatcher(None, q, t[i:i + n]).ratio())
        if best >= 0.9:
            return "approx"
    return "not_found"


# ---------------------------------------------------------------- calling the model
def extract(client, types, text, state):
    prompt = PROMPT.replace("{text}", text)
    for attempt in range(1, MAX_RETRIES + 1):
        wait = state["last"] + 60 / REQUESTS_PER_MINUTE - time.time()
        if wait > 0:
            time.sleep(wait)
        state["last"] = time.time()
        try:
            r = client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"))
            raw = (r.text or "").strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
            return json.loads(raw), None
        except json.JSONDecodeError as e:
            err = f"reply was not valid JSON ({e})"
        except Exception as e:
            err = str(e)
            if "perday" in err.lower() or "per day" in err.lower():
                return None, "daily limit reached"
        print(f"    attempt {attempt}: {err[:120]}")
        time.sleep(5 * attempt)
    return None, err


def cache_path(sid, text):
    return CACHE / f"{sid}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}.json"


def load_cached(sid, text):
    p = cache_path(sid, text)
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("prompt_version") == PROMPT_VERSION:
            return d
    return None


# ---------------------------------------------------------------- building the tables
def v(field):
    return field.get("value") if isinstance(field, dict) else None


def as_text(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "Y" if x else "N"
    return str(x)


Z_COLS = ["name", "gender", "father_name", "residence", "birthplace", "ethnicity_as_recorded", "age_years",
          "date_raw", "date_iso", "year", "occupation", "reason_or_circumstance", "recorded_at"] + list(FLAGS)
EXTRA_COLS = ["origin_of_enslavement", "kidnap_place", "kidnapper", "current_owner", "owner_chain",
              "n_transfers", "intermediaries", "money", "earnings_withheld", "sale_feared_or_planned",
              "fled_from", "fled_to", "family", "father_name_status", "authentication"]
META_COLS = ["model", "prompt_version", "extracted_at", "unverified_fields", "noise_lines_removed"]
CODING_COLS = ["counts_as_application", "ground_coded", "notes"]          # your own coding, carried over
SINGLE = {"residence": "residence", "occupation": "occupation", "ethnicity_as_recorded": "ethnicity_stated",
          "reason_or_circumstance": "reason_summary", "origin_of_enslavement": "origin_of_enslavement",
          "kidnap_place": "kidnap_place", "kidnapper": "kidnapper", "current_owner": "current_owner",
          "earnings_withheld": "earnings_withheld", "sale_feared_or_planned": "sale_feared_or_planned",
          "fled_from": "fled_from", "fled_to": "fled_to"}


def build_row(s, text, removed, d, evidence, transfers_out):
    sid = s["statement_id"]
    row = {"statement_id": sid, "source_file": SOURCE_FILE, "start_page": s["start_page"], "end_page": s["end_page"]}
    sex = {"male": "M", "female": "F"}.get(s.get("sex_auto", ""), "")
    di = date_iso(s.get("date_raw", ""))
    row.update({"name": s["name_raw"], "gender": sex, "father_name": father_name(s["name_raw"], s["father_name_status"]),
                "birthplace": s.get("born_at", ""), "age_years": s.get("age_stated", ""), "date_raw": s.get("date_raw", ""),
                "date_iso": di, "year": di[:4], "recorded_at": recorded_at(text),
                "father_name_status": s["father_name_status"], "authentication": s["authentication_auto"]})
    for f in ("name", "birthplace", "age_years", "date_raw", "father_name_status", "authentication"):
        evidence.append([sid, f, row[f], "copied", "", ""])
    for f in ("gender", "father_name", "date_iso", "recorded_at"):
        evidence.append([sid, f, row[f], "rule", "", ""])

    unverified = []
    reply = (d or {}).get("reply") or {}
    for col, key in SINGLE.items():
        field = reply.get(key) or {}
        val = v(field)
        row[col] = as_text(val)
        if val not in (None, "", []):
            chk = check_quote(field.get("quote"), text)
            evidence.append([sid, col, row[col], "model", field.get("quote") or "", chk])
            if chk != "exact" and chk != "approx":
                unverified.append(col)

    steps = reply.get("transfers") or []
    chain = []
    for i, t in enumerate(steps, 1):
        chk = check_quote(t.get("quote"), text)
        transfers_out.append([sid, i, as_text(t.get("from")), as_text(t.get("to")), as_text(t.get("mode")),
                              as_text(t.get("price")), as_text(t.get("place")), as_text(t.get("when")),
                              t.get("quote") or "", chk])
        if chk == "not_found":
            unverified.append(f"transfer_{i}")
        for who in (t.get("from"), t.get("to")):
            if who and (not chain or chain[-1] != who):
                chain.append(who)
    row["owner_chain"] = " -> ".join(chain)
    row["n_transfers"] = len(steps)

    for col in ("intermediaries", "money", "family"):
        items = reply.get(col) or []
        parts = []
        for it in items:
            chk = check_quote(it.get("quote"), text)
            label = " ".join(as_text(it.get(k)) for k in ("name", "role", "amount", "what", "relation") if it.get(k))
            parts.append(label)
            evidence.append([sid, col, label, "model", it.get("quote") or "", chk])
            if chk == "not_found":
                unverified.append(col)
        row[col] = "; ".join(parts)

    for f, pat in FLAGS.items():
        row[f] = "Y" if re.search(pat, row["reason_or_circumstance"], re.I) else ""
    row.update({"model": (d or {}).get("model", ""), "prompt_version": (d or {}).get("prompt_version", ""),
                "extracted_at": (d or {}).get("extracted_at", ""), "unverified_fields": ";".join(dict.fromkeys(unverified)),
                "noise_lines_removed": removed})
    for c in CODING_COLS:
        row[c] = s.get(c, "")
    row["text_clean"] = text
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="extract at most this many new statements")
    ap.add_argument("--dry-run", action="store_true", help="no API calls")
    args = ap.parse_args()

    statements = list(csv.DictReader(open(STATEMENTS_CSV, encoding="utf-8-sig")))
    CACHE.mkdir(parents=True, exist_ok=True)
    cleaned = {s["statement_id"]: clean(s["text"]) for s in statements}

    todo = [s for s in statements if not load_cached(s["statement_id"], cleaned[s["statement_id"]][0])]
    if args.limit is not None:
        todo = todo[:args.limit]
    print(f"{len(statements)} statements; {len(statements) - len(todo) if args.limit is None else '?'} already extracted; "
          f"{len(todo)} to extract now")

    if args.dry_run:
        s = statements[0]
        (CACHE / "_example_prompt.txt").write_text(PROMPT.replace("{text}", cleaned[s["statement_id"]][0]), encoding="utf-8")
        print(f"dry run: example prompt written to {CACHE / '_example_prompt.txt'}; no API calls made")
    elif todo:
        from google import genai
        from google.genai import types
        from config import API_KEY
        client, state = genai.Client(api_key=API_KEY), {"last": 0.0}
        for i, s in enumerate(todo, 1):
            sid = s["statement_id"]
            text = cleaned[sid][0]
            print(f"[{i}/{len(todo)}] {sid} {s['name_raw'][:40]}")
            reply, err = extract(client, types, text, state)
            if reply is None:
                print(f"    not extracted: {err}")
                if err == "daily limit reached":
                    break
                continue
            cache_path(sid, text).write_text(json.dumps(
                {"statement_id": sid, "model": MODEL, "prompt_version": PROMPT_VERSION,
                 "extracted_at": datetime.now().isoformat(timespec="seconds"), "reply": reply},
                ensure_ascii=False, indent=1), encoding="utf-8")

    rows, evidence, transfers = [], [], []
    for s in statements:
        text, removed = cleaned[s["statement_id"]]
        rows.append(build_row(s, text, removed, load_cached(s["statement_id"], text), evidence, transfers))

    cols = ["statement_id", "source_file", "start_page", "end_page"] + Z_COLS + EXTRA_COLS + META_COLS + CODING_COLS + ["text_clean"]
    with open("statements_zschema.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    with open("transfers.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["statement_id", "step", "from", "to", "mode", "price", "place", "when", "quote", "quote_check"])
        w.writerows(transfers)
    with open("evidence.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["statement_id", "field", "value", "source", "quote", "quote_check"]); w.writerows(evidence)

    done = sum(1 for r in rows if r["model"])
    checks = Counter(e[5] for e in evidence if e[3] == "model") + Counter(t[9] for t in transfers)
    lines = [f"statements: {len(rows)}; extracted by the model: {done}; not yet extracted: {len(rows) - done}",
             f"noise lines removed from statement text: {sum(r['noise_lines_removed'] for r in rows)} "
             f"(in {sum(1 for r in rows if r['noise_lines_removed'])} statements)",
             f"model values with a quotation: {sum(checks.values())}; exact {checks['exact']}, "
             f"approx {checks['approx']}, not found {checks['not_found']}",
             f"transfers extracted: {len(transfers)} in {sum(1 for r in rows if r['n_transfers'])} statements",
             "", "Values whose quotation was not found in the statement (check against the image):"]
    lines += [f"  {e[0]}  {e[1]}: {e[2]!r}  quote: {e[4][:80]!r}" for e in evidence if e[5] == "not_found"]
    lines += [f"  {t[0]}  transfer {t[1]}: {t[2]} -> {t[3]} ({t[4]})  quote: {t[8][:80]!r}" for t in transfers if t[9] == "not_found"]
    Path("zschema_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:5]))
    print("Wrote statements_zschema.csv, transfers.csv, evidence.csv, zschema_report.txt")


if __name__ == "__main__":
    main()
