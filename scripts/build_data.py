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
            polys = [x for x in geom.geoms if x.geom_type in ("Polygon", "MultiPolygon")]
            lines_ = [x for x in geom.geoms if x.geom_type in ("LineString", "MultiLineString")]
            geom = unary_union(polys) if polys else unary_union(lines_) if lines_ else None
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
    # "Who lives nearby": the study census tracts taken whole, as one group (the studio's Study_Census_Tracts list)
    grp = profile_from(pd.Series(1.0, index=list(study)))
    v["tract_profile"] = {k: {"group": (round(float(grp[k]), 4) if grp.get(k) is not None else None), "city": CITY.get(k)} for k in PROFILE_KEYS if k in CITY}
    v["tracts"] = [{"geoid": g, "name": (str(int(g[5:9])) + ("" if g[9:] == "00" else "." + g[9:])),
                    "pop": num(acs.loc[g, "B01003_001E"]) if g in acs.index else None, "site": g == contains}
                   for g in sorted(study, key=lambda g: -study[g])]

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

# ================================================================ community assets: the five domain inventories
# scripts/fetch/<domain>.py write scripts/fetch/out/<domain>/*.geojson + manifest.json (see scripts/fetch/CONTRACT.md).
PACDC = json.loads((CA / "_source/pacdc_cdc_members.json").read_text())
key = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)|\b(inc|the|corporation|corp|cdc|community development)\b", "", s.lower()))
is_cdc = lambda name: bool(re.search(r"\bCDC\b|community development|revitalization corp|development corp", name, re.I)) or any(key(name) and key(name) == key(p) for p in PACDC)
one_line = lambda v: re.sub(r"\s*,(\s*,)+\s*", ", ", re.sub(r"\s*[\r\n]+\s*", ", ", str(v or ""))).strip(", ").strip()
rco_city = read(P2 / "phl_rco_registered_community_orgs_citywide.geojson").rename(columns=str.lower)

FETCH = Path(__file__).resolve().parent / "fetch/out"
CATS = ["schools", "early_childhood", "libraries", "youth", "higher_ed", "health_care", "pharmacies", "older_adults", "social_services",
        "food", "gardens_farms", "parks_rec", "arts_culture", "historic", "civic_safety", "community_orgs", "economic", "worship"]
MANIFEST, CONTEXT_SRC, parts = [], {}, []
for mf in sorted(FETCH.glob("*/manifest.json")):
    for m in json.loads(mf.read_text()):
        m["domain"] = mf.parent.name
        f = mf.parent / f"{m['id']}.geojson"
        if not f.exists():
            print(f"  manifest lists {m['id']} but {f.name} is missing"); continue
        if m.get("context"):
            CONTEXT_SRC[m["id"]] = (m, f); continue
        g = read(f).to_crs(4326)
        g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
        if not len(g):
            MANIFEST.append(m); continue
        g["geometry"] = [x if x.geom_type == "Point" else x.representative_point() for x in g.geometry]
        for c in ("category", "kind", "name", "address", "phone", "website", "detail"):
            g[c] = g[c].map(clean) if c in g else ""
        g["source_id"] = m["id"]
        g["rank"] = 1 if "openstreetmap" in (m.get("publisher", "") + m.get("title", "")).lower() else 0   # official sources win over OSM
        bad = ~g.category.isin(CATS)
        if bad.any():
            print(f"  {m['id']}: {int(bad.sum())} rows with unknown category {sorted(set(g.category[bad]))[:4]} dropped")
        parts.append(g[~bad][["category", "kind", "name", "address", "phone", "website", "detail", "source_id", "rank", "geometry"]])
        MANIFEST.append(m)
INV = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326) if parts else gpd.GeoDataFrame(columns=["category", "geometry"], crs=4326)
INV_FT = INV.to_crs(FT)
print(f"inventory: {len(INV):,} records from {len(MANIFEST)} datasets ({len(CONTEXT_SRC)} context datasets)")

STOP = {"the", "of", "inc", "llc", "and", "at", "a", "philadelphia", "phila", "center", "centre", "school", "church", "co"}
def toks(n):
    return {t for t in re.findall(r"[a-z0-9]+", n.lower().replace("&", " and ")) if t not in STOP}


