"""Build the web layers for the six-school community map.

The six candidate schools are the studio's (Pre-Mid Review/Data_Sources/sites.csv). For the two finalists,
Wagner and Blankenburg, the studio's own outputs are used as they are: the community asset table, RCOs,
15-minute walk areas, study tracts and half-mile profile. For the other four the same methods are run here:

  community assets   01_assets.py: City of Philadelphia services within one mile (organizations two), PA DHS
                     child care providers, OpenStreetMap places of worship
  RCOs               the City's RCO registry: boundaries reaching the half mile; "covers" = contains the school
  walk areas         01_walkshed.py: walk network from OpenStreetMap, 80 m a minute, reachable streets widened
                     25 m with block interiors filled; residents from 2020 Census blocks
  profile            03_profile.py: tract counts weighted by the share of each tract's 2020 residents inside the
                     half mile (block population), medians by the aggregate median method
The check at the end runs the rebuilt methods on Wagner and Blankenburg and prints them beside the studio's
numbers.

Context layers (transit, streets, crashes, zoning, land use, ...) are built once for the area within 1.5 miles
of any of the six, from the studio's per-school extracts and citywide files.

Run:  npm run build:data      (uv; first run fetches City / PA / OpenStreetMap data into scripts/.cache)
"""
import json, math, os, re, warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, Polygon, mapping
from shapely.ops import substring, unary_union

warnings.filterwarnings("ignore")
STUDIO = Path(os.environ.get("STUDIO", Path.home() / "Desktop/FW 2026/Studio"))
M = STUDIO / "Final Two School/MIDREVIEW"
DS = STUDIO / "Pre-Mid Review/Data_Sources"
ODP = STUDIO / "Pre-Mid Review/9.21.26"
OUT = Path(__file__).resolve().parents[1] / "public/data"
CACHE = Path(__file__).resolve().parent / ".cache"
CACHE.mkdir(exist_ok=True)
FT, UTM = 2272, 32618
MILE, HALF = 5280, 2640
UA = {"User-Agent": "studio-community-maps/1.0 (research map)"}

BG, TR, EC, CA = M / "Background1/_source/data", M / "Transportation1/_source/data", M / "Economic1/_source/data", M / "Community Asset"
P2 = DS / "02_parcel_zoning_landuse_historic"
P4 = DS / "04_market_transit"

SHORT = {"wagner": "Wagner", "blankenburg": "Blankenburg", "robeson": "Robeson", "pennypacker": "Pennypacker", "fitler": "Fitler", "amynw": "AMY Northwest"}
ORDER = ["wagner", "blankenburg", "robeson", "pennypacker", "fitler", "amynw"]
STUDIO_DONE = {"wagner": "Wagner", "blankenburg": "Blankenburg"}
# Colour follows the school. Five hues pass the palette checks; the sixth (Robeson) is a dark slate. Spatial
# neighbours get the most distant hues (Wagner–Pennypacker, Wagner–Fitler, Blankenburg–Robeson) and every
# school is labelled on the map, so colour is never the only cue.
COLOR = {"wagner": "#C4513F", "pennypacker": "#3D63C9", "fitler": "#1E8A5A", "amynw": "#D18A00", "blankenburg": "#8E4FB0", "robeson": "#2B2B33"}
SELF = {"wagner": r"WAGNER", "blankenburg": r"BLANKENBURG", "robeson": r"ROBESON", "pennypacker": r"PENNYPACKER", "fitler": r"FITLER", "amynw": r"MIDDLE YEARS|\bAMY\b"}


# ================================================================ helpers
def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip()
    return "" if s.lower() in ("nan", "none", "null", "<na>") else s


def num(v, dp=None):
    try:
        f = float(str(v).replace(",", "").replace("%", "")) if v is not None else None
    except (TypeError, ValueError):
        return None
    if f is None or math.isnan(f) or f < -1e8:
        return None
    return round(f, dp) if dp is not None else f


def title(s):
    s = clean(s)
    if s.isupper() or s.islower():
        s = re.sub(r"\b(Of|And|The|At|For|On|In)\b", lambda m: m.group(0).lower(), s.title()).replace("'S", "'s")
        s = re.sub(r"\b(Ii|Iii|Iv|Llc|Cdc|Nac|Ppr|Ymca|Ywca|Pa|Usa)\b", lambda m: m.group(0).upper(), s)
        s = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    return s[:1].upper() + s[1:] if s else s


def col(r, *names):
    """First non-empty value among columns (case-insensitive)."""
    idx = {c.lower(): c for c in r.index}
    for n in names:
        c = idx.get(n.lower())
        if c is not None and clean(r[c]):
            return r[c]
    return None


def rnd(geom, dp=5):
    def r(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(c[0], dp), round(c[1], dp)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def fc(gdf, props, simplify_ft=0, dp=5):
    g = gdf.to_crs(FT).copy()
    if simplify_ft:
        g["geometry"] = g.geometry.simplify(simplify_ft, preserve_topology=True)
    g = g.to_crs(4326)
    feats = []
    for _, r in g.iterrows():
        geom = r.geometry
        if geom is not None and geom.geom_type == "GeometryCollection":     # make_valid / clipping leftovers
            parts = [x for x in geom.geoms if x.geom_type in ("Polygon", "MultiPolygon", "LineString", "MultiLineString")]
            geom = unary_union(parts) if parts else None
        if geom is None or geom.is_empty:
            continue
        p = {k: v for k, v in props(r).items() if v not in ("", None)}
        feats.append({"type": "Feature", "properties": p, "geometry": rnd(geom, dp)})
    return {"type": "FeatureCollection", "features": feats}


def save(rel, obj):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))
    n = len(obj["features"]) if isinstance(obj, dict) and "features" in obj else ""
    return f"{rel} {n} ({path.stat().st_size / 1024:.0f} KB)"


def read(p, **kw):
    g = gpd.read_file(p, **kw)
    return g.set_crs(4326) if g.crs is None else g


def cached_json(name, fetch):
    f = CACHE / name
    if not f.exists():
        f.write_text(json.dumps(fetch()))
    return json.loads(f.read_text())


# ================================================================ the six schools
sites = pd.read_csv(DS / "sites.csv").set_index("slug")
studio_pts = read(BG / "school_points.geojson").to_crs(4326)
studio_parcels = read(BG / "school_parcels.geojson").to_crs(4326)

