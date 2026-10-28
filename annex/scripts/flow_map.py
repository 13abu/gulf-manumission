"""First exploratory map: who went from where to which Agency, before and after 1937.
Usage: python3 flow_map.py zdanowski_annex_geo.csv  -> flow_map.html
"""
import csv, sys, collections
import folium
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SRC = sys.argv[1] if len(sys.argv) > 1 else PROJECT / "zdanowski_annex_geo.csv"

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8"))
        if r["entry_type"] == "statement" and r["res_lat"] and r["ag_lat"] and r["year"].isdigit()]

PERIODS = [("1921–1936", 1921, 1936), ("1937–1942", 1937, 1942)]
COLOURS = {"Sharjah Agency": "#c0392b", "Bahrain Agency": "#2471a3", "Muscat Agency": "#1e8449"}

# Esri's light grey basemap: OpenStreetMap's servers block pages opened from your own disk
m = folium.Map(location=[25.4, 55.0], zoom_start=6, tiles=None)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ", name="Esri light grey", max_zoom=16).add_to(m)
for label, a, b in PERIODS:
    for g_label, g in [("all", None), ("women", "F"), ("men", "M")]:
        fg = folium.FeatureGroup(name=f"{label} · {g_label}", show=(g_label == "all" and a == 1921))
        flows = collections.Counter()
        for r in rows:
            if a <= int(r["year"]) <= b and (g is None or r["gender"] == g):
                flows[(r["residence_place"], float(r["res_lat"]), float(r["res_lon"]),
                       r["agency"], float(r["ag_lat"]), float(r["ag_lon"]))] += 1
        for (res, la, lo, ag, al, ao), n in flows.items():
            col = COLOURS.get(ag, "#7f8c8d")
            if (la, lo) != (al, ao):
                folium.PolyLine([(la, lo), (al, ao)], weight=1 + n ** 0.6, color=col, opacity=0.55,
                                tooltip=f"{res} → {ag}: {n}").add_to(fg)
            folium.CircleMarker((la, lo), radius=2 + n ** 0.5, color=col, fill=True, fill_opacity=0.6,
                                tooltip=f"{res} → {ag}: {n}").add_to(fg)
        fg.add_to(m)
for ag, (lat, lon) in {"Sharjah Agency": (25.358, 55.390), "Bahrain Agency": (26.220, 50.580),
                       "Muscat Agency": (23.615, 58.590)}.items():
    folium.Marker((lat, lon), tooltip=ag, icon=folium.Icon(color="black", icon="flag")).add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
m.get_root().html.add_child(folium.Element(
    "<div style='position:fixed;bottom:12px;left:12px;z-index:9999;background:#fff;padding:8px 10px;"
    "font:13px sans-serif;border:1px solid #ccc'>Lines: residence → Agency where statement was taken. "
    "<span style='color:#c0392b'>Sharjah</span> · <span style='color:#2471a3'>Bahrain</span> · "
    "<span style='color:#1e8449'>Muscat</span>. Coordinates: GeoNames and manual identifications (see gazetteer.csv); unresolved places omitted.</div>"))
m.save(str(PROJECT / "flow_map.html"))
print("saved", len(rows), "statements mapped to", PROJECT / "flow_map.html")