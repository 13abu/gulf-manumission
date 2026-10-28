# Level 2: the original statements in file IOR/R/15/1/212

Run from inside this folder. The `annex/` pipeline must have run first, because the linking step reads `../annex/zdanowski_annex_table.csv`.

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `212_transcribe.py` | `images/` (page images from the Qatar Digital Library) | `transcriptions/` (one text file per page) |
| 2 | `212_extract_statements.py` | transcriptions | `statements.csv` (one row per statement) |
| 3 | `212_zschema.py` | `statements.csv` | `statements_zschema.csv`, `evidence.csv`, `transfers.csv`, cache in `extractions/212/` |
| 4 | `link_annex.py` | `statements_zschema.csv`, the annex table | `results/link_summary.txt` |
| 5 | `owner_recurrence.py` | `statements_zschema.csv` | `results/recurrence_summary.txt` |
| 6 | `transfer_moment.py` | statements, evidence, transfers, the annex table | `results/transfer_moment_report.txt` |

Steps 1 and 3 call the Gemini API. The key is read from `~/qdl_ocr.cfg` (see `config.py`).

## Notes on method

- **Transcription.** Page images are transcribed by `gemini-3.5-flash-lite`. Of 404 pages, 8 were refused by the model and 7 returned refusal text. Both are recorded, not silently dropped.
- **Extraction.** Each statement is extracted blind: the model never sees Zdanowski's annex. Every value must come with a quotation from the statement, and the script checks each quotation against the text (exact, approximate at ≥ 0.9 similarity, or not found). Of 1,011 quotations, 991 match exactly, 3 approximately and 5 are not found.
- **Transfers.** Each change in a person's status is recorded as an event (sold, bought, inherited, gifted, pledged, married off, born in the house, kidnapped). Births and kidnappings are entries into slavery. The rest are changes of owner.
- **Linking.** A statement links to an annex entry when the name keys agree and the dates fall within 3 days. Statements that match on name only are listed separately as date differences or spelling variants for checking by hand.
- **Recurrence.** Owners and other named people are grouped by name to see who appears in more than one application. Bare names and groups are not linked.

## Included outputs

`results/` holds counts only. Everything else these scripts write contains personal names or source text and stays local (see `.gitignore` at the top level).