SCH = {}
for slug in ORDER:
    s = sites.loc[slug]
    if slug in STUDIO_DONE:
        name = STUDIO_DONE[slug]
        center = studio_pts[studio_pts.school == name].geometry.iloc[0]
        parcel = studio_parcels[studio_parcels.school == name].geometry.iloc[0]
    else:
        pw = read(P2 / f"{slug}_school_parcel_pwd_polygon.geojson").to_crs(FT)
        parcel_ft = unary_union(pw.geometry)
        center = gpd.GeoSeries([parcel_ft.centroid], crs=FT).to_crs(4326).iloc[0]
        parcel = gpd.GeoSeries([parcel_ft], crs=FT).to_crs(4326).iloc[0]
    SCH[slug] = {"row": s, "center": center, "parcel": parcel, "center_ft": gpd.GeoSeries([center], crs=4326).to_crs(FT).iloc[0]}

# how far the PWD parcel centroid sits from the studio's point for the two finalists (a check on the method)
for slug, name in STUDIO_DONE.items():
    pw = read(P2 / f"{slug}_school_parcel_pwd_polygon.geojson").to_crs(FT)
    d = unary_union(pw.geometry).centroid.distance(SCH[slug]["center_ft"])
    print(f"check: {name} PWD parcel centroid is {d:.0f} ft from the studio's school point")

REGION = unary_union([v["center_ft"].buffer(1.5 * MILE) for v in SCH.values()])   # context layers: 1.5 miles of any school
NEAR1 = unary_union([v["center_ft"].buffer(MILE) for v in SCH.values()])


def in_region(g, area=REGION, clip=False):
    g = g.to_crs(FT)
    g = g[g.geometry.notna() & g.intersects(area)].copy()
    if clip:
        g["geometry"] = g.geometry.intersection(area)
        g = g[~g.geometry.is_empty]
    return g


# ================================================================ census: tracts, blocks, profile
acs_all = pd.read_csv(BG / "acs_tracts_philadelphia_2014_2024.csv", dtype={"GEOID": str})
ACS_YEAR = int(acs_all.year.max())
acs = acs_all[acs_all.year == ACS_YEAR].set_index("GEOID")
more = pd.read_csv(BG / "acs_more_tracts_philadelphia_2014_2024.csv", dtype={"GEOID": str})
more = more[more.year == more.year.max()].set_index("GEOID")
bins = pd.read_csv(BG / "acs_bins.csv")
tracts20 = read(BG / "tracts_2020.geojson").to_crs(4326)
studio_shares = pd.read_csv(BG / "tract_shares.csv", dtype={"GEOID": str})
studio_shares = studio_shares[studio_shares.tract_vintage == 2020]
profile_csv = pd.read_csv(BG / "profile_2024.csv").set_index("indicator")


def ratio(a, b):
    a, b = num(a), num(b)
    return round(a / b, 4) if a is not None and b else None


def tract_measures(geoid):
    if geoid not in acs.index:
        return {}
    r = acs.loc[geoid]
    m = more.loc[geoid] if geoid in more.index else None
    ba = sum(num(r.get(f"B15003_0{i}E")) or 0 for i in (22, 23, 24, 25))
    kids = None
    if m is not None:
        k = sum(num(m.get(f"B01001_00{i}E")) or 0 for i in (3, 4, 5, 6)) + sum(num(m.get(f"B01001_0{i}E")) or 0 for i in (27, 28, 29, 30))
        kids = ratio(k, m.get("B01001_001E"))
    return {"pop": num(r.get("B01003_001E")), "income": num(r.get("B19013_001E")), "home_value": num(r.get("B25077_001E")),
            "poverty": ratio(r.get("B17001_002E"), r.get("B17001_001E")), "unemployment": ratio(r.get("B23025_005E"), r.get("B23025_003E")),
            "bachelors": ratio(ba, r.get("B15003_001E")), "renter": ratio(r.get("B25003_003E"), r.get("B25003_001E")),
            "children": kids, "black": ratio(r.get("B03002_004E"), r.get("B03002_001E"))}


def agg_median(counts, lo, hi, method="pareto"):
    """Background1/_source/aggregate_median.py, verbatim in substance."""
    n = counts.sum(); half = n / 2; c = np.cumsum(counts); i = int(np.searchsorted(c, half))
    below = c[i] - counts[i]; L, U = lo[i], hi[i]
    r = lambda x: math.floor(x + 0.5)
    if not np.isfinite(U):
        if i == 0 or counts[i - 1] == 0:
            return L
        alpha = math.log((counts[i - 1] + counts[i]) / counts[i]) / math.log(L / lo[i - 1])
        return r(L * (counts[i] / half) ** (1 / alpha))
    A, B = n - below, n - c[i]
    if L == 0 or B == 0 or method == "linear":
        return r(L + (half - below) / counts[i] * (U - L))
    alpha = math.log(A / B) / math.log(U / L)
    return r(L * (A / half) ** (1 / alpha))


def profile_from(weights):
    """03_profile.py: weighted tract sums, aggregate medians, the same indicators."""
    t = acs.loc[[g for g in weights.index if g in acs.index]].drop(columns="year")
    row = t.mul(weights.loc[t.index], axis=0).sum(min_count=1)
    med = {}
    for table, name, how in (("B19001", "income", "pareto"), ("B25075", "home_value", "linear")):
        b = bins[(bins.year == ACS_YEAR) & (bins.table == table)]
        med[name] = agg_median(row[b.variable].values.astype(float), b.lo.values.astype(float), b.hi.values.astype(float), how)
    edu, race, occ = row["B15003_001E"], row["B03002_001E"], row["B25003_001E"]
    return {
        "Population": row["B01003_001E"], "Households": row["B11001_001E"],
        "Median household income": med["income"], "Median home value": med["home_value"],
        "High school diploma or higher": row[[f"B15003_{n:03d}E" for n in range(17, 26)]].sum() / edu,
        "Bachelor's degree or higher": row[[f"B15003_{n:03d}E" for n in range(22, 26)]].sum() / edu,
        "Poverty rate": row["B17001_002E"] / row["B17001_001E"], "Unemployment rate": row["B23025_005E"] / row["B23025_003E"],
        "Black": row["B03002_004E"] / race, "White": row["B03002_003E"] / race, "Hispanic or Latino": row["B03002_012E"] / race,
        "Asian": row["B03002_006E"] / race,
        "Owner-occupied": row["B25003_002E"] / occ, "Renter-occupied": row["B25003_003E"] / occ,
        "Average household size": row["B11002_001E"] / row["B11001_001E"],
    }


