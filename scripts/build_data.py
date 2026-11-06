"""Build the web layers for the Wagner and Blankenburg community maps.

Reads the studio's own outputs (Community Asset, Background, Transportation, Economic) from the
Final Two School folder and writes small, rounded GeoJSON files to public/data/<school>/.
Nothing is fetched from the internet: every layer is a file the studio already made.

Run:  uv run --no-project --with geopandas --with pyogrio --with pandas python scripts/build_data.py
      STUDIO="/path/to/Final Two School/MIDREVIEW" to read from somewhere else.
"""
import json, math, os, re, warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping, Point

warnings.filterwarnings("ignore")
M = Path(os.environ.get("STUDIO", Path.home() / "Desktop/FW 2026/Studio/Final Two School/MIDREVIEW"))
DS = M.parents[1] / "Pre-Mid Review/Data_Sources/02_parcel_zoning_landuse_historic"
OUT = Path(__file__).resolve().parents[1] / "public/data"
FT = 2272                                   # PA State Plane South, feet
MILE = 5280
SCHOOLS = {"wagner": "Wagner", "blankenburg": "Blankenburg"}

BG = M / "Background1/_source/data"
TR = M / "Transportation1/_source/data"
EC = M / "Economic1/_source/data"
CA = M / "Community Asset"

points = gpd.read_file(BG / "school_points.geojson").to_crs(4326)
parcels = gpd.read_file(BG / "school_parcels.geojson").to_crs(4326)
rings = gpd.read_file(BG / "half_mile_areas.geojson").to_crs(4326)
tracts20 = gpd.read_file(BG / "tracts_2020.geojson").to_crs(4326)
shares = pd.read_csv(BG / "tract_shares.csv", dtype={"GEOID": str})
shares = shares[(shares.tract_vintage == 2020) & shares.study]
profile = pd.read_csv(BG / "profile_2024.csv")


