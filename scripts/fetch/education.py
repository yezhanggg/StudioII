"""Education domain asset pull: schools, early childhood, libraries, youth, higher education.

Collects points within 1.5 miles (2,414 m) of any of the six studio sites in scripts/fetch/schools.json and
writes one GeoJSON per source dataset plus manifest.json to scripts/fetch/out/education/ (see CONTRACT.md).

Run (from the repo root):
    uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/education.py
Add --refresh to ignore the raw-response cache in scripts/.cache/fetch/education/.

The six candidate schools themselves are left out of the school lists. Programs that operate inside one of
those buildings (a Head Start classroom, an after-school provider) are kept, and their `detail` starts with
"At the <site> school site" so the map can tell them apart.
"""
import io
import json
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
FETCH = ROOT / "scripts" / "fetch"
OUT = FETCH / "out" / "education"
CACHE = ROOT / "scripts" / ".cache" / "fetch" / "education"
REFRESH = "--refresh" in sys.argv
TODAY = date.today().isoformat()
UA = {"User-Agent": "studio-community-maps/1.0"}
RADIUS_M = 2414.0          # 1.5 miles
DEDUPE_M = 40.0            # contract: same name within 40 m is a duplicate
MILE_M = 1609.344
UTM = 32618                # WGS 84 / UTM 18N, metres

CITY = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
NCES = "https://nces.ed.gov/opengis/rest/services"
PA = "https://data.pa.gov"
AIS = "https://api.phila.gov/ais/v1/search/"
CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
SDP_PREK = "https://cdn.philasd.org/offices/performance/Open_Data/School_Information/Pre_K/PRE_K_Information_2023-2024.xlsx"

CITY_LICENSE = "City of Philadelphia License (OpenDataPhilly)"
CITY_AGO_LICENSE = "Not stated on the item (public City of Philadelphia ArcGIS Online layer)"
FED_LICENSE = "Public domain (U.S. federal government data)"
OSM_LICENSE = "ODbL 1.0, (c) OpenStreetMap contributors"

SITES = json.loads((FETCH / "schools.json").read_text())
SITE_PTS = gpd.GeoSeries([Point(s["lng"], s["lat"]) for s in SITES], crs=4326).to_crs(UTM)
AREA_UTM = unary_union([p.buffer(RADIUS_M) for p in SITE_PTS])
AREA = gpd.GeoSeries([AREA_UTM], crs=UTM).to_crs(4326).iloc[0]
BBOX = AREA.bounds  # (minx, miny, maxx, maxy) in lon/lat

# the candidate schools, matched by name (and only near their own site)
SELF = {"wagner": r"\bWAGNER\b", "blankenburg": r"BLANKENBURG", "robeson": r"ROBESON", "pennypacker": r"PENNYPACKER",
        "fitler": r"FITLER", "amynw": r"ACADEMY FOR THE MIDDLE YEARS|\bAMY\b"}
SELF_M = 150.0

CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- download helpers (raw responses cached)

def cached(name, fetch):
    f = CACHE / name
    if f.exists() and not REFRESH:
        return json.loads(f.read_text())
    data = fetch()
    f.write_text(json.dumps(data))
    return data


def cached_bytes(name, url):
    f = CACHE / name
    if not f.exists() or REFRESH:
        f.write_bytes(http("GET", url, raw=True))
    return f.read_bytes()


def http(method, url, raw=False, tries=5, **kw):
    last = None
    for i in range(tries):
        try:
            r = requests.request(method, url, headers=UA, timeout=180, **kw)
            if 400 <= r.status_code < 500 and r.status_code not in (404, 408, 429):
                raise RuntimeError(f"{url}: HTTP {r.status_code} {r.text[:300]}")      # a bad request will not get better
            r.raise_for_status()
            return r.content if raw else r.json()
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001 - retry any network / decode failure
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def arcgis_meta(layer_url, cache_name):
    return cached(cache_name + "_meta.json", lambda: http("GET", layer_url, params={"f": "json"}))


def last_edit(meta):
    ms = (meta.get("editingInfo") or {}).get("lastEditDate") or (meta.get("editingInfo") or {}).get("dataLastEditDate")
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat() if ms else ""


def arcgis_near(layer_url, cache_name, where="1=1"):
    """Features of an ArcGIS layer within RADIUS_M of any site (one distance query per site), as GeoJSON-like dicts."""
    def fetch():
        feats = {}
        for s in SITES:
            offset = 0
            while True:
                j = http("GET", f"{layer_url}/query", params={
                    "where": where, "geometry": f"{s['lng']},{s['lat']}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects", "distance": RADIUS_M, "units": "esriSRUnit_Meter",
                    "outFields": "*", "outSR": 4326, "f": "json", "resultOffset": offset, "resultRecordCount": 1000})
                if "error" in j:
                    raise RuntimeError(f"{layer_url}: {j['error']}")
                for f in j.get("features", []):
                    a = f["attributes"]
                    k = a.get("objectid", a.get("OBJECTID", a.get("ObjectId", a.get("FID", json.dumps(a, sort_keys=True)))))
                    feats[str(k)] = {"attributes": a, "geometry": f.get("geometry")}
                if not j.get("exceededTransferLimit"):
                    break
                offset += len(j.get("features", []))
        return list(feats.values())
    return cached(cache_name + ".json", fetch)


def esri_geom(g):
    """Esri JSON geometry (outSR 4326) -> shapely geometry."""
    if not g:
        return None
    if "x" in g:
        return Point(g["x"], g["y"]) if g["x"] is not None else None
    if "rings" in g:
        return shape({"type": "Polygon", "coordinates": g["rings"]}).buffer(0)
    if "paths" in g:
        return shape({"type": "MultiLineString", "coordinates": g["paths"]})
    return None


def socrata_view(dsid):
    return cached(f"pa_{dsid}_view.json", lambda: http("GET", f"{PA}/api/views/{dsid}.json"))


def socrata_near(dsid, geocol, cache_name, where=None):
    """Rows of a data.pa.gov dataset within RADIUS_M of any site (within_circle per site), de-duplicated by row id."""
    def fetch():
        rows = {}
        for s in SITES:
            w = f"within_circle({geocol}, {s['lat']}, {s['lng']}, {int(RADIUS_M)})" + (f" AND {where}" if where else "")
            for r in http("GET", f"{PA}/resource/{dsid}.json", params={"$select": ":*, *", "$where": w, "$limit": 50000}):
                rows[r[":id"]] = r
        return list(rows.values())
    return cached(cache_name + ".json", fetch)


def socrata_date(dsid):
    v = socrata_view(dsid)
    t = v.get("rowsUpdatedAt") or v.get("viewLastModified")
    return datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat() if t else ""


