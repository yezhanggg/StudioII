"""Health domain of the community-asset inventory: health care, pharmacies, older adults, social services.

Collects every asset within 1.5 miles (2,414 m) of any of the six school sites (scripts/fetch/schools.json) from
official sources first (City of Philadelphia, Commonwealth of Pennsylvania, HRSA, SAMHSA, CMS, HUD) and
OpenStreetMap to fill gaps, then writes one GeoJSON per source dataset plus manifest.json to
scripts/fetch/out/health/ (see scripts/fetch/CONTRACT.md).

Left out on purpose: addiction-treatment residences and any residential treatment setting, shelters, group homes,
nursing homes / assisted living / personal care homes (residences, not walk-in services), domestic-violence and
victim services, and every personal name, e-mail or personal phone a source carries.

Run:  uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/health.py
      REFRESH=1 ... re-downloads everything instead of using scripts/.cache/fetch/health/
"""
import csv
import datetime as dt
import html
import io
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out" / "health"
CACHE = ROOT / "scripts" / ".cache" / "fetch" / "health"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

SITES = json.loads((HERE / "schools.json").read_text())
RADIUS = 2414.0          # 1.5 miles: every category in this domain
MILE = 1609.344
UA = {"User-Agent": "studio-community-maps/1.0"}
REFRESH = os.environ.get("REFRESH") == "1"
TODAY = dt.date.today()
CITY = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
ODP = "https://opendataphilly.org/datasets"
CITY_LICENSE = "City of Philadelphia License (per OpenDataPhilly)"
FED = "Public domain (U.S. federal government data)"
OSM_LICENSE = "ODbL 1.0, (c) OpenStreetMap contributors"


# ================================================================ small helpers
def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = re.sub(r"\s+", " ", html.unescape(str(v))).strip()
    return "" if s.lower() in ("nan", "none", "null", "<na>", "n/a") else s


ACRONYMS = {"CVS", "PHMC", "GPHA", "DVCH", "FPCN", "QCHC", "LLC", "PA", "WIC", "CDC", "NAC", "NEC", "HUD", "VA", "PCA",
            "LIFE", "PACE", "CAO", "LIHEAP", "HIV", "USA", "YMCA", "YWCA", "II", "III", "IV", "PC", "MH", "CHOP", "HUP",
            "DHS", "PDPH", "RHD", "APM", "GPASS", "HACE", "PCDC", "GPCA", "UAC", "DMD", "DDS", "MD", "DO", "LTC", "WES",
            "NET", "MCP", "FQHC", "UPENN", "CCIS", "PSC", "ECA", "AHCOPA", "JFK", "AME", "PCOM", "FIGHT", "SHARE", "CTR"}
SMALL = {"of", "and", "the", "at", "for", "on", "in", "to", "de", "la", "del"}


def title(s):
    """Title case for ALL-CAPS (or all-lower) source text; acronyms stay upper case."""
    s = clean(s)
    if not s or not (s.isupper() or s.islower()):
        return s
    words = []
    for i, w in enumerate(s.split(" ")):
        core = re.sub(r"[^A-Za-z]", "", w).upper()
        if core in ACRONYMS and len(core) == len(re.sub(r"[^A-Za-z]", "", w)):
            words.append(w.upper())
        elif i and w.lower() in SMALL:
            words.append(w.lower())
        else:
            words.append(w.capitalize() if "-" not in w else "-".join(p.capitalize() for p in w.split("-")))
    s = " ".join(words)
    s = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    s = re.sub(r"'S\b", "'s", s)
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    s = re.sub(r"\bInc\b(?!\.)", "Inc.", s)
    return s


def phone(v):
    s = clean(v)
    d = re.sub(r"\D", "", s.split(" x")[0].split("ext")[0])
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"{d[:3]}-{d[3:6]}-{d[6:10]}" if len(d) == 10 else s


def web(v):
    s = clean(v)
    if not s:
        return ""
    return s if re.match(r"https?://", s, re.I) else "https://" + s.lstrip("/")