def inventory_for(v):
    """Every inventory record within 1.5 miles (community organizations 2) of a school, de-duplicated across
    sources: the same kind of place with the same or a similar name within 150 m (or any name within 25 m when
    one source left it unnamed) is one place; the official source's record is kept."""
    d = INV_FT.geometry.distance(v["center_ft"]) / MILE
    keep = (d <= 1.5) | ((INV.category == "community_orgs") & (d <= 2))
    a = INV[keep].copy(); a["miles"] = d[keep].round(3).values
    a_ft = a.to_crs(FT)
    a["x"], a["y"] = a_ft.geometry.x.values, a_ft.geometry.y.values
    a = a.sort_values(["rank", "miles"])
    out = []
    for cat, g in a.groupby("category", sort=False):
        kept = []
        for r in g.itertuples():
            t = toks(r.name)
            dup = False
            for k in kept:
                dist = math.hypot(r.x - k[0], r.y - k[1])
                if dist > 500:
                    continue
                kt = k[2]
                same = t and kt and (t == kt or len(t & kt) / max(1, min(len(t), len(kt))) >= 0.67)
                if (same and dist <= 500) or (dist <= 80 and (not t or not kt)):
                    dup = True; break
            if not dup:
                kept.append((r.x, r.y, t)); out.append(r.Index)
    return a.loc[out].drop(columns=["x", "y", "rank"]).sort_values(["category", "miles"])


BROKEN = set(json.loads((Path(__file__).resolve().parent / "broken_links.json").read_text())) if (Path(__file__).resolve().parent / "broken_links.json").exists() else set()
web = lambda u: "" if not u or u in BROKEN or ("https://" + u.strip()) in BROKEN or u.strip() in ("https://", "http://") else u   # scripts/check_links.mjs


# Plain-language types in five groups (src/lib/layers.js TYPES): what a first-time reader looks for.
GROUP_OF = {"grocery": "food", "market": "food", "meals": "food", "garden": "food",
            "pharmacy": "health", "health_center": "health", "clinic": "health", "hospital": "health",
            "public_school": "learning", "private_school": "learning", "childcare": "learning", "library": "learning", "youth": "learning", "college": "learning",
            "park": "community", "playground": "community", "rec": "community", "sports": "community", "senior": "community",
            "worship": "more", "groups": "more", "services": "more", "arts": "more", "history": "more", "safety": "more", "money": "more"}
def classify(cat, src, kind):
    k = (kind or "").lower()
    if cat == "food":
        if src == "phl_free_meal_sites": return "meals"
        if src == "phl_farmers_markets" or "farmers market" in k: return "market"
        return "grocery"
    if cat == "gardens_farms": return "garden"
    if cat == "pharmacies": return "pharmacy"
    if cat == "health_care":
        if "hospital" in k: return "hospital"
        if src in ("hrsa_health_center_sites", "phl_health_centers"): return "health_center"
        return "clinic"
    if cat == "schools": return "private_school" if re.search(r"private|archdiocese|catholic|parochial", k) else "public_school"
    if cat == "early_childhood": return "childcare"
    if cat == "libraries": return "library"
    if cat == "youth": return "youth"
    if cat == "higher_ed": return "college"
    if cat == "parks_rec":
        if src in ("phl_ppr_playgrounds", "phl_ppr_spraygrounds") or "playground" in k: return "playground"
        if src in ("phl_ppr_program_sites", "phl_ppr_swimming_pools"): return "rec"
        if src in ("phl_ppr_tennis_courts", "osm_sports_facilities") or re.search(r"athletic|field|court|track", k): return "sports"
        return "park"
    if cat == "older_adults": return "senior"
    return {"worship": "worship", "community_orgs": "groups", "social_services": "services", "arts_culture": "arts", "historic": "history",
            "civic_safety": "safety", "economic": "money"}.get(cat, "groups")


def asset_fc(a):
    return fc(a, lambda r: {"category": r.category, "type": classify(r.category, r.source_id, r.kind), "kind": r.kind, "name": r["name"] or r.kind, "address": r.address, "detail": r.detail,
                            "phone": re.sub(r"\.0$", "", r.phone), "website": web(r.website), "source_id": r.source_id, "miles": round(float(r.miles), 2)})


# the studio's own inventory for the two finalists, mapped to the new kinds, for the check at the end
STUDIO_KIND = {"Schools": "schools", "Child care": "early_childhood", "Libraries": "libraries", "Parks and recreation": "parks_rec", "Health care": "health_care",
               "Older adult centers": "older_adults", "Community organizations": "community_orgs", "Fire and police": "civic_safety", "Places of worship": "worship"}
