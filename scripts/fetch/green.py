"""Green domain asset pull: food, gardens & farms, parks & recreation.

Collects points within 1.5 miles (2,414 m) of any of the six studio sites in scripts/fetch/schools.json and
writes one GeoJSON per source dataset plus manifest.json to scripts/fetch/out/green/ (see CONTRACT.md).

Run (from the repo root):
    uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/green.py
Add --refresh to ignore the raw-response cache in scripts/.cache/fetch/green/.
"""
import json
import math
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, shape
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[2]
FETCH = ROOT / "scripts" / "fetch"
OUT = FETCH / "out" / "green"
CACHE = ROOT / "scripts" / ".cache" / "fetch" / "green"
REFRESH = "--refresh" in sys.argv
TODAY = date.today().isoformat()
UA = {"User-Agent": "studio-community-maps/1.0"}
RADIUS_M = 2414.0          # 1.5 miles
DEDUPE_M = 40.0            # contract: same name within 40 m is a duplicate
MILE_M = 1609.344
UTM = 32618                # WGS 84 / UTM 18N, metres

CITY = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
SNAP = "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0"
PHS = "https://services2.arcgis.com/qjOOiLCYeUtwT7x7/arcgis/rest/services"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CITY_LICENSE = "City of Philadelphia License (OpenDataPhilly)"
OSM_LICENSE = "ODbL 1.0, (c) OpenStreetMap contributors"

SITES = json.loads((FETCH / "schools.json").read_text())
SITE_PTS = gpd.GeoSeries([Point(s["lng"], s["lat"]) for s in SITES], crs=4326).to_crs(UTM)
AREA_UTM = unary_union([p.buffer(RADIUS_M) for p in SITE_PTS])
AREA = gpd.GeoSeries([AREA_UTM], crs=UTM).to_crs(4326).iloc[0]
BBOX = AREA.bounds  # (minx, miny, maxx, maxy) in lon/lat

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


def http(method, url, **kw):
    last = None
    for i in range(5):
        try:
            r = requests.request(method, url, headers=UA, timeout=180, **kw)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 - retry any network / decode failure
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def arcgis(layer_url, cache_name, where="1=1", spatial=True):
    """All features of an ArcGIS layer (optionally limited to the study envelope) as GeoJSON + layer metadata."""
    def fetch():
        meta = http("GET", layer_url, params={"f": "json"})
        base = {"where": where, "f": "json"}
        if spatial:
            base.update(geometry=json.dumps({"xmin": BBOX[0], "ymin": BBOX[1], "xmax": BBOX[2], "ymax": BBOX[3],
                                              "spatialReference": {"wkid": 4326}}),
                        geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects")
        ids = http("POST", f"{layer_url}/query", data={**base, "returnIdsOnly": "true"})
        oid, oids = ids["objectIdFieldName"], sorted(ids.get("objectIds") or [])
        feats = []
        for i in range(0, len(oids), 400):
            chunk = oids[i:i + 400]
            g = http("POST", f"{layer_url}/query", data={"objectIds": ",".join(map(str, chunk)), "outFields": "*",
                                                          "outSR": 4326, "f": "geojson"})
            feats += g.get("features", [])
        return {"meta": {k: meta.get(k) for k in ("name", "editingInfo", "description")}, "objectIdField": oid,
                "geojson": {"type": "FeatureCollection", "features": feats}}
    return cached(cache_name, fetch)


def to_gdf(raw):
    feats = [f for f in raw["geojson"]["features"] if f.get("geometry")]
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    return gpd.GeoDataFrame.from_features(feats, crs=4326)


def last_edit(raw):
    ei = (raw.get("meta") or {}).get("editingInfo") or {}
    ms = ei.get("dataLastEditDate") or ei.get("lastEditDate")
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat() if ms else ""


GEOCODES_FILE = CACHE / "address_geocodes.json"
GEOCODES = json.loads(GEOCODES_FILE.read_text()) if GEOCODES_FILE.exists() and not REFRESH else {}


def geocode(address, zip_code=""):
    """[lon, lat, matcher] for a Philadelphia street address: City AIS first, Census geocoder as fallback. Cached."""
    street = re.split(r",|#|\bsuite\b|\bste\b|\bfl\b|\bfloor\b|\bunit\b|\brm\b|\(", clean(address), flags=re.I)[0].strip(" .")
    if not street or not re.match(r"^\d", street):
        return None
    key = f"{street}|{clean(zip_code)}"
    if key in GEOCODES:
        return GEOCODES[key]
    hit = None
    try:
        r = requests.get("https://api.phila.gov/ais/v1/search/" + requests.utils.quote(street), headers=UA, timeout=30)
        if r.ok and r.json().get("features"):
            lon, lat = r.json()["features"][0]["geometry"]["coordinates"]
            hit = [lon, lat, "City of Philadelphia AIS"]
    except Exception:  # noqa: BLE001
        pass
    if hit is None:
        try:
            r = requests.get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress", headers=UA, timeout=30,
                             params={"address": f"{street}, Philadelphia, PA {clean(zip_code)}".strip(), "benchmark": "Public_AR_Current", "format": "json"})
            m = r.json()["result"]["addressMatches"] if r.ok else []
            if m:
                hit = [m[0]["coordinates"]["x"], m[0]["coordinates"]["y"], "U.S. Census geocoder"]
        except Exception:  # noqa: BLE001
            pass
    GEOCODES[key] = hit
    GEOCODES_FILE.write_text(json.dumps(GEOCODES))
    time.sleep(0.15)
    return hit


def gap_m(p, lon, lat):
    a = gpd.GeoSeries([p, Point(lon, lat)], crs=4326).to_crs(UTM)
    return a.iloc[0].distance(a.iloc[1])


def overpass(cache_name, selectors):
    """OSM elements matching any selector within 1.5 mi of any site. Ways/relations come back with geometry."""
    around = "".join(f"nwr{sel}(around:{int(RADIUS_M)},{s['lat']},{s['lng']});" for sel in selectors for s in SITES)
    q = f"[out:json][timeout:240];({around})->.a;node.a;out body;way.a;out tags geom;rel.a;out tags geom;"

    def fetch():
        last = None
        for i in range(8):
            url = OVERPASS[i % len(OVERPASS)]
            try:
                r = requests.post(url, data={"data": q}, headers=UA, timeout=300)
                r.raise_for_status()
                d = r.json()
                if d.get("remark") and "error" in d["remark"].lower():
                    raise RuntimeError(d["remark"])
                return d
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(10 * (i + 1))
        raise RuntimeError(f"Overpass failed: {last}")
    return cached(cache_name, fetch)