def meters(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def nearest(lat, lon):
    return min(meters(s["lat"], s["lng"], lat, lon) for s in SITES)


def in_area(lat, lon, r=RADIUS):
    try:
        return lat is not None and lon is not None and nearest(float(lat), float(lon)) <= r
    except (TypeError, ValueError):
        return False


LAT0 = sum(s["lat"] for s in SITES) / len(SITES)
LON0 = sum(s["lng"] for s in SITES) / len(SITES)
REACH = max(meters(LAT0, LON0, s["lat"], s["lng"]) for s in SITES) + RADIUS + 300      # one circle around all six
DLAT, DLON = RADIUS / 111320, RADIUS / (111320 * math.cos(math.radians(LAT0)))
BBOX = (min(s["lat"] for s in SITES) - DLAT, min(s["lng"] for s in SITES) - DLON,
        max(s["lat"] for s in SITES) + DLAT, max(s["lng"] for s in SITES) + DLON)          # S, W, N, E


# ================================================================ downloads (cached)
def http(method, url, retries=4, **kw):
    kw.setdefault("timeout", 180)
    kw["headers"] = {**UA, **kw.get("headers", {})}
    last = None
    for attempt in range(retries):
        try:
            r = requests.request(method, url, **kw)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except Exception as e:                                     # noqa: BLE001  (network hiccups: retry)
            last = e
            time.sleep(4 * (attempt + 1))
    raise last


def cached(name, fetch, text=False):
    """Raw response cached under scripts/.cache/fetch/health/<name>; returns (data, retrieved date)."""
    f = CACHE / name
    if REFRESH or not f.exists():
        data = fetch()
        f.write_text(data if text else json.dumps(data), encoding="utf-8")
    raw = f.read_text(encoding="utf-8")
    return (raw if text else json.loads(raw)), dt.date.fromtimestamp(f.stat().st_mtime).isoformat()


def city_layer(service, where="1=1", layer=0):
    """All records of a City ArcGIS layer as [(attributes, lat, lon)], plus layer metadata."""
    base = f"{CITY}/{service}/FeatureServer/{layer}"

    def fetch():
        feats, offset = [], 0
        while True:
            j = http("GET", base + "/query", params={"where": where, "outFields": "*", "outSR": 4326, "f": "json",
                                                     "resultOffset": offset, "resultRecordCount": 1000}).json()
            if "error" in j:
                raise RuntimeError(f"{service}: {j['error']}")
            feats += j.get("features", [])
            if not j.get("exceededTransferLimit"):
                break
            offset += len(j.get("features", []))
        meta = http("GET", base, params={"f": "json"}).json()
        return {"features": feats, "meta": {k: meta.get(k) for k in ("name", "editingInfo", "description")}}

    data, got = cached(f"city_{service}_{layer}.json", fetch)
    rows = []
    for f in data["features"]:
        g = f.get("geometry") or {}
        if "x" in g and "y" in g and g["x"] is not None:
            rows.append((f["attributes"], g["y"], g["x"]))
    ed = (data["meta"].get("editingInfo") or {}).get("lastEditDate")
    edited = dt.datetime.fromtimestamp(ed / 1000, dt.timezone.utc).date().isoformat() if ed else ""
    return rows, got, edited, base + "/query"


def overpass():
    s, w, n, e = BBOX
    b = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    q = f"""[out:json][timeout:180];
(
  nwr["amenity"~"^(pharmacy|clinic|doctors|dentist|social_facility|community_centre)$"]{b};
  nwr["healthcare"]{b};
  nwr["shop"="chemist"]{b};
  nwr["social_facility"]{b};
  nwr["office"~"^(government|lawyer|ngo|association|charity)$"]{b};
);
out center tags;"""

    def fetch():
        last = None
        for attempt in range(6):                    # Overpass is busy at times: back off and alternate with a mirror
            url = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")[attempt % 2]
            try:
                r = requests.post(url, data={"data": q}, timeout=240, headers=UA)
                r.raise_for_status()
                j = r.json()
                if "elements" in j:
                    return j
                last = RuntimeError(str(j)[:200])
            except Exception as ex:                  # noqa: BLE001
                last = ex
            time.sleep(10 * (attempt + 1))
        raise last

    data, got = cached("osm_overpass.json", fetch)
    out = []
    for el in data["elements"]:
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is not None:
            out.append((el.get("tags", {}), lat, lon, f"{el['type']}/{el['id']}"))
    return out, got, (data.get("osm3s") or {}).get("timestamp_osm_base", "")[:10]


AIS_FILE = CACHE / "ais_geocode.json"
AIS = json.loads(AIS_FILE.read_text()) if AIS_FILE.exists() and not REFRESH else {}


def geocode(street):
    """City of Philadelphia Address Information System (AIS) -> (lat, lon) or None. Cached."""
    q = clean(street).split(",")[0]
    q = re.sub(r"\b(FL|FLR|FLOOR|STE|SUITE|RM|ROOM|UNIT|APT|BLDG|BUILDING)\b\.?\s*[\w-]*.*$", "", q, flags=re.I)
    q = re.sub(r"#.*$", "", q).strip().rstrip(".")
    q = re.sub(r"\bChesnut\b", "Chestnut", q, flags=re.I)
    if not q:
        return None
    if q not in AIS:
        r = http("GET", "https://api.phila.gov/ais/v1/search/" + quote(q), retries=2, timeout=60)
        hit = None
        if r.status_code == 200:
            fs = r.json().get("features") or []
            if fs and fs[0].get("geometry", {}).get("coordinates"):
                x, y = fs[0]["geometry"]["coordinates"][:2]
                hit = [y, x]
        AIS[q] = hit
        AIS_FILE.write_text(json.dumps(AIS))
        time.sleep(0.15)
    return tuple(AIS[q]) if AIS[q] else None


# ================================================================ standard records
def rec(cat, kind, name, address, lat, lon, ph="", site="", detail="", keep_case=False):
    fix = clean if keep_case else title
    return {"category": cat, "kind": clean(kind), "name": fix(name), "address": fix(address).rstrip(" .,"), "phone": phone(ph),
            "website": web(site), "detail": clean(detail), "lat": float(lat), "lon": float(lon)}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def dedupe(rows):
    keep = []
    for r in rows:
        if any(norm(r["name"]) == norm(k["name"]) and meters(r["lat"], r["lon"], k["lat"], k["lon"]) <= 40 for k in keep):
            continue
        keep.append(r)
    return keep


MANIFEST, SUMMARY = [], []
WAGNER = next(s for s in SITES if s["slug"] == "wagner")
BLANK = next(s for s in SITES if s["slug"] == "blankenburg")


def write(meta, rows):
    rows = dedupe([r for r in rows if r["name"] and in_area(r["lat"], r["lon"])])
    rows.sort(key=lambda r: (r["category"], r["name"]))
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r["lon"], 6), round(r["lat"], 6)]},
              "properties": {**{k: r[k] for k in ("category", "kind", "name", "address", "phone", "website", "detail")},
                             "source_id": meta["id"]}} for r in rows]
    (OUT / f"{meta['id']}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, indent=1), encoding="utf-8")
    MANIFEST.append({**meta, "categories": sorted({r["category"] for r in rows}) or meta["categories"], "records": len(rows)})
    w = sum(meters(WAGNER["lat"], WAGNER["lng"], r["lat"], r["lon"]) <= MILE for r in rows)
    b = sum(meters(BLANK["lat"], BLANK["lng"], r["lat"], r["lon"]) <= MILE for r in rows)
    SUMMARY.append((meta["id"], len(rows), w, b))
    print(f"  {meta['id']:<36} {len(rows):>4} in area   {w:>3} within 1 mi of Wagner   {b:>3} of Blankenburg")


def m(id_, title_, cats, publisher, landing, api, license_, retrieved, data_date, notes):
    return {"id": id_, "title": title_, "categories": cats, "publisher": publisher, "landing_url": landing, "api_url": api,
            "license": license_, "retrieved": retrieved, "data_date": data_date, "notes": notes}


def edited(d):
    return f"layer last edited {d}" if d else ""


# ================================================================ health care
def phl_health_centers():
    rows, got, ed, api = city_layer("Health_Centers")
    out = []
    for a, lat, lon in rows:
        org = clean(a.get("organization"))
        kind = "City health center" if org == "PDPH" else "Community health center"
        detail = " · ".join(x for x in ((f"Operated by {org}" if org and org != "PDPH" else "Philadelphia Department of Public Health"),
                                         "dental care" if clean(a.get("dental_phone")) else "") if x)
        out.append(rec("health_care", kind, a.get("name"), a.get("full_address"), lat, lon, a.get("phone"), a.get("website"), detail))
    write(m("phl_health_centers", "Health Centers", ["health_care"], "City of Philadelphia, Department of Public Health",
            f"{ODP}/health-centers/", api, CITY_LICENSE, got, edited(ed),
            "City health centers (PDPH) and the community health centers the City lists. Quality Community Health Care (QCHC) "
            "sites appear here but not in HRSA's current FQHC list, so check that they still operate."), out)


def phl_hospitals():
    rows, got, ed, api = city_layer("Hospitals")
    out = []
    for a, lat, lon in rows:
        name = clean(a.get("hospital_name"))
        if re.search(r"kirkbride", name, re.I):      # residential addiction treatment: left out under the contract
            continue
        t = clean(a.get("hospital_type"))
        detail = ""
        if re.search(r"Mercy Philadelphia", name, re.I):
            detail = "PA DOH and SAMHSA now list this address as Hospital of the University of Pennsylvania – Cedar Avenue"
        out.append(rec("health_care", "Hospital" + (f" ({t.lower()})" if t else ""), name, a.get("street_address"), lat, lon,
                       a.get("phone_number"), "", detail))
    write(m("phl_hospitals", "Philadelphia Hospitals", ["health_care"], "City of Philadelphia, Department of Public Health",
            f"{ODP}/philadelphia-hospitals/", api, CITY_LICENSE, got, edited(ed),
            "All hospitals on the City list. Kirkbride Center (111 N 49th St, mostly residential addiction treatment) is left out "
            "under the no-addiction-residence rule. Some names predate mergers and closures; pa_doh_hospitals carries the "
            "current state licensure names."), out)


def pa_doh_hospitals():
    base = "https://mapservices.pasda.psu.edu/server/rest/services/pasda/DepHealth/MapServer"
    s, w, n, e = BBOX

    def fetch():
        lyr = http("GET", f"{base}/6", params={"f": "json"}).json()
        j = http("GET", f"{base}/6/query", params={"where": "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
                                                   "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
                                                   "outSR": 4326, "f": "json"}).json()
        return {"layer": lyr.get("name"), "features": j.get("features", [])}

    data, got = cached("pasda_doh_hospitals.json", fetch)
    out = []
    for f in data["features"]:
        a, g = f["attributes"], f.get("geometry") or {}
        name = clean(a.get("NAME")).replace("CORPORALMICHAEL", "CORPORAL MICHAEL")
        name = re.split(r"\s+d/b/a\s+", name, flags=re.I)[-1]
        if not g or re.search(r"kirkbride", name, re.I):
            continue
        out.append(rec("health_care", "Hospital", name, a.get("STREET"), g["y"], g["x"], a.get("TELEPHONE"), a.get("WEBSITE"),
                       "Licensed by the PA Department of Health"))
    stamp = re.search(r"(\d{4})(\d{2})\s*$", data.get("layer") or "")
    write(m("pa_doh_hospitals", "PA Department of Health Hospitals (DOH Hospitals " + (stamp.group(0).strip() if stamp else "") + ")",
            ["health_care"], "Pennsylvania Department of Health (via PASDA)",
            "https://www.pasda.psu.edu/uci/FullMetadataDisplay.aspx?file=DOH_Hospitals202511.xml", f"{base}/6/query",
            "Not specified by the publisher", got, f"{stamp.group(1)}-{stamp.group(2)}" if stamp else "",
            "Hospitals licensed by PA DOH. Private psychiatric hospitals licensed by PA DHS (e.g. Belmont, Friends) are not "
            "in this list; the City list has them. Executive names are not kept."), out)


SHELTERED = re.compile(r"interim house|family manor|\bPEC\b|hopephl|shelter|safe haven|residence|recovery house", re.I)


def hrsa_sites():
    url = "https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv"

    def fetch():
        r = http("GET", url, timeout=300, headers={"User-Agent": "Mozilla/5.0 (studio-community-maps/1.0)"})
        rows = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        return [a for a in rows if a.get("Site State Abbreviation") in ("PA", "NJ")       # keep a margin around the area
                and in_area(a["Geocoding Artifact Address Primary Y Coordinate"], a["Geocoding Artifact Address Primary X Coordinate"], r=RADIUS + 3000)]

    data, got = cached("hrsa_health_center_sites.json", fetch)
    out, dates = [], set()
    for a in data:
        dates.add(a.get("Data Warehouse Record Create Date", ""))
        if a["Site Status Description"] != "Active" or a["Health Center Location Type Description"] != "Permanent" \
                or a["Health Center Type Description"] == "Administrative":
            continue
        if SHELTERED.search(a["Site Name"]):
            continue                                 # clinics inside shelters / residential treatment
        school = "School" in a["Health Center Service Delivery Site Location Setting Description"]
        lookalike = "Look-Alike" in a["Health Center Type"]
        kind = "School-based health center" if school else ("FQHC look-alike site" if lookalike else "Federally qualified health center site")
        out.append(rec("health_care", kind, a["Site Name"], a["Site Address"], a["Geocoding Artifact Address Primary Y Coordinate"],
                       a["Geocoding Artifact Address Primary X Coordinate"], a["Site Telephone Number"], a["Site Web Address"],
                       f"Operated by {title(a['Health Center Name'])}"))
    d = sorted(x for x in dates if x)
    dd = dt.datetime.strptime(d[-1], "%m/%d/%Y").date().isoformat() if d else ""
    write(m("hrsa_health_center_sites", "Health Center Service Delivery and Look-Alike Sites", ["health_care"],
            "U.S. Health Resources and Services Administration (HRSA), Bureau of Primary Health Care", "https://data.hrsa.gov/data/download",
            url, FED, got, f"{dd} (HRSA Data Warehouse record date)" if dd else "",
            "Active, permanent FQHC and look-alike service delivery sites; administrative-only offices, seasonal sites and mobile "
            "vans are left out, as are clinics inside shelters or residential treatment (Interim House West, Stenton Family "
            "Manor, PEC/HopePHL). School-based sites are kept and labeled."), out)


def samhsa():
    api = "https://findtreatment.gov/locator/exportsAsJson/v2"

    def fetch():
        rows, page = [], 1
        while True:
            j = http("GET", api, params={"sAddr": f"{LAT0:.6f},{LON0:.6f}", "limitType": 2, "limitValue": int(REACH), "sType": "both",
                                         "pageSize": 2000, "page": page, "sort": 0}).json()
            rows += j.get("rows", [])
            if page >= (j.get("totalPages") or 1):
                return rows
            page += 1

    data, got = cached("samhsa_findtreatment.json", fetch)
    groups = {}
    for x in data:
        if not x.get("latitude") or not in_area(x["latitude"], x["longitude"]):
            continue
        sv = {s["f2"]: s["f3"] for s in x.get("services", [])}
        settings = sv.get("SET", "")
        if "Outpatient" not in settings or "Residential" in settings:   # outpatient only; no residential programs of any kind
            continue
        key = (norm(x["name1"] + (x.get("name2") or "")), norm(x.get("street1") or ""))
        g = groups.setdefault(key, {"x": x, "types": set(), "ft": []})
        g["types"].add(x.get("typeFacility"))
        if sv.get("FT"):
            g["ft"].append(sv["FT"])
    out = []
    for g in groups.values():
        x, t = g["x"], g["types"]
        kind = ("Outpatient mental health and substance use treatment" if t >= {"MH", "SA"} else
                "Outpatient mental health" if "MH" in t else "Outpatient substance use treatment")
        name = x["name1"] + (f" – {x['name2']}" if clean(x.get("name2")) else "")
        out.append(rec("health_care", kind, name, x.get("street1"), x["latitude"], x["longitude"], x.get("phone"), x.get("website"),
                       "; ".join(dict.fromkeys(g["ft"]))))
    write(m("samhsa_treatment_outpatient", "FindTreatment.gov behavioral health treatment facilities (outpatient)", ["health_care"],
            "U.S. Substance Abuse and Mental Health Services Administration (SAMHSA)", "https://findtreatment.gov/", api, FED, got, "",
            "Mental health and substance use facilities that offer outpatient care. Any facility that also offers residential or "
            "24-hour residential treatment is left out (no addiction-treatment residences); facilities listed twice (MH and SUD) "
            "are merged."), out)


# ================================================================ OpenStreetMap (health care, pharmacies, older adults, social services)
OSM = None


def osm():
    global OSM
    if OSM is None:
        OSM = overpass()
    return OSM


def osm_fields(t):
    addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
    return addr, t.get("phone") or t.get("contact:phone") or "", t.get("website") or t.get("contact:website") or ""


HC = {"clinic": "Clinic", "doctor": "Doctor's office", "doctors": "Doctor's office", "dentist": "Dentist", "centre": "Health center",
      "dialysis": "Dialysis center", "laboratory": "Medical laboratory", "optometrist": "Optometrist", "physiotherapist": "Physical therapy",
      "counselling": "Counseling center", "blood_donation": "Blood donation center", "podiatrist": "Podiatrist", "audiologist": "Audiologist",
      "speech_therapist": "Speech therapy", "occupational_therapist": "Occupational therapy", "midwife": "Midwife",
      "birthing_centre": "Birth center", "sample_collection": "Lab sample collection", "yes": "Health care"}
HC_SKIP = {"hospital", "pharmacy", "alternative", "home_care", "rehabilitation", "psychotherapist", "nursing_home", "hospice"}
SUD = re.compile(r"\b(recovery|detox|addiction|methadone|suboxone|substance|marijuana|cannabis)\b", re.I)
RITE_AID = re.compile(r"rite\s*aid", re.I)


def osm_health_care():
    els, got, base = osm()
    out = []
    for t, lat, lon, _ in els:
        a, h, name = t.get("amenity", ""), t.get("healthcare", ""), clean(t.get("name"))
        if not name or a in ("hospital", "pharmacy", "social_facility") or h in HC_SKIP or t.get("shop") == "chemist":
            continue
        if a not in ("clinic", "doctors", "dentist") and h not in HC:
            continue
        if SUD.search(name) or re.search(r"research", name, re.I) or "marijuana" in t.get("healthcare:speciality", ""):
            continue
        kind = HC.get(h) or HC.get(a) or "Health care"
        sp = t.get("healthcare:speciality", "")
        if re.search(r"urgent care", name, re.I):
            kind = "Urgent care"
        elif "dialysis" in sp or "dialysis" in h:
            kind = "Dialysis center"
        addr, ph, site = osm_fields(t)
        out.append(rec("health_care", kind, name, addr, lat, lon, ph, site, sp.replace("_", " ").replace(";", ", ").capitalize() if sp else "", keep_case=True))
    write(m("osm_health_care", "OpenStreetMap clinics, doctors, dentists and other health care", ["health_care"], "OpenStreetMap contributors",
            "https://www.openstreetmap.org/", "https://overpass-api.de/api/interpreter", OSM_LICENSE, got, f"OSM data as of {base}" if base else "",
            "amenity=clinic|doctors|dentist and healthcare=* points with a name. Hospitals and pharmacies are in their own datasets; "
            "alternative medicine, home-care agencies, individual psychotherapists, 'rehabilitation' and anything named for "
            "addiction / recovery treatment are left out. Coverage is uneven: OSM misses many small practices."), out)


def osm_pharmacies():
    els, got, base = osm()
    out = []
    for t, lat, lon, _ in els:
        if not (t.get("amenity") == "pharmacy" or t.get("healthcare") == "pharmacy" or t.get("shop") == "chemist"):
            continue
        name = clean(t.get("name")) or clean(t.get("brand")) or "Pharmacy"
        if any(RITE_AID.search(clean(t.get(k))) for k in ("name", "brand", "operator")):
            continue                                 # Rite Aid closed all stores in 2025
        kind = "Pharmacy" if (t.get("amenity") == "pharmacy" or t.get("healthcare") == "pharmacy") else "Drugstore"
        addr, ph, site = osm_fields(t)
        out.append(rec("pharmacies", kind, name, addr, lat, lon, ph, site, "", keep_case=True))
    write(m("osm_pharmacies", "OpenStreetMap pharmacies", ["pharmacies"], "OpenStreetMap contributors", "https://www.openstreetmap.org/",
            "https://overpass-api.de/api/interpreter", OSM_LICENSE, got, f"OSM data as of {base}" if base else "",
            "amenity=pharmacy, healthcare=pharmacy and shop=chemist. Rite Aid is dropped (all stores closed in 2025). OSM may still "
            "show chain stores closed in 2024-26 and misses independents; see cms_nppes_pharmacies."), out)


SENIOR = re.compile(r"senior (center|centre|citizens? cent|community cent|services)|older adult|adult day|active adult|living independently for elders", re.I)
LIFE = re.compile(r"\bLIFE\b")                       # the PACE program, upper case (not "Family Life Center")
RESIDENCE = re.compile(r"apartments?|residence|manor|\bhome\b|house|towers|assisted|nursing|village|terrace", re.I)


def osm_older_adults():
    els, got, base = osm()
    out = []
    for t, lat, lon, _ in els:
        name, sf = clean(t.get("name")), t.get("social_facility", "")
        is_day = sf == "day_care" and re.search(r"senior|disabled", t.get("social_facility:for", ""))
        if not name or not (SENIOR.search(name) or LIFE.search(name) or is_day):
            continue
        if (sf in ("nursing_home", "assisted_living", "group_home", "shelter") or RESIDENCE.search(name)) and \
                not (re.search(r"senior cent|older adult cent|living independently|adult day", name, re.I) or LIFE.search(name)):
            continue                                 # residences, not centers
        kind = "Adult day center" if (is_day or LIFE.search(name) or re.search(r"adult day|living independently", name, re.I)) else \
            "Senior services" if re.search(r"senior services", name, re.I) else "Senior center"
        addr, ph, site = osm_fields(t)
        out.append(rec("older_adults", kind, name, addr, lat, lon, ph, site, "", keep_case=True))
    write(m("osm_older_adults", "OpenStreetMap senior centers and adult day centers", ["older_adults"], "OpenStreetMap contributors",
            "https://www.openstreetmap.org/", "https://overpass-api.de/api/interpreter", OSM_LICENSE, got, f"OSM data as of {base}" if base else "",
            "Named senior / older adult centers, senior service agencies and adult day centers. Senior housing, nursing homes and "
            "assisted living are left out (residences)."), out)


GONE = re.compile(r"shelter|victim|abuse|domestic|safe haven|recovery|rehab|detox|residen|entrepreneur|boys (&|and) girls|child care|youth", re.I)


def osm_social_services():
    els, got, base = osm()
    out = []
    for t, lat, lon, _ in els:
        name, off, sf, gov = clean(t.get("name")), t.get("office", ""), t.get("social_facility", ""), t.get("government", "")
        sfor = t.get("social_facility:for", "")
        if not name or GONE.search(name) or re.search(r"abused|victim|homeless|drug|child|juvenile", sfor):
            continue
        kind = ""
        if off == "government" and (gov == "social_security" or re.search(r"social security", name, re.I)):
            kind = "Social Security office"
        elif off == "government" and re.search(r"veterans affairs.*regional office", name, re.I):
            kind = "Veterans benefits office"
        elif off in ("lawyer", "ngo", "association", "charity") and re.search(r"legal (aid|services|assistance|clinic)|community legal|law cent", name, re.I):
            kind = "Legal aid"
        elif t.get("amenity") == "social_facility" and sf in ("outreach", "advice"):
            kind = "Social service agency"
        elif re.search(r"family (center|centre|services|support)", name, re.I) and sf not in ("group_home", "shelter", "nursing_home", "assisted_living"):
            kind = "Family services"
        if not kind:
            continue
        addr, ph, site = osm_fields(t)
        out.append(rec("social_services", kind, name, addr, lat, lon, ph, site, "", keep_case=True))
    write(m("osm_social_services", "OpenStreetMap social service offices", ["social_services"], "OpenStreetMap contributors",
            "https://www.openstreetmap.org/", "https://overpass-api.de/api/interpreter", OSM_LICENSE, got, f"OSM data as of {base}" if base else "",
            "Gap fill only: Social Security and VA benefits offices, legal aid, social_facility=outreach|advice and family service "
            "agencies. County Assistance and WIC offices come from the official datasets. Shelters, group homes, recovery "
            "residences and victim / domestic-violence services are left out."), out)


# ================================================================ pharmacies (CMS NPPES)
def cms_nppes_pharmacies():
    api = "https://npiregistry.cms.hhs.gov/api/"

    def fetch():
        rows = []
        for skip in range(0, 1001, 200):           # the registry serves at most 1,200 records per query
            j = http("GET", api, params={"version": "2.1", "taxonomy_description": "Community/Retail Pharmacy", "city": "PHILADELPHIA",
                                         "state": "PA", "enumeration_type": "NPI-2", "limit": 200, "skip": skip}).json()
            rows += j.get("results", [])
            if j.get("result_count", 0) < 200:
                break
        return rows

    data, got = cached("cms_nppes_pharmacies.json", fetch)
    cutoff = (TODAY - dt.timedelta(days=5 * 365)).isoformat()
    out, n_old, n_geo = [], 0, 0
    for r in data:
        b = r.get("basic", {})
        prim = [t["code"] for t in r.get("taxonomies", []) if t.get("primary")]
        if not set(prim) & {"3336C0003X", "333600000X"}:
            continue
        names = [clean(b.get("organization_name")), clean(b.get("parent_organization_legal_business_name"))] + \
                [clean(o.get("organization_name")) for o in r.get("other_names", [])]
        if any(RITE_AID.search(n) for n in names):
            continue
        if (b.get("last_updated") or "") < cutoff:
            n_old += 1
            continue
        loc = next((a for a in r.get("addresses", []) if a.get("address_purpose") == "LOCATION"), None)
        if not loc or clean(loc.get("city")).upper() != "PHILADELPHIA":
            continue
        dba = next((clean(o.get("organization_name")) for o in r.get("other_names", []) if o.get("type") == "Doing Business As"), "")
        name = dba or clean(b.get("organization_name"))
        name = re.sub(r",?\s+(INC|LLC|CORP|CORPORATION|CO|LTD|PC)\.?$", "", name, flags=re.I)
        xy = geocode(loc.get("address_1", ""))
        if not xy:
            n_geo += 1
            continue
        kind = "Hospital outpatient pharmacy" if re.search(r"hospital|trustees of the university", name, re.I) else "Pharmacy"
        out.append(rec("pharmacies", kind, name, loc.get("address_1"), xy[0], xy[1], loc.get("telephone_number"), "",
                       f"NPI {r.get('number')} · record updated {b.get('last_updated')}"))
    print(f"    NPPES: {n_old} pharmacy records not updated since {cutoff} skipped, {n_geo} not geocoded")
    write(m("cms_nppes_pharmacies", "NPPES NPI Registry: community / retail pharmacies in Philadelphia", ["pharmacies"],
            "U.S. Centers for Medicare & Medicaid Services (CMS), National Plan and Provider Enumeration System",
            "https://npiregistry.cms.hhs.gov/api-page", api, FED, got, "",
            "Organization NPIs whose primary taxonomy is community/retail pharmacy, at their practice location, geocoded with the "
            "City's AIS. NPIs are rarely deactivated when a store closes, so Rite Aid is dropped and records not updated in the "
            "last five years are skipped; the rest are likely but not certain to be open."), out)


# ================================================================ older adults
def phl_pca_senior_centers():
    rows, got, ed, api = city_layer("PCA_SeniorCenters")
    out = [rec("older_adults", "Senior center", a.get("Name"), a.get("Address"), lat, lon, a.get("Phone_Number"), "",
               "PHA satellite site" if re.search(r"satellite", clean(a.get("Name")), re.I) else "") for a, lat, lon in rows]
    write(m("phl_pca_senior_centers", "PCA Senior Centers", ["older_adults"], "Philadelphia Corporation for Aging (geocoded by the City of Philadelphia)",
            "https://www.arcgis.com/home/item.html?id=c892ec757bf2445bb0b2689c017f9ffb", api, "Not stated (City of Philadelphia ArcGIS Online item)",
            got, edited(ed), "Senior community centers and PHA satellite sites from PCA's Find a Senior Center list, as geocoded by the City."), out)


def phl_ppr_older_adult_centers():
    rows, got, ed, api = city_layer("PPR_Program_Sites", where="program_type='OLDER_ADULT_CENTER'")
    out = [rec("older_adults", "Older adult center (PPR)", a.get("park_name"), "", lat, lon, "", "", "Philadelphia Parks & Recreation program site")
           for a, lat, lon in rows]
    write(m("phl_ppr_older_adult_centers", "Parks & Recreation Program Sites: older adult centers", ["older_adults"], "Philadelphia Parks & Recreation",
            f"{ODP}/parks-recreation-program-sites/", api, CITY_LICENSE, got, edited(ed),
            "PPR program sites with program_type = OLDER_ADULT_CENTER (the value the layer uses now; older extracts used PPR_OAC). "
            "The layer has no street address."), out)


def pa_dhs_life_centers():
    url = "https://www.pa.gov/agencies/dhs/resources/aging-physical-disabilities/life.html"
    page, got = cached("pa_dhs_life.html", lambda: http("GET", url, headers={"User-Agent": "Mozilla/5.0 (studio-community-maps/1.0)"}).text, text=True)
    i = page.find("LifeProvidersbyCounty")
    table = page[page.find("<table", i): page.find("</table>", page.find("<table", i))]
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = [clean(re.sub(r"<[^>]+>", " ", c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 5 or not re.search(r"\b191\d\d\b", cells[2]):
            continue
        provider, center, address, _, tel = cells[:5]
        brand = provider.split(" (")[0]
        name = center if brand.split()[0].lower() in center.lower() else f"{brand} – {center}"
        xy = geocode(address)
        if xy:
            out.append(rec("older_adults", "LIFE (PACE) center", name, address.split(",")[0].replace("Chesnut", "Chestnut"), xy[0], xy[1], tel, "",
                           "Living Independence for the Elderly: day center and all-inclusive care for adults 55+"))
    rev = re.search(r"Revised:\s*([0-9/]+)", re.sub(r"<[^>]+>", " ", page))
    write(m("pa_dhs_life_centers", "LIFE (Living Independence for the Elderly) provider centers", ["older_adults"],
            "Pennsylvania Department of Human Services, Office of Long-Term Living", url, url,
            "Commonwealth of Pennsylvania web page (no open license stated)", got, f"Revised {rev.group(1)}" if rev else "",
            "Philadelphia LIFE (PACE) centers from the provider table on the DHS page, geocoded with the City's AIS. LIFE centers "
            "are the adult day health sites of the program."), out)


# ================================================================ social services
def phl_wic_offices():
    rows, got, ed, api = city_layer("WIC_Offices")
    out = [rec("social_services", "WIC office", a.get("name"), " ".join(x for x in (clean(a.get("address")), clean(a.get("address_2"))) if x),
               lat, lon, a.get("phone_number"), "", "Women, Infants & Children nutrition program") for a, lat, lon in rows]
    write(m("phl_wic_offices", "Women, Infants & Children (WIC) Offices", ["social_services"], "City of Philadelphia, Department of Public Health",
            f"{ODP}/women-infants-children-wic-offices/", api, CITY_LICENSE, got, edited(ed), "All WIC offices in the City list."), out)


def phl_neighborhood_resources():
    rows, got, ed, api = city_layer("NeighborhoodResources")
    out = []
    for a, lat, lon in rows:
        nec, hca = clean(a.get("nec")) == "Yes", clean(a.get("hca")) == "Yes"
        if not (nec or hca):
            continue                                  # NAC-only offices belong to community_orgs (civic domain)
        kind = " and ".join(x for x in ("Neighborhood Energy Center" if nec else "", "Housing counseling agency" if hca else "") if x)
        prog = [p.strip() for p in clean(a.get("programs")).split("|") if p.strip()] if hca else []
        spec = clean(a.get("specialty"))
        detail = " · ".join(x for x in (", ".join(prog), f"specialty: {spec.lower()}" if spec and spec != " " else "") if x)
        out.append(rec("social_services", kind, a.get("agency"), a.get("street_address"), lat, lon, a.get("phone_number"), a.get("website_url"), detail))
    write(m("phl_neighborhood_resources", "Neighborhood Resources (Neighborhood Energy Centers and Housing Counseling Agencies)", ["social_services"],
            "City of Philadelphia, Department of Planning and Development, Division of Housing and Community Development",
            f"{ODP}/neighborhood-resources/", api, CITY_LICENSE, got, edited(ed),
            "Agencies flagged as a Neighborhood Energy Center (utility bill help, ECA) or a City-funded housing counseling agency. "
            "NAC-only offices are left to community_orgs. This layer supersedes the separate Neighborhood_Energy_Centers and "
            "HousingCounselingAgencies layers. Contact names and e-mails are not kept."), out)


HUD_SVC = {"PPC": "pre-purchase counseling", "PPW": "homebuyer education", "RHC": "rental counseling", "RHW": "rental workshops",
           "DFC": "mortgage default counseling", "DFW": "default workshops", "FBC": "financial / credit counseling",
           "FBW": "financial workshops", "HMC": "reverse mortgage counseling", "NDW": "post-purchase workshops",
           "HIC": "home improvement counseling"}


def hud_housing_counseling():
    api = "https://data.hud.gov/Housing_Counselor/searchByLocation"

    def fetch():
        rows = {}
        for s in SITES:
            for a in http("GET", api, params={"Lat": s["lat"], "Long": s["lng"], "Distance": 2}).json():
                rows[a["agcid"]] = a
        return list(rows.values())

    data, got = cached("hud_housing_counselors.json", fetch)
    out = []
    for a in data:
        try:
            lat, lon = float(a["agc_ADDR_LATITUDE"]), float(a["agc_ADDR_LONGITUDE"])
        except (TypeError, ValueError):
            continue
        svc = [HUD_SVC[c] for c in clean(a.get("services")).split(",") if c in HUD_SVC]
        langs = clean(a.get("languages")).replace("ENG", "English").replace("SPA", "Spanish")
        detail = " · ".join(x for x in (", ".join(svc), f"languages: {langs}" if langs else "") if x)
        out.append(rec("social_services", "HUD-approved housing counseling agency", a.get("nme"), a.get("adr1"), lat, lon,
                       a.get("phone1"), a.get("weburl"), detail))
    write(m("hud_housing_counseling", "HUD-approved Housing Counseling Agencies", ["social_services"],
            "U.S. Department of Housing and Urban Development (HUD)", "https://data.hud.gov/housing_counseling.html", api, FED, got, "",
            "HUD-approved agencies returned by HUD's search-by-location API within 2 miles of each site, kept within 1.5 miles. "
            "Agency phone and website only; staff e-mails are not kept."), out)


def pa_dhs_caos():
    api = "https://data.pa.gov/resource/ytxr-yigf.json"

    def fetch():
        rows = http("GET", api, params={"$limit": 5000}).json()
        meta = http("GET", "https://data.pa.gov/api/views/ytxr-yigf.json").json()
        return {"rows": rows, "rowsUpdatedAt": meta.get("rowsUpdatedAt"), "license": (meta.get("license") or {}).get("name")}

    data, got = cached("pa_dhs_cao.json", fetch)
    pts = []
    for r in data["rows"]:
        try:
            lat, lon = float(r["outlatitud"]), float(r["outlongitu"])
        except (KeyError, TypeError, ValueError):
            continue
        pts.append((r, lat, lon))
    groups = []                                       # districts that share a building become one point
    for r, lat, lon in pts:
        g = next((g for g in groups if meters(g["lat"], g["lon"], lat, lon) <= 40), None)
        if g:
            g["rows"].append(r)
        else:
            groups.append({"lat": lat, "lon": lon, "rows": [r]})
    out = []
    for g in groups:
        dists = [title(r.get("indistname")) for r in g["rows"]]
        county = title(re.sub(r"\s*CAO$", "", clean(g["rows"][0].get("inname")), flags=re.I))
        named = [d for d in dists if d and not re.search(r"\bCAO\b|^Philadelphia", d, re.I)]
        if any(re.search(r"low income home energy", d, re.I) for d in named):
            named = [("LIHEAP" if re.search(r"low income home energy", d, re.I) else d) for d in named]
        if named:
            name = f"{county} County Assistance Office – " + " / ".join(named) + (" District" if len(named) == 1 else " Districts")
        else:
            name = f"{county} County Assistance Office (headquarters)"
        name = name.replace("LIHEAP District", "LIHEAP Office")
        out.append(rec("social_services", "County Assistance Office (PA DHS)", name, g["rows"][0].get("inadr1"), g["lat"], g["lon"],
                       g["rows"][0].get("phone_1"), "", "SNAP, cash assistance, Medical Assistance and LIHEAP applications"))
    upd = dt.datetime.fromtimestamp(data["rowsUpdatedAt"], dt.timezone.utc).date().isoformat() if data.get("rowsUpdatedAt") else ""
    write(m("pa_dhs_county_assistance_offices", "County Assistance Office Current Statewide Human Services", ["social_services"],
            "Pennsylvania Department of Human Services (via data.pa.gov)",
            "https://data.pa.gov/Services-Near-You/County-Assistance-Office-Current-Statewide-Human-S/ytxr-yigf", api,
            (data.get("license") or "Not stated") + " (as labeled on data.pa.gov)", got, f"rows last updated {upd}" if upd else "",
            "DHS County Assistance Offices (SNAP / 'food stamps', cash assistance, Medical Assistance, LIHEAP). District offices that "
            "share a building are merged into one point. The rows were last updated in 2022."), out)


def phl_healthy_start():
    rows, got, ed, api = city_layer("Healthy_Start_CRCs")
    out = [rec("social_services", "Healthy Start community resource center", a.get("facility_name"), a.get("address"), lat, lon, a.get("phone"), "",
               " ".join(x for x in (clean(a.get("days_open")), clean(a.get("hours"))) if x)) for a, lat, lon in rows]
    write(m("phl_healthy_start_crcs", "Healthy Start Community Resource Centers", ["social_services"], "City of Philadelphia, Department of Public Health",
            f"{ODP}/healthy-start-community-resource-centers/", api, CITY_LICENSE, got, edited(ed),
            "PDPH-affiliated Healthy Start family resource centers (prenatal and early-childhood family support)."), out)


def phl_bme_resources():
    rows, got, ed, api = city_layer("Black_Male_Engagement_Resources")
    out = []
    for a, lat, lon in rows:
        svc, name = clean(a.get("services_offered")), clean(a.get("organization_name"))
        if clean(a.get("public_yn")).upper().startswith("N") or not lat or re.search(r"victim|shelter|medical center|hospital", name, re.I):
            continue
        kinds = [k for k, rx in (("Legal services", r"legal"), ("Family / fatherhood support", r"fatherhood|family services")) if re.search(rx, svc, re.I)]
        if not kinds:
            continue
        out.append(rec("social_services", " and ".join(kinds), name, a.get("address"), lat, lon, a.get("phone"), a.get("website"), svc))
    write(m("phl_bme_resources", "Black Male Engagement Resources (legal and family support entries)", ["social_services"],
            "City of Philadelphia, Office of Black Male Engagement", "https://www.arcgis.com/home/item.html?id=c901b5701b3e42a69b1d2167d9732161",
            api, "Not stated (City of Philadelphia ArcGIS Online item)", got, edited(ed),
            "Only entries offering legal services or fatherhood / family support; this is the only official geocoded source found "
            "for legal aid offices. Shelters, victim services and hospital programs are left out; e-mails are not kept."), out)


# ================================================================ run
if __name__ == "__main__":
    print(f"Health domain: assets within {RADIUS:.0f} m of the six sites -> {OUT}")
    steps = [phl_health_centers, phl_hospitals, pa_doh_hospitals, hrsa_sites, samhsa, osm_health_care,
             osm_pharmacies, cms_nppes_pharmacies,
             phl_pca_senior_centers, phl_ppr_older_adult_centers, pa_dhs_life_centers, osm_older_adults,
             phl_wic_offices, phl_neighborhood_resources, hud_housing_counseling, pa_dhs_caos, phl_healthy_start,
             phl_bme_resources, osm_social_services]
    failed = []
    for step in steps:
        try:
            step()
        except Exception as e:                        # noqa: BLE001  (one source down must not stop the others)
            failed.append((step.__name__, repr(e)[:300]))
            print(f"  !! {step.__name__} failed: {e!r}"[:400])
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(MANIFEST)} datasets, {sum(x['records'] for x in MANIFEST)} records")
    if failed:
        print("FAILED:", failed)