print("reading 2020 Census blocks …")
blocks = gpd.read_file(Path.home() / "Library/Caches/tigris/tl_2020_42_tabblock20.shp", bbox=(-75.30, 39.86, -74.95, 40.14), columns=["GEOID20", "POP20"])
blocks = blocks[blocks.GEOID20.str.startswith("42101")].to_crs(FT)
blocks["tract"] = blocks.GEOID20.str[:11]
blocks["a"] = blocks.geometry.area
tract_pop = blocks.groupby("tract").POP20.sum()


def residents_in(shape_ft):
    b = blocks[blocks.intersects(shape_ft)]
    return float((b.POP20 * b.geometry.intersection(shape_ft).area / b.a).sum())


def tract_shares(center_ft):
    """01_areas.R: share of each 2020 tract's residents inside the half mile (blocks split by area)."""
    ring = center_ft.buffer(HALF, 64)
    b = blocks[blocks.intersects(ring)].copy()
    b["pop_in"] = b.POP20 * b.geometry.intersection(ring).area / b.a
    s = b.groupby("tract").pop_in.sum()
    return (s / tract_pop.loc[s.index]).fillna(0)


PROFILE_KEYS = list(profile_from(pd.Series({studio_shares.GEOID.iloc[0]: 1.0})).keys())
CITY = {k: num(profile_csv.loc[k, "Philadelphia"]) for k in PROFILE_KEYS if k in profile_csv.index}
for slug, v in SCH.items():
    mine = tract_shares(v["center_ft"])
    contains = tracts20[tracts20.contains(v["center"])].GEOID.iloc[0]
    if slug in STUDIO_DONE:
        sh = studio_shares[studio_shares.school == STUDIO_DONE[slug]].set_index("GEOID")
        w = sh[(sh.share >= 0.01) | sh.study].share
        study = {g: round(float(sh.loc[g, "share"]), 3) for g in sh[sh.study].index}
        prof = {k: num(profile_csv.loc[k, STUDIO_DONE[slug]]) for k in PROFILE_KEYS if k in profile_csv.index}
        rebuilt = profile_from(mine[(mine >= 0.01) | mine.index.isin(study)])
        v["check_profile"] = {k: (prof.get(k), rebuilt.get(k)) for k in ("Population", "Median household income", "Poverty rate", "Median home value")}
        v["check_shares"] = max(abs(mine.get(g, 0) - sh.loc[g, "share"]) for g in sh.index)
        v["study_rule"] = "team"
    else:
        study = {g: round(float(s), 3) for g, s in mine.items() if s >= 0.2 or g == contains}
        w = mine[(mine >= 0.01) | mine.index.isin(study)]
        prof = profile_from(w)
        v["study_rule"] = "share"
    v["study"] = study
    v["profile"] = {k: {"school": (round(float(prof[k]), 4) if prof.get(k) is not None else None), "city": CITY.get(k)} for k in PROFILE_KEYS if k in CITY}
    v["contains_tract"] = contains

# ================================================================ catchments (SDP 2024) and neighborhoods
CATCH = ODP / "18 SDP Catchment Areas - ODP/raw/extracted/Catchments_ES_2024/Catchments_ES_2024/Catchments_ES_2024.shp"
es = read(CATCH).to_crs(FT)
GR = [c for c in es.columns if c.startswith("GR_ID_")]
GLAB = {c: ("K" if c.endswith("_K") else str(int(c[-2:]))) for c in GR}
azavea = read(P2 / "phl_neighborhoods_azavea_citywide.geojson").to_crs(4326)
studio_nbhd = read(M / "Neighborhood Boundary/Both_Neighborhood_Boundaries.shp").to_crs(4326)

for slug, v in SCH.items():
    ulcs = str(int(v["row"].sdp_ulcs))
    hit = es[es[GR].astype(str).eq(ulcs).any(axis=1)]
    if len(hit):
        grades = sorted({GLAB[c] for c in GR if (hit[c].astype(str) == ulcs).any()}, key=lambda g: -1 if g == "K" else int(g))
        sets = {tuple(GLAB[c] for c in GR if str(r[c]) == ulcs) for _, r in hit.iterrows()}
        geom = gpd.GeoSeries([unary_union(hit.geometry).buffer(0).simplify(15)], crs=FT).to_crs(4326).iloc[0]
        v["catchment"] = {"geometry": rnd(geom), "grades": f"{grades[0]}–{grades[-1]}", "varies": len(sets) > 1,
                          "sq_mi": round(unary_union(hit.geometry).area / MILE ** 2, 2)}
    else:
        v["catchment"] = None
    az = azavea[azavea.contains(v["center"])]
    v["area_name"] = clean(az.MAPNAME.iloc[0]) if len(az) else ""
    if slug in STUDIO_DONE:
        nb = studio_nbhd[studio_nbhd.Name == STUDIO_DONE[slug]]
        v["neighborhood"] = {"geometry": rnd(nb.geometry.iloc[0]), "source": "studio", "acres": num(nb.Acres.iloc[0], 1)}
    elif len(az):
        v["neighborhood"] = {"geometry": rnd(az.geometry.iloc[0].simplify(0.00003)), "source": "azavea", "name": v["area_name"]}
    else:
        v["neighborhood"] = None

# ================================================================ community assets
CITY_SVC = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
PPR = {"PPR_REC": "Recreation center", "PPR_PLAY": "Playground", "PPR_OAC": "Older adult center", "PPR_POOL": "Pool", "PPR_ENVIRON": "Environmental center",
       "PPR_ICE": "Ice rink", "PPR_GOLF": "Golf course", "PPR_HIST": "Historic site", "PPR_COMM": "Community center"}
PACDC = json.loads((CA / "_source/pacdc_cdc_members.json").read_text())
key = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)|\b(inc|the|corporation|corp|cdc|community development)\b", "", s.lower()))
is_cdc = lambda name: bool(re.search(r"\bCDC\b|community development|revitalization corp|development corp", name, re.I)) or any(key(name) and key(name) == key(p) for p in PACDC)
GEOCODED = CA / "_source/data/geocoded.json"


def city(name, slug, pt, meters, layer=0):
    f = CACHE / f"city_{name}_{slug}_{int(meters)}.geojson"
    if not f.exists():
        r = requests.get(f"{CITY_SVC}/{name}/FeatureServer/{layer}/query", timeout=120, headers=UA, params={
            "where": "1=1", "geometry": f"{pt.x},{pt.y}", "geometryType": "esriGeometryPoint", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "distance": meters, "units": "esriSRUnit_Meter", "outFields": "*", "outSR": 4326, "f": "geojson"})
        r.raise_for_status(); f.write_text(r.text)
    g = gpd.read_file(f)
    return g if len(g) else gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=4326)