def osm_geom(e):
    """Shapely geometry for an Overpass element (node point, way polygon/line, relation multipolygon)."""
    if e["type"] == "node":
        return Point(e["lon"], e["lat"])
    if e["type"] == "way":
        pts = [(p["lon"], p["lat"]) for p in e.get("geometry") or []]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts) if len(pts) >= 2 else None
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", [])
             if m.get("type") == "way" and m.get("role") in ("outer", "") and len(m.get("geometry") or []) >= 2]
    polys = list(polygonize(unary_union(lines))) if lines else []
    if polys:
        return MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return unary_union(lines) if lines else None


def osm_gdf(raw):
    rows = []
    for e in raw.get("elements", []):
        g = osm_geom(e)
        if g is None or g.is_empty:
            continue
        rows.append({"osm": f"{e['type']}/{e['id']}", "tags": e.get("tags", {}), "geometry": g})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326) if rows else gpd.GeoDataFrame(columns=["osm", "tags", "geometry"], geometry="geometry", crs=4326)


def osm_date(raw):
    return (raw.get("osm3s") or {}).get("timestamp_osm_base", "")[:10]


# ---------------------------------------------------------------- text helpers

KEEP_UPPER = {"PPR", "YMCA", "YWCA", "AME", "CME", "CDC", "LLC", "PHA", "CVS", "ALDI", "II", "III", "IV", "NGT", "PHS",
              "MLK", "USA", "SNAP", "WIC", "JFK", "SEPTA", "PAL", "ACME", "BJ'S", "IGA", "NE", "NW", "SE", "SW", "UPENN",
              "KIPP", "COGIC", "MCC", "LDS", "AKA", "BBQ"}


def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip()
    return "" if s.lower() in ("none", "nan", "null", "n/a") else s


def tidy(v):
    """Title-case text that arrives ALL CAPS (or all lower case); leave mixed case alone."""
    s = clean(v)
    if not s or not re.search(r"[A-Za-z]", s) or not (s == s.upper() or s == s.lower()):
        return s
    out = []
    for w in s.split(" "):
        core = re.sub(r"[^\w']", "", w).upper()
        if core in KEEP_UPPER:
            out.append(w.upper())
        elif re.fullmatch(r"\d+(ST|ND|RD|TH)", w.upper()):
            out.append(w.lower())
        else:
            out.append(re.sub(r"[A-Za-z]+('[A-Za-z]+)?", lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), w))
    s = " ".join(out)
    s = re.sub(r"'S\b", "'s", s)
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    return s


def site_url(v):
    s = clean(v)
    if not s or " " in s or "@" in s:
        return ""
    return s if re.match(r"https?://", s) else "https://" + s


def phone(v):
    d = re.sub(r"\D", "", clean(v))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def street_addr(t):
    num, st = clean(t.get("addr:housenumber")), clean(t.get("addr:street"))
    city = clean(t.get("addr:city"))
    a = " ".join(x for x in (num, st) if x)
    return ", ".join(x for x in (a, city) if x) if a else ""


# ---------------------------------------------------------------- geometry helpers

def point_inside(geom_utm):
    """A point inside the polygon, chosen inside the study area when the polygon reaches beyond it."""
    if geom_utm.geom_type in ("Point",):
        return geom_utm
    if not geom_utm.is_valid:
        geom_utm = make_valid(geom_utm)
        if geom_utm.geom_type == "GeometryCollection":
            polys = [x for x in geom_utm.geoms if x.geom_type in ("Polygon", "MultiPolygon")]
            geom_utm = unary_union(polys) if polys else geom_utm
    part = geom_utm.intersection(AREA_UTM) if geom_utm.geom_type in ("Polygon", "MultiPolygon") else geom_utm
    target = part if not part.is_empty else geom_utm
    if target.geom_type in ("LineString", "MultiLineString"):
        return target.interpolate(0.5, normalized=True)
    return target.representative_point()


def to_points(gdf):
    """Convert any geometry to an inside point (computed in metres)."""
    if gdf.empty:
        return gdf
    u = gdf.to_crs(UTM)
    u["geometry"] = [point_inside(g) for g in u.geometry]
    return u.to_crs(4326)


def nearest_site_m(gdf):
    u = gdf.to_crs(UTM).geometry
    return pd.concat([u.distance(p) for p in SITE_PTS], axis=1).min(axis=1).values


def in_area(gdf):
    if gdf.empty:
        return gdf
    return gdf[nearest_site_m(gdf) <= RADIUS_M + 0.5].copy()


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", clean(s).lower())


def dedupe(gdf, merge_detail=None):
    """Drop features with the same (normalised) name within 40 m of an earlier one (contract rule).
    merge_detail(list_of_rows) -> detail string (or dict of fields), if the cluster is summarised instead of dropped."""
    if gdf.empty:
        return gdf
    u = gdf.to_crs(UTM).reset_index(drop=True)
    keys = [norm_name(n) for n in u["name"]]
    parent = list(range(len(u)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(u)):
        for j in range(i + 1, len(u)):
            if keys[i] == keys[j] and u.geometry[i].distance(u.geometry[j]) <= DEDUPE_M:
                parent[find(j)] = find(i)
    groups = {}
    for i in range(len(u)):
        groups.setdefault(find(i), []).append(i)
    keep = []
    for root, members in groups.items():
        row = gdf.iloc[members[0]].copy()
        if merge_detail and len(members) > 1:
            merged = merge_detail([gdf.iloc[m] for m in members])
            for k, v in (merged.items() if isinstance(merged, dict) else [("detail", merged)]):
                row[k] = v
        keep.append(row)
    return gpd.GeoDataFrame(keep, geometry="geometry", crs=4326)


# ---------------------------------------------------------------- output

FIELDS = ["category", "kind", "name", "address", "phone", "website", "detail"]
MANIFEST = []
SUMMARY = []


def write(ds_id, gdf, meta):
    gdf = in_area(gdf) if not gdf.empty else gdf
    feats = []
    for _, r in gdf.iterrows():
        props = {k: clean(r.get(k, "")) for k in FIELDS}
        props["source_id"] = ds_id
        x, y = r.geometry.x, r.geometry.y
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [round(x, 6), round(y, 6)]}})
    feats.sort(key=lambda f: (f["properties"]["category"], f["properties"]["kind"], f["properties"]["name"]))
    (OUT / f"{ds_id}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=0))
    entry = {"id": ds_id, **meta, "retrieved": TODAY, "records": len(feats)}
    entry["categories"] = sorted({f["properties"]["category"] for f in feats}) or meta.get("categories", [])
    order = ["id", "title", "categories", "publisher", "landing_url", "api_url", "license", "retrieved", "data_date", "records", "notes"]
    MANIFEST.append({k: entry.get(k, "") for k in order})
    if feats:
        g = gpd.GeoDataFrame(geometry=[Point(f["geometry"]["coordinates"]) for f in feats], crs=4326).to_crs(UTM).geometry
        w = int((g.distance(SITE_PTS.iloc[0]) <= MILE_M).sum())
        b = int((g.distance(SITE_PTS.iloc[1]) <= MILE_M).sum())
    else:
        w = b = 0
    SUMMARY.append((ds_id, len(feats), w, b))
    print(f"  {ds_id:38s} {len(feats):5d} written | within 1 mi: Wagner {w:4d}  Blankenburg {b:4d}")


def frame(rows):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326) if rows else gpd.GeoDataFrame(columns=FIELDS + ["geometry"], geometry="geometry", crs=4326)


