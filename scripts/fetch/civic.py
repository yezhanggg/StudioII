"""Civic and culture inventory (domain `civic`) around the six school sites.

Categories: arts_culture, historic, civic_safety, community_orgs, worship (see scripts/fetch/CONTRACT.md).
Writes scripts/fetch/out/civic/<dataset_id>.geojson (Point features) and scripts/fetch/out/civic/manifest.json.
Raw responses are cached under scripts/.cache/fetch/civic/; pass --refresh to download everything again.

Run:  uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/civic.py

Kept out on purpose: names, e-mails and phones of people (RCO contacts, NAC coordinators, friends-group
contacts); shelters and supportive housing in the City facilities database; community centres that belong to
another domain (youth, older adults, recreation), which are listed at the end of the run for the other agents.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out/civic"
CACHE = ROOT / "scripts/.cache/fetch/civic"
for d in (OUT, CACHE):
    d.mkdir(parents=True, exist_ok=True)
REFRESH = "--refresh" in sys.argv
TODAY = date.today().isoformat()
UA = {"User-Agent": "studio-community-maps/1.0"}
FT = 2272                                   # PA State Plane South (US feet)
M2FT = 3.280833
R_ASSET, R_ORG = 2414.0, 3219.0             # 1.5 miles; 2 miles for community organizations (metres)
MILE_M = 1609.344
SITES = json.loads((HERE / "schools.json").read_text())
CITY = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
NPS = "https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/0"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
STUDIO = Path.home() / "Desktop/FW 2026/Studio"
P2 = STUDIO / "Pre-Mid Review/Data_Sources/02_parcel_zoning_landuse_historic"
CITY_LICENSE = "City of Philadelphia open data terms of use (https://metadata.phila.gov/#help/help-faqs/what-are-the-terms-of-use/)"
OSM_LICENSE = "Open Database License (ODbL) 1.0, © OpenStreetMap contributors"

CENTERS = gpd.GeoSeries([Point(s["lng"], s["lat"]) for s in SITES], crs=4326).to_crs(FT)
SITE_NAME = {s["slug"]: s["name"] for s in SITES}
# The five school buildings listed on the National Register (NRIS reference numbers from the nominations the studio
# saved in Data_Sources/02_parcel_zoning_landuse_historic/historic/; Robeson is not listed).
SCHOOL_NRIS = {"86003340": "wagner", "88002248": "blankenburg", "86003281": "fitler", "88002314": "pennypacker",
               "88002292": "amynw"}
MANIFEST: list[dict] = []
REPORT: list[tuple] = []
ELSEWHERE: list[str] = []                   # records seen that belong to another agent's domain


# ---------------------------------------------------------------- text helpers
def clean(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\r", " ").replace("\n", " ")).strip()


def one_line(v) -> str:
    s = re.sub(r"\s*[\r\n]+\s*", ", ", str(v or "")).strip()
    s = re.sub(r"\s*,(\s*,)+\s*", ", ", s)
    return clean(s).strip(", ")


ACRONYMS = {"PAL", "YMCA", "YWCA", "CDC", "NAC", "RCO", "PHA", "AME", "CME", "AMEZ", "COGIC", "LLC", "USA", "US", "PA",
            "II", "III", "IV", "VFW", "PPR", "SEPTA", "PECO", "LGBT", "LGBTQ", "UCC", "MLK", "JFK", "NW", "NE", "SW", "SE",
            "PMA", "PCA", "PHMC", "WWI", "WWII", "CEO", "HQ", "APM", "HACE", "ACANA"}
SMALL = {"of", "and", "the", "at", "for", "in", "on", "to", "by", "a", "an"}


def nice(s) -> str:
    """Title case for ALL-CAPS text, keeping acronyms; mixed-case text is left as published."""
    s = clean(s)
    if not s or not re.search(r"[A-Za-z]", s) or s != s.upper():
        return s

    def word(m):
        w = m.group(0)
        if w.upper() in ACRONYMS:
            return w.upper()
        return w[0].upper() + w[1:].lower()
    out = re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", word, s)
    out = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), out)
    out = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), out)
    out = re.sub(r"(?<=\s)([A-Z][a-z]*)\b", lambda m: m.group(1).lower() if m.group(1).lower() in SMALL else m.group(1), out)
    return out


def name_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def layer_date(url: str) -> str:
    """'service last edited YYYY-MM-DD' from an ArcGIS layer's metadata, or ''."""
    try:
        d = json.loads(fetch("meta_" + re.sub(r"\W+", "_", url)[-60:], url, {"f": "json"}))
        ms = (d.get("editingInfo") or {}).get("lastEditDate") or (d.get("editingInfo") or {}).get("dataLastEditDate")
        return f"service last edited {datetime.fromtimestamp(ms / 1000, timezone.utc).date()}" if ms else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- downloads (cached)
def fetch(name: str, url: str, params: dict | None = None, data: dict | None = None, tries: int = 4, timeout: int = 240) -> str:
    key = hashlib.md5(json.dumps([url, params, data], sort_keys=True, default=str).encode()).hexdigest()[:10]
    f = CACHE / f"{re.sub(r'[^A-Za-z0-9_]+', '_', name)[:60]}_{key}.txt"
    if f.exists() and not REFRESH:
        return f.read_text()
    last = None
    for i in range(tries):
        try:
            r = (requests.post(url, data=data, headers=UA, timeout=timeout) if data is not None
                 else requests.get(url, params=params, headers=UA, timeout=timeout))
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            f.write_text(r.text)
            return r.text
        except Exception as e:                       # retry with backoff
            last = e
            time.sleep(4 * 2 ** i)
    raise RuntimeError(f"{name}: {last}")


def bbox(radius_m: float):
    b = gpd.GeoSeries(CENTERS.buffer(radius_m * M2FT), crs=FT).to_crs(4326).total_bounds
    return [float(x) for x in b]