def city_all(name, layer=0):
    f = CACHE / f"cityall_{name}_{layer}.geojson"
    if not f.exists():
        r = requests.get(f"{CITY_SVC}/{name}/FeatureServer/{layer}/query", timeout=120, headers=UA,
                         params={"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson", "resultRecordCount": 5000})
        r.raise_for_status(); f.write_text(r.text)
    return read(f)


def geocode(address):
    memo = json.loads(GEOCODED.read_text()) if GEOCODED.exists() else {}
    mine = CACHE / "geocoded.json"; own = json.loads(mine.read_text()) if mine.exists() else {}
    if address in memo:
        return memo[address]
    if address not in own:
        try:
            r = requests.get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress", timeout=60, headers=UA,
                             params={"address": address, "benchmark": "Public_AR_Current", "format": "json"}).json()
            m = r["result"]["addressMatches"]; own[address] = [m[0]["coordinates"]["x"], m[0]["coordinates"]["y"]] if m else None
        except Exception:
            own[address] = None
        mine.write_text(json.dumps(own, indent=1))
    return own[address]


def child_care(slug, pt):
    def fetch():
        r = requests.get("https://data.pa.gov/resource/ajn5-kaxt.json", timeout=120, headers=UA,
                         params={"$where": f"within_circle(geocoded_column, {pt.y}, {pt.x}, 1700)", "$limit": 5000})
        r.raise_for_status(); return r.json()
    out = []
    for a in cached_json(f"child_care_{slug}.json", fetch):
        if not a.get("geocoded_column") or a.get("provider_type") == "Other" or a.get("capacity") == "School Age Provider":
            continue
        if re.search(SELF[slug], a.get("facility_name", "").upper()):
            continue
        x, y = a["geocoded_column"]["coordinates"]
        out.append({"category": "Child care", "kind": clean(a["provider_type"]).capitalize(), "name": title(a["facility_name"]), "address": title(a.get("facility_address")),
                    "source": "PA Department of Human Services child care providers", "geometry": Point(x, y)})
    return out


def worship(slug, pt):
    def fetch():
        import time
        q = f'[out:json][timeout:90];nwr["amenity"="place_of_worship"](around:1700,{pt.y},{pt.x});out center tags;'
        last = None
        for attempt in range(6):                     # Overpass is busy at times: back off, then try a mirror
            url = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")[attempt % 2]
            try:
                r = requests.post(url, data={"data": q}, timeout=180, headers=UA)
                r.raise_for_status(); return r.json()["elements"]
            except Exception as e:
                last = e; time.sleep(10 * (attempt + 1))
        raise last
    out = []
    for e in cached_json(f"worship_{slug}.json", fetch):
        t = e.get("tags", {}); lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None:
            continue
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        rel = t.get("religion", "").replace("_", " ")
        out.append({"category": "Places of worship", "kind": "Place of worship", "name": t.get("name") or "Place of worship", "address": addr,
                    "detail": rel.capitalize() if rel and rel != "christian" else "", "source": "OpenStreetMap", "geometry": Point(lon, lat)})
    return out


def rows(g, cat, kind, name, address="", detail="", phone="", web="", source="City of Philadelphia"):
    def val(r, a):
        if callable(a):
            return clean(a(r))
        v = col(r, a) if isinstance(a, str) and a else None
        return clean(v) if v is not None else (a if isinstance(a, str) and a and a.lower() not in {c.lower() for c in r.index} else "")
    out = []
    for _, r in g.iterrows():
        if r.geometry is None:
            continue
        out.append({"category": cat, "kind": val(r, kind), "name": title(val(r, name)), "address": title(val(r, address)), "detail": val(r, detail),
                    "phone": val(r, phone), "website": val(r, web), "source": source,
                    "geometry": r.geometry if r.geometry.geom_type == "Point" else r.geometry.representative_point()})
    return out


def rebuild_assets(slug, pt):
    """Community Asset/_source/01_assets.py for one school."""
    R = []
    g = city("Schools", slug, pt, 1609.344)
    g = g[~g.apply(lambda r: bool(re.search(SELF[slug], clean(col(r, "school_name")).upper())), axis=1)] if len(g) else g
    tmap = {"DISTRICT": "District school", "CHARTER": "Charter school", "PRIVATE": "Private school", "ARCHDIOCESE": "Archdiocese school", "CONTRACTED": "Contracted school"}
    R += rows(g, "Schools", lambda r: tmap.get(clean(col(r, "type_specific")).upper(), title(col(r, "type_specific")) + " school"), "school_name_label", "street_address",
              lambda r: f"Grades {clean(col(r, 'grade_org'))}" + (f" · {int(num(col(r, 'enrollment'))):,} students" if num(col(r, "enrollment")) else ""), "phone_number")
    R += rows(city("Free_Library_Locations", slug, pt, 1609.344), "Libraries", "Free Library branch", lambda r: clean(col(r, "Branch")) + " Library", "Street_Address", source="Free Library of Philadelphia")
    g = city("PPR_Program_Sites", slug, pt, 1609.344)
    if len(g):
        R += rows(g[g.program_type != "PPR_OAC"], "Parks and recreation", lambda r: PPR.get(r.program_type, "Recreation site"), "park_name", source="Philadelphia Parks & Recreation")
        R += rows(g[g.program_type == "PPR_OAC"], "Older adult centers", "Older adult center", "park_name", source="Philadelphia Parks & Recreation")
    R += rows(city("PCA_SeniorCenters", slug, pt, 1609.344), "Older adult centers", "Senior center", "Name", "Address", phone="Phone_Number", source="Philadelphia Corporation for Aging")
    R += rows(city("Health_Centers", slug, pt, 1609.344), "Health care", lambda r: "City health center" if clean(col(r, "organization")) == "PDPH" else "Community health center",
              "name", "full_address", "organization", "phone", "website")
    R += rows(city("Hospitals", slug, pt, 1609.344), "Health care", lambda r: "Hospital" + (f" ({clean(col(r, 'hospital_type')).lower()})" if clean(col(r, "hospital_type")) else ""),
              "hospital_name", "street_address", phone="phone_number")
    R += rows(city("Fire_Dept_Facilities", slug, pt, 1609.344), "Fire and police", "Fire station",
              lambda r: " / ".join(x for x in (f"Engine {int(num(col(r, 'eng')))}" if num(col(r, "eng")) else "", f"Ladder {int(num(col(r, 'lad')))}" if num(col(r, "lad")) else "") if x) or "Fire station",
              "location", source="Philadelphia Fire Department")
    R += rows(city("Police_Stations", slug, pt, 1609.344), "Fire and police", "Police station",
              lambda r: f"{int(num(col(r, 'dist_num')))}th Police District" if num(col(r, "dist_num")) else "Police station", "location", source="Philadelphia Police Department")
    g = city("free_meal_sites", slug, pt, 1609.344)
    g = g[g.status.fillna("").str.lower().eq("active")] if len(g) and "status" in g else g
    R += rows(g, "Food access", "Food pantry or free meal site", "site_name", "address", lambda r: title(col(r, "category")), "phone_number", "website")
    R += rows(city("Farmers_Markets", slug, pt, 1609.344), "Food access", "Farmers market", "name", "address", "operator", "contact_phone", "contact_website")
    R += rows(city("Registered_Community_Gardens", slug, pt, 1609.344), "Food access", "Community garden", "garden_name", "address", web="contact_website", source="Philadelphia Parks & Recreation")
    R += rows(city("PPR_Urban_Agriculture_Projects", slug, pt, 1609.344), "Food access", "Urban agriculture project", "project_name", "address", "park_name", web="contact_website", source="Philadelphia Parks & Recreation")
    R += rows(city("PPR_Friends_Groups", slug, pt, 1609.344), "Community organizations", "Park friends group", "friends_group_name", "address", "public_name", web="contact_website", source="Philadelphia Parks & Recreation")
    R += rows(city("NAC_Offices", slug, pt, 2 * 1609.344), "Community organizations", lambda r: "Neighborhood Advisory Committee" + (" · CDC" if is_cdc(clean(col(r, "organization"))) else ""),
              "organization", "street_address", phone="phone_number", web="website_url")
    for r in RCO_CDC:
        xy = geocode(r["address"])
        if xy:
            R.append({**r, "geometry": Point(xy)})
    R += child_care(slug, pt)
    R += worship(slug, pt)
    a = gpd.GeoDataFrame(R, geometry="geometry", crs=4326)
    a["miles"] = (a.to_crs(FT).distance(gpd.GeoSeries([pt], crs=4326).to_crs(FT).iloc[0]) / MILE).round(2)
    a = a[(a.miles <= 1) | ((a.category == "Community organizations") & (a.miles <= 2))]
    a = a.sort_values(["category", "miles"]).drop_duplicates(["category", "name", "address"])
    org = a.category == "Community organizations"
    a = pd.concat([a[org].assign(k=a[org].name.map(key)).drop_duplicates("k").drop(columns="k"), a[~org]]).sort_values(["category", "miles"]).reset_index(drop=True)
    a["within_half_mile"] = a.miles <= 0.5
    return a.fillna("")