# ================================================================ PPR properties (used for parks and for address lookups)

print("PPR properties ...")
ppr_raw = arcgis(f"{CITY}/PPR_Properties/FeatureServer/0", "ppr_properties.json")
ppr = to_gdf(ppr_raw)
ppr_utm = ppr.to_crs(UTM)
ppr_utm["geometry"] = [g if g.is_valid else make_valid(g) for g in ppr_utm.geometry]
ppr_utm["area"] = ppr_utm.geometry.area


def ppr_lookup(gdf, max_m=30):
    """(site name, 911 address) of the smallest PPR property containing / within max_m of each point."""
    out = []
    pts = gdf.to_crs(UTM).geometry
    sidx = ppr_utm.sindex
    for p in pts:
        cand = ppr_utm.iloc[list(sidx.query(p.buffer(max_m)))]
        cand = cand[cand.geometry.distance(p) <= max_m]
        if cand.empty:
            out.append(("", "", ""))
            continue
        r = cand.sort_values("area").iloc[0]
        nm = clean(r.get("official_name")) or clean(r.get("site_name")) or clean(r.get("label"))
        out.append((tidy(nm), tidy(r.get("address_911")), tidy(r.get("park_name"))))
    return out


def best_site(src, pname, parent):
    """The source's park name, unless it names the parent park and the point sits in a more specific PPR site."""
    s = tidy(src)
    if not s:
        return pname
    if pname and norm_name(pname) != norm_name(s) and norm_name(parent) == norm_name(s):
        return pname
    return s


# ================================================================ FOOD

print("Food ...")

# --- City free food & meal sites (OCF)
raw = arcgis(f"{CITY}/free_meal_sites/FeatureServer/0", "free_meal_sites.json")
g = to_gdf(raw)
FMS_KIND = {  # source category -> (kind, food-bank network)
    "Caring for Friends Food Site": ("Food pantry", "Caring for Friends"),
    "Community Refrigerators": ("Community fridge", ""),
    "Free Grocery Site": ("Free grocery site", ""),
    "Free Meal Site": ("Free meal site", ""),
    "General Food Site": ("Food pantry", ""),
    "Nutritional Development Services": ("Food pantry", "Nutritional Development Services"),
    "PHILABUNDANCE": ("Food pantry", "Philabundance"),
    "PHILABUNDANCE meal": ("Free meal site", "Philabundance"),
    "PHILABUNDANCE/SHARE FOOD PROGRAM": ("Food pantry", "Philabundance, SHARE"),
    "SHARE FOOD PROGRAM": ("Food pantry", "SHARE"),
    "Small Things Philly": ("Free market", "Small Things Philly"),
}
NETWORK_SITE = re.compile(r"(?i)^(https?://)?(www\.)?(philabundance\.org|sharefoodprogram\.org|caringforfriends\.org)/?$")
DAYS = [("mon", "Mon"), ("tues", "Tue"), ("wed", "Wed"), ("thurs", "Thu"), ("fri", "Fri"), ("sat", "Sat"), ("sun", "Sun")]
rows = []
excluded = {}
MOVE_M = 250  # source point this far from its own address -> use the geocoded address point
moved = {"moved": 0, "unverified": 0}
for _, r in g.iterrows():
    cat = clean(r.get("category"))
    if clean(r.get("status")).lower() != "active":
        excluded["not active"] = excluded.get("not active", 0) + 1
        continue
    if cat not in FMS_KIND:
        excluded[cat] = excluded.get(cat, 0) + 1
        continue
    kind, net = FMS_KIND[cat]
    if cat == "PHILABUNDANCE" and clean(r.get("category_type")) == "General Meal Site":
        kind = "Free meal site"
    days = [lab for key, lab in DAYS if clean(r.get(f"hours_{key}_start1"))]
    seasonal = clean(r.get("seasonally_closed")).lower() == "yes"
    geom = r.geometry
    hit = geocode(r.get("address"), r.get("zip_code"))
    if hit is None:
        moved["unverified"] += 1
    elif gap_m(geom, hit[0], hit[1]) > MOVE_M:
        moved["moved"] += 1
        moved["moved_" + cat] = moved.get("moved_" + cat, 0) + 1
        geom = Point(hit[0], hit[1])
    rows.append({"category": "food", "kind": kind, "name": tidy(r.get("site_name")), "address": tidy(r.get("address")),
                 "phone": phone(r.get("phone_number")), "geometry": geom,
                 "website": "" if NETWORK_SITE.search(clean(r.get("website"))) else site_url(r.get("website")),
                 "_net": [x.strip() for x in net.split(",") if x.strip()], "_days": days, "_seasonal": seasonal})


def fms_detail(members):
    """kind + detail for one site (several programs at one address are merged into a single record)."""
    kinds = list(dict.fromkeys(m["kind"] for m in members))
    nets = list(dict.fromkeys(n for m in members for n in m["_net"]))
    days = [lab for _, lab in DAYS if any(lab in m["_days"] for m in members)]
    parts = ([f"Network: {', '.join(nets)}"] if nets else []) + ([f"Open {', '.join(days)}"] if days else [])
    if any(m["_seasonal"] for m in members):
        parts.append("seasonally closed")
    return {"kind": " / ".join(kinds), "detail": " · ".join(parts)}


fr = frame(rows)
fr["detail"] = [fms_detail([r]).get("detail") for _, r in fr.iterrows()]
fms = dedupe(fr, fms_detail)
write("phl_free_meal_sites", fms, {
    "title": "Philadelphia Free Food and Meal Sites", "categories": ["food"],
    "publisher": "City of Philadelphia, Office of Children and Families (with Philabundance, SHARE and partner food banks)",
    "landing_url": "https://opendataphilly.org/datasets/free-food-and-meal-sites/",
    "api_url": f"{CITY}/free_meal_sites/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active food pantries, free grocery sites, community fridges and free meal sites only. Excluded: Office of Homeless "
             "Services meal sites (shelter locations), WIC / BenePhilly / Neighborhood Community Action Center benefit sites "
             "(social services) and PCA / PPR senior meal sites (older adults), plus permanently closed sites. "
             "Food-bank homepages given as a site's website are left blank. "
             f"Every address was geocoded (City AIS, Census fallback): citywide {moved['moved']} source points lying more than {MOVE_M} m "
             f"from their own address (mostly Caring for Friends sites) were moved to the address; {moved['unverified']} addresses "
             "could not be geocoded and keep the source point.",
})
print("    free_meal_sites excluded (citywide):", excluded)
print("    free_meal_sites relocated to their geocoded address (citywide):", moved)