def studio_counts(slug):
    t = pd.read_csv(CA / f"Raw_Source/{STUDIO_DONE[slug]}_Community_Assets.csv")
    t = t[t.miles <= 1]
    cat = t.apply(lambda r: STUDIO_KIND.get(r.category) or ("gardens_farms" if re.search(r"garden|agricult", str(r.kind), re.I) else "food"), axis=1)
    return cat.value_counts().to_dict()


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
NEAR = {}
for slug in ORDER:
    v = SCH[slug]; pt = v["center"]; s = v["row"]; short = SHORT[slug]; log = []
    # assets: the five inventories, measured from this school
    a = inventory_for(v)
    log.append(save(f"{slug}/assets.json", asset_fc(a)))
    counts = {c: {"half": int((d.miles <= 0.5).sum()), "mile": int((d.miles <= 1).sum())} for c, d in a.groupby("category")}
    a["group"] = [GROUP_OF[classify(c, sid, k)] for c, sid, k in zip(a.category, a.source_id, a.kind)]
    NEAR[slug] = a[a.miles <= 1].groupby(["source_id", "group"]).size()
    if slug in STUDIO_DONE:
        checks.append((short, studio_counts(slug), a[a.miles <= 1].category.value_counts().to_dict()))

    # RCOs (contact names, emails and phones of private people are left out)
    if slug in STUDIO_DONE:
        rco = read(CA / f"_source/data/Zoning_RCO_{slug}.geojson").rename(columns=str.lower).to_crs(4326)
    else:
        rco = rco_city.to_crs(FT)
        rco = rco[rco.intersects(v["center_ft"].buffer(HALF))].to_crs(4326)
    rco_ft = rco.to_crs(FT)
    rco["covers"] = rco_ft.buffer(0).contains(v["center_ft"]).values
    rprops = lambda r: {"name": clean(r.organization_name), "type": clean(r.org_type), "covers": bool(r.covers), "cdc": is_cdc(clean(r.organization_name)),
                        "meets": one_line(r.meeting_location_address), "website": web(clean(r.websites)), "expires": clean(r.expirationyear).replace(".0", "")}
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
        "study_tracts": v["study"], "profile": v["profile"], "tract_profile": v["tract_profile"], "tracts": v["tracts"], "asset_counts": counts, "rcos": rco_list, "walk": wrows,
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

# ================================================================ context layers (around all six) — a short list
import shutil
shutil.rmtree(OUT / "ctx", ignore_errors=True)
log = []
log.append(save("ctx/tracts.json", fc(tracts20, lambda r: {"geoid": r.GEOID, "name": clean(r.NAME), **tract_measures(r.GEOID)}, simplify_ft=10)))
# the Philadelphia County outline (the 2020 tracts dissolved: they reach the county line, rivers included), for the
# light-outside / white-inside base style
log.append(save("ctx/city.json", fc(tracts20[["geometry"]].dissolve(), lambda r: {"name": "Philadelphia"}, simplify_ft=40)))

pk = read(P2 / "phl_ppr_properties_citywide.geojson")
pk = pk[~pk.get("property_classification", pd.Series("", index=pk.index)).isin(["TRAFFIC_ISLAND_MEDIAN", "PATHWAY", "OPERATIONAL_INTERNAL"])]
pk["geometry"] = pk.geometry.make_valid()
log.append(save("ctx/parks.json", fc(in_region(pk), lambda r: {"name": title(col(r, "label", "public_name", "park_name")), "acres": num(col(r, "acreage"), 1)}, simplify_ft=3)))

cc = read(next(DS.rglob("phl_commercial_corridors_citywide.geojson")))
log.append(save("ctx/corridors.json", fc(in_region(cc), lambda r: {"name": clean(r["name"]), "storefronts": num(r.comm_count), "vacant": num(r.vac_count), "year": num(r.survey_year)}, simplify_ft=2)))

routes = read(next(DS.rglob("septa_transit_routes_spring2025.geojson")))
METRO, TROLLEY = {"B1", "B2", "B3", "L1", "M1"}, {"T1", "T2", "T3", "T4", "T5", "G1", "D1", "D2"}
routes["mode"] = routes.LineAbbr.astype(str).map(lambda x: "Metro" if x in METRO else "Trolley" if x in TROLLEY else "Bus")
rr = read(next(DS.rglob("septa_regional_rail_lines.geojson")))
rr = rr.assign(LineAbbr=rr.Route_Name, LineName=rr.Route_Name + " Line", mode="Regional Rail")
lines = gpd.GeoDataFrame(pd.concat([routes[routes["mode"] != "Bus"][["LineAbbr", "LineName", "mode", "geometry"]], rr[["LineAbbr", "LineName", "mode", "geometry"]]]), crs=4326)
log.append(save("ctx/transit_lines.json", fc(in_region(lines, clip=True), lambda r: {"route": clean(r.LineAbbr), "name": clean(r.LineName), "mode": r["mode"]}, simplify_ft=10)))

