# Manumission statements at the British Agencies in the Gulf, 1921–1942

Code for an MA thesis in Digital Humanities (Hamad Bin Khalifa University, in progress). The project works at two levels on the statements that enslaved people made when they asked British Political Agencies in the Gulf for manumission certificates.

1. **The annex (`annex/`).** Zdanowski's index of manumission statements (*Slavery in the Gulf in the First Half of the 20th Century*, Warsaw, 2008, pp. 191–231) is parsed into a table of 1,022 entries. Place names are grouped and geocoded against GeoNames. The table is then used to test where people from the Trucial Coast went to apply.
2. **The original statements (`statements/`).** File IOR/R/15/1/212 (the Sharjah Agency file, 1939–1941, digitised on the Qatar Digital Library) is transcribed from page images with a vision-language model (Gemini). Each statement is extracted into Zdanowski's schema plus fields his index does not record: owners, sales, inheritances and the moment of transfer. Every extracted value carries a quotation that is checked against the transcription. The statements are then reconciled with the annex.

All results are **preliminary** and will change as the gazetteer and the extraction are checked by hand.

## Preliminary findings

From the shipped outputs (`annex/analysis/test_results.txt`, `statements/results/`):

- **Agency choice shifts to Sharjah.** Of statements by people living on the Trucial Coast, 27% were made at Sharjah in 1921–1936 and 78% in 1937–1942 (χ² = 146.5). The shift holds when repeated statements are excluded. Moving the dividing year shows the sharpest break at 1938.
- **Women and men used different Agencies.** Before 1937, 63% of Trucial Coast women applied at Sharjah, against 14% of men.
- **The annex against the originals.** 59 of 97 statements in file 212 link to an annex entry on name and date. 6 more match with a different date, and in 2 of these the day and month agree but the year differs (a misprinted year). 7 match only on a spelling variant. 25 have no annex entry. 38 annex entries recorded at Sharjah in the same months are not in the file as digitised.
- **Ownership in the statements.** 53% of the statements name a moment of transfer as a ground for applying: a threatened sale (37%), a master's death (20%), or another transfer. In 32% it is the only ground given. Women never cite unpaid work as a ground (0 of 37); men do in 33% of cases.

## Layout

```
annex/        parse, geocode and analyse Zdanowski's annex       (see annex/README.md)
statements/   transcribe, extract and reconcile file 212           (see statements/README.md)
```

## Data and what is not in this repository

The sources are not redistributed here.

- **Zdanowski's annex** is under copyright. The parser runs on your own copy of the PDF (`annex/data/README.md`). The parsed table is not included.
- **File IOR/R/15/1/212** is available on the Qatar Digital Library. Page images, transcriptions and the per-statement extractions are not included.
- **Personal names.** The statements name enslaved people, their parents and their owners. Outputs at the level of individuals are kept private. Only aggregate tables and counts are shared.
- **GeoNames** country extracts (CC BY 4.0) are downloaded by the script on first run.

## Running it

Python 3.10 or later.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd annex && ./run_all.sh              # needs annex/data/ZDANOWSKI_slaved_data.pdf
cd ../statements                       # see statements/README.md for the input files
```

The transcription and extraction steps call the Gemini API (model `gemini-3.5-flash-lite`, temperature 0). They need a key in `~/qdl_ocr.cfg`, read by `statements/config.py`. Extractions are cached by statement and text hash, so a rerun on unchanged text makes no API calls.