# --- City farmers markets
raw = arcgis(f"{CITY}/Farmers_Markets/FeatureServer/0", "farmers_markets.json")
g = to_gdf(raw)
ORG_RE = re.compile(r"(?i)farm|market|food|trust|inc\b|assoc|communit|church|center|centre|coalition|llc|co-?op|foundation|"
                    r"alliance|project|program|universit|college|school|club|society|network|cdc|corporation|corp\b|city|partners|"
                    r"collective|garden|ministr|district|council|group|organization|initiative|philly|philadelphia|township|borough|"
                    r"conservancy|service|department|authority|parks|recreation|meeting|friends of|county|commonwealth|museum")
MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MKT_DAYS = [("mon", "Mon"), ("tues", "Tue"), ("wed", "Wed"), ("thurs", "Thu"), ("fri", "Fri"), ("sat", "Sat"), ("sun", "Sun")]


def month(v):
    try:
        return MONTHS[int(float(v))]
    except (TypeError, ValueError, IndexError):
        return clean(v)[:3].title()


rows = []
for _, r in g.iterrows():
    parts = []
    hrs = [f"{lab} {clean(r.get(f'hours_{k}_start'))}–{clean(r.get(f'hours_{k}_end'))}" for k, lab in MKT_DAYS if clean(r.get(f"hours_{k}_start"))]
    if hrs:
        parts.append(", ".join(hrs))
    if clean(r.get("season_year_round")).lower() in ("y", "yes", "true", "1"):
        parts.append("year-round")
    elif clean(r.get("season_opening_month")):
        parts.append(f"{month(r.get('season_opening_month'))}–{month(r.get('season_closing_month'))}")
    pay = [lab for f, lab in (("payment_snap", "SNAP"), ("payment_fmnp", "FMNP"), ("payment_philly_food_bucks", "Philly Food Bucks"))
           if clean(r.get(f)).lower() in ("y", "yes", "true", "1")]
    if pay:
        parts.append("accepts " + ", ".join(pay))
    op = clean(r.get("operator"))
    org = bool(op and ORG_RE.search(op))
    if org and norm_name(op) not in norm_name(r.get("name")):
        parts.insert(0, f"Run by {op}")
    rows.append({"category": "food", "kind": "Farmers market", "name": tidy(r.get("name")), "address": tidy(r.get("address")),
                 "phone": phone(r.get("contact_phone")) if org else "", "website": site_url(r.get("contact_website")),
                 "detail": " · ".join(parts), "geometry": r.geometry})
write("phl_farmers_markets", dedupe(frame(rows)), {
    "title": "Farmers' Market Locations", "categories": ["food"], "publisher": "City of Philadelphia (compiled from market managers and operators)",
    "landing_url": "https://opendataphilly.org/datasets/farmers-markets-locations/",
    "api_url": f"{CITY}/Farmers_Markets/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "All listed markets; schedule, season and SNAP / FMNP / Philly Food Bucks acceptance in detail. Operator name and phone kept "
             "only when the operator is an organisation (individual farmers' names and phones are left out).",
})

# --- USDA FNS SNAP authorized retailers (fresh-food store types only)
raw = arcgis(SNAP, "usda_snap_retailers.json")
g = to_gdf(raw)
SNAP_KIND = {"Supermarket": "Supermarket", "Super Store": "Super store", "Grocery Store": "Grocery store",
             "Specialty Store": "Specialty food store", "Farmers and Markets": "Farmers market / produce vendor"}
rows = []
for _, r in g.iterrows():
    st = clean(r.get("Store_Type"))
    if st not in SNAP_KIND:
        continue
    addr = ", ".join(x for x in (" ".join(x for x in (tidy(r.get("Store_Street_Address")), tidy(r.get("Additonal_Address"))) if x),
                                  tidy(r.get("City"))) if x)
    det = "SNAP authorized"
    inc = clean(r.get("Incentive_Program"))
    if inc:
        det += f" · incentive: {inc}"
    rows.append({"category": "food", "kind": f"{SNAP_KIND[st]} (SNAP)", "name": tidy(r.get("Store_Name")), "address": addr,
                 "phone": "", "website": "", "detail": det, "geometry": r.geometry})
write("usda_snap_retailers", dedupe(frame(rows)), {
    "title": "SNAP Retailer Locator: authorized retailers", "categories": ["food"],
    "publisher": "U.S. Department of Agriculture, Food and Nutrition Service (SNAP Retailer Policy and Management Division)",
    "landing_url": "https://www.arcgis.com/home/item.html?id=8b260f9a10b0459aa441ad8588c2251c",
    "api_url": f"{SNAP}/query", "license": "U.S. Government work; no license stated on the item",
    "data_date": f"layer last edited {last_edit(raw)} (USDA updates every 2 weeks)",
    "notes": "Kept USDA store types Supermarket, Super Store, Grocery Store, Specialty Store and Farmers and Markets; dropped "
             "Convenience Store and Other (pharmacies, dollar and gas-station stores). Store type is USDA's classification; "
             "many small 'Grocery Store' retailers are corner stores with limited fresh food.",
})

# --- OSM food stores
raw = overpass("osm_food_stores.json", ['[shop~"^(supermarket|greengrocer|grocery)$"]'])
g = to_points(osm_gdf(raw))
OSM_SHOP = {"supermarket": "Supermarket", "greengrocer": "Produce market", "grocery": "Grocery store"}
rows = []
for _, r in g.iterrows():
    t = r.tags
    if clean(t.get("access")) in ("private", "no"):
        continue
    kind = OSM_SHOP.get(t.get("shop"), "Grocery store")
    rows.append({"category": "food", "kind": f"{kind} (OSM)", "name": clean(t.get("name")) or kind, "address": street_addr(t),
                 "phone": phone(t.get("phone") or t.get("contact:phone")), "website": site_url(t.get("website") or t.get("contact:website")),
                 "detail": "", "geometry": r.geometry})
write("osm_food_stores", dedupe(frame(rows)), {
    "title": "OpenStreetMap supermarkets, grocery stores and produce markets", "categories": ["food"],
    "publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org/",
    "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"OSM data as of {osm_date(raw)}",
    "notes": "shop=supermarket, greengrocer and grocery (convenience stores skipped). Gap filler for the USDA list; OSM coverage "
             "of small stores is incomplete.",
})

# ================================================================ GARDENS & FARMS

print("Gardens & farms ...")