rco_city = read(P2 / "phl_rco_registered_community_orgs_citywide.geojson").rename(columns=str.lower)
one_line = lambda v: re.sub(r"\s*,(\s*,)+\s*", ", ", re.sub(r"\s*[\r\n]+\s*", ", ", str(v or ""))).strip(", ").strip()
RCO_CDC = []
for _, r in rco_city.assign(name=lambda d: d.organization_name.map(clean)).drop_duplicates("name").iterrows():
    if is_cdc(r["name"]):
        RCO_CDC.append({"category": "Community organizations", "kind": "Registered community organization · CDC", "name": r["name"], "address": one_line(r.organization_address),
                        "detail": "", "phone": "", "website": clean(r.websites), "source": "City of Philadelphia, RCO registry; address placed by the Census geocoder"})

studio_assets = {s: pd.read_csv(CA / f"Raw_Source/{n}_Community_Assets.csv") for s, n in STUDIO_DONE.items()}
walk_inv = read(TR / "amenities.geojson")


def studio_asset_rows(slug):
    a = studio_assets[slug].copy()
    inv = walk_inv[walk_inv.school == STUDIO_DONE[slug]]
    src = {(clean(r["name"]), clean(r["address"])): clean(r["source"]) for _, r in inv.iterrows()}
    a["source"] = [clean(s) if clean(s) and not clean(s).startswith("<function") else (src.get((clean(n), clean(ad))) or "15-minute walk inventory (Transportation)")
                   for s, n, ad in zip(a.source, a["name"], a.address)]
    return gpd.GeoDataFrame(a, geometry=gpd.points_from_xy(a.longitude, a.latitude), crs=4326).fillna("")


def asset_fc(a):
    return fc(a, lambda r: {"category": clean(r.category), "kind": clean(r.kind), "name": clean(r["name"]), "address": clean(r.address),
                            "detail": clean(r.detail), "phone": re.sub(r"\.0$", "", clean(r.phone)), "website": clean(r.website),
                            "source": clean(r.source), "miles": num(r.miles, 2)})


# ================================================================ walk areas (rebuilt for the four)
M_PER_MIN, BANDS = 80, [5, 10, 15]
REACH, EDGE, CLOSE, HOLE = 1200, 25, 110, 60000
studio_walk = read(TR / "walk_areas.geojson")


def walk_areas(slug, pt):
    import networkx as nx
    import osmnx as ox
    ox.settings.cache_folder = str(CACHE / "osmnx"); ox.settings.use_cache = True; ox.settings.log_console = False
    G = ox.graph_from_point((pt.y, pt.x), dist=1700, network_type="walk", simplify=True)
    Gu = ox.convert.to_undirected(G)
    nodes = ox.graph_to_gdfs(Gu, edges=False).to_crs(UTM)
    p = gpd.GeoSeries([pt], crs=4326).to_crs(UTM).iloc[0]
    start = nodes.geometry.distance(p).idxmin()
    dist = nx.single_source_dijkstra_path_length(Gu, start, cutoff=REACH, weight="length")
    edges = ox.graph_to_gdfs(Gu, nodes=False).reset_index().to_crs(UTM)
    xy = nodes.geometry
    lines = {b: [] for b in BANDS}
    for u, v, L, geom in zip(edges["u"], edges["v"], edges["length"], edges.geometry):
        du, dv = dist.get(u, math.inf), dist.get(v, math.inf)
        if min(du, dv) >= REACH or L <= 0:
            continue
        if Point(geom.coords[0]).distance(xy[u]) > Point(geom.coords[-1]).distance(xy[u]):
            geom = geom.reverse()
        for b in BANDS:
            R = b * M_PER_MIN
            a = min(L, max(0.0, R - du)) if math.isfinite(du) else 0.0
            c = min(L, max(0.0, R - dv)) if math.isfinite(dv) else 0.0
            if a + c >= L:
                lines[b].append(geom)
            else:
                if a > 0.5:
                    lines[b].append(substring(geom, 0, a / L, normalized=True))
                if c > 0.5:
                    lines[b].append(substring(geom, 1 - c / L, 1, normalized=True))
    out, rows_ = [], []
    for b in BANDS:
        shape = unary_union(lines[b]).buffer(CLOSE).buffer(EDGE - CLOSE)
        parts = [Polygon(q.exterior, [h for h in q.interiors if Polygon(h).area > HOLE]) for q in (shape.geoms if shape.geom_type == "MultiPolygon" else [shape])]
        shape = max(parts, key=lambda q: q.area).simplify(1.5)
        ft = gpd.GeoSeries([shape], crs=UTM).to_crs(FT).iloc[0]
        circle = math.pi * (b * M_PER_MIN) ** 2
        rows_.append({"minutes": b, "meters": b * M_PER_MIN, "area_sq_mi": round(shape.area / 2589988.11, 2),
                      "share_of_straight_line_circle": round(shape.area / circle, 3), "residents_2020": int(round(residents_in(ft), -1))})
        out.append({"minutes": b, "geometry": gpd.GeoSeries([shape], crs=UTM).to_crs(4326).iloc[0]})
    return gpd.GeoDataFrame(out, crs=4326).sort_values("minutes", ascending=False), rows_