def arcgis(name: str, layer_url: str, radius_m: float, where: str = "1=1", out_fields: str = "*") -> gpd.GeoDataFrame:
    """All features of an ArcGIS layer whose geometry meets the bounding box of the study area (paged)."""
    w, s, e, n = bbox(radius_m)
    feats, off = [], 0
    while True:
        p = {"where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields, "outSR": 4326, "f": "geojson",
             "resultOffset": off, "resultRecordCount": 1000}
        d = json.loads(fetch(f"{name}_{off}", layer_url + "/query", p))
        if "error" in d:
            raise RuntimeError(f"{name}: {d['error']}")
        fs = d.get("features") or []
        feats += fs
        more = (d.get("properties") or {}).get("exceededTransferLimit") or d.get("exceededTransferLimit")
        if not fs or (not more and len(fs) < 1000):
            break
        off += len(fs)
    feats = [f for f in feats if f.get("geometry")]
    if not feats:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=4326)
    return gpd.GeoDataFrame.from_features(feats, crs=4326)


def overpass(name: str, query: str) -> list[dict]:
    last = None
    for url in OVERPASS:
        try:
            return json.loads(fetch(name, url, data={"data": query}, tries=3))["elements"]
        except Exception as e:
            last = e
    raise RuntimeError(f"Overpass failed on both mirrors: {last}")


GEO_MEMO = CACHE / "census_geocodes.json"
_geo = json.loads(GEO_MEMO.read_text()) if GEO_MEMO.exists() else {}


STREET_NO = re.compile(r"\b\d{1,5}(?:-\d{1,5})?[A-Za-z]?\s+(?:[NSEW]\.?\s+)?(?:\d+(?:st|nd|rd|th)\b|[A-Za-z]{2,})", re.I)


def street_part(addr: str) -> str | None:
    """The first street address in a free-text address field ('PAX Cafe, 2336 S. 18th St, ...' -> '2336 S. 18th St, ...';
    links, 'virtual', 'or ...' alternatives and suite numbers dropped)."""
    a = re.sub(r"\([^)]*\)", " ", one_line(addr))
    a = re.sub(r"https?://\S+|\b\S+\.(?:com|org|us|net)/\S*", " ", a)
    a = re.sub(r"(?<=\d)\s+#\s*\w+\b", "", a)           # '3729 #1 Melon St' -> '3729 Melon St'
    if not a or re.search(r"\bP\.?\s*O\.?\s*Box\b", a, re.I) and not STREET_NO.search(re.split(r"\bP\.?\s*O\.?\s*Box", a, flags=re.I)[0]):
        return None
    parts = re.split(r";|/|\s+or\s+|\s+&\s+|\s+and\s+(?=\d)|\s-\s|\balso\b|\bunless\b|\bmailing\b|\bvirtual\b|\bzoom\b|\bP\.?\s*O\.?\s*Box|,\s*(?=\d{1,5}\s)", a, flags=re.I)
    for part in parts:
        m = STREET_NO.search(part)
        if not m:
            continue
        s = part[m.start():]
        s = re.sub(r"[,\s]+(Suite|Ste\.?|Fl\.?|Floor|Unit|Apt\.?|Rm\.?|Room|#)\s*[\w-]+", "", s, flags=re.I)
        s = re.sub(r"\b\d+(st|nd|rd|th)\s+(Fl|Floor)\b\.?", "", s, flags=re.I)
        s = re.sub(r"\bPhila\.?(?=[\s,]|$)|\bPhialdelphia\b|\bPhiladelhia\b", "Philadelphia", s, flags=re.I)
        s = re.sub(r"(\b19\d{3})(?:-\d{4})?\b.*$", r"\1", s)        # nothing after the ZIP code
        if not re.search(r"philadelphia|\bPA\b|\b19\d{3}\b", s, re.I):
            s += ", Philadelphia, PA"
        s = clean(s).strip(", -")
        return s[:100]
    return None


_geo_fresh: set[str] = set()


def _census(addr: str):
    for i in range(3):
        try:
            r = requests.get(CENSUS, params={"address": addr, "benchmark": "Public_AR_Current", "format": "json"},
                             headers=UA, timeout=90)
            if 400 <= r.status_code < 500:
                return addr, None, True                  # the geocoder rejects this address: unmatched
            r.raise_for_status()
            m = r.json()["result"]["addressMatches"]
            return addr, ([m[0]["coordinates"]["x"], m[0]["coordinates"]["y"]] if m else None), True
        except Exception:
            time.sleep(3 * 2 ** i)
    return addr, None, False                         # network failure: not memoised, retried next run