# --- PHS / NGT supported community gardens (current view) + Dec 2022 snapshot for addresses
raw = arcgis(f"{PHS}/PHS_NGT_Supported_Current_view/FeatureServer/0", "phs_ngt_supported_current.json")
g = to_gdf(raw)
raw22 = arcgis(f"{PHS}/Philadelphia_Supported_Gardens_Dec_2022/FeatureServer/0", "phs_ngt_supported_dec2022.json")
g22 = to_gdf(raw22)
g22u = g22.to_crs(UTM) if not g22.empty else g22
ADDR_RE = re.compile(r"^\s*\d[\d\-A-Za-z]*\s+[A-Za-z]")
rows = []
for (_, r), pu in zip(g.iterrows(), g.to_crs(UTM).geometry):
    nm = clean(r.get("Site_Name"))
    addr = ""
    if not g22u.empty:
        d = g22u.geometry.distance(pu)
        if d.min() <= 40:
            addr = clean(g22u.loc[d.idxmin(), "Address_Range"]).split(";")[0]
    if ADDR_RE.match(nm) and not re.match(r"(?i)^\d+(st|nd|rd|th)\b", nm) and not re.search(r"(?i)garden|farm|orchard|park|grow|green", nm):
        # site recorded by address only
        addr = addr or nm.split(";")[0]
        nm = "Community garden"
    sup = clean(r.get("Supported"))
    rows.append({"category": "gardens_farms", "kind": "Community garden", "name": tidy(nm), "address": tidy(addr), "phone": "",
                 "website": site_url(r.get("Website")), "detail": f"Supported by {sup}".replace("NGT", "Neighborhood Gardens Trust") if sup else "",
                 "geometry": r.geometry})
write("phs_ngt_supported_gardens", dedupe(frame(rows)), {
    "title": "PHS Community Garden Program: PHS- and NGT-supported gardens (current)", "categories": ["gardens_farms"],
    "publisher": "Pennsylvania Horticultural Society (PHS), with Neighborhood Gardens Trust (NGT)",
    "landing_url": "https://www.arcgis.com/home/item.html?id=1f4ef32948d64b8280bf78e308c4dead",
    "api_url": f"{PHS}/PHS_NGT_Supported_Current_view/FeatureServer/0/query",
    "license": "No license stated; public layer shared by PHS", "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active gardens in PHS's Community Garden Program ('CGP active gardens'). The current layer has no addresses, so the "
             "address comes from PHS's December 2022 supported-gardens layer when a garden point lies within 40 m.",
})

# --- PPR registered community gardens
raw = arcgis(f"{CITY}/Registered_Community_Gardens/FeatureServer/0", "registered_community_gardens.json")
g = to_gdf(raw)
rows = []
for _, r in g.iterrows():
    if clean(r.get("garden_status")).upper() not in ("ACTIVE", ""):
        continue
    rows.append({"category": "gardens_farms", "kind": "Community garden (PPR-registered)", "name": tidy(r.get("garden_name")),
                 "address": tidy(r.get("address")), "phone": "", "website": site_url(r.get("contact_website")),
                 "detail": clean(r.get("garden_description"))[:140], "geometry": r.geometry})
write("phl_registered_community_gardens", dedupe(frame(rows)), {
    "title": "Registered Community Gardens", "categories": ["gardens_farms"],
    "publisher": "Philadelphia Parks & Recreation, Urban Agriculture Team",
    "landing_url": "https://opendataphilly.org/datasets/registered-community-gardens/",
    "api_url": f"{CITY}/Registered_Community_Gardens/FeatureServer/0/query", "license": CITY_LICENSE,
    "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active gardens registered with PPR's Urban Agriculture Team (a short citywide list of 23; most community gardens are "
             "not registered). Contact emails left out.",
})

# --- PPR urban agriculture projects
raw = arcgis(f"{CITY}/PPR_Urban_Agriculture_Projects/FeatureServer/0", "ppr_urban_agriculture.json")
g = to_gdf(raw)
rows = []
for _, r in g.iterrows():
    if clean(r.get("project_status")).upper() not in ("ACTIVE", ""):
        continue
    park = tidy(r.get("park_name"))
    nm = tidy(r.get("project_name"))
    det = " · ".join(x for x in ((f"In {park}" if park and norm_name(park) != norm_name(nm) else ""),
                                  ("Public hours: " + clean(r.get("public_hours"))[:80]) if clean(r.get("public_hours")) else "") if x)
    rows.append({"category": "gardens_farms", "kind": "Urban agriculture project (PPR land)", "name": nm, "address": tidy(r.get("address")),
                 "phone": "", "website": site_url(r.get("contact_website")), "detail": det, "geometry": r.geometry})
write("phl_ppr_urban_agriculture", dedupe(frame(rows)), {
    "title": "Urban Agriculture Projects", "categories": ["gardens_farms"], "publisher": "Philadelphia Parks & Recreation (Farm Philly)",
    "landing_url": "https://opendataphilly.org/datasets/urban-agriculture-projects/",
    "api_url": f"{CITY}/PPR_Urban_Agriculture_Projects/FeatureServer/0/query", "license": CITY_LICENSE,
    "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active urban agriculture projects on PPR sites (10 citywide). Contact emails left out.",
})

# --- OSM gardens and farms
raw = overpass("osm_gardens_farms.json", ['[landuse~"^(allotments|farmland|farmyard)$"]', '[leisure=garden]["garden:type"=community]'])
g = to_points(osm_gdf(raw))
rows = []
for _, r in g.iterrows():
    t = r.tags
    farm = t.get("landuse") in ("farmland", "farmyard")
    kind = "Urban farm" if farm else "Community garden"
    det = []
    if ORG_RE.search(clean(t.get("operator"))):  # organisations only, never a private person's name
        det.append(f"Operator: {clean(t.get('operator'))}")
    if clean(t.get("access")) in ("private", "no"):
        det.append("access: private (OSM)")
    rows.append({"category": "gardens_farms", "kind": f"{kind} (OSM)", "name": clean(t.get("name")) or kind, "address": street_addr(t),
                 "phone": "", "website": site_url(t.get("website")), "detail": " · ".join(det), "geometry": r.geometry})
write("osm_gardens_farms", dedupe(frame(rows)), {
    "title": "OpenStreetMap community gardens and urban farms", "categories": ["gardens_farms"],
    "publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org/",
    "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"OSM data as of {osm_date(raw)}",
    "notes": "landuse=allotments (community garden), landuse=farmland / farmyard (urban farm) and leisure=garden with "
             "garden:type=community. Polygons placed at a point inside; unnamed features are labelled by type.",
})

# ================================================================ PARKS & RECREATION

print("Parks & recreation ...")