# ---------------------------------------------------------------- helpers
def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def num(v, dp=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or f < -1e8:           # ACS writes -666666666 for "not available"
        return None
    return round(f, dp) if dp is not None else f


def rnd(geom, dp=5):
    """GeoJSON geometry with coordinates rounded to dp decimals (~1 m at 5)."""
    def r(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(c[0], dp), round(c[1], dp)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def write(slug, name, gdf, props, simplify_ft=0):
    """Write gdf as a FeatureCollection; props(row) -> dict of feature properties."""
    feats = []
    g = gdf.to_crs(FT)
    if simplify_ft:
        g["geometry"] = g.geometry.simplify(simplify_ft, preserve_topology=True)
    g = g.to_crs(4326)
    for _, r in g.iterrows():
        if r.geometry is None or r.geometry.is_empty:
            continue
        p = {k: v for k, v in props(r).items() if v not in ("", None)}
        feats.append({"type": "Feature", "properties": p, "geometry": rnd(r.geometry)})
    path = OUT / slug / f"{name}.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    return len(feats), path.stat().st_size


def near(gdf, site_ft, miles):
    """Rows of gdf within `miles` of the site (geometry intersects the buffer), clipped to it."""
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    g = gdf.to_crs(FT)
    buf = site_ft.buffer(miles * MILE)
    g = g[g.intersects(buf)].copy()
    return g


def clip(gdf, site_ft, miles):
    g = near(gdf, site_ft, miles)
    g["geometry"] = g.geometry.intersection(site_ft.buffer(miles * MILE))
    return g[~g.geometry.is_empty]


def miles_from(g_ft, site_ft):
    return (g_ft.geometry.distance(site_ft) / MILE).round(2)


def title(s):
    s = clean(s)
    if s.isupper():
        s = re.sub(r"\b(Of|And|The|At|For)\b", lambda m: m.group(0).lower(), s.title()).replace("'S", "'s")
    return s


# ---------------------------------------------------------------- tract measures (ACS 2020-2024 5-year)
acs = pd.read_csv(BG / "acs_tracts_philadelphia_2014_2024.csv", dtype={"GEOID": str})
acs = acs[acs.year == acs.year.max()].set_index("GEOID")
more = pd.read_csv(BG / "acs_more_tracts_philadelphia_2014_2024.csv", dtype={"GEOID": str})
more = more[more.year == more.year.max()].set_index("GEOID")
ACS_YEAR = int(acs.year.max()) if "year" in acs else 2024


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
        kids_n = sum(num(m.get(f"B01001_00{i}E")) or 0 for i in (3, 4, 5, 6)) + sum(num(m.get(f"B01001_0{i}E")) or 0 for i in (27, 28, 29, 30))
        kids = ratio(kids_n, m.get("B01001_001E"))
    return {
        "pop": num(r.get("B01003_001E")),
        "income": num(r.get("B19013_001E")),
        "home_value": num(r.get("B25077_001E")),
        "poverty": ratio(r.get("B17001_002E"), r.get("B17001_001E")),
        "unemployment": ratio(r.get("B23025_005E"), r.get("B23025_003E")),
        "bachelors": ratio(ba, r.get("B15003_001E")),
        "renter": ratio(r.get("B25003_003E"), r.get("B25003_001E")),
        "children": kids,
        "black": ratio(r.get("B03002_004E"), r.get("B03002_001E")),
    }


# ---------------------------------------------------------------- source tables read once
assets_csv = {s: pd.read_csv(CA / f"Raw_Source/{s}_Community_Assets.csv") for s in SCHOOLS.values()}
rco_csv = {s: pd.read_csv(CA / f"Raw_Source/{s}_RCOs.csv") for s in SCHOOLS.values()}
walk_inv = gpd.read_file(TR / "amenities.geojson")
walk_areas = gpd.read_file(TR / "walk_areas.geojson")
walk_summary = pd.read_csv(M / "Transportation1/15-Minute Walk/Raw_Source/Walk_Area_Summary.csv") \
    if (M / "Transportation1/15-Minute Walk/Raw_Source/Walk_Area_Summary.csv").exists() else None
nbhd = gpd.read_file(M / "Neighborhood Boundary/Both_Neighborhood_Boundaries.shp").to_crs(4326)
parks_city = gpd.read_file(DS / "phl_ppr_properties_citywide.geojson")
transit_lines = gpd.read_file(TR / "round3_transit_lines.gpkg", layer="lines")
stops = gpd.read_file(TR / "round2_transit_stops.gpkg", layer="stops_near_school")
L = lambda f, layer: gpd.read_file(f, layer=layer)
STREET, CRASH, ECON = TR / "street_layers.gpkg", TR / "crash_layers.gpkg", EC / "layers.gpkg"

INDICATORS = ["Population", "Households", "Median household income", "Median home value", "Poverty rate", "Unemployment rate",
              "Bachelor's degree or higher", "High school diploma or higher", "Owner-occupied", "Renter-occupied",
              "Black", "White", "Hispanic or Latino", "Asian", "Other or multiracial", "Average household size"]

OUT.mkdir(parents=True, exist_ok=True)
for slug, school in SCHOOLS.items():
    (OUT / slug).mkdir(exist_ok=True)
    p = points[points.school == school].geometry.iloc[0]
    site_ft = gpd.GeoSeries([p], crs=4326).to_crs(FT).iloc[0]
    sel = lambda g: g[g.school == school] if "school" in g.columns else g
    report = []
    log = lambda name, res: report.append(f"{name} {res[0]} ({res[1] / 1024:.0f} KB)")

    # ---- community assets (the studio's Raw_Source table)
    a = assets_csv[school].copy()
    inv = walk_inv[walk_inv.school == school]
    inv_src = {(clean(r["name"]), clean(r["address"])): clean(r["source"]) for _, r in inv.iterrows()}
    def src(r):
        s = clean(r.source)
        if not s or s.startswith("<function"):          # the CSV kept a lambda's repr for the 15-minute walk inventory rows
            s = inv_src.get((clean(r["name"]), clean(r.address))) or "15-minute walk inventory (Transportation)"
        return s
    a["source"] = a.apply(src, axis=1)
    ag = gpd.GeoDataFrame(a, geometry=gpd.points_from_xy(a.longitude, a.latitude), crs=4326)
    log("assets", write(slug, "assets", ag, lambda r: {
        "category": clean(r.category), "kind": clean(r.kind), "name": clean(r["name"]), "address": clean(r.address),
        "detail": clean(r.detail), "phone": clean(r.phone).replace(".0", ""), "website": clean(r.website),
        "source": clean(r.source), "miles": num(r.miles, 2), "half": bool(r.within_half_mile)}))

    # ---- RCO boundaries; contact names, emails and phones of private people are left out of a public map
    rco = gpd.read_file(CA / f"_source/data/Zoning_RCO_{slug}.geojson").to_crs(4326)
    info = rco_csv[school].set_index("organization")
    rco_ft = rco.to_crs(FT)
    rco["covers"] = rco_ft.buffer(0).contains(site_ft).values
    def rco_props(r):
        n = clean(r.organization_name)
        cdc = bool(info.loc[n, "is_cdc"]) if n in info.index else False
        return {"name": n, "type": clean(r.org_type), "covers": bool(r.covers), "cdc": cdc,
                "meets": clean(r.meeting_location_address), "website": clean(r.websites), "expires": clean(r.expirationyear)}
    log("rco", write(slug, "rco", rco.sort_values("covers"), rco_props, simplify_ft=4))
    rco_list = sorted([rco_props(r) for _, r in rco.iterrows()], key=lambda d: (not d["covers"], d["name"]))

    # ---- study area
    walk = walk_areas[walk_areas.school == school].sort_values("minutes", ascending=False)
    log("walk", write(slug, "walk", walk, lambda r: {"minutes": int(r.minutes)}))
    study_ids = set(shares[shares.school == school].GEOID)
    tr = near(tracts20, site_ft, 1.6).to_crs(4326)
    sh = shares[shares.school == school].set_index("GEOID")
    log("tracts", write(slug, "tracts", tr, lambda r: {
        "geoid": r.GEOID, "name": clean(r.NAME), "study": r.GEOID in study_ids,
        "share": num(sh.loc[r.GEOID, "share"], 3) if r.GEOID in sh.index else None,
        **tract_measures(r.GEOID)}, simplify_ft=6))

    # ---- parks, corridors, BIDs (as on the studio's community asset map)
    pk = near(parks_city, site_ft, 1.0).to_crs(4326)
    log("parks", write(slug, "parks", pk, lambda r: {"name": title(r.get("label") or r.get("public_name")), "acres": num(r.get("acreage"), 1)}, simplify_ft=3))
    cc = gpd.read_file(CA / f"_source/data/Commercial_Corridors_{slug}.geojson")
    def corr(r):
        vac = clean(r.get("vac_rate"))
        return {"name": clean(r.get("name")), "type": clean(r.get("corridor_type")), "storefronts": num(r.get("comm_count")),
                "vacant": num(r.get("vac_count")), "vac_rate": vac, "stage": clean(r.get("stage")), "year": num(r.get("survey_year"))}
    log("corridors", write(slug, "corridors", cc, corr, simplify_ft=2))
    bid = gpd.read_file(CA / f"_source/data/business_improvement_districts_{slug}.geojson")
    log("bids", write(slug, "bids", bid, lambda r: {"name": title(r.get("organization") or r.get("name")), "phone": clean(r.get("phone")), "website": clean(r.get("website"))}, simplify_ft=3))

    # ---- mobility
    tl = clip(transit_lines, site_ft, 1.6).to_crs(4326)
    log("transit_lines", write(slug, "transit_lines", tl, lambda r: {"route": clean(r.route_short_name), "mode": clean(r["mode"])}, simplify_ft=6))
    st = sel(stops)
    log("transit_stops", write(slug, "transit_stops", st, lambda r: {
        "name": clean(r.stop_name), "mode": clean(r["mode"]), "routes": num(r.routes_weekday), "departures": num(r.weekday_departures),
        "feet": num(r.dist_ft, 0), "shelter": bool(r.shelter_within_100ft) if pd.notna(r.shelter_within_100ft) else None,
        "accessible": clean(r.wheelchair_accessible)}))
    log("bike_lanes", write(slug, "bike_lanes", sel(L(STREET, "bike_lanes")), lambda r: {"kind": clean(r.kind)}, simplify_ft=3))
    bs = sel(L(STREET, "bike_share"))
    if len(bs):
        log("bike_share", write(slug, "bike_share", bs, lambda r: {"name": clean(r["name"]), "docks": num(r.totalDocks)}))
    else:
        write(slug, "bike_share", bs, lambda r: {})
    log("hin", write(slug, "hin", sel(L(CRASH, "high_injury_network")), lambda r: {"street": title(r.stname)}, simplify_ft=3))
    cr = sel(L(CRASH, "crashes"))
    log("crashes", write(slug, "crashes", cr, lambda r: {"year": num(r.crash_year), "killed": num(r.killed), "serious": num(r.serious),
                                                       "ksi": bool(num(r.ksi)), "ped": bool(num(r.ped)), "bike": bool(num(r.bike))}))
    log("crossing_guards", write(slug, "crossing_guards", sel(L(CRASH, "crossing_guards")), lambda r: {"name": title(r.address)}))
    cams = pd.concat([sel(L(CRASH, "speed_cameras_point")), sel(L(CRASH, "speed_cameras_linestring"))])
    log("speed_cameras", write(slug, "speed_cameras", gpd.GeoDataFrame(cams, crs=4326), lambda r: {"kind": clean(r.kind), "status": clean(r.status)}))
    log("curb_ramps", write(slug, "curb_ramps", sel(L(STREET, "missing_curb_ramps")), lambda r: {"status": clean(r.status).title()}))

    # ---- economy and land
    biz = sel(L(ECON, "businesses"))
    log("businesses", write(slug, "businesses", biz, lambda r: {"name": title(r.business_name), "kind": clean(r.kind), "license": clean(r.licensetype), "address": title(r.address)}))
    zn = sel(L(ECON, "zoning"))
    log("zoning", write(slug, "zoning", zn, lambda r: {"code": clean(r.long_code), "group": clean(r.zoninggroup)}, simplify_ft=3))
    lu = sel(L(ECON, "land_use")).dissolve(by="use").reset_index()      # 40,000 lots -> one shape per use
    log("land_use", write(slug, "land_use", lu, lambda r: {"use": clean(r.use)}, simplify_ft=5))
    ia = sel(L(ECON, "incentive_areas"))
    log("incentives", write(slug, "incentives", ia, lambda r: {"layer": clean(r.layer), "name": clean(r["name"])}, simplify_ft=6))
    ah = sel(L(ECON, "affordable_housing"))
    log("affordable_housing", write(slug, "affordable_housing", ah, lambda r: {"name": clean(r.project_name), "units": num(r.total_units),
                                                                            "year": num(r.fiscal_year_complete), "status": clean(r.status)}))
    sg = sel(L(ECON, "storefront_grants"))
    log("storefront_grants", write(slug, "storefront_grants", sg, lambda r: {"name": clean(r.user_business_name), "year": num(r.fiscal_year),
                                                                          "amount": num(r.user_grant_amount, 0)}))
    fr = sel(L(ECON, "food_retail"))
    log("food_access", write(slug, "food_access", fr, lambda r: {"access": clean(r.hpss_access), "supermarket": clean(r.supermarket_access),
                                                              "hpss": num(r.total_hpss), "lpss": num(r.total_lpss)}, simplify_ft=4))

    # ---- the site file: geometry the map always needs + the summary panel's numbers
    one_mile = gpd.GeoSeries([site_ft.buffer(MILE, 64)], crs=FT).to_crs(4326).iloc[0]
    nb = nbhd[nbhd.Name == school]
    counts = {}
    for cat, d in a.groupby("category"):
        counts[cat] = {"half": int(d.within_half_mile.sum()), "mile": int((d.miles <= 1).sum()), "all": int(len(d))}
    prof = {r.indicator: {"school": num(r[school]), "city": num(r["Philadelphia"])} for _, r in profile.iterrows() if r.indicator in INDICATORS}
    city_tr = [tract_measures(g) for g in acs.index]
    walk_rows = []
    if walk_summary is not None and "school" in walk_summary:
        for _, r in walk_summary[walk_summary.school == school].iterrows():
            walk_rows.append({k: (num(v) if k != "school" else v) for k, v in r.items()})
    addr = clean(points[points.school == school].address.iloc[0])
    site = {
        "slug": slug, "school": school, "address": title(addr), "center": [round(p.y, 6), round(p.x, 6)],
        "acs_year": ACS_YEAR,
        "parcel": rnd(parcels[parcels.school == school].geometry.iloc[0], 6),
        "half_mile": rnd(rings[rings.school == school].geometry.iloc[0]),
        "one_mile": rnd(one_mile),
        "neighborhood": rnd(nb.geometry.iloc[0]) if len(nb) else None,
        "neighborhood_acres": num(nb.Acres.iloc[0], 1) if len(nb) else None,
        "study_tracts": sorted(study_ids),
        "profile": prof,
        "asset_counts": counts,
        "rcos": rco_list,
        "walk": walk_rows,
    }
    (OUT / slug / "site.json").write_text(json.dumps(site, separators=(",", ":")))
    print(f"{school}: " + " · ".join(report))

(OUT / "meta.json").write_text(json.dumps({"built": pd.Timestamp.now().strftime("%Y-%m-%d"), "acs_year": ACS_YEAR}))
print("wrote", OUT)
