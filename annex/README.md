# Level 1: Zdanowski's annex

Run from inside this folder, in order (or `./run_all.sh`):

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `scripts/zdanowski_parser.py` | `data/ZDANOWSKI_slaved_data.pdf` | `zdanowski_annex_table.csv` (1,022 entries) |
| 2 | `scripts/normalise_places.py` | the table, `places/merge_decisions.csv` | `places/place_variants.csv`, `places/merge_suggestions.csv` |
| 3 | `scripts/geocode_places.py` | place variants, GeoNames | `places/gazetteer_auto.csv`, `places/geocode_candidates.csv` |
| 4 | `scripts/build_geo_table.py` | automatic gazetteer, `places/gazetteer_manual.csv` | `gazetteer.csv`, `zdanowski_annex_geo.csv` |
| 5 | `scripts/flow_map.py` | geocoded table | `flow_map.html` |
| 6 | `scripts/analyse_agency_choice.py` | geocoded table | `analysis/` (test, robustness checks, chart) |
| 7 | `scripts/describe_annex.py` | geocoded table | `analysis/descriptive/` |

## Notes on method

- **Parsing.** Text is read character by character with pdfplumber, and fields are separated with regular expressions. The wording of every field is Zdanowski's summary, not the Agency's.
- **Place names.** Spellings are grouped by a transliteration key (`scripts/placenames.py`). Near matches are only suggested. A merge happens only when it is accepted in `places/merge_decisions.csv`, which is included as the record of those decisions.
- **Geocoding.** Each place is matched against GeoNames. Candidates are scored by distance from an anchor taken from the annex itself (the context given with the place, or the Agency where the statement was made). Certainty (high, region, ambiguous, none) is computed from the scores, and the rules and constants are documented at the top of `geocode_places.py`. Ambiguous places go to a manual file, and every manual coordinate there needs a source and a citation.
- **Test.** People living on the Trucial Coast are those whose residence geocodes to the present-day UAE. The share of them applying at Sharjah is compared before and after 1937 with a 2×2 chi-square test. Robustness checks exclude repeated statements and move the dividing year.

## Included outputs

`analysis/` and `analysis/descriptive/` hold aggregate tables only. Tables that list individuals' names (`father_names.csv`, `given_names.csv`, `kidnapping_entries.csv`) are produced locally but not shared.