# --- PPR properties as park points
DROP_CLASS = {"TRAFFIC_ISLAND_MEDIAN", "PATHWAY", "OPERATIONAL_INTERNAL"}
DROP_USE = {"OPERATIONS", "OLDER_ADULT_SITE"}
USE_KIND = {"NEIGHBORHOOD_PARK": "Neighborhood park", "RECREATION_SITE": "Park / recreation site", "SQUARE_PLAZA": "Square / plaza",
            "NATURE_AREA": "Natural area", "SPORTS_COMPLEX": "Athletic fields / sports complex", "GREENWAY": "Greenway",
            "ENVIRONMENTAL_EDUCATION_CENTER": "Environmental education center", "GOLF": "Golf course",
            "HISTORIC_SITE": "Park (historic site)", "MUSEUM_CAMPUS": "Park (museum grounds)", "EVENT_SPACE": "Park (event space)",
            "BOATHOUSE_LAUNCH": "Boat launch", "GARDEN_FARM": "Garden / farm on PPR land", "OTHER": "Park"}
CLASS_KIND = {"WATERSHED_PARK": "Watershed park", "CONSERVATION": "Conservation land", "URBAN_AGRICULTURE": "Garden / farm on PPR land"}
sel = ppr[ppr.intersects(AREA)].copy()
sel_utm = sel.to_crs(UTM)
rows = []
dropped = {}
for (_, r), gu in zip(sel.iterrows(), sel_utm.geometry):
    cls, use = clean(r.get("property_classification")), clean(r.get("ppr_use"))
    if cls in DROP_CLASS or use in DROP_USE:
        dropped[cls if cls in DROP_CLASS else use] = dropped.get(cls if cls in DROP_CLASS else use, 0) + 1
        continue
    garden = use == "GARDEN_FARM" or cls == "URBAN_AGRICULTURE"
    kind = CLASS_KIND.get(cls) if cls in ("WATERSHED_PARK", "CONSERVATION") and use in ("NATURE_AREA", "OTHER", "") else None
    kind = kind or USE_KIND.get(use) or CLASS_KIND.get(cls) or "Park"
    if garden:
        kind = "Garden / farm on PPR land"
    nm = tidy(clean(r.get("official_name")) or clean(r.get("site_name")) or clean(r.get("label")))
    acres = r.get("acreage")
    det = [f"{acres:,.1f} acres" if isinstance(acres, (int, float)) and not math.isnan(acres) else ""]
    parent = tidy(r.get("park_name"))
    if clean(r.get("nested")).upper() == "Y" and parent and norm_name(parent) != norm_name(nm):
        det.append(f"part of {parent}")
    pt = gpd.GeoSeries([point_inside(gu)], crs=UTM).to_crs(4326).iloc[0]
    rows.append({"category": "gardens_farms" if garden else "parks_rec", "kind": kind, "name": nm, "address": tidy(r.get("address_911")),
                 "phone": "", "website": "", "detail": " · ".join(x for x in det if x), "geometry": pt})