stops = read(next(DS.rglob("septa_bus_stop_ridership_fall2025.geojson"))).to_crs(FT)
stops = stops[stops.within(unary_union([v["center_ft"].buffer(0.75 * MILE) for v in SCH.values()]))]
for c in ("WK_Ons", "WK_Offs"):
    stops[c] = pd.to_numeric(stops[c], errors="coerce").fillna(0)
st = stops.groupby("Stop_Code").agg(name=("Stop", "first"), mode=("Mode", "first"), routes=("Route", lambda x: ", ".join(sorted(set(map(str, x)), key=lambda z: (len(z), z)))),
                                     ons=("WK_Ons", "sum"), offs=("WK_Offs", "sum"), geometry=("geometry", "first")).reset_index()
log.append(save("ctx/transit_stops.json", fc(gpd.GeoDataFrame(st, geometry="geometry", crs=FT), lambda r: {"name": clean(r["name"]), "mode": clean(r["mode"]), "routes": r.routes, "ons": int(r.ons), "offs": int(r.offs)})))

hin = read(next(DS.rglob("vision_zero_high_injury_network_2025.geojson")))
log.append(save("ctx/hin.json", fc(in_region(hin, clip=True), lambda r: {"street": title(r.stname)}, simplify_ft=3)))

def per_school(stem):
    return gpd.GeoDataFrame(pd.concat([read(p) for slug in ORDER for p in [next(DS.rglob(f"{slug}_{stem}.geojson"), None)] if p]), crs=4326)
zn = per_school("zoning_basedistricts_1mi").drop_duplicates("objectid")
log.append(save("ctx/zoning.json", fc(zn, lambda r: {"code": clean(r.long_code), "group": clean(r.zoninggroup)}, simplify_ft=3)))
LU = {1: "Residential", 2: "Commercial", 3: "Industrial", 4: "Civic and institutional", 5: "Transportation", 6: "Culture and recreation", 7: "Parks and open space", 8: "Water", 9: "Vacant"}
lu = per_school("landuse_1mi").drop_duplicates("objectid")
lu = lu[lu.geometry.notna()].to_crs(FT); lu["geometry"] = lu.geometry.buffer(0)
lu["use"] = pd.to_numeric(lu.c_dig1, errors="coerce").map(LU)
log.append(save("ctx/land_use.json", fc(lu.dissolve(by="use").reset_index(), lambda r: {"use": r.use}, simplify_ft=6)))

# housing and vacant land: the economy agent's context datasets
def ctx_frames(pred):
    out = []
    for cid, (m, f) in CONTEXT_SRC.items():
        if pred(cid, m):
            g = read(f).to_crs(4326); g["_src"] = cid; g["_title"] = f"{m.get('title', cid)} ({m.get('publisher', '')})"; out.append(g)
    return out
def program(cid, r):
    t = clean(col(r, "program")).lower() if "program" in r.index else ""
    if "public housing" in t or "pha" in t:
        return "Public housing"
    if "lihtc" in t:
        return "Tax credit housing"
    return "Affordable housing"
hs = ctx_frames(lambda cid, m: re.search(r"housing|lihtc|pha", cid, re.I))
if hs:
    h = gpd.GeoDataFrame(pd.concat(hs), crs=4326)
    h["geometry"] = [x if x.geom_type == "Point" else x.representative_point() for x in h.geometry]
    log.append(save("ctx/housing.json", fc(in_region(h, NEAR1), lambda r: {"name": title(col(r, "name", "project_name", "development", "property_name")) or "Housing development",
                                                                         "units": num(col(r, "units", "total_units", "li_units", "n_units")), "program": program(r._src, r),
                                                                         "detail": " · ".join(x for x in (clean(col(r, "type")), clean(col(r, "status")), f"{int(num(col(r, 'year')))}" if num(col(r, "year")) else "") if x), "source": r._title})))
vs = ctx_frames(lambda cid, m: re.search(r"vacant|land_bank|landbank", cid, re.I))
if vs:
    vg = gpd.GeoDataFrame(pd.concat(vs), crs=4326)
    vg["geometry"] = [x if x.geom_type == "Point" else x.representative_point() for x in vg.geometry]
    log.append(save("ctx/vacant.json", fc(in_region(vg, NEAR1), lambda r: {"address": title(col(r, "address")), "public": clean(col(r, "owner_type")) == "public",
                                                                       "owner": clean(col(r, "public_owner")), "zoning": clean(col(r, "zoning"))})))