walk_summary = pd.read_csv(M / "Transportation1/15-Minute Walk/Raw_Source/Walk_Area_Summary.csv")

# ================================================================ per-school outputs
summary = []
checks = []
for slug in ORDER:
    v = SCH[slug]; pt = v["center"]; s = v["row"]; short = SHORT[slug]; log = []
    # assets
    if slug in STUDIO_DONE:
        a = studio_asset_rows(slug)
        try:
            rb = rebuild_assets(slug, pt)
            checks.append((short, a.groupby("category").size().to_dict(), rb.groupby("category").size().to_dict()))
        except Exception as e:
            checks.append((short, {}, {"error": str(e)[:80]}))
    else:
        a = rebuild_assets(slug, pt)
    log.append(save(f"{slug}/assets.json", asset_fc(a)))
    counts = {c: {"half": int((d.miles <= 0.5).sum()), "mile": int((d.miles <= 1).sum())} for c, d in a.groupby("category")}

    # RCOs (contact names, emails and phones of private people are left out)
    if slug in STUDIO_DONE:
        rco = read(CA / f"_source/data/Zoning_RCO_{slug}.geojson").rename(columns=str.lower).to_crs(4326)
    else:
        rco = rco_city.to_crs(FT)
        rco = rco[rco.intersects(v["center_ft"].buffer(HALF))].to_crs(4326)
    rco_ft = rco.to_crs(FT)
    rco["covers"] = rco_ft.buffer(0).contains(v["center_ft"]).values
    rprops = lambda r: {"name": clean(r.organization_name), "type": clean(r.org_type), "covers": bool(r.covers), "cdc": is_cdc(clean(r.organization_name)),
                        "meets": one_line(r.meeting_location_address), "website": clean(r.websites), "expires": clean(r.expirationyear).replace(".0", "")}
    log.append(save(f"{slug}/rco.json", fc(rco.sort_values("covers"), rprops, simplify_ft=4)))
    rco_list = sorted([rprops(r) for _, r in rco.iterrows()], key=lambda d: (not d["covers"], d["name"]))

    # walk areas
    if slug in STUDIO_DONE:
        wk = studio_walk[studio_walk.school == STUDIO_DONE[slug]].sort_values("minutes", ascending=False)
        wrows = [{k: num(x) for k, x in r.items() if k != "school"} for _, r in walk_summary[walk_summary.school == STUDIO_DONE[slug]].iterrows()]
    else:
        try:
            wk, wrows = walk_areas(slug, pt)
        except Exception as e:
            print(f"  walk areas for {short} failed: {e}")
            wk, wrows = gpd.GeoDataFrame({"minutes": [], "geometry": []}, crs=4326), []
    log.append(save(f"{slug}/walk.json", fc(wk, lambda r: {"minutes": int(r.minutes)})))

    summary.append({
        "slug": slug, "short": short, "name": clean(s.school), "address": clean(s.address), "zip": str(int(s.zip)) if num(s.zip) else "",
        "grades": clean(s.grades), "ulcs": str(int(s.sdp_ulcs)), "network": num(s.sdp_network), "council_district": num(s.council_district),
        "fmp": {"building": [clean(s.bldg_score), clean(s.bldg_rating)], "program": [clean(s.program_score), clean(s.program_rating)],
                "utilization": [clean(s.utilization_score), clean(s.utilization_rating)], "vulnerability": [clean(s.vulnerability_score), clean(s.vulnerability_rating)]},
        "dashboard": clean(s.fmp_dashboard_url), "color": COLOR[slug], "center": [round(pt.y, 6), round(pt.x, 6)],
        "area_name": v["area_name"], "studio": slug in STUDIO_DONE, "study_rule": v["study_rule"],
        "study_tracts": v["study"], "profile": v["profile"], "asset_counts": counts, "rcos": rco_list, "walk": wrows,
        "catchment": None if not v["catchment"] else {k: x for k, x in v["catchment"].items() if k != "geometry"},
        "neighborhood": None if not v["neighborhood"] else {k: x for k, x in v["neighborhood"].items() if k != "geometry"},
    })
    print(f"{short}: " + " · ".join(log))

# geometry the map always needs, for all six in one file
sites_fc = {"type": "FeatureCollection", "features": []}
for slug in ORDER:
    v = SCH[slug]
    sites_fc["features"].append({"type": "Feature", "properties": {"slug": slug, "kind": "parcel"}, "geometry": rnd(v["parcel"], 6)})
    if v["catchment"]:
        sites_fc["features"].append({"type": "Feature", "properties": {"slug": slug, "kind": "catchment", "grades": v["catchment"]["grades"]}, "geometry": v["catchment"]["geometry"]})
    if v["neighborhood"]:
        sites_fc["features"].append({"type": "Feature", "properties": {"slug": slug, "kind": "neighborhood", "source": v["neighborhood"]["source"]}, "geometry": v["neighborhood"]["geometry"]})
print(save("sites.json", sites_fc))

# ================================================================ context layers (around all six)
log = []
tr = tracts20.copy()
log.append(save("ctx/tracts.json", fc(tr, lambda r: {"geoid": r.GEOID, "name": clean(r.NAME), **tract_measures(r.GEOID)}, simplify_ft=10)))

pk = read(P2 / "phl_ppr_properties_citywide.geojson")
pk = pk[~pk.get("property_classification", pd.Series("", index=pk.index)).isin(["TRAFFIC_ISLAND_MEDIAN", "PATHWAY", "OPERATIONAL_INTERNAL"])]
pk["geometry"] = pk.geometry.make_valid()
log.append(save("ctx/parks.json", fc(in_region(pk), lambda r: {"name": title(col(r, "label", "public_name", "park_name")), "acres": num(col(r, "acreage"), 1)}, simplify_ft=3)))

