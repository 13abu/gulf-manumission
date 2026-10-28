#!/bin/bash
# Runs the whole pipeline in order. Run from inside the annex folder.
set -e
# activate your environment first if you use one, e.g.  source ../.venv/bin/activate
python3 scripts/zdanowski_parser.py      # 1. PDF -> zdanowski_annex_table.csv
python3 scripts/normalise_places.py      # 2. group spellings -> places/place_variants.csv
python3 scripts/geocode_places.py        # 3. GeoNames lookup -> places/gazetteer_auto.csv
python3 scripts/build_geo_table.py       # 4. + your manual file -> gazetteer.csv, zdanowski_annex_geo.csv
python3 scripts/flow_map.py              # 5. map -> flow_map.html
python3 scripts/analyse_agency_choice.py # 6. Agency choice, test, chart -> analysis/
python3 scripts/describe_annex.py        # 7. descriptive tables and report -> analysis/descriptive/
echo "Done. Open flow_map.html to see the map."