print("context: " + " · ".join(log))

# ================================================================ sources.json: the documentation window
NEAR_BY_SOURCE = {}
for slug, ser in NEAR.items():
    for (sid, grp), n in ser.items():
        NEAR_BY_SOURCE.setdefault(sid, {}).setdefault(slug, {})[grp] = int(n)
CAT_GROUP = {"food": "food", "gardens_farms": "food", "pharmacies": "health", "health_care": "health", "schools": "learning", "early_childhood": "learning",
             "libraries": "learning", "youth": "learning", "higher_ed": "learning", "parks_rec": "community", "older_adults": "community"}
assets_doc = [{k: m.get(k, "") for k in ("id", "title", "publisher", "landing_url", "api_url", "license", "retrieved", "data_date", "records", "notes", "domain")}
              | {"groups": sorted({CAT_GROUP.get(c, "more") for c in m.get("categories", [])}), "near": NEAR_BY_SOURCE.get(m["id"], {})} for m in MANIFEST]
CONTEXT_DOCS = json.loads((Path(__file__).resolve().parent / "context_sources.json").read_text())
for cid, (m, f) in CONTEXT_SRC.items():
    CONTEXT_DOCS.append({"id": cid, "layer": "Public & affordable housing" if re.search(r"housing|lihtc|pha", cid, re.I) else "Vacant & Land Bank land",
                         "title": m.get("title", cid), "publisher": m.get("publisher", ""), "landing_url": m.get("landing_url") or m.get("api_url", ""), "notes": m.get("notes", "")})
METHODS = [
    {"title": "What the map is for", "text": "An inventory of what exists around each site, to inform how Wagner and Blankenburg could be reused. It does not rank sites or recommend uses; empty categories are reported as facts, not as needs."},
    {"title": "Collection", "text": "Five inventories (education, health and social services, food and open space, civic and culture, economy and housing) were pulled from the publishers listed under Asset sources, within 1.5 miles of each of the six schools (community organizations within 2 miles). Official City, Commonwealth and federal sources come first; OpenStreetMap fills kinds the official sources do not cover, and is labelled as such."},
    {"title": "De-duplication", "text": "The same kind of place listed by two sources (same or very similar name within about 500 m, or an unnamed record within 80 m) is counted once, keeping the official source's record."},
    {"title": "Distances and the radius", "text": "Distances are straight lines from the school (the centroid of its building parcel), shown in miles; walk times assume the studio's pace of 80 m a minute. The radius slider changes the ring, the counts and the within-radius filter; nothing is inventoried beyond 1.5 miles."},
    {"title": "15-minute walk", "text": "Areas reachable along the OpenStreetMap walk network in 5, 10 and 15 minutes from the street corner nearest the school, with reachable streets widened 25 m and small enclosed gaps filled; residents from 2020 Census blocks. Wagner and Blankenburg use the studio's own walk areas; the other four use the same method."},
    {"title": "Study-area profile", "text": "Census tract counts from the ACS 2020–2024 5-year estimates, each weighted by the share of the tract's 2020 residents living within half a mile of the school (block population); medians by the aggregate median method. Rebuilding Wagner and Blankenburg this way reproduces the studio's published figures."},
    {"title": "Catchments and building ratings", "text": "Attendance boundaries are the School District's 2024 catchments (all grades whose assignment is the school). Building condition, program, utilization and vulnerability ratings are the District's Facilities Master Plan scores as recorded in the studio's site list."},
    {"title": "Privacy and safety", "text": "No private individuals: RCO contact names, emails and phones are left out, as are domestic-violence shelters, residential treatment sites and other locations sources mark confidential. Family child care homes appear as the State lists them."},
    {"title": "Caveats", "text": "Open data lags reality: places close and open, OpenStreetMap coverage is uneven, and some City layers carry older survey dates (see each source's data date). Census tract estimates carry wide margins of error. Check anything decisive on the ground."},
]
(OUT / "sources.json").write_text(json.dumps({"built": pd.Timestamp.now().strftime("%B %-d, %Y"), "assets": assets_doc, "context": CONTEXT_DOCS, "methods": METHODS}, separators=(",", ":")))
print("wrote sources.json:", len(assets_doc), "asset datasets,", len(CONTEXT_DOCS), "context entries")

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
    print(f"  {short} assets within 1 mile, studio inventory / new inventory: " + " · ".join(f"{c} {studio_c.get(c, 0)}/{rebuilt_c.get(c, 0)}" for c in cats))