def geocode_many(addrs) -> None:
    """US Census geocoder (Public_AR_Current) for every address not yet in the cache, four at a time."""
    todo = sorted({a for a in addrs if a and (a not in _geo or (REFRESH and a not in _geo_fresh))})
    if not todo:
        return
    print(f"    geocoding {len(todo)} addresses with the Census geocoder ...", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for addr, xy, ok in pool.map(_census, todo):
            if ok:
                _geo[addr] = xy
                _geo_fresh.add(addr)
            else:
                failed.append(addr)
    for addr in failed:                               # second, one-at-a-time pass for requests that timed out
        addr, xy, ok = _census(addr)
        if ok:
            _geo[addr] = xy
            _geo_fresh.add(addr)
    GEO_MEMO.write_text(json.dumps(_geo, indent=1, sort_keys=True))


def geocode(addr: str) -> tuple[float, float] | None:
    """Census point for an address already passed to geocode_many (None when unmatched or the geocoder was down)."""
    v = _geo.get(addr)
    return tuple(v) if v else None


# ---------------------------------------------------------------- standardise, filter, write
COLS = ["category", "kind", "name", "address", "phone", "website", "detail"]


def rec(geom, category, kind, name="", address="", phone="", website="", detail="") -> dict:
    return {"category": category, "kind": kind, "name": name, "address": address, "phone": phone,
            "website": website, "detail": detail, "geometry": geom}


def joined(*parts, sep=" · ") -> str:
    return sep.join(p for p in (clean(x) for x in parts) if p)


def site_dist_m(g: gpd.GeoSeries) -> pd.DataFrame:
    """Distance (m) from each geometry to each of the six school centres."""
    gf = g.to_crs(FT)
    return pd.DataFrame({s["slug"]: gf.distance(CENTERS.iloc[i]) / M2FT for i, s in enumerate(SITES)}, index=g.index)


def write(ds_id: str, rows: list[dict], meta: dict) -> None:
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326) if rows else gpd.GeoDataFrame(columns=COLS + ["geometry"], geometry="geometry", crs=4326)
    if len(g):
        g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
        g["geometry"] = [x if x.geom_type == "Point" else x.representative_point() for x in g.geometry]
        for c in COLS:
            g[c] = g[c].map(clean)
        d = site_dist_m(g.geometry)
        radius = g.category.map(lambda c: R_ORG if c == "community_orgs" else R_ASSET)
        g = g[d.min(axis=1) <= radius].copy()
        # within-dataset duplicates: same name within 40 m
        gf = g.to_crs(FT)
        drop = set()
        for key, grp in gf.assign(k=gf["name"].map(name_key)).groupby("k"):
            if not key or len(grp) < 2:
                continue
            idx = list(grp.index)
            for i, a in enumerate(idx):
                if a in drop:
                    continue
                for b in idx[i + 1:]:
                    if b not in drop and gf.geometry[a].distance(gf.geometry[b]) <= 40 * M2FT:
                        drop.add(b)
        g = g.drop(index=list(drop))
        g = g.sort_values(["category", "kind", "name"]).reset_index(drop=True)
    feats = []
    for _, r in g.iterrows():
        props = {c: r[c] for c in COLS}
        props["source_id"] = ds_id
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [round(r.geometry.x, 6), round(r.geometry.y, 6)]}})
    (OUT / f"{ds_id}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=0))
    meta = {"id": ds_id, **meta, "retrieved": TODAY, "records": len(feats)}
    meta["categories"] = sorted(set(g.category)) if len(g) else meta.get("categories", [])
    order = ["id", "title", "categories", "publisher", "landing_url", "api_url", "license", "retrieved", "data_date", "records", "notes"]
    MANIFEST.append({k: meta.get(k, "") for k in order})
    near = site_dist_m(g.geometry) if len(g) else pd.DataFrame({"wagner": [], "blankenburg": []})
    REPORT.append((ds_id, len(g), int((near["wagner"] <= MILE_M).sum()), int((near["blankenburg"] <= MILE_M).sum())))
    print(f"  {ds_id:32s} {len(g):5d} records  (1 mi: Wagner {REPORT[-1][2]}, Blankenburg {REPORT[-1][3]})", flush=True)


def run(fn):
    """Run one dataset builder; a failing source is reported, not fatal."""
    try:
        fn()
    except Exception as e:
        print(f"  !! {fn.__name__} failed: {e}", flush=True)
        FAILED.append(f"{fn.__name__}: {e}")


FAILED: list[str] = []


def school_parcels() -> gpd.GeoDataFrame:
    """The six school parcels (PWD parcel polygons, as saved by the studio from the City's PWD_PARCELS layer)."""
    parts = []
    for s in SITES:
        f = P2 / f"{s['slug']}_school_parcel_pwd_polygon.geojson"
        if f.exists():
            p = gpd.read_file(f).to_crs(4326)
            parts.append(gpd.GeoDataFrame({"slug": [s["slug"]]}, geometry=[p.geometry.union_all()], crs=4326))
    return pd.concat(parts, ignore_index=True) if parts else gpd.GeoDataFrame({"slug": []}, geometry=[], crs=4326)


PARCELS = school_parcels()


def on_school_parcel(geom) -> str:
    for _, p in PARCELS.iterrows():
        if geom.intersects(p.geometry.buffer(-0.00001)):
            return p.slug
    return ""


def this_site(slug: str) -> str:
    return f"This school site ({SITE_NAME[slug]})" if slug else ""


# ================================================================ arts & culture
def percent_for_art():
    url = f"{CITY}/Percent_for_Art_Public/FeatureServer/0"
    g = arcgis("percent_for_art", url, R_ASSET)

    def artist(a):
        out = []
        for x in re.split(r"\s*;\s*|\s+and\s+|\s*&\s*", clean(a)):
            if x.count(",") == 1:
                last, first = [y.strip() for y in x.split(",")]
                x = f"{first} {last}"
            out.append(x)
        return ", ".join(o for o in out if o)
    rows = [rec(r.geometry, "arts_culture", "Public art (Percent for Art)", clean(r.title),
                one_line(r.address) or clean(r.location_name), "", "",
                joined(artist(r.artist), clean(r.date_), clean(r.medium), clean(r.location_name)))
            for r in g.itertuples() if clean(getattr(r, "status", "")) == "Active"]
    write("phl_percent_for_art", rows, {
        "title": "Percent for Art Locations", "publisher": "City of Philadelphia, Office of Arts, Culture and the Creative Economy (Creative Philadelphia)",
        "landing_url": "https://opendataphilly.org/datasets/percent-for-art-locations/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "Artworks commissioned under the City's Percent for Art program; only status 'Active' kept (works listed as 'Inaccessible' or 'In Progress' left out). Polygon footprints placed as a point inside the footprint."})


def ppr_art():
    url = f"{CITY}/PPR_Art_Monuments_point/FeatureServer/0"
    g = arcgis("ppr_art_monuments", url, R_ASSET)
    kinds = {"fountain": "Fountain", "free-standing": "Monument or sculpture", "wall": "Wall-mounted artwork or plaque"}
    rows = []
    for r in g.itertuples():
        who = clean(f"{clean(r.firstnamea)} {clean(r.lastname)}")
        rows.append(rec(r.geometry, "arts_culture", kinds.get(clean(r.type).lower(), "Public art or monument") + " (PPR collection)",
                        clean(r.name), clean(r.address) or clean(r.generalloc), "", "",
                        joined(who, clean(r.installati), clean(r.generalloc))))
    item = json.loads(fetch("ppr_art_service", f"{CITY}/PPR_Art_Monuments_point/FeatureServer", {"f": "json"})).get("serviceItemId", "")
    write("phl_ppr_art_monuments", rows, {
        "title": "PPR Art and Monuments", "publisher": "Philadelphia Parks & Recreation",
        "landing_url": f"https://www.arcgis.com/home/item.html?id={item}" if item else url, "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "Sculpture, fountains and monuments in the Parks & Recreation collection (inventory points). No OpenDataPhilly page was found for this layer; landing link is the City's ArcGIS item."})


LANDMARK = {"Fountain / Monument / Statue": ("arts_culture", "Monument, statue or fountain"), "Mural": ("arts_culture", "Mural"),
            "Indoor Entertainment Venue": ("arts_culture", "Performance or entertainment venue"),
            "Outdoor Entertainment Venue": ("arts_culture", "Outdoor performance venue"),
            "Historic Site": ("historic", "Historic site (City landmark)"),
            "Place of Worship": ("worship", "Place of worship"), "Religious": ("worship", "Place of worship")}


def city_landmarks():
    url = f"{CITY}/Landmark_Points/FeatureServer/0"
    g = arcgis("landmark_points", url, R_ASSET)
    rows = []
    for r in g.itertuples():
        sub = clean(r.SUBTYPE)
        if sub not in LANDMARK or clean(r.PUBLIC_).upper() == "N" or clean(r.ARCHIVE_DATE):
            continue
        cat, kind = LANDMARK[sub]
        if cat == "historic" and OUTBUILDING.search(clean(r.NAME)):
            continue                                  # guard boxes, ruins, springhouses
        parent = clean(r.PARENT_NAME)
        rows.append(rec(r.geometry, cat, kind, clean(r.NAME), nice(r.ADDRESS), "", "", f"In {parent}" if parent else ""))
    write("phl_city_landmarks", rows, {
        "title": "City Landmarks (points)", "publisher": "City of Philadelphia, Office of Innovation and Technology (CityGeo)",
        "landing_url": "https://opendataphilly.org/datasets/city-landmarks/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "The City's basemap landmark points, limited to the subtypes that are civic or cultural (monuments, statues and fountains, murals, entertainment venues, historic sites, places of worship); zoo exhibit points, guard boxes and ruins, archived and non-public points left out. Last edited 2020, so recent changes may be missing."})


FAC_OCC = {"PPR": "Philadelphia Parks & Recreation", "PMA": "Philadelphia Museum of Art", "ZOO": "Philadelphia Zoo",
           "L&I": "Licenses & Inspections", "POLICE": "Police Department", "Public use": "Public use", "Public Use": "Public use",
           "PUBLIC USE": "Public use", "Vacant": "Vacant"}
OUTBUILDING = re.compile(r"guard box|ruin|springhouse|smokehouse|necessary|dependency|shed|careta?k?er|entrance house|"
                         r"#\d|canoe house|tenant house|porters? house|north building|south building", re.I)
CITY_OFFICE = re.compile(r"L&I .*District Office|Public Safety Services Campus|Municipal Services Building|City Hall", re.I)


def city_facilities():
    url = f"{CITY}/City_Facilities_pub/FeatureServer/0"
    g = arcgis("city_facilities", url, R_ASSET)
    rows = []
    for r in g.itertuples():
        sub, name, occ = clean(r.asset_subt1_desc), clean(r.asset_name), clean(r.occupant)
        if clean(r.status).upper() == "I" or clean(r.not_public).upper() == "Y":
            continue
        occ_txt = FAC_OCC.get(occ, occ)
        addr = nice(r.asset_addr)
        if sub == "Museum":
            rows.append(rec(r.geometry, "arts_culture", "City-owned museum building", name, addr, "", "", joined(f"Occupant: {occ_txt}" if occ_txt else "")))
        elif sub == "Historic House\\Site" and not OUTBUILDING.search(name):
            rows.append(rec(r.geometry, "historic", "City-owned historic house or site", name, addr, "", "",
                            joined(f"Occupant: {occ_txt}" if occ_txt else "", clean(r.site_name) if clean(r.site_name) != name else "")))
        elif sub == "Multi-Use\\Office Building" and CITY_OFFICE.search(name):
            kind = "Police headquarters" if "Public Safety" in name else "City service office"
            rows.append(rec(r.geometry, "civic_safety", kind, name, addr, "", "", joined(f"Occupant: {occ_txt}" if occ_txt else "")))
    write("phl_city_facilities_civic", rows, {
        "title": "City Facilities (Master Facilities Database) — civic and cultural subset", "publisher": "City of Philadelphia, Department of Public Property",
        "landing_url": "https://opendataphilly.org/datasets/city-facilities-master-facilities-database/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "Public-facing City assets only: museum buildings (arts_culture), City-owned historic houses (historic; guard boxes, ruins, springhouses and other outbuildings dropped) and City service offices such as L&I district offices and the Public Safety Services Campus (civic_safety). Inactive and not-public assets dropped; shelters and supportive housing deliberately left out; fire and police stations come from their own layers; recreation, library and health buildings belong to other domains."})


ART_TYPE = {"mural": "Mural", "statue": "Statue", "sculpture": "Sculpture", "bust": "Bust", "relief": "Relief",
            "installation": "Installation", "mosaic": "Mosaic", "painting": "Painting", "street_art": "Street art",
            "graffiti": "Graffiti", "stone": "Sculpture"}
OUT_OF_DOMAIN = re.compile(r"senior|older adult|\byouth\b|\bteen\b|police athletic|\bPAL\b|boys (and|&) girls|\bYMCA\b|\bYWCA\b|"
                           r"recreation|\brec\b|playground|\bYAC\b|ice rink|child|day ?care|head start|library", re.I)
VET = re.compile(r"\bVFW\b|American Legion|\bPost\b|Veterans", re.I)
FRATERNAL = re.compile(r"Odd Fellows|Elks|Masonic|Lodge|Moose|Fraternal|Alpha |Phi |Sons of|Order of", re.I)
OSM_ELEMENTS: list[dict] = []


def osm_elements():
    if not OSM_ELEMENTS:
        w, s, e, n = bbox(R_ORG)
        b = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
        q = (f'[out:json][timeout:240];('
             f'nwr["amenity"="place_of_worship"]{b};'
             f'nwr["tourism"~"^(museum|gallery|artwork|zoo)$"]{b};'
             f'nwr["amenity"~"^(arts_centre|theatre|cinema|music_venue|community_centre|social_centre)$"]{b};'
             f');out center tags;')
        OSM_ELEMENTS.extend(overpass("overpass_civic", q))
    return OSM_ELEMENTS


def osm_geom(e):
    if "lat" in e:
        return Point(e["lon"], e["lat"])
    c = e.get("center")
    return Point(c["lon"], c["lat"]) if c else None


def osm_addr(t):
    street = " ".join(x for x in (t.get("addr:housenumber", ""), t.get("addr:street", "")) if x)
    return joined(street, t.get("addr:city", "") if street else "", sep=", ")


def osm_web(t):
    return t.get("website") or t.get("contact:website") or t.get("url") or ""


def osm_phone(t):
    return t.get("phone") or t.get("contact:phone") or ""


OSM_META = {"publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org/",
            "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"live OSM data as of {TODAY}"}


def osm_arts():
    rows = []
    for e in osm_elements():
        t, geom = e.get("tags", {}), osm_geom(e)
        tour, am = t.get("tourism", ""), t.get("amenity", "")
        if geom is None or am == "place_of_worship":
            continue
        name = t.get("name", "")
        if tour == "museum":
            kind = "Museum"
        elif tour == "gallery":
            kind = "Gallery"
        elif tour == "zoo":
            kind = "Zoo"
        elif tour == "artwork":
            kind = ART_TYPE.get(t.get("artwork_type", ""), "Public artwork")
        elif am == "arts_centre":
            kind = "Arts center"
        elif am == "theatre":
            kind = "Theater"
        elif am == "cinema":
            kind = "Cinema"
        elif am == "music_venue":
            kind = "Music venue"
        elif am == "community_centre" and (t.get("community_centre") == "cultural_centre" or re.search(r"cultural|\barts?\b", name, re.I)):
            kind = "Cultural center"
        else:
            continue
        detail = joined(t.get("artist_name", "") and f"{t['artist_name']}", t.get("start_date", ""), t.get("operator", ""))
        rows.append(rec(geom, "arts_culture", kind, name, osm_addr(t), osm_phone(t), osm_web(t), detail))
    write("osm_arts_culture", rows, {"title": "OpenStreetMap: museums, galleries, theaters, arts centers, public art", **OSM_META,
        "notes": "OSM tourism=museum|gallery|artwork|zoo and amenity=arts_centre|theatre|cinema|music_venue, plus community centres tagged or named as cultural centres. Fills gaps in the official layers (no machine-readable Mural Arts inventory is published); OSM mural coverage is partial and many artworks are unnamed."})


def osm_community_centres():
    rows = []
    for e in osm_elements():
        t, geom = e.get("tags", {}), osm_geom(e)
        am, name = t.get("amenity", ""), t.get("name", "")
        if geom is None or am not in ("community_centre", "social_centre"):
            continue
        if t.get("community_centre") == "cultural_centre" or re.search(r"cultural|\barts?\b", name, re.I):
            continue                                  # in osm_arts_culture
        if t.get("community_centre") in ("youth_centre", "senior_centre") or OUT_OF_DOMAIN.search(name):
            ELSEWHERE.append(f"OSM {am}: {name or '(unnamed)'}")
            continue
        op = t.get("operator", "")
        if re.search(r"City of Philadelphia|Parks (and|&) Recreation", op, re.I):
            ELSEWHERE.append(f"OSM City-run {am}: {name}")
            continue
        kind = "Veterans post" if VET.search(name) else "Fraternal or social club" if FRATERNAL.search(name) else "Community center"
        rows.append(rec(geom, "community_orgs", kind, name, osm_addr(t), osm_phone(t), osm_web(t), joined(op and f"Operator: {op}")))
    write("osm_community_centres", rows, {"title": "OpenStreetMap: community centers and social clubs", **OSM_META,
        "notes": "OSM amenity=community_centre|social_centre that are not City-run and not youth, older-adult or recreation centres (those belong to other categories and were left out). Non-City community centres are filed under community_orgs as community-run places; cultural centres went to arts_culture."})


RELIGION = {"christian": "Church", "muslim": "Mosque", "jewish": "Synagogue", "buddhist": "Buddhist temple",
            "hindu": "Hindu temple", "sikh": "Gurdwara", "bahai": "Bahá'í center", "unitarian_universalist": "Unitarian Universalist congregation",
            "multifaith": "Multifaith center", "scientologist": "Scientology center"}


def osm_worship():
    rows = []
    for e in osm_elements():
        t, geom = e.get("tags", {}), osm_geom(e)
        if geom is None or t.get("amenity") != "place_of_worship":
            continue
        rel, den = t.get("religion", ""), t.get("denomination", "")
        kind = "Kingdom Hall" if den == "jehovahs_witness" else RELIGION.get(rel, "Place of worship")
        detail = joined(rel.replace("_", " ").title(), {"jehovahs_witness": "Jehovah's Witnesses"}.get(den, den.replace("_", " ").title()))
        rows.append(rec(geom, "worship", kind, t.get("name", ""), osm_addr(t), osm_phone(t), osm_web(t), detail))
    write("osm_places_of_worship", rows, {"title": "OpenStreetMap: places of worship", **OSM_META,
        "notes": "OSM amenity=place_of_worship (nodes, ways and relations, placed at the feature or its centre); religion and denomination from OSM tags in detail. Unnamed features kept with an empty name. No official citywide inventory of congregations is published."})


# ================================================================ historic
def philreg():
    url = f"{CITY}/Historic_sites_PhilReg/FeatureServer/0"
    g = arcgis("historic_sites_philreg", url, R_ASSET)
    rows = []
    for r in g.itertuples():
        slug = on_school_parcel(r.geometry)
        ind, dist = clean(r.idesigdate1), clean(r.district)
        if not ind and not slug:
            continue                                  # district-only properties are represented by the district point
        kind = "Philadelphia Register, individually designated" if ind else f"Philadelphia Register, contributing to {dist} Historic District"
        detail = joined(this_site(slug), f"Designated {ind}" if ind else "",
                        f"In {dist} Historic District ({clean(r.districtdesdate)})" if dist and ind else
                        (f"District designated {clean(r.districtdesdate)}" if dist else ""))
        rows.append(rec(r.geometry.representative_point(), "historic", kind, nice(r.loc), nice(r.loc), "", "", detail))
    write("phl_historic_register_sites", rows, {
        "title": "Philadelphia Register of Historic Places — individually designated properties", "publisher": "City of Philadelphia, Philadelphia Historical Commission",
        "landing_url": "https://opendataphilly.org/datasets/philadelphia-registered-historic-properties/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "Properties individually designated on the Philadelphia Register, as a point inside each parcel; the layer carries addresses, not names, so the address is the name. Properties that are only contributing to a historic district are summarised by the district points (phl_historic_districts), except a school site itself, which is kept and marked 'This school site'."})


def districts():
    url = f"{CITY}/HistoricDistricts_Local/FeatureServer/0"
    g = arcgis("historic_districts_local", url, R_ASSET)
    stats = json.loads(fetch("philreg_district_dates", f"{CITY}/Historic_sites_PhilReg/FeatureServer/0/query", {
        "where": "district IS NOT NULL", "groupByFieldsForStatistics": "district,districtdesdate", "f": "json",
        "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "objectid", "outStatisticFieldName": "n"}])}))
    STOPW = {"historic", "district", "boundary", "residential", "thematic", "the", "of", "st", "street", "ave", "avenue", "e", "east"}
    tok = lambda s: frozenset(t for t in re.findall(r"[a-z0-9]+", clean(s).lower()) if t not in STOPW)
    reg: dict[frozenset, dict] = {}                   # Register properties per district name (Historic_sites_PhilReg)
    for f in stats.get("features", []):
        a = f["attributes"]
        k = tok(a["district"])
        if not k:
            continue
        e = reg.setdefault(k, {"n": 0, "dates": {}})
        e["n"] += a["n"]
        if clean(a["districtdesdate"]):
            e["dates"][clean(a["districtdesdate"])] = e["dates"].get(clean(a["districtdesdate"]), 0) + a["n"]

    def lookup(nm):
        k = tok(nm)
        if k in reg:
            return reg[k]
        hits = [v for kk, v in reg.items() if k and (kk <= k or k <= kk)]
        return hits[0] if len(hits) == 1 else None
    if not len(g):
        raise RuntimeError("HistoricDistricts_Local returned no districts")
    buf = gpd.GeoSeries(CENTERS.buffer(R_ASSET * M2FT), crs=FT).to_crs(4326)
    gf = g.to_crs(FT)
    rows = []
    for i, r in g.iterrows():
        d = [gf.geometry[i].distance(c) for c in CENTERS]
        k = min(range(len(d)), key=d.__getitem__)
        part = r.geometry.buffer(0).intersection(buf.iloc[k])
        if part.is_empty:
            continue
        nm = re.sub(r"\s+Boundary$", "", re.sub(r"DIstrict", "District", clean(r["name"])))
        des = clean(r.get("designated1"))
        info = lookup(nm)
        if not des or des.endswith("3000"):         # missing or the layer's 1/1/3000 placeholder: use the properties' date
            des = max(info["dates"], key=info["dates"].get) if info and info["dates"] else ""
        rows.append(rec(part.representative_point(), "historic", "Philadelphia Register historic district",
                        nm if re.search(r"district", nm, re.I) else f"{nm} Historic District", "", "", "",
                        joined(f"Designated {des}" if des else "Designation date not given",
                               f"{info['n']:,} properties on the Register" if info else "")))
    write("phl_historic_districts", rows, {
        "title": "Philadelphia Register historic districts (one point per district)", "publisher": "City of Philadelphia, Philadelphia Historical Commission",
        "landing_url": "https://opendataphilly.org/datasets/philadelphia-registered-historic-districts/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "One point per local historic district (including thematic districts) that reaches within 1.5 miles of a site, placed inside the part of the district nearest that site; detail gives the designation date (from the property records when the district layer has none or its 1/1/3000 placeholder) and the number of Register properties in the district."})


def national_register():
    g = arcgis("nps_nrhp_points", NPS, R_ASSET, where="STATUS='Listed'")
    rows = []
    for r in g.itertuples():
        ref = clean(r.NRIS_Refnum)
        slug = SCHOOL_NRIS.get(ref, "")
        typ = clean(r.ResType).lower()
        kind = "National Register historic district" if typ == "district" else f"National Register listing ({typ})" if typ else "National Register listing"
        nhl = clean(r.Is_NHL).lower() in ("true", "yes", "y", "1")
        rows.append(rec(r.geometry, "historic", kind, clean(r.RESNAME), clean(r.Address), "", clean(r.NARA_URL),
                        joined(this_site(slug), "National Historic Landmark" if nhl else "", f"Listed {clean(r.CertDate).rstrip('-')}",
                               f"NRIS {ref}")))
    write("nps_national_register", rows, {
        "title": "National Register of Historic Places (points)", "publisher": "National Park Service, National Register of Historic Places",
        "landing_url": "https://www.nps.gov/subjects/nationalregister/data-downloads.htm", "api_url": NPS + "/query",
        "license": "Public domain (U.S. federal government data)", "data_date": "",
        "notes": "Public, non-restricted National Register listings with status 'Listed' (removed listings dropped); districts appear as a single point. Website is the National Archives catalog record of the nomination. Five of the six school buildings are listed (Robeson is not) and are marked 'This school site'."})


def phmc_markers():
    api = "https://data.pa.gov/resource/xt8f-pzzz.json"
    d = json.loads(fetch("phmc_markers", api, {"$where": "county='Philadelphia'", "$limit": 5000}))
    rows = []
    for r in d:
        if clean(r.get("status")).lower() == "true":     # publisher: status False = "as far as we know the marker is in place"
            continue
        try:
            geom = Point(float(r["longitude"]), float(r["latitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        yr = clean(r.get("dedicateddate"))[:4]
        rows.append(rec(geom, "historic", "Pennsylvania historical marker", clean(r.get("name")), clean(r.get("location")), "", "",
                        joined(f"Dedicated {yr}" if yr else "", f"{clean(r.get('markertype'))} marker" if r.get("markertype") else "")))
    try:
        upd = json.loads(fetch("phmc_markers_meta", "https://data.pa.gov/api/views/xt8f-pzzz.json")).get("rowsUpdatedAt")
        data_date = f"rows last updated {datetime.fromtimestamp(upd, timezone.utc).date()}" if upd else ""
    except Exception:
        data_date = ""
    write("phmc_historical_markers", rows, {
        "title": "Pennsylvania Historical Markers", "publisher": "Pennsylvania Historical and Museum Commission (data.pa.gov)",
        "landing_url": "https://data.pa.gov/d/xt8f-pzzz", "api_url": api, "license": "Public Domain",
        "data_date": data_date, "notes": "PHMC historical markers in Philadelphia at the coordinates PHMC publishes; markers whose status is 'True' (known missing) left out."})


# ================================================================ civic & safety
def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def police():
    url = f"{CITY}/Police_Stations/FeatureServer/0"
    g = arcgis("police_stations", url, R_ASSET)
    rows = []
    for r in g.itertuples():
        n = int(r.dist_num) if pd.notna(r.dist_num) else None
        ph = clean(r.phone__)
        rows.append(rec(r.geometry, "civic_safety", "Police district station", f"{ordinal(n)} Police District" if n else "Police station",
                        clean(r.location), f"215-{ph}" if re.fullmatch(r"\d{3}-\d{4}", ph) else ph, "", ""))
    write("phl_police_stations", rows, {
        "title": "Police Stations (district headquarters)", "publisher": "City of Philadelphia, Philadelphia Police Department",
        "landing_url": "https://opendataphilly.org/datasets/police-stations/", "api_url": url + "/query", "license": CITY_LICENSE,
        "data_date": layer_date(url), "notes": "Police district headquarters; the published phone has no area code, so 215 was added. Some locations are given as intersections."})


def fire():
    url = f"{CITY}/Fire_Dept_Facilities/FeatureServer/0"
    g = arcgis("fire_dept_facilities", url, R_ASSET)
    rows = []
    for r in g.itertuples():
        units = []
        for lab, v in (("Engine", r.eng), ("Ladder", r.lad)):
            try:
                if int(v):
                    units.append(f"{lab} {int(v)}")
            except (TypeError, ValueError):
                pass
        extra = []
        if clean(r.med) and clean(r.med) not in ("0",):
            extra.append(f"Medic {clean(r.med)}")
        try:
            if int(r.bc):
                extra.append(f"Battalion {int(r.bc)}")
        except (TypeError, ValueError):
            pass
        rows.append(rec(r.geometry, "civic_safety", "Fire station", " / ".join(units) or "Fire station", nice(r.location), "", "", joined(*extra)))
    write("phl_fire_stations", rows, {
        "title": "Fire Department Facilities", "publisher": "City of Philadelphia, Philadelphia Fire Department",
        "landing_url": "https://opendataphilly.org/datasets/fire-department-facilities/", "api_url": url + "/query", "license": CITY_LICENSE,
        "data_date": layer_date(url), "notes": "Fire stations named by the engine and ladder companies housed there; medic and battalion units in detail (the layer's special-unit codes are not explained by the publisher and were left out). Most locations are given as intersections."})


ACCESS = {"F": "Building fully accessible", "A": "Alternate entrance", "B": "Building substantially accessible",
          "R": "Accessible with ramp", "M": "Building accessibility modified", "N": "Building not accessible"}
PARKING = {"N": "No parking", "L": "Loading zone", "H": "Handicap parking", "G": "General parking"}


def polling():
    url = f"{CITY}/POLLING_PLACES/FeatureServer/0"
    g = arcgis("polling_places", url, R_ASSET)
    rows = []
    if len(g):
        g["k"] = g.placename.map(lambda s: name_key(clean(s))) + "|" + g.street_address.map(lambda s: name_key(clean(s)))
        for _, grp in g.groupby("k"):
            r = grp.iloc[0]
            divs = sorted({f"{int(a):02d}-{int(b):02d}" for a, b in zip(grp.ward, grp.division) if pd.notna(a) and pd.notna(b)})
            acc, park = ACCESS.get(clean(r.accessibility_code)), PARKING.get(clean(r.parking_code))
            rows.append(rec(r.geometry, "civic_safety", "Polling place", nice(r.placename), nice(r.street_address), "", "",
                            joined(f"Ward-division {', '.join(divs)}" if divs else "", acc, park)))
    write("phl_polling_places", rows, {
        "title": "Polling Places", "publisher": "City of Philadelphia, City Commissioners (Philadelphia County Board of Elections)",
        "landing_url": "https://opendataphilly.org/datasets/polling-places/", "api_url": url + "/query", "license": CITY_LICENSE,
        "data_date": layer_date(url),
        "notes": "One point per polling place (divisions voting at the same place merged; ward-divisions in detail). Accessibility and parking codes spelled out from the City Commissioners' legend (vote.phila.gov polling place list). Polling places change between elections."})


# ================================================================ community organizations
def nac():
    url = f"{CITY}/NAC_Offices/FeatureServer/0"
    g = arcgis("nac_offices", url, R_ORG, out_fields="organization,street_address,zip_code,phone_number,website_url")
    rows = [rec(r.geometry, "community_orgs", "Neighborhood Advisory Committee", clean(r.organization),
                joined(one_line(r.street_address), f"Philadelphia, PA {clean(r.zip_code)}".strip(), sep=", "), clean(r.phone_number),
                clean(r.website_url), "") for r in g.itertuples()]
    write("phl_nac_offices", rows, {
        "title": "Neighborhood Advisory Committees (offices)", "publisher": "City of Philadelphia, Division of Housing and Community Development",
        "landing_url": "https://opendataphilly.org/datasets/neighborhood-advisory-committees-nacs/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "NAC office locations; organization phone and website kept, coordinator names and e-mails not requested."})


def friends():
    url = f"{CITY}/PPR_Friends_Groups/FeatureServer/0"
    g = arcgis("ppr_friends_groups", url, R_ORG, out_fields="friends_group_name,public_name,address,zip_code,contact_website")
    rows = [rec(r.geometry, "community_orgs", "Park friends group", clean(r.friends_group_name),
                joined(nice(one_line(r.address)), f"Philadelphia, PA {clean(r.zip_code)}", sep=", "), "", clean(r.contact_website),
                f"Supports {clean(r.public_name)}" if clean(r.public_name) else "") for r in g.itertuples()]
    write("phl_ppr_friends_groups", rows, {
        "title": "PPR Friends Groups", "publisher": "Philadelphia Parks & Recreation",
        "landing_url": "https://opendataphilly.org/datasets/ppr-friends-group/", "api_url": url + "/query", "license": CITY_LICENSE,
        "data_date": layer_date(url), "notes": "Volunteer friends groups, placed at the park they support; contact e-mails not requested."})


def display_addr(a: str) -> str:
    """An address field as text for the map: links, virtual-meeting details and 'mailing / otherwise' alternatives dropped."""
    t = re.sub(r"https?://\S+|\b\S+\.(?:com|org|us|net)/\S*", " ", one_line(a))
    t = re.split(r";|\bvirtual\b|\bzoom\b|passcode|meeting id|\bmailing\b|\bunless\b|\botherwise\b", t, flags=re.I)[0]
    t = clean(t).strip(" ,:-&")
    return t[:120]


def addr_key(a: str) -> str:
    s = street_part(a) or ""
    m = re.match(r"\s*(\d+)\D+?([A-Za-z0-9]+)", re.sub(r"\b[NSEW]\.?\s+", "", s))
    return f"{m.group(1)}{m.group(2).lower()}" if m else ""


def rcos():
    url = f"{CITY}/Zoning_RCO/FeatureServer/0"
    fields = "organization_name,organization_address,meeting_location_address,org_type,websites,expirationyear,primary_address,alternate_address"
    g = arcgis("zoning_rco", url, R_ORG * 1.5, out_fields=fields)
    g = g[site_dist_m(g.geometry).min(axis=1) <= R_ORG * 1.5].copy()   # candidates: boundaries within 3 miles of a site
    geocode_many([street_part(a) for a in pd.concat([g.organization_address, g.meeting_location_address])])
    rows, unplaced = [], []
    for r in g.itertuples():
        home = {addr_key(r.primary_address), addr_key(r.alternate_address)} - {""}
        office, meet = street_part(r.organization_address), street_part(r.meeting_location_address)
        xy, basis, addr = None, "", ""
        suite = bool(re.search(r"\b(Suite|Ste|Floor|Fl|Unit|Room|Rm)\b", one_line(r.organization_address), re.I))
        if office and (addr_key(r.organization_address) not in home or suite):    # a contact's own address only if it is a suite
            xy = geocode(office)
            if xy:
                basis, addr = "Mapped at its office address", display_addr(r.organization_address)
        if not xy and meet:
            xy = geocode(meet)
            if xy:
                basis, addr = "Mapped at its meeting place", display_addr(r.meeting_location_address)
        if xy:
            geom = Point(xy)
        else:
            geom = r.geometry.buffer(0).representative_point()
            basis = "Mapped inside its boundary (no public office or meeting address could be placed)"
            unplaced.append(clean(r.organization_name))
        covers = [s["short"] for s in SITES if r.geometry.buffer(0).contains(Point(s["lng"], s["lat"]))]
        typ = clean(r.org_type)
        rows.append(rec(geom, "community_orgs", "Registered Community Organization", clean(r.organization_name), addr, "",
                        clean(r.websites).split(" ")[0] if clean(r.websites) else "",
                        joined(f"Type: {typ}" if typ and typ.lower() != "other" else "", f"Boundary covers the {', '.join(covers)} site" if covers else "", basis,
                               f"Registered through {clean(r.expirationyear)}" if clean(r.expirationyear) else "")))
    write("phl_rco_offices", rows, {
        "title": "Registered Community Organizations (office or meeting point)", "publisher": "City of Philadelphia, Philadelphia City Planning Commission",
        "landing_url": "https://opendataphilly.org/datasets/registered-community-organizations-rco-boundaries/", "api_url": url + "/query",
        "license": CITY_LICENSE, "data_date": layer_date(url),
        "notes": "Each RCO placed at its organization address with the US Census geocoder; when that is a PO box, cannot be matched, or is the same as a contact person's own address (and not a suite or floor in an office building), its meeting place is used instead, and failing both a point inside its boundary (detail says which). Only name, type, website and which school sites the boundary covers are kept; no contact names, e-mails or phones."})
    if unplaced:
        print(f"    RCOs placed inside their boundary: {len(unplaced)}")


def pacdc():
    kml_url = "https://www.google.com/maps/d/kml"
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    root = ET.fromstring(fetch("pacdc_member_map", kml_url, {"mid": "1MNPGrcyP-aqpqtswG5f_vpvs5XAyEnM", "forcekml": "1"}).encode())
    members = []
    for fo in root.iter("{http://www.opengis.net/kml/2.2}Folder"):
        if clean(fo.findtext("k:name", namespaces=ns)) != "CDC Members":
            continue                                  # 'Associate Members' are banks, firms and consultants
        for p in fo.findall("k:Placemark", ns):
            ex = {d.get("name"): clean(d.findtext("k:value", namespaces=ns)) for d in p.iter("{http://www.opengis.net/kml/2.2}Data")}
            ex["name"] = clean(p.findtext("k:name", namespaces=ns))
            ex["query"] = street_part(joined(ex.get("Street Address", ""), ex.get("City", ""),
                                             joined(ex.get("State", ""), ex.get("Zip Code", ""), sep=" "), sep=", "))
            members.append(ex)
    geocode_many([m["query"] for m in members])
    rows, missed = [], []
    for ex in members:
        xy = geocode(ex["query"]) if ex["query"] else None
        if not xy:
            missed.append(ex["name"])
            continue
        rows.append(rec(Point(xy), "community_orgs", "Community development corporation", ex["name"],
                        joined(ex.get("Street Address", ""), ex.get("Suite", ""), ex.get("City", ""), sep=", "), ex.get("Phone", ""),
                        ex.get("Website", ""), "PACDC member"))
    write("pacdc_cdc_members", rows, {
        "title": "PACDC member CDCs", "publisher": "Philadelphia Association of Community Development Corporations (PACDC)",
        "landing_url": "https://pacdc.org/members-list/", "api_url": f"{kml_url}?mid=1MNPGrcyP-aqpqtswG5f_vpvs5XAyEnM&forcekml=1",
        "license": "No license stated; published by PACDC as its public member map", "data_date": "",
        "notes": "The 'CDC Members' layer of PACDC's public member map (Associate Members such as banks and consultants left out), placed with the US Census geocoder from the street address PACDC lists. Organization phone and website kept."
                 + (f" Not matched by the geocoder: {', '.join(missed)}." if missed else "")})


# ================================================================ main
if __name__ == "__main__":
    print(f"civic inventory — {len(SITES)} sites, cache {CACHE.relative_to(ROOT)}{' (refresh)' if REFRESH else ''}")
    for fn in (percent_for_art, ppr_art, city_landmarks, city_facilities, osm_arts,
               philreg, districts, national_register, phmc_markers,
               police, fire, polling,
               rcos, nac, friends, pacdc, osm_community_centres,
               osm_worship):
        run(fn)
    order = [m["id"] for m in MANIFEST]
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=1, ensure_ascii=False))
    for f in OUT.glob("*.geojson"):                   # stale outputs from datasets no longer produced
        if f.stem not in order:
            f.unlink()
    print(f"\nwrote {len(MANIFEST)} datasets to {OUT.relative_to(ROOT)}")
    if ELSEWHERE:
        print(f"\nfor other domains ({len(ELSEWHERE)}):\n  " + "\n  ".join(sorted(set(ELSEWHERE))))
    if FAILED:
        print("\nFAILED:\n  " + "\n  ".join(FAILED))
        sys.exit(1)