def overpass(query, cache_name):
    def fetch():
        last = None
        for attempt in range(8):                     # Overpass is busy at times: back off, alternate with the mirror
            url = OVERPASS[attempt % 2]
            try:
                r = requests.post(url, data={"data": query}, headers=UA, timeout=240)
                r.raise_for_status()
                j = r.json()
                if "runtime error" in (j.get("remark") or ""):
                    raise RuntimeError(j["remark"])
                return j
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(15 * (attempt + 1))
        raise RuntimeError(f"Overpass failed: {last}")
    return cached(cache_name + ".json", fetch)


# ---------------------------------------------------------------- text helpers

def clean(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        if v.is_integer():
            v = int(v)
    s = re.sub(r"\s+", " ", str(v)).strip()
    return "" if s.lower() in ("nan", "none", "null", "<na>", "n/a") else s


ACRONYMS = {"YMCA", "YWCA", "PAL", "CDC", "LLC", "II", "III", "IV", "VI", "PA", "KIPP", "ASPIRA", "GPY", "YOACAP", "ASASP", "ECE",
            "STEM", "PHL", "CS", "HS", "CCP", "AME", "USA", "OST", "PHMC", "HSSAP", "PKC", "LEAP", "AMY", "MYA", "FCCH", "GCCH",
            "CDLC", "YEP", "DBA", "UPENN", "STEAM", "LC", "ELC", "CHOP", "SDP", "AVTS", "MLK", "ABC", "PEC", "WES", "YESPhilly",
            "KKC", "TLC", "NE", "NW", "SW", "SE", "PO", "LLP", "CTE", "ESL", "GED", "UMOJA", "ASAS"}
SMALL = {"of", "and", "the", "at", "for", "on", "in", "a", "an", "to", "by", "de", "la", "del", "y"}


def title(s):
    """Readable names: title case for ALL-CAPS or all-lower text, keeping acronyms."""
    s = clean(s)
    letters = [c for c in s if c.isalpha()]
    mostly_caps = letters and sum(c.isupper() for c in letters) / len(letters) >= 0.7    # 'YOUNG aCHIEVERS ...', 'SHAs LITTLE ...'
    if not s or not (s.isupper() or s.islower() or mostly_caps):
        return s
    s = s.upper() if mostly_caps else s
    out = []
    for i, w in enumerate(re.split(r"(\s+|-|/|\(|\))", s)):
        if not w or re.fullmatch(r"\s+|-|/|\(|\)", w):
            out.append(w)
            continue
        up = w.upper()
        if up in ACRONYMS:
            out.append(up)
        elif re.fullmatch(r"\d+(ST|ND|RD|TH)", up):
            out.append(w.lower())
        elif i > 0 and w.lower() in SMALL:
            out.append(w.lower())
        else:
            t = w.capitalize()
            t = re.sub(r"^Mc(\w)", lambda m: "Mc" + m.group(1).upper(), t)
            t = re.sub(r"^O'(\w)", lambda m: "O'" + m.group(1).upper(), t)
            out.append(t)
    s = "".join(out).replace("'S ", "'s ")
    s = re.sub(r"'S$", "'s", s)
    return s[:1].upper() + s[1:]


def address(*parts):
    """'street, City, PA ZIP' from loose parts (street, city, state, zip)."""
    street, city, state, zipc = (list(parts) + ["", "", "", ""])[:4]
    street, city, state = title(street), title(city), clean(state)
    zipc = clean(zipc)[:5]
    state = {"PENNSYLVANIA": "PA", "Pennsylvania": "PA"}.get(state, state)
    tail = " ".join(x for x in (state, zipc) if x)
    return ", ".join(x for x in (street, city, tail) if x)


def phone(v):
    s = clean(v)
    d = re.sub(r"\D", "", s)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else (s if d else "")


STOP_TOKS = {"the", "of", "inc", "and", "at", "a", "philadelphia", "phila", "school", "schools", "sch", "academy", "st", "saint",
             "christian", "day", "elementary", "high", "learning", "center", "incorporated"}


def _toks(n):
    return {t for t in re.findall(r"[a-z0-9]+", clean(n).lower().replace("&", " and ")) if t not in STOP_TOKS}


def expand_school(n):
    """NCES short forms: 'Belmont Hills El Sch' -> 'Belmont Hills Elementary School', 'Cheltenham HS' -> 'Cheltenham High School'."""
    n = re.sub(r"\bEl Sch\b", "Elementary School", n)
    n = re.sub(r"\bSch\b", "School", n)
    n = re.sub(r"\bHS$", "High School", n)
    n = re.sub(r"\bMS$", "Middle School", n)
    return n


def site_name(n):
    """City OST site names written 'Pennypacker, Samuel Sch' -> 'Samuel Pennypacker School'."""
    m = re.match(r"^([A-Za-z.' ]+), ([A-Za-z.' ]+?)(?: (Sch|School|Elementary|Elem|El))?$", n)
    if not m or re.search(r"\b(Inc|LLC|Corp|Co)\b", m.group(2)) or len(m.group(1).split()) > 3 or len(m.group(2).split()) > 2:
        return n
    suffix = {"Sch": "School", "Elem": "Elementary", "El": "Elementary"}.get(m.group(3), m.group(3) or "")
    return " ".join(x for x in (m.group(2), m.group(1), suffix) if x)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", clean(s).lower())


def addr_key(s):
    """'1701 W Chelten Avenue' -> '1701 CHELTEN' (house number + street name, no direction or suffix)."""
    m = re.match(r"\s*(\d+)[-\d]*\s+(?:(?:N|S|E|W|NORTH|SOUTH|EAST|WEST)\.?\s+)?([A-Z0-9]+)", clean(s).upper())
    return f"{m.group(1)} {m.group(2)}" if m else ""


SITE_ADDR = {s["slug"]: addr_key(s["address"]) for s in SITES}


def at_site(name, lon, lat, addr=""):
    """Slug of the candidate site this record sits on (by name near the site, or by the site's street address)."""
    p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(UTM).iloc[0]
    for s, sp in zip(SITES, SITE_PTS):
        d = p.distance(sp)
        if d <= SELF_M and re.search(SELF[s["slug"]], clean(name).upper()):
            return s["slug"]
        if d <= SELF_M and addr and addr_key(addr) and addr_key(addr) == SITE_ADDR[s["slug"]]:
            return s["slug"]
    return None


SHORT = {s["slug"]: s["short"] for s in SITES}


def site_note(slug):
    return f"At the {SHORT[slug]} school site" if slug else ""


def join(*parts, sep=" · "):
    return sep.join(p for p in (clean(x) for x in parts) if p)


# ---------------------------------------------------------------- output

PROPS = ["category", "kind", "name", "address", "phone", "website", "detail"]
MANIFEST = []
SUMMARY = []


def write(ds, recs, meta):
    """Standardize, keep records within RADIUS_M of a site, drop same-name duplicates within DEDUPE_M, write GeoJSON."""
    recs = [r for r in recs if r.get("lon") is not None and r.get("lat") is not None]
    if recs:
        g = gpd.GeoDataFrame(recs, geometry=[Point(r["lon"], r["lat"]) for r in recs], crs=4326)
        gu = g.to_crs(UTM)
        dist = pd.concat([gu.distance(p) for p in SITE_PTS], axis=1)
        g = g[(dist.min(axis=1) <= RADIUS_M).values].copy()
        gu = gu.loc[g.index]
        keep, seen = [], []
        for i, r in g.iterrows():
            n, p = norm(r["name"]), gu.geometry[i]
            dup = any(n and (n == k or (len(min(n, k, key=len)) >= 6 and (n in k or k in n))) and p.distance(q) <= DEDUPE_M for k, q in seen)
            if not dup:
                keep.append(i)
                seen.append((n, p))
        g = g.loc[keep]
        miles = {s["slug"]: (g.to_crs(UTM).distance(sp) / MILE_M) for s, sp in zip(SITES, SITE_PTS)}
    else:
        g = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=4326)
        miles = {s["slug"]: pd.Series(dtype=float) for s in SITES}
    feats = []
    for _, r in g.iterrows():
        props = {k: clean(r.get(k, "")) for k in PROPS}
        props["source_id"] = ds
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [round(r.geometry.x, 6), round(r.geometry.y, 6)]}})
    (OUT / f"{ds}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=None))
    entry = {"id": ds, **meta, "retrieved": TODAY, "records": len(feats)}
    order = ["id", "title", "categories", "publisher", "landing_url", "api_url", "license", "retrieved", "data_date", "records", "notes"]
    MANIFEST.append({k: entry.get(k, "") for k in order})
    w1 = int((miles["wagner"] <= 1).sum()) if len(g) else 0
    b1 = int((miles["blankenburg"] <= 1).sum()) if len(g) else 0
    SUMMARY.append((ds, len(feats), w1, b1))
    print(f"  {ds}: {len(feats)} records (within 1 mi: Wagner {w1}, Blankenburg {b1})")


def rec(category, kind, name, addr, lon, lat, phone_="", website="", detail=""):
    return {"category": category, "kind": kind, "name": name, "address": addr, "phone": phone_, "website": website,
            "detail": detail, "lon": lon, "lat": lat}


# ================================================================ schools

def phl_schools():
    url = f"{CITY}/Schools/FeatureServer/0"
    meta = arcgis_meta(url, "phl_schools")
    kinds = {"DISTRICT": "District school", "CHARTER": "Charter school", "PRIVATE": "Private school",
             "ARCHDIOCESE": "Archdiocese (Catholic) school", "CONTRACTED": "District-contracted school"}
    out, dropped = [], []
    for f in arcgis_near(url, "phl_schools"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        name = title(a.get("school_name_label") or a.get("school_name"))
        raw_names = f"{clean(a.get('school_name'))} {clean(a.get('school_name_label'))}"
        if at_site(raw_names, g.x, g.y):
            dropped.append(name)
            continue
        n = a.get("enrollment")
        grades = re.sub(r"PREK", "Pre-K", clean(a.get("grade_org")).upper())
        detail = join(f"Grades {grades}" if grades else "",
                      f"{int(n):,} students" if isinstance(n, (int, float)) and n == n and n > 0 else "")
        out.append(rec("schools", kinds.get(clean(a.get("type_specific")).upper(), "School"), name,
                       address(a.get("street_address"), "Philadelphia", "PA", a.get("zip_code")), g.x, g.y,
                       phone(a.get("phone_number")), "", detail))
    write("phl_schools", out, {
        "title": "Schools (district, charter, private, Archdiocese)", "categories": ["schools"],
        "publisher": "City of Philadelphia, Department of Planning and Development",
        "landing_url": "https://opendataphilly.org/datasets/schools/", "api_url": f"{url}/query", "license": CITY_LICENSE,
        "data_date": f"layer last edited {last_edit(meta)}" if last_edit(meta) else "",
        "notes": f"All school points in the City layer; the candidate schools themselves were left out ({', '.join(sorted(dropped))}). "
                 "Enrollment and grades are as the City layer states them; the layer covers Philadelphia only."})


def nces_k12():
    """NCES school points for schools the City layer cannot have: those outside Philadelphia (city-line sites)."""
    # public schools: Common Core of Data 2024-25 (administrative data layer has grades, phone, enrollment)
    url = f"{NCES}/K12_School_Locations/EDGE_ADMINDATA_PUBLICSCH_2425/MapServer/1"
    out = []
    for f in arcgis_near(url, "nces_ccd_public_2425"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None or clean(a.get("CNTY")) == "42101" or clean(a.get("VIRTUAL")).lower().startswith("full"):
            continue
        if clean(a.get("SY_STATUS_TEXT")) and not re.search(r"open|operational|new|added|changed|reopened", clean(a.get("SY_STATUS_TEXT")), re.I):
            continue
        lo, hi = clean(a.get("GSLO")), clean(a.get("GSHI"))
        n = a.get("MEMBER") if isinstance(a.get("MEMBER"), (int, float)) and a.get("MEMBER", -1) > 0 else a.get("TOTAL")
        lo, hi = ("K" if lo == "KG" else "Pre-K" if lo == "PK" else lo.lstrip("0") or lo), (hi.lstrip("0") or hi)
        detail = join(re.sub(r"\bSD$", "School District", title(a.get("LEA_NAME"))), f"Grades {lo}-{hi}" if lo and hi else "",
                      f"{int(n):,} students" if isinstance(n, (int, float)) and n == n and n > 0 else "")
        kind = "Charter school" if clean(a.get("CHARTER_TEXT")).lower() == "yes" else "Public school"
        out.append(rec("schools", kind, expand_school(title(a.get("SCH_NAME"))), address(a.get("LSTREET1"), a.get("LCITY"), a.get("LSTATE"), a.get("LZIP")),
                       g.x, g.y, phone(a.get("PHONE")), "", detail))
    write("nces_ccd_public_schools_outside_phl", out, {
        "title": "Public school locations outside Philadelphia, 2024-25 (NCES Common Core of Data)", "categories": ["schools"],
        "publisher": "U.S. Department of Education, National Center for Education Statistics (EDGE / CCD)",
        "landing_url": "https://nces.ed.gov/programs/edge/Geographic/SchoolLocations", "api_url": f"{url}/query", "license": FED_LICENSE,
        "data_date": "school year 2024-25",
        "notes": "Only schools outside Philadelphia County (the City Schools layer stops at the city line); full-time virtual schools and "
                 "closed schools were left out."})

    # private schools: Private School Survey 2023-24
    url = f"{NCES}/K12_School_Locations/EDGE_GEOCODE_PRIVATESCH_2324/MapServer/0"
    city = [(esri_geom(f["geometry"]), _toks(f"{f['attributes'].get('school_name_label')} {f['attributes'].get('school_name')}"))
            for f in arcgis_near(f"{CITY}/Schools/FeatureServer/0", "phl_schools") if f.get("geometry")]
    city = [(gpd.GeoSeries([g], crs=4326).to_crs(UTM).iloc[0], t) for g, t in city if g is not None]
    out, n_city = [], 0
    for f in arcgis_near(url, "nces_pss_private_2324"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        name = title(a.get("NAME"))
        in_phl = clean(a.get("NMCNTY")).lower().startswith("philadelphia")
        if in_phl:
            p, t = gpd.GeoSeries([g], crs=4326).to_crs(UTM).iloc[0], _toks(a.get("NAME"))
            if any(p.distance(q) <= 80 or (p.distance(q) <= 400 and t and kt and len(t & kt) >= max(1, min(len(t), len(kt)) / 2))
                   for q, kt in city):
                continue                                  # already in the City Schools layer
            if at_site(a.get("NAME"), g.x, g.y, a.get("STREET")):
                continue
            n_city += 1
        out.append(rec("schools", "Private school", name, address(a.get("STREET"), a.get("CITY"), a.get("STATE"), a.get("ZIP")),
                       g.x, g.y, "", "", "" if not in_phl else "listed by NCES; not in the City Schools layer"))
    write("nces_pss_private_schools", out, {
        "title": "Private school locations, 2023-24 (NCES Private School Survey), gap fill", "categories": ["schools"],
        "publisher": "U.S. Department of Education, National Center for Education Statistics (EDGE / PSS)",
        "landing_url": "https://nces.ed.gov/programs/edge/Geographic/SchoolLocations", "api_url": f"{url}/query", "license": FED_LICENSE,
        "data_date": "school year 2023-24",
        "notes": "Only private schools the City Schools layer does not have: those outside Philadelphia, and Philadelphia schools with no City "
                 "point of a similar name within 400 m (or any school within 80 m). The survey lists schools teaching at least one of grades K-12 "
                 "(some may have closed since 2023-24); this layer gives no grade span or enrollment."})


# ================================================================ early childhood

def star(v):
    v = clean(v)
    m = re.match(r"STAR\s*(\d)(.*)", v)
    if not m:
        return ""
    return f"Keystone STAR {m.group(1)}" + (" (accredited)" if "ACC" in m.group(2).upper() else "")


def pa_child_care():
    dsid = "ajn5-kaxt"
    rows = socrata_near(dsid, "geocoded_column", "pa_dhs_child_care")
    view = socrata_view(dsid)
    kinds = {"Child Care Center": "Child care center", "Group Child Care Home": "Group child care home",
             "Family Child Care Home": "Family child care home"}
    ec, sa = [], []
    n_other, n_sa = 0, 0
    for r in rows:
        gc = r.get("geocoded_column")
        if not gc:
            continue
        lon, lat = gc["coordinates"]
        ptype = clean(r.get("provider_type"))
        hs, ehs = clean(r.get("federal_head_start")) == "Yes", clean(r.get("federal_early_head_start")) == "Yes"
        programs = [p for p, flag in (("Pre-K Counts", r.get("pa_pre_k_counts")), ("Head Start", r.get("federal_head_start")),
                                      ("Early Head Start", r.get("federal_early_head_start")),
                                      ("Head Start Supplemental", r.get("head_start_state_supplemental"))) if clean(flag) == "Yes"]
        cap = clean(r.get("capacity"))
        name = title(r.get("facility_name"))
        addr = address(join(r.get("facility_address"), r.get("facility_address_continued"), sep=" "), r.get("facility_city"),
                       r.get("facility_state"), r.get("facility_zip_code"))
        here = at_site(name, lon, lat, r.get("facility_address"))
        if cap == "School Age Provider":
            n_sa += 1
            sa.append(rec("youth", "Licensed school-age program", name, addr, lon, lat, phone(r.get("facility_phone")), "",
                          join(site_note(here), "before/after-school care for school-age children", star(r.get("star_level")))))
            continue
        if ptype in kinds:
            home = ptype != "Child Care Center"   # homes are residences: no phone (a private person's number)
            ec.append(rec("early_childhood", kinds[ptype], name, addr, lon, lat, "" if home else phone(r.get("facility_phone")), "",
                          join(site_note(here), star(r.get("star_level")), f"licensed capacity {cap}" if cap.isdigit() else "",
                               " + ".join(programs))))
        elif ptype == "Other" and (hs or ehs):
            home = bool(re.search(r"FCCH|Family|Home\b", name, re.I))   # Head Start partner run from a residence: no phone
            ec.append(rec("early_childhood", "Head Start site", name, addr, lon, lat, "" if home else phone(r.get("facility_phone")), "",
                          join(site_note(here), "federal Head Start program location (not a DHS-licensed facility)")))
        else:
            n_other += 1
    data_date = f"monthly list, rows updated {socrata_date(dsid)}"
    common = {"publisher": "Pennsylvania Department of Human Services, Office of Child Development and Early Learning (OCDEL)",
              "landing_url": f"{PA}/d/{dsid}", "api_url": f"{PA}/resource/{dsid}.json",
              "license": (view.get("license") or {}).get("name", ""), "data_date": data_date}
    write("pa_dhs_child_care_providers", ec, {
        "title": "Child care providers including early learning programs (PA DHS certified facilities)", "categories": ["early_childhood"], **common,
        "notes": "Certified child care centers, group homes and family homes, plus federal Head Start locations the list carries as provider type "
                 f"'Other'; {n_other} other 'Other' rows (private academic school programs) and the school-age-only providers were left out "
                 "(the latter are in pa_dhs_school_age_child_care). Family and group homes are residences: facility name and address as "
                 "published, no phone, no owner names."})
    write("pa_dhs_school_age_child_care", sa, {
        "title": "School-age child care providers (PA DHS certified, school-age only)", "categories": ["youth"], **common,
        "notes": "Providers in the same PA DHS list whose capacity is 'School Age Provider', i.e. licensed before/after-school programs "
                 "for school-age children only; kept as out-of-school-time assets."})


def phlprek():
    url = f"{CITY}/PHLpreKenrollment_FY25/FeatureServer/0"
    meta = arcgis_meta(url, "phl_phlprek_fy25")
    out = []
    for f in arcgis_near(url, "phl_phlprek_fy25"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        name = title(a.get("Site_Name"))
        slots, enr = a.get("FY25_Slot_Count"), a.get("FY25_Enrollment_12_2_24")
        here = at_site(name, g.x, g.y, a.get("Address"))
        detail = join(site_note(here), f"FY25: {int(slots)} PHLpreK slots" if isinstance(slots, (int, float)) else "",
                      f"{int(enr)} enrolled (Dec 2, 2024)" if isinstance(enr, (int, float)) else "")
        out.append(rec("early_childhood", "PHLpreK site", name, address(a.get("Address"), "Philadelphia", "PA", a.get("ZIP_Code")),
                       g.x, g.y, "", "", detail))
    write("phl_phlprek_sites_fy25", out, {
        "title": "PHLpreK program sites, FY25 enrollment", "categories": ["early_childhood"],
        "publisher": "City of Philadelphia, Office of Children and Families (PHLpreK), published by PhillyStat 360",
        "landing_url": "https://www.arcgis.com/home/item.html?id=c6ffe18c08684f5eab1192b5a0516ac4", "api_url": f"{url}/query",
        "license": CITY_AGO_LICENSE,
        "data_date": f"FY25 slots and enrollment as of 2024-12-02 (layer last edited {last_edit(meta)})",
        "notes": "Every PHLpreK provider site in the layer. It is the most recent public PHLpreK site list found (FY25); sites added or "
                 "dropped since then are not reflected."})


def prek_counts():
    dsid = "pgbt-5wid"
    view = socrata_view(dsid)
    latest = cached("pa_pkc_hssap_latest.json", lambda: http("GET", f"{PA}/resource/{dsid}.json", params={"$select": "max(date) as d"}))[0]["d"]
    rows = socrata_near(dsid, "geocoded_column_1", "pa_pkc_hssap", where=f"date = '{latest}'")
    grouped = {}
    for r in rows:
        gc = r.get("geocoded_column_1")
        if not gc:
            continue
        k = (norm(r.get("location_name")), norm(r.get("street_address")))
        e = grouped.setdefault(k, {"r": r, "slots": {}})
        g = clean(r.get("grant"))
        try:
            e["slots"][g] = e["slots"].get(g, 0) + int(float(r.get("total_funded_slots") or 0))
        except ValueError:
            pass
    out, fy = [], ""
    for e in grouped.values():
        r = e["r"]
        lon, lat = r["geocoded_column_1"]["coordinates"]
        fy = clean(r.get("fiscal_year")) or fy
        grants = sorted(e["slots"])
        has_pkc, has_hs = any("PKC" in g for g in grants), any("HSSAP" in g for g in grants)
        kind = ("Pre-K Counts and HSSAP site" if has_pkc and has_hs else "Pre-K Counts site" if has_pkc
                else "Head Start Supplemental (HSSAP) site" if has_hs else "State-funded pre-K site")
        name = title(r.get("location_name"))
        here = at_site(name, lon, lat, r.get("street_address"))
        slots = join(*[f"{'Pre-K Counts' if 'PKC' in g else 'HSSAP' if 'HSSAP' in g else g} {n} funded slots" for g, n in sorted(e["slots"].items())])
        lead = clean(r.get("lead_agency_name"))
        out.append(rec("early_childhood", kind, name, address(r.get("street_address"), r.get("city"), r.get("state"), r.get("zip_code")),
                       lon, lat, "", "", join(site_note(here), clean(r.get("fiscal_year")), slots,
                                              f"lead agency: {title(lead)}" if lead and norm(lead) != norm(r.get("location_name")) else "")))
    write("pa_ocdel_prek_counts_hssap", out, {
        "title": "Pre-K Counts and Head Start Supplemental Assistance Program (HSSAP) funded locations", "categories": ["early_childhood"],
        "publisher": "Pennsylvania Department of Education, Office of Child Development and Early Learning (OCDEL)",
        "landing_url": f"{PA}/d/{dsid}", "api_url": f"{PA}/resource/{dsid}.json", "license": (view.get("license") or {}).get("name", ""),
        "data_date": f"{fy} funding (quarter ending {latest[:10]})",
        "notes": "Only the latest funding quarter; one point per location, with its Pre-K Counts and HSSAP slots combined. Includes "
                 "School District of Philadelphia classrooms that are not DHS-licensed child care."})


def xlsx_sheets(blob):
    """Minimal .xlsx reader (stdlib only): {sheet name: list of row lists}."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", ns):
        target = rels[sh.get(f"{{{ns['r']}}}id")].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter(f"{{{ns['m']}}}row"):
            vals = {}
            for c in row.findall("m:c", ns):
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                idx = 0
                for ch in col:
                    idx = idx * 26 + ord(ch) - 64
                v = c.find("m:v", ns)
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
                else:
                    val = v.text if v is not None else ""
                vals[idx - 1] = val
            rows.append([vals.get(i, "") for i in range(max(vals) + 1)] if vals else [])
        out[sh.get("name")] = rows
    return out


def geocode(addr):
    """City AIS first (official Philadelphia address index), Census geocoder as fallback. Cached."""
    memo_f = CACHE / "geocode.json"
    memo = json.loads(memo_f.read_text()) if memo_f.exists() else {}
    if addr in memo and not REFRESH:
        return memo[addr]
    street = addr.split(",")[0]
    xy = None
    try:
        j = http("GET", AIS + quote(street), params={"srid": 4326}, tries=2)
        if j.get("features"):
            xy = j["features"][0]["geometry"]["coordinates"][:2]
    except RuntimeError:
        pass
    if xy is None:
        try:
            m = http("GET", CENSUS_GEOCODER, params={"address": addr, "benchmark": "Public_AR_Current", "format": "json"}, tries=2)["result"]["addressMatches"]
            xy = [m[0]["coordinates"]["x"], m[0]["coordinates"]["y"]] if m else None
        except (RuntimeError, KeyError, IndexError):
            xy = None
    memo[addr] = xy
    memo_f.write_text(json.dumps(memo, indent=1))
    return xy


def sdp_prek():
    sheets = xlsx_sheets(cached_bytes("sdp_prek_information_2023_2024.xlsx", SDP_PREK))
    year = max(sheets)                                   # the workbook carries 2023-2024 and 2024-2025 sheets
    rows = [r for r in sheets[year] if any(clean(x) for x in r)]
    hdr = [clean(h).upper() for h in rows[0]]
    out, missed = [], []
    for row in rows[1:]:
        a = dict(zip(hdr, row + [""] * (len(hdr) - len(row))))
        name = clean(a.get("SCHOOL_NAME"))
        street = clean(a.get("ADDRESS"))
        if not name or not street:
            continue
        full = f"{street}, {clean(a.get('CITY')) or 'Philadelphia'}, {clean(a.get('STATE')) or 'PA'} {clean(a.get('ZIP_CODE'))[:5]}"
        xy = geocode(full)
        if not xy:
            missed.append(name)
            continue
        up = name.upper()
        prog = clean(a.get("ECE_PROGRAM"))
        kind = ("School District Head Start site" if re.search(r"HEAD START|HD START|\bHS\b", up)
                else "School District Bright Futures pre-K" if "BRIGHT FUTURES" in up
                else "School District pre-K partner site" if prog.upper().startswith("ECH")
                else "School District pre-K site")
        where = ("community partner site" if prog.upper().startswith("ECH") else
                 "district-run, outside a school" if prog.lower().startswith("non school") else
                 "district-run, in a school" if prog else "")
        nm = title(name)
        here = at_site(nm, xy[0], xy[1], street)
        out.append(rec("early_childhood", kind, nm, address(street, a.get("CITY"), a.get("STATE"), a.get("ZIP_CODE")), xy[0], xy[1],
                       phone(a.get("PHONE_NUMBER")), "", join(site_note(here), f"SY {year}", where)))
    write("sdp_prek_sites", out, {
        "title": f"School District of Philadelphia pre-K sites (Head Start, Bright Futures, partners), SY {year}",
        "categories": ["early_childhood"], "publisher": "School District of Philadelphia, Office of Research and Evaluation",
        "landing_url": "https://www.philasd.org/research/#opendata", "api_url": SDP_PREK,
        "license": "School District of Philadelphia open data (terms at philasd.org/research)",
        "data_date": f"school year {year} (sheet in the 2023-2024 workbook)",
        "notes": "District pre-K list (district-run Head Start / Bright Futures classrooms and community partner sites). The file has "
                 "addresses only; points were geocoded with the City's AIS address service (Census geocoder as fallback)"
                 + (f"; not geocoded: {', '.join(title(m) for m in missed)}." if missed else ".")})


# ================================================================ libraries

def libraries():
    url = f"{CITY}/library_locations/FeatureServer/0"
    meta = arcgis_meta(url, "phl_library_locations")
    out, flp_pts = [], []
    for f in arcgis_near(url, "phl_library_locations"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        name = clean(a.get("building"))
        kind = ("Central library" if "Central" in name else "Regional library" if "Regional" in name
                else "Free Library service" if "LAMP" in name or "Accessible Media" in name else "Free Library branch")
        out.append(rec("libraries", kind, name, address(a.get("address"), "Philadelphia", "PA", a.get("zip_code")), g.x, g.y,
                       phone(a.get("phone_number")), clean(a.get("library_url")), "Free Library of Philadelphia"))
        flp_pts.append(g)
    write("phl_free_library_locations", out, {
        "title": "Free Library of Philadelphia locations", "categories": ["libraries"],
        "publisher": "Free Library of Philadelphia, published by the City of Philadelphia (maps.phl.data)",
        "landing_url": "https://www.arcgis.com/home/item.html?id=a3bf9f696fb14d5d87ee1b184fbed711", "api_url": f"{url}/query",
        "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(meta)}" if last_edit(meta) else "",
        "notes": "Active Free Library locations (the City's current 'library_locations' layer; the older 'Free_Library_Locations' layer "
                 "was last edited in 2018 and was not used)."})

    # other public libraries known to the Commonwealth (outside the Free Library system)
    dsid = "da8t-93kj"
    view = socrata_view(dsid)
    rows = socrata_near(dsid, "the_geom", "pa_public_libraries", where="layername = 'Public Library'")
    flp = gpd.GeoSeries(flp_pts, crs=4326).to_crs(UTM) if flp_pts else gpd.GeoSeries([], crs=UTM)
    out, skipped = [], []
    for r in rows:
        gc = r.get("the_geom")
        if not gc:
            continue
        lon, lat = gc["coordinates"]
        name = clean(r.get("name"))
        p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(UTM).iloc[0]
        if len(flp) and flp.distance(p).min() <= 150:
            continue                      # a Free Library branch, already in phl_free_library_locations
        if re.search(r"hosting solutions|library consulting", name, re.I):
            skipped.append(name)          # a library-services consortium office, not a library open to the public
            continue
        out.append(rec("libraries", "Public library", title(name), address(r.get("address"), r.get("city"), r.get("state"), r.get("zip")),
                       lon, lat, phone(r.get("phonenumber")), "", ""))
    write("pa_public_libraries_other", out, {
        "title": "Public libraries outside the Free Library system (PA 'Services Near You': Public Library layer)", "categories": ["libraries"],
        "publisher": "Commonwealth of Pennsylvania (Department of Education, Office of Commonwealth Libraries, via data.pa.gov)",
        "landing_url": f"{PA}/d/{dsid}", "api_url": f"{PA}/resource/{dsid}.json", "license": (view.get("license") or {}).get("name", ""),
        "data_date": f"rows updated {socrata_date(dsid)}",
        "notes": "Public libraries in the Commonwealth list that are not Free Library branches (those within 150 m of a Free Library "
                 "location were dropped as duplicates)" + (f"; also dropped: {', '.join(skipped)} (a library-services office)." if skipped else ".")})


# ================================================================ youth

FUNDERS = {"DHS": "funded by City DHS / OCF", "SDP": "funded by the School District", "21C": "21st Century Community Learning Center (federal, via PDE)",
           "MURAL ARTS": "Mural Arts program"}


def ost():
    url = f"{CITY}/FY24_OST/FeatureServer/0"
    meta = arcgis_meta(url, "phl_ocf_ost_fy24")
    out = []
    for f in arcgis_near(url, "phl_ocf_ost_fy24"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        site, prov = site_name(title(a.get("Site_Name"))), clean(a.get("Provider"))
        tbd = bool(re.search(r"\bTBD\b", prov, re.I))
        prov = re.sub(r"\s*\((no summer)\)", "", prov).strip()
        name = site if tbd or not prov or norm(prov) in norm(site) else f"{prov} at {site}"
        here = at_site(f"{site} {a.get('Address')}", g.x, g.y, a.get("Address"))
        slots = a.get("Slots")
        detail = join(site_note(here), "FY24", "provider to be selected (new RFP)" if tbd else "",
                      FUNDERS.get(clean(a.get("Funding_Type")).upper(), clean(a.get("Funding_Type"))),
                      f"{int(slots)} slots" if isinstance(slots, (int, float)) and slots == slots else "")
        out.append(rec("youth", "Out-of-school-time program", name, address(a.get("Address"), a.get("City") or "Philadelphia", "PA", a.get("ZIP_Code")),
                       g.x, g.y, "", "", detail))
    write("phl_ocf_ost_sites_fy24", out, {
        "title": "Out-of-school-time (OST) program sites, FY24", "categories": ["youth"],
        "publisher": "City of Philadelphia, Office of Children and Families (OST)",
        "landing_url": "https://www.arcgis.com/home/item.html?id=2b66e37ec8784f73a97527f4e09f5f56", "api_url": f"{url}/query",
        "license": CITY_AGO_LICENSE, "data_date": f"FY24 (2023-24) program year; layer last edited {last_edit(meta)}",
        "notes": "Publicly funded after-school sites (City DHS/OCF, School District, federal 21st CCLC, Mural Arts) as the City listed them for FY24; "
                 "the newest public OST site list found (FY25/26 layers in the City's OST map are not public). Sites marked 'TBD new RFP' had "
                 "funded slots but no provider yet."})


def pal():
    url = f"{CITY}/PAL_Centers/FeatureServer/0"
    meta = arcgis_meta(url, "phl_pal_centers")
    out = []
    for f in arcgis_near(url, "phl_pal_centers"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        host = clean(a.get("center_own"))
        detail = "PAL-owned building" if re.fullmatch(r"PAL OWNED", host, re.I) else (f"in {title(host)}" if host else "")
        out.append(rec("youth", "Police Athletic League center", f"{title(a.get('center_nam'))} PAL Center",
                       address(clean(a.get("address")).rstrip(". "), "Philadelphia", "PA"), g.x, g.y, phone(a.get("telephone")),
                       "https://www.phillypal.org", detail))
    write("phl_pal_centers", out, {
        "title": "Police Athletic League (PAL) Centers", "categories": ["youth"],
        "publisher": "City of Philadelphia, Police Department", "landing_url": "https://opendataphilly.org/datasets/police-athletic-league-pal-centers/",
        "api_url": f"{url}/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(meta)}" if last_edit(meta) else "",
        "notes": "All PAL centers in the layer; the center director's name in the source was not kept."})


def osm_points(elements):
    for e in elements:
        t = e.get("tags", {})
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None:
            continue
        yield e, t, lon, lat


def osm_addr(t):
    return address(" ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x), t.get("addr:city"), t.get("addr:state"),
                   t.get("addr:postcode"))


OSM_YOUTH = re.compile(r"\bYMCA\b|\bYWCA\b|Boys\s*(&|and)\s*Girls|Boys'? Club|Girls,? Inc|Police Athletic|\bPAL Cent|Youth (Access )?Cent|"
                       r"Teen Cent|Youth .*Education Cent|Scouts?\b|Big Brothers", re.I)
OSM_YOUTH_NOT = re.compile(r"\bCSA\b|drop site|shelter|detention|juvenile|treatment|residential|church|ministr|health|services? cent|"
                           r"fields?$|playground|park$|pool$|ice rink|court$", re.I)
OSM_HIGHER = re.compile(r"College|Universit|Institute|School|Seminary|Academy|Campus|Center", re.I)


def osm_merge(recs, metres=200):
    """OSM often maps one place twice (a POI and its building): same name within 200 m -> keep the one with an address."""
    recs = sorted(recs, key=lambda r: (not r["address"], r["name"]))
    pts = gpd.GeoSeries([Point(r["lon"], r["lat"]) for r in recs], crs=4326).to_crs(UTM) if recs else []
    keep = []
    for i, r in enumerate(recs):
        if not any(norm(r["name"]) == norm(recs[j]["name"]) and pts.iloc[i].distance(pts.iloc[j]) <= metres for j in keep):
            keep.append(i)
    return [recs[i] for i in keep]


def osm():
    s, w, n, e = BBOX[1], BBOX[0], BBOX[3], BBOX[2]
    q = (f'[out:json][timeout:180][bbox:{s},{w},{n},{e}];('
         'nwr["amenity"~"^(college|university|youth_centre)$"];'
         'nwr["community_centre"="youth_centre"];'
         'nwr["club"="scout"];'
         'nwr["name"~"YMCA|YWCA|Boys . Girls|Boys and Girls|Girls Inc|Police Athletic|Youth|Teen"];'
         ');out center tags;')
    j = overpass(q, "osm_education")
    stamp = (j.get("osm3s") or {}).get("timestamp_osm_base", "")
    youth, higher = [], []
    for el, t, lon, lat in osm_points(j.get("elements", [])):
        name = clean(t.get("name"))
        amen = t.get("amenity", "")
        if amen in ("college", "university"):
            if not name or not OSM_HIGHER.search(name) or (t.get("building") and el["type"] == "way"):
                continue                  # unnamed parts and single campus buildings (e.g. 'Ritter Hall') are not institutions
            kind = "University" if amen == "university" else "College"
            higher.append(rec("higher_ed", kind, name, osm_addr(t), lon, lat, phone(t.get("phone") or t.get("contact:phone")),
                              clean(t.get("website") or t.get("contact:website")), f"OpenStreetMap {el['type']} {el['id']}"))
            continue
        youth_tag = amen == "youth_centre" or t.get("community_centre") == "youth_centre" or t.get("club") == "scout"
        if not name or not (youth_tag or OSM_YOUTH.search(name)) or OSM_YOUTH_NOT.search(name):
            continue
        if amen in ("school", "place_of_worship", "childcare", "kindergarten") or t.get("leisure") in ("pitch", "playground", "park", "swimming_pool"):
            continue
        if t.get("shop") or t.get("highway") or t.get("office") == "government":
            continue
        kind = ("YMCA" if re.search(r"\bYMCA\b", name) else "YWCA" if re.search(r"\bYWCA\b", name)
                else "Boys & Girls Club" if re.search(r"Boys\s*(&|and)\s*Girls", name, re.I)
                else "Police Athletic League center" if re.search(r"Police Athletic|\bPAL\b", name)
                else "Scouting" if t.get("club") == "scout" or re.search(r"Scout", name) else "Youth center")
        here = at_site(name, lon, lat, osm_addr(t))
        youth.append(rec("youth", kind, name, osm_addr(t), lon, lat, phone(t.get("phone") or t.get("contact:phone")),
                         clean(t.get("website") or t.get("contact:website")), join(site_note(here), f"OpenStreetMap {el['type']} {el['id']}")))
    youth = osm_merge(youth)
    higher = osm_merge(higher)
    common = {"publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org",
              "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"OSM data as of {stamp}" if stamp else ""}
    write("osm_youth", youth, {
        "title": "Youth centers, YMCA / YWCA, Boys & Girls Clubs, scouting (OpenStreetMap)", "categories": ["youth"], **common,
        "notes": "OSM fills the gap where no official list exists (YMCA / Boys & Girls Club branches, youth centers): features tagged as youth "
                 "centres or scouting, or named YMCA, YWCA, Boys & Girls Club, PAL, Youth or Teen; schools, churches, shelters, "
                 "treatment and justice facilities, playgrounds and courts were left out. Coverage depends on volunteer mapping."})
    write("osm_higher_ed", higher, {
        "title": "Colleges and universities (OpenStreetMap)", "categories": ["higher_ed"], **common,
        "notes": "Named features tagged amenity=college or amenity=university (campus outlines become a point inside them). Used only to "
                 "fill gaps in the NCES / PDE / City lists; OSM 'college' also covers some trade and career schools."})


# ================================================================ higher education

def higher_ed():
    # NCES IPEDS institution points (current year)
    url = f"{NCES}/Postsecondary_School_Locations/EDGE_GEOCODE_POSTSECONDARYSCH_2526/MapServer/0"
    out = []
    for f in arcgis_near(url, "nces_ipeds_2526"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None:
            continue
        name = clean(a.get("NAME"))
        kind = ("University" if re.search(r"Universit", name, re.I) else "Nursing school" if re.search(r"Nursing", name, re.I)
                else "Beauty / cosmetology school" if re.search(r"Beauty|Cosmetolog|Barber|Hair", name, re.I)
                else "Seminary" if re.search(r"Seminary|Theolog", name, re.I)
                else "College" if re.search(r"College", name, re.I) else "Career / technical school")
        out.append(rec("higher_ed", kind, name, address(a.get("STREET"), a.get("CITY"), a.get("STATE"), a.get("ZIP")), g.x, g.y, "", "",
                       f"IPEDS institution {clean(a.get('UNITID'))}"))
    write("nces_ipeds_postsecondary", out, {
        "title": "Postsecondary institution locations, 2025-26 (NCES EDGE / IPEDS)", "categories": ["higher_ed"],
        "publisher": "U.S. Department of Education, National Center for Education Statistics (EDGE / IPEDS)",
        "landing_url": "https://nces.ed.gov/programs/edge/Geographic/SchoolLocations", "api_url": f"{url}/query", "license": FED_LICENSE,
        "data_date": "school year 2025-26",
        "notes": "One point per IPEDS institution (its main address), so branch campuses are not here (see pa_pde_higher_ed_campuses). "
                 "The kind is read from the institution name."})

    # PDE campus list (includes Community College of Philadelphia regional centers)
    dsid = "8u5h-xvus"
    view = socrata_view(dsid)
    out = []
    for r in socrata_near(dsid, "georeferenced_latitude_longitude", "pa_pde_higher_ed"):
        gc = r.get("georeferenced_latitude_longitude")
        if not gc:
            continue
        lon, lat = gc["coordinates"]
        name = clean(r.get("college"))
        name = re.sub(r"^CCP-?\s*(.+)$", lambda m: f"Community College of Philadelphia, {m.group(1)}"
                      + ("" if re.search(r"Center|Campus", m.group(1)) else " Regional Center"), name)
        sector, typ = clean(r.get("sector")), clean(r.get("type"))
        kind = ("Community college site" if "Community College" in sector else "University / college campus")
        addr = clean(r.get("address"))
        addr = addr if re.match(r"\d", addr) else ""          # some rows hold only the institution name
        out.append(rec("higher_ed", kind, name, addr, lon, lat, "", "", join(sector, typ)))
    write("pa_pde_higher_ed_campuses", out, {
        "title": "PA higher education institutions by sector (campus locations)", "categories": ["higher_ed"],
        "publisher": "Pennsylvania Department of Education", "landing_url": f"{PA}/d/{dsid}", "api_url": f"{PA}/resource/{dsid}.json",
        "license": (view.get("license") or {}).get("name", ""), "data_date": f"rows updated {socrata_date(dsid)}",
        "notes": "Full-service college locations (main campuses, branch campuses and off-campus operations such as the Community College of "
                 "Philadelphia regional centers); limited instructional sites are not in this list."})

    # City building inventory, one point per cluster of a university's buildings
    url = f"{CITY}/Universities_Colleges/FeatureServer/0"
    meta = arcgis_meta(url, "phl_universities_colleges")
    rows = []
    for f in arcgis_near(url, "phl_universities_colleges"):
        a, g = f["attributes"], esri_geom(f["geometry"])
        if g is None or g.is_empty:
            continue
        rows.append({**{k: clean(v) for k, v in a.items()}, "geometry": g})
    out = []
    if rows:
        b = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326).to_crs(UTM)
        b = b[[AREA_UTM.intersects(x) for x in b.geometry]]           # buildings touching the study area
        for uni, grp in b.groupby("university_name"):
            blobs = unary_union([x.buffer(100) for x in grp.geometry])
            blobs = list(getattr(blobs, "geoms", [blobs]))
            for blob in blobs:
                cl = grp[[blob.intersects(x) for x in grp.geometry]]
                if not len(cl):
                    continue
                c = unary_union(list(cl.geometry)).centroid
                core = cl.iloc[int(cl.geometry.distance(c).values.argmin())]
                pt = gpd.GeoSeries([core.geometry.representative_point()], crs=UTM).to_crs(4326).iloc[0]
                named = [n for n in cl.building_name if n]
                name = (named[0] if named[0].lower().startswith(uni.lower()) else f"{uni}, {named[0]}") if len(cl) == 1 and named else uni
                sub = clean(core.get("sub_type"))
                kind = {"Two year college": "Community college site", "Graduate Institution": "Graduate institution"}.get(sub, "University / college buildings")
                detail = join(f"{len(cl)} building{'s' if len(cl) > 1 else ''} in the City's inventory",
                              ("incl. " + ", ".join(sorted(set(named))[:3])) if len(cl) > 1 and named else "", clean(core.get("type")))
                out.append(rec("higher_ed", kind, name, address(core.get("address"), "Philadelphia", "PA"), pt.x, pt.y, "", "", detail))
    write("phl_universities_colleges", out, {
        "title": "Universities and Colleges (City building inventory, grouped into campus points)", "categories": ["higher_ed"],
        "publisher": "City of Philadelphia, Department of Planning and Development", "landing_url": "https://opendataphilly.org/datasets/philadelphia-universities-and-colleges/",
        "api_url": f"{url}/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(meta)}" if last_edit(meta) else "",
        "notes": "The source has one polygon per college building. Buildings of the same institution within ~200 m of each other inside the "
                 "study area were grouped into one point (at the building nearest the group's center); single buildings keep their name."})


# ================================================================ run

def main():
    print("education: schools")
    phl_schools()
    nces_k12()
    print("education: early childhood")
    pa_child_care()
    phlprek()
    prek_counts()
    sdp_prek()
    print("education: libraries")
    libraries()
    print("education: youth")
    ost()
    pal()
    print("education: higher education")
    higher_ed()
    print("education: OpenStreetMap (youth, higher ed gaps)")
    osm()
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=1, ensure_ascii=False))
    ids = {m["id"] for m in MANIFEST}
    for f in OUT.glob("*.geojson"):
        if f.stem not in ids:
            f.unlink()                                   # outputs of datasets this script no longer writes
    print(f"wrote {len(MANIFEST)} datasets to {OUT.relative_to(ROOT)}")
    print("within 1 mile:  dataset / Wagner / Blankenburg")
    for ds, n, w1, b1 in SUMMARY:
        print(f"  {ds:42s} {n:5d} {w1:5d} {b1:5d}")


if __name__ == "__main__":
    main()