cc = read(P2 / "phl_commercial_corridors_citywide.geojson") if (P2 / "phl_commercial_corridors_citywide.geojson").exists() else read(next(DS.rglob("phl_commercial_corridors_citywide.geojson")))
log.append(save("ctx/corridors.json", fc(in_region(cc), lambda r: {"name": clean(r["name"]), "type": clean(r.corridor_type), "storefronts": num(r.comm_count),
                                                                  "vacant": num(r.vac_count), "vac_rate": clean(r.vac_rate), "stage": clean(r.stage), "year": num(r.survey_year)}, simplify_ft=2)))
bid = read(next(DS.rglob("business_improvement_districts.geojson")))
log.append(save("ctx/bids.json", fc(in_region(bid), lambda r: {"name": title(r.organization), "phone": clean(r.phone), "website": clean(r.website)}, simplify_ft=3)))

# transit: SEPTA routes (bus, trolley, metro) and Regional Rail lines
routes = read(next(DS.rglob("septa_transit_routes_spring2025.geojson")))
METRO = {"B1", "B2", "B3", "L1", "M1", "MFL", "BSL", "BSO", "MFO", "NHSL"}
TROLLEY = {"T1", "T2", "T3", "T4", "T5", "G1", "D1", "D2", "10", "11", "13", "15", "34", "36", "101", "102"}
mode = lambda a: "Metro" if a in METRO else "Trolley" if a in TROLLEY else "Bus"
routes["mode"] = routes.LineAbbr.astype(str).map(mode)
rr = read(next(DS.rglob("septa_regional_rail_lines.geojson")))
rr = rr.assign(LineAbbr=rr.Route_Name, LineName=rr.Route_Name + " Line", mode="Regional Rail")
lines = pd.concat([routes[["LineAbbr", "LineName", "mode", "geometry"]], rr[["LineAbbr", "LineName", "mode", "geometry"]]])
lines = gpd.GeoDataFrame(lines, crs=4326)
log.append(save("ctx/transit_lines.json", fc(in_region(lines, clip=True), lambda r: {"route": clean(r.LineAbbr), "name": clean(r.LineName), "mode": r["mode"]}, simplify_ft=10)))
print("  route modes:", lines.groupby("mode").LineAbbr.apply(lambda s: ", ".join(sorted(set(map(str, s)))[:30])).to_dict())

stops = read(next(DS.rglob("septa_bus_stop_ridership_fall2025.geojson"))).to_crs(FT)
stops = stops[stops.within(unary_union([v["center_ft"].buffer(0.75 * MILE) for v in SCH.values()]))]
for c in ("WK_Ons", "WK_Offs"):
    stops[c] = pd.to_numeric(stops[c], errors="coerce").fillna(0)
st = stops.groupby("Stop_Code").agg(name=("Stop", "first"), mode=("Mode", "first"), routes=("Route", lambda x: ", ".join(sorted(set(map(str, x)), key=lambda z: (len(z), z)))),
                                     ons=("WK_Ons", "sum"), offs=("WK_Offs", "sum"), geometry=("geometry", "first")).reset_index()
st = gpd.GeoDataFrame(st, geometry="geometry", crs=FT)
log.append(save("ctx/transit_stops.json", fc(st, lambda r: {"name": clean(r["name"]), "mode": clean(r["mode"]), "routes": r.routes, "ons": int(r.ons), "offs": int(r.offs)})))
stations = []
for f, m_ in (("septa_metro_stations.geojson", "Metro"), ("septa_regional_rail_stations.geojson", "Regional Rail")):
    p = next(DS.rglob(f), None)
    if p:
        g = read(p)
        stations.append(gpd.GeoDataFrame({"name": [title(col(r, "Station_Name", "station_name", "Station", "STATION", "name", "Name", "stop_name")) for _, r in g.iterrows()],
                                          "line": [clean(col(r, "Line_Name", "line", "Line", "Route", "route_name")) for _, r in g.iterrows()], "mode": m_}, geometry=g.geometry, crs=g.crs))
if stations:
    sa = gpd.GeoDataFrame(pd.concat(stations), crs=4326)
    log.append(save("ctx/rail_stations.json", fc(in_region(sa), lambda r: {"name": r["name"], "line": r.line, "mode": r["mode"]})))

bike = read(next(DS.rglob("phl_bike_network_citywide.geojson")))
log.append(save("ctx/bike_lanes.json", fc(in_region(bike, clip=True), lambda r: {"kind": clean(r.bikewaytyp) or clean(r.facityp)}, simplify_ft=3)))
indego = next(DS.rglob("indego_stations_phila_api.geojson"), None)
if indego:
    ig = read(indego)
    log.append(save("ctx/bike_share.json", fc(in_region(ig), lambda r: {"name": clean(col(r, "name", "addressStreet")), "docks": num(col(r, "totalDocks", "docks", "capacity"))})))
hin = read(next(DS.rglob("vision_zero_high_injury_network_2025.geojson")))
log.append(save("ctx/hin.json", fc(in_region(hin, clip=True), lambda r: {"street": title(r.stname)}, simplify_ft=3)))

# crashes: the studio's per-school PennDOT extracts (2020–2024), within a mile of any school
cr = []
for slug in ORDER:
    g = read(P4 / f"{slug}_penndot_crashes_2020_2024_1mi_box.geojson") if (P4 / f"{slug}_penndot_crashes_2020_2024_1mi_box.geojson").exists() else read(next(DS.rglob(f"{slug}_penndot_crashes_2020_2024_1mi_box.geojson")))
    cr.append(g)
cr = gpd.GeoDataFrame(pd.concat(cr), crs=4326).drop_duplicates("crn")
cr = in_region(cr, NEAR1)
n = lambda r, *c: sum(num(r.get(x)) or 0 for x in c if x in r.index)
log.append(save("ctx/crashes.json", fc(cr, lambda r: {"year": num(r.crash_year), "killed": int(n(r, "fatal_count")), "serious": int(n(r, "susp_serious_inj_count", "maj_inj_count")),
                                                       "ksi": bool(n(r, "fatal_count", "susp_serious_inj_count", "maj_inj_count")),
                                                       "ped": bool(n(r, "ped_count")), "bike": bool(n(r, "bicycle_count"))})))