write("phl_ppr_properties", dedupe(frame(rows)), {
    "title": "PPR Properties (parks as points)", "categories": ["parks_rec", "gardens_farms"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/ppr-properties/",
    "api_url": f"{CITY}/PPR_Properties/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(ppr_raw)}",
    "notes": "One point inside each PPR property polygon (inside the part that lies within 1.5 mi of a site for large parks); acreage is "
             "the whole property. Dropped traffic islands / medians, pathways, internal operational sites and older-adult-center "
             "properties; PPR garden / farm properties are tagged gardens_farms.",
})
print("    PPR properties dropped in area:", dropped)

# --- PPR program sites (recreation centers, pools, environmental education centers)
raw = arcgis(f"{CITY}/PPR_Program_Sites/FeatureServer/0", "ppr_program_sites.json")
g = to_gdf(raw)
g = g[g.program_type != "OLDER_ADULT_CENTER"].copy()
look = ppr_lookup(g) if not g.empty else []
rows = []
for (_, r), (pname, paddr, parent) in zip(g.iterrows(), look):
    pt_ = clean(r.get("program_type"))
    bld, gym = clean(r.get("building")).upper() == "Y", clean(r.get("gym")).upper() == "Y"
    if pt_ == "PPR_REC":
        kind = "Recreation center" if bld else "Recreation site (no building)"
    elif pt_ == "POOL":
        kind = "Pool (program site)"
    elif pt_ == "ENVIRONMENTAL_EDUCATION_CENTER":
        kind = "Environmental education center"
    else:
        kind = tidy(pt_.replace("_", " "))
    det = "Building with gym" if bld and gym else ("Building, no gym" if bld else "")
    rows.append({"category": "parks_rec", "kind": kind, "name": best_site(r.get("park_name"), pname, parent), "address": paddr,
                 "phone": "", "website": "", "detail": det, "geometry": r.geometry})
write("phl_ppr_program_sites", dedupe(frame(rows)), {
    "title": "Parks & Recreation Program Sites", "categories": ["parks_rec"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/parks-recreation-program-sites/",
    "api_url": f"{CITY}/PPR_Program_Sites/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Recreation centers / staffed recreation sites, program pools and environmental education centers. Older adult centers "
             "(program_type OLDER_ADULT_CENTER) excluded for the health domain. Address taken from the PPR property the point sits in.",
})

# --- PPR playgrounds (one point per play area; same-site play areas within 40 m merged)
raw = arcgis(f"{CITY}/PPR_Playgrounds/FeatureServer/0", "ppr_playgrounds.json")
g = to_gdf(raw)
PPR_PLAY = g.to_crs(UTM) if not g.empty else g
look = ppr_lookup(g) if not g.empty else []
AGES = {"2_5_YEARS": "ages 2–5", "5_12_YEARS": "ages 5–12", "2_12_YEARS": "ages 2–12"}
rows = []
for (_, r), (pname, paddr, parent) in zip(g.iterrows(), look):
    park = best_site(r.get("park_name"), pname, parent)
    rows.append({"category": "parks_rec", "kind": "Playground", "name": f"Playground at {park}" if park else "Playground",
                 "address": paddr, "phone": "", "website": "", "detail": AGES.get(clean(r.get("age_range")), ""), "geometry": r.geometry})


def merge_ages(members):
    ages = sorted({m["detail"] for m in members if m["detail"]})
    return f"{len(members)} play areas" + (" (" + ", ".join(ages) + ")" if ages else "")


write("phl_ppr_playgrounds", dedupe(frame(rows), merge_ages), {
    "title": "PPR Playgrounds", "categories": ["parks_rec"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/ppr-playgrounds/",
    "api_url": f"{CITY}/PPR_Playgrounds/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "PPR play areas (grouped by age range). Play areas of the same park within 40 m are merged into one point with the "
             "count and age ranges in detail.",
})

# --- PPR spraygrounds (active)
raw = arcgis(f"{CITY}/PPR_Spraygrounds/FeatureServer/0", "ppr_spraygrounds.json")
g = to_gdf(raw)
look = ppr_lookup(g) if not g.empty else []
rows = []
for (_, r), (pname, paddr, parent) in zip(g.iterrows(), look):
    if clean(r.get("spray_status")).upper() != "ACTIVE":
        continue
    kind = "Sprinkler" if clean(r.get("spray_type")).upper() == "SPRINKLER" else "Sprayground"
    park = best_site(r.get("park_name"), pname, parent)
    rows.append({"category": "parks_rec", "kind": kind, "name": f"{kind} at {park}" if park else kind, "address": paddr,
                 "phone": "", "website": "", "detail": "", "geometry": r.geometry})
write("phl_ppr_spraygrounds", dedupe(frame(rows)), {
    "title": "PPR Spraygrounds", "categories": ["parks_rec"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/ppr-spraygrounds/",
    "api_url": f"{CITY}/PPR_Spraygrounds/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active spraygrounds and sprinklers only (status INACTIVE / UNKNOWN dropped).",
})

# --- PPR swimming pools (active)
raw = arcgis(f"{CITY}/PPR_Swimming_Pools/FeatureServer/0", "ppr_swimming_pools.json")
g = to_gdf(raw)
rows = []
for _, r in g.iterrows():
    if clean(r.get("pool_status")).upper() != "ACTIVE":
        continue
    site = tidy(r.get("site_name"))
    det = [f"at {site}" if site else ""]
    if clean(r.get("ada_lift")).upper() == "Y":
        det.append("ADA lift")
    rows.append({"category": "parks_rec", "kind": "Indoor pool" if clean(r.get("pool_type")).upper() == "INDOOR" else "Outdoor pool",
                 "name": tidy(r.get("pool_name")) or tidy(r.get("label")), "address": tidy(r.get("address_911")), "phone": "", "website": "",
                 "detail": " · ".join(x for x in det if x), "geometry": r.geometry})
write("phl_ppr_swimming_pools", dedupe(frame(rows)), {
    "title": "PPR Swimming Pools", "categories": ["parks_rec"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/ppr-swimming-pools/",
    "api_url": f"{CITY}/PPR_Swimming_Pools/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "Active PPR pools (inactive pools dropped). Pool status is PPR's facility status, not this season's opening schedule.",
})

# --- PPR tennis courts (courts at one park within 40 m merged with a count)
raw = arcgis(f"{CITY}/PPR_Tennis_Courts/FeatureServer/0", "ppr_tennis_courts.json")
g = to_gdf(raw)
PPR_TENNIS = g.to_crs(UTM) if not g.empty else g
look = ppr_lookup(g) if not g.empty else []
rows = []
for (_, r), (pname, paddr, parent) in zip(g.iterrows(), look):
    park = best_site(r.get("park_name"), pname, parent)
    rows.append({"category": "parks_rec", "kind": "Tennis courts", "name": f"Tennis courts at {park}" if park else "Tennis courts",
                 "address": paddr, "phone": "", "website": "", "detail": "1 court", "geometry": r.geometry})
write("phl_ppr_tennis_courts", dedupe(frame(rows), lambda m: f"{len(m)} courts"), {
    "title": "PPR Tennis Courts", "categories": ["parks_rec"], "publisher": "Philadelphia Parks & Recreation",
    "landing_url": "https://opendataphilly.org/datasets/ppr-tennis-courts/",
    "api_url": f"{CITY}/PPR_Tennis_Courts/FeatureServer/0/query", "license": CITY_LICENSE, "data_date": f"layer last edited {last_edit(raw)}",
    "notes": "One record per court in the source; courts at the same park within 40 m are merged into one point with a count.",
})

# --- OSM context polygons: school / college grounds (for labelling) and PPR land (for gap filtering)
raw_ctx = overpass("osm_school_grounds.json", ['[amenity~"^(school|college|university)$"]'])
schools_osm = osm_gdf(raw_ctx)
schools_osm = schools_osm[schools_osm.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(UTM)
schools_osm["kind"] = schools_osm.tags.map(lambda t: "school" if t.get("amenity") == "school" else "campus")
PPR_LAND = unary_union(list(ppr_utm.geometry.buffer(10)))
PPR_NAMES = [(g_, {norm_name(r.get(k)) for k in ("official_name", "site_name", "label", "alias") if norm_name(r.get(k))})
             for g_, (_, r) in zip(ppr_utm.geometry, ppr_utm.iterrows())]


def same_ppr_name(name, pt_utm, max_m=300):
    n = norm_name(name)
    for geom, names in PPR_NAMES:
        if any(n == x or (len(n) > 6 and len(x) > 6 and (n in x or x in n)) for x in names) and geom.distance(pt_utm) <= max_m:
            return True
    return False


def setting(pt_utm):
    """(where, label, park) for an OSM feature point: in a PPR park / on school grounds / on a college campus."""
    hit = ppr_utm[ppr_utm.geometry.contains(pt_utm)]
    if not hit.empty:
        r = hit.sort_values("area").iloc[0]
        park = tidy(clean(r.get("official_name")) or clean(r.get("site_name")) or clean(r.get("label")))
        return "ppr", f"in {park}", park
    s = schools_osm[schools_osm.geometry.contains(pt_utm)]
    if not s.empty:
        return ("school", "on school grounds", "") if (s.kind == "school").any() else ("campus", "on a college campus", "")
    return "", "", ""


# --- OSM sports facilities: courts, fields, tracks, rinks, skateparks
raw = overpass("osm_sports.json", ['[leisure~"^(pitch|track|ice_rink|skatepark)$"]'])
g = osm_gdf(raw)
g = to_points(g)
SPORT_KIND = [
    (r"basketball", "Basketball court"), (r"pickleball|padel", "Pickleball / padel court"), (r"tennis", "Tennis court"),
    (r"baseball|softball", "Baseball / softball field"), (r"american_football|canadian_football", "Football field"),
    (r"soccer|futsal", "Soccer field"), (r"lacrosse", "Lacrosse field"), (r"rugby", "Rugby field"), (r"cricket", "Cricket field"),
    (r"athletics|running", "Running track"), (r"beachvolleyball|volleyball", "Volleyball court"), (r"handball", "Handball court"),
    (r"skateboard", "Skatepark"), (r"roller_hockey", "Roller hockey rink"), (r"ice_hockey|ice_skating", "Ice rink"), (r"bmx", "BMX track"),
]
SKIP_SPORT = re.compile(r"^(four_square|gaga|shuffleboard|batting_cage|equestrian|rowing|bocce|chess|table_tennis)$")
rows = []
for (_, r), pu in zip(g.iterrows(), g.to_crs(UTM).geometry):
    t = r.tags
    if clean(t.get("access")) in ("private", "no", "customers", "members"):
        continue
    sport = clean(t.get("sport")).lower()
    if sport and SKIP_SPORT.match(sport):
        continue
    lei = t.get("leisure")
    kind = None
    if sport.startswith("multi") and ";" in sport:
        kind = "Multi-use field"
    for pat, k in SPORT_KIND:
        if kind is None and re.search(pat, sport):
            kind = k
    if kind is None:
        kind = {"ice_rink": "Ice rink", "skatepark": "Skatepark", "track": "Running track"}.get(lei, "Athletic field / court")
    if kind == "Tennis court" and not PPR_TENNIS.empty and PPR_TENNIS.geometry.distance(pu).min() <= 100:
        continue  # PPR's own tennis-court layer covers these
    where, label, park = setting(pu)
    nm = clean(t.get("name"))
    if not nm:
        nm = {"ppr": f"{kind} at {park}", "school": f"{kind} (school grounds)", "campus": f"{kind} (college campus)"}.get(where, kind)
    rows.append({"category": "parks_rec", "kind": kind, "name": nm, "address": street_addr(t), "phone": "",
                 "website": site_url(t.get("website")), "detail": "" if where == "ppr" and park in nm else label, "geometry": r.geometry})


def count_courts(m):
    k = m[0]["kind"].lower()
    unit = next((u for w, u in (("court", "courts"), ("field", "fields"), ("track", "tracks"), ("rink", "rinks"), ("skatepark", "skateparks"))
                 if w in k), "facilities")
    label = m[0]["detail"]
    return f"{len(m)} {unit}" + (f" · {label}" if label else "")


write("osm_sports_facilities", dedupe(frame(rows), count_courts), {
    "title": "OpenStreetMap courts, athletic fields, tracks, rinks and skateparks", "categories": ["parks_rec"],
    "publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org/",
    "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"OSM data as of {osm_date(raw)}",
    "notes": "leisure=pitch / track / ice_rink / skatepark, typed by sport; access=private / customers dropped, as are painted "
             "schoolyard games (four square, gaga). Adjacent same-type courts within 40 m merged with a count. Detail says whether the "
             "facility sits in a PPR park, on school grounds or on a college campus (school courts may not be open to the public). "
             "Fills the gap left by PPR, which publishes no ballfield / basketball court layer.",
})

# --- OSM parks, playgrounds and dog parks that are NOT on PPR land
raw = overpass("osm_parks_playgrounds.json", ['[leisure~"^(park|playground|dog_park|nature_reserve)$"]'])
g = osm_gdf(raw)
g_utm = g.to_crs(UTM)
rows = []
for (_, r), gu in zip(g.iterrows(), g_utm.geometry):
    t = r.tags
    if clean(t.get("access")) in ("private", "no", "customers", "members"):
        continue
    pu = point_inside(gu)
    if PPR_LAND.contains(pu):
        continue
    lei = t.get("leisure")
    nm = clean(t.get("name"))
    if nm and same_ppr_name(nm, pu):
        continue  # PPR property of the same name nearby (polygons drawn differently)
    if lei in ("park", "nature_reserve") and not nm:
        continue  # unnamed OSM 'parks' are mostly landscaped strips
    if lei == "playground" and not PPR_PLAY.empty and PPR_PLAY.geometry.distance(pu).min() <= 60:
        continue
    kind = {"park": "Park (non-PPR)", "nature_reserve": "Nature preserve (non-PPR)", "playground": "Playground (non-PPR)",
            "dog_park": "Dog park"}[lei]
    det = []
    if lei in ("park", "nature_reserve") and gu.geom_type in ("Polygon", "MultiPolygon"):
        det.append(f"{gu.area / 4046.856:,.1f} acres")
    if ORG_RE.search(clean(t.get("operator"))):  # organisations only, never a private person's name
        det.append(f"Operator: {clean(t.get('operator'))}")
    _, label, _ = setting(pu)
    if label:
        det.append(label)
    rows.append({"category": "parks_rec", "kind": kind, "name": nm or kind.replace(" (non-PPR)", ""), "address": street_addr(t), "phone": "",
                 "website": site_url(t.get("website")), "detail": " · ".join(det),
                 "geometry": gpd.GeoSeries([pu], crs=UTM).to_crs(4326).iloc[0]})
write("osm_parks_playgrounds_nonppr", dedupe(frame(rows)), {
    "title": "OpenStreetMap parks, playgrounds and dog parks outside PPR property", "categories": ["parks_rec"],
    "publisher": "OpenStreetMap contributors (via Overpass API)", "landing_url": "https://www.openstreetmap.org/",
    "api_url": OVERPASS[0], "license": OSM_LICENSE, "data_date": f"OSM data as of {osm_date(raw)}",
    "notes": "Gap filler: named leisure=park / nature_reserve, leisure=playground and leisure=dog_park whose point lies outside every "
             "PPR property (playgrounds also > 60 m from a PPR play area); includes township parks across the city line, "
             "institutional and housing-site playgrounds. access=private / customers dropped; detail flags school grounds.",
})

# --- OSM trailheads
raw = overpass("osm_trailheads.json", ["[highway=trailhead]"])
g = osm_gdf(raw)
g = to_points(g)
rows = []
for (_, r), pu in zip(g.iterrows(), g.to_crs(UTM).geometry):
    t = r.tags
    if clean(t.get("access")) in ("private", "no"):
        continue
    _, label, _ = setting(pu)
    det = " · ".join(x for x in (label, clean(t.get("description"))[:100]) if x)
    rows.append({"category": "parks_rec", "kind": "Trailhead / park entrance", "name": clean(t.get("name")) or "Trailhead",
                 "address": street_addr(t), "phone": "", "website": "", "detail": det, "geometry": r.geometry})
write("osm_trailheads", dedupe(frame(rows)), {
    "title": "OpenStreetMap trailheads", "categories": ["parks_rec"], "publisher": "OpenStreetMap contributors (via Overpass API)",
    "landing_url": "https://www.openstreetmap.org/", "api_url": OVERPASS[0], "license": OSM_LICENSE,
    "data_date": f"OSM data as of {osm_date(raw)}",
    "notes": "highway=trailhead nodes (mostly Wissahickon Valley Park entrances). No official City trailhead point layer exists; "
             "PPR publishes trails only as lines.",
})

# ---------------------------------------------------------------- manifest

(OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=1, ensure_ascii=False))
print(f"\nWrote {len(MANIFEST)} datasets to {OUT}")
print(f"{'dataset':38s} {'total':>5s} {'Wagner<=1mi':>12s} {'Blankenburg<=1mi':>17s}")
for ds, n, w, b in SUMMARY:
    print(f"{ds:38s} {n:5d} {w:12d} {b:17d}")
