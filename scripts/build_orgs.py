"""Registered Community Organization (RCO) boundaries around each school, for the map's RCO layer and panel.

Every RCO whose boundary comes within 1.5 miles of a school, from the City's live Zoning_RCO layer, with the
distance from the school to the boundary (0 when the boundary covers the school), so the map can show the RCOs
that reach whatever radius is set. Writes public/data/<slug>/rco.json and the `rcos` list in schools.json.

Contact names, emails, phone numbers and organization (mailing) addresses are never requested: many are the
home of a volunteer. Only the public meeting place and the organization's own links are kept.

Run: uv run --no-project --with geopandas --with pyogrio --with requests python scripts/build_orgs.py
"""
import json
import re
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point, mapping

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data"
CACHE = Path(__file__).resolve().parent / ".cache/links"
CACHE.mkdir(parents=True, exist_ok=True)
FT = 2272
MI = 5280
REACH_MI = 1.5
URL = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/Zoning_RCO/FeatureServer/0/query"
FIELDS = "organization_name,meeting_location_address,org_type,websites,expirationyear"


def fetch_rcos() -> gpd.GeoDataFrame:
    path = CACHE / "rco_city.geojson"
    if not path.exists():
        feats, offset = [], 0
        while True:
            r = requests.get(URL, params={"where": "1=1", "outFields": FIELDS, "outSR": 4326, "f": "geojson",
                                          "resultOffset": offset, "resultRecordCount": 1000}, timeout=120)
            r.raise_for_status()
            page = r.json()["features"]
            feats += page
            if len(page) < 1000:
                break
            offset += 1000
        path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return gpd.read_file(path).set_crs(4326, allow_override=True)


def clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip() if v is not None and str(v) != "nan" else ""


def one_line(v) -> str:
    return re.sub(r"\s*,(\s*,)+\s*", ", ", re.sub(r"\s*[\r\n]+\s*", ", ", str(v or ""))).strip(", ").strip()


SOCIAL = {"facebook": r"(?:^|//|\.)(?:facebook|fb)\.com/", "instagram": r"(?:^|//|\.)instagram\.com/"}


def split_links(raw: str) -> dict:
    """An RCO's `websites` field can hold several links; sort them into website / facebook / instagram."""
    out = {}
    for tok in re.split(r"[\s,;|]+", raw or ""):
        tok = tok.strip().strip(".").strip()
        if not re.search(r"[a-z0-9-]+\.[a-z]{2,}", tok, re.I) or "@" in tok:
            continue
        url = tok if re.match(r"https?://", tok, re.I) else f"https://{tok}"
        kind = next((k for k, pat in SOCIAL.items() if re.search(pat, url, re.I)), "website")
        out.setdefault(kind, url)
    return out


def rnd(geom, dp=5):
    def r(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(c[0], dp), round(c[1], dp)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def main():
    dead = set(json.loads((ROOT / "scripts/broken_links.json").read_text()))
    schools_path = OUT / "schools.json"
    meta = json.loads(schools_path.read_text())
    city = fetch_rcos()
    city = city[city.geometry.notna()].copy()
    city["geometry"] = city.geometry.buffer(0)
    city_ft = city.to_crs(FT)
    simple = city_ft.geometry.simplify(12, preserve_topology=True).to_crs(4326)
    pacdc = json.loads((Path.home() / "Desktop/FW 2026/Studio/Final Two School/MIDREVIEW/Community Asset/_source/pacdc_cdc_members.json").read_text()) \
        if (Path.home() / "Desktop/FW 2026/Studio/Final Two School/MIDREVIEW/Community Asset/_source/pacdc_cdc_members.json").exists() else []
    key = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)|\b(inc|the|corporation|corp|cdc|community development)\b", "", s.lower()))
    is_cdc = lambda name: bool(re.search(r"\bCDC\b|community development|revitalization corp|development corp", name, re.I)) or any(key(name) and key(name) == key(p) for p in pacdc)

    for s in meta["schools"]:
        here = gpd.GeoSeries([Point(s["center"][1], s["center"][0])], crs=4326).to_crs(FT).iloc[0]
        dist = city_ft.geometry.distance(here) / MI
        rows = []
        for i in dist[dist <= REACH_MI].sort_values().index:
            r = city.loc[i]
            name = clean(r.organization_name)
            links = {k: v for k, v in split_links(clean(r.websites)).items() if v not in dead}
            props = {"name": name, "type": clean(r.org_type), "covers": bool(dist[i] == 0), "miles": round(float(dist[i]), 3),
                     "cdc": is_cdc(name), "meets": one_line(r.meeting_location_address),
                     "expires": clean(r.expirationyear).replace(".0", ""), **links}
            rows.append({"type": "Feature", "properties": {k: v for k, v in props.items() if v not in ("", None)}, "geometry": rnd(simple.loc[i])})
        rows.sort(key=lambda f: (not f["properties"]["covers"], f["properties"]["miles"], f["properties"]["name"]))
        (OUT / s["slug"] / "rco.json").write_text(json.dumps({"type": "FeatureCollection", "features": rows}, separators=(",", ":")))
        s["rcos"] = [f["properties"] for f in rows]
        n_cover = sum(f["properties"]["covers"] for f in rows)
        print(f"{s['short']}: {len(rows)} RCOs within {REACH_MI} mi ({n_cover} cover the site, "
              f"{sum(f['properties']['miles'] <= 0.5 for f in rows)} reach ½ mi) · {(OUT / s['slug'] / 'rco.json').stat().st_size // 1024} KB")
    schools_path.write_text(json.dumps(meta, separators=(",", ":")))


if __name__ == "__main__":
    main()