try:
    gd = city_all("School_Crossing_Guards", 0)
    log.append(save("ctx/crossing_guards.json", fc(in_region(gd), lambda r: {"name": title(col(r, "address", "location", "intersection"))})))
    cams = pd.concat([city_all("ASE_October_2025_WFL1", 1).assign(kind="School-zone speed camera"), city_all("ASE_October_2025_WFL1", 2).assign(kind="Speed-camera corridor")])
    cams = gpd.GeoDataFrame(cams, crs=4326)
    log.append(save("ctx/speed_cameras.json", fc(in_region(cams), lambda r: {"kind": r.kind, "status": clean(col(r, "Status", "status")), "school": title(col(r, "SCHOOL_NAM"))})))
except Exception as e:
    print("  crossing guards / speed cameras:", e)

# economy & land: the studio's per-school extracts, joined
def per_school(stem):
    gs = []
    for slug in ORDER:
        p = next(DS.rglob(f"{slug}_{stem}.geojson"), None)
        if p:
            gs.append(read(p))
    return gpd.GeoDataFrame(pd.concat(gs), crs=4326)

KIND = {"Restaurants and take-out": ["Food Preparing and Serving", "Food Preparing and Serving (30+ SEATS)", "Food Caterer", "Sidewalk Cafe"],
        "Food stores": ["Food Establishment, Retail Permanent Location", "Food Establishment, Retail Perm Location (Large)", "Food Estab, Retail Non-Permanent Location (Annual)", "Food Manufacturer / Wholesaler"],
        "Auto repair, sales and towing": ["Motor Vehicle Repair / Fuel Dispensing", "Tire Dealer", "Vendor - Motor Vehicle Sales", "Tow Truck", "Tow Company", "Auto Wrecking / Waste Handling", "Public Garage / Parking Lot"],
        "Child care": ["Child Care Facility"]}
NOT_A_BUSINESS = ["Rental", "Dumpster License - Private Property", "Dumpster License - Public ROW", "Vacant Residential Property / Lot", "Vacant Commercial Property", "High Rise",
                  "Hazardous Materials", "Handbill Distribution", "Annual Small Games Of Chance", "Special Assembly Occupancy"]
bz = per_school("li_business_licenses_active_1mi").drop_duplicates("licensenum")
bz = bz[~bz.licensetype.isin(NOT_A_BUSINESS) & bz.geometry.notna()]
bz = bz.drop_duplicates(["business_name", "address"])
log.append(save("ctx/businesses.json", fc(in_region(bz, NEAR1), lambda r: {"name": title(r.business_name), "kind": next((k for k, v in KIND.items() if r.licensetype in v), "Other businesses"),
                                                                           "license": clean(r.licensetype), "address": title(r.address)})))
zn = per_school("zoning_basedistricts_1mi").drop_duplicates("objectid")
log.append(save("ctx/zoning.json", fc(zn, lambda r: {"code": clean(r.long_code), "group": clean(r.zoninggroup)}, simplify_ft=3)))
LU = {1: "Residential", 2: "Commercial", 3: "Industrial", 4: "Civic and institutional", 5: "Transportation", 6: "Culture and recreation", 7: "Parks and open space", 8: "Water", 9: "Vacant"}
lu = per_school("landuse_1mi").drop_duplicates("objectid")
lu = lu[lu.geometry.notna()].to_crs(FT)
lu["geometry"] = lu.geometry.buffer(0)
lu["use"] = pd.to_numeric(lu.c_dig1, errors="coerce").map(LU)
lu = lu.dissolve(by="use").reset_index()
log.append(save("ctx/land_use.json", fc(lu, lambda r: {"use": r.use}, simplify_ft=6)))

oz = read(next(DS.rglob("phl_opportunity_zones_citywide.geojson")))
oz = oz.assign(layer="Opportunity Zone", name=oz.iloc[:, oz.columns.get_loc("Population_2016_Tract_GIS_PLA_4")].astype(str) if "Population_2016_Tract_GIS_PLA_4" in oz else "")
ra = read(next(DS.rglob("phl_redevelopment_certified_areas_citywide.geojson")))
ra = ra.assign(layer="Redevelopment area", name=ra["name"].map(title))
inc = gpd.GeoDataFrame(pd.concat([oz[["layer", "name", "geometry"]], ra[["layer", "name", "geometry"]]]), crs=4326)
log.append(save("ctx/incentives.json", fc(in_region(inc), lambda r: {"layer": r.layer, "name": clean(r["name"])}, simplify_ft=8)))
ah = read(next(DS.rglob("affordable_housing_production_dpd.geojson")))
log.append(save("ctx/affordable_housing.json", fc(in_region(ah), lambda r: {"name": clean(r.project_name), "units": num(r.total_units), "year": num(r.fiscal_year_complete),
                                                                         "status": clean(r.status), "type": clean(r.project_type)})))
sg = read(next(DS.rglob("commerce_storefront_improvement_grants.geojson")))
log.append(save("ctx/storefront_grants.json", fc(in_region(sg), lambda r: {"name": clean(r.user_business_name), "year": num(r.fiscal_year), "amount": num(r.user_grant_amount, 0)})))
fr = read(ODP / "07 Community Assets - ODP/raw/phl_neighborhood_food_retail.geojson")
fr = fr[fr.HPSS_ACCESS.fillna("").isin(["Low Access", "No Access"])]
log.append(save("ctx/food_access.json", fc(in_region(fr), lambda r: {"access": clean(r.HPSS_ACCESS), "supermarket": clean(r.SUPERMARKET_ACCESS),
                                                                  "hpss": num(r.TOTAL_HPSS), "lpss": num(r.TOTAL_LPSS)}, simplify_ft=4)))
print("context: " + " · ".join(log))

(OUT / "schools.json").write_text(json.dumps({"built": pd.Timestamp.now().strftime("%Y-%m-%d"), "acs_year": ACS_YEAR, "schools": summary}, separators=(",", ":")))
print("wrote", OUT / "schools.json")

# ================================================================ checks against the studio's own numbers
print("\nCHECK: rebuilt methods vs the studio, for the two finalists")
for slug, name in STUDIO_DONE.items():
    v = SCH[slug]
    print(f"  {name}: largest tract-share difference {v['check_shares']:.3f}")
    for k, (studio_v, mine_v) in v["check_profile"].items():
        print(f"    {k:<26} studio {studio_v:>12,.3f}   rebuilt {mine_v:>12,.3f}")
for short, studio_c, rebuilt_c in checks:
    cats = sorted(set(studio_c) | set(rebuilt_c))
    print(f"  {short} assets  " + " · ".join(f"{c.split()[0]} {studio_c.get(c, 0)}/{rebuilt_c.get(c, 0)}" for c in cats) + "   (studio/rebuilt)")
