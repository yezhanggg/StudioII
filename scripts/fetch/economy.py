"""Economy domain pull: `economic` assets plus three context datasets.

Assets (category `economic`, 1.5 mi of any site):
  fdic_bank_branches            FDIC BankFind Suite, bank branch locations
  ncua_credit_union_sites       NCUA Credit Union Locator, credit union offices
  pa_careerlink_phl_sites       PA CareerLink Philadelphia (Philadelphia Works) centers + outreach sites
  phl_obme_workforce_resources  City Office of Black Male Engagement directory, workforce/employment orgs

Context (manifest "context": true):
  vacant_land          City Vacant Property Indicators (land) + Philadelphia Land Bank parcels (OPA), 1 mi
  public_housing       HUD Public Housing Developments (PHA), City-hosted PHA Senior Sites, HUD LIHTC, 1.5 mi
  affordable_housing   City DHCD/DPD Affordable Housing Production, 1.5 mi

Run:
  uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/economy.py [--refresh]
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
FETCH = ROOT / "scripts" / "fetch"
OUT = FETCH / "out" / "economy"
CACHE = ROOT / "scripts" / ".cache" / "fetch" / "economy"
LOCAL_DS = Path.home() / "Desktop" / "FW 2026" / "Studio" / "Pre-Mid Review" / "Data_Sources"
SITES = json.loads((FETCH / "schools.json").read_text())

R15 = 2414.0   # 1.5 miles (m), contract collection radius
R10 = 1609.344  # 1 mile (m), vacant land radius per brief
UA = {"User-Agent": "studio-community-maps/1.0"}
REFRESH = "--refresh" in sys.argv
CACHE_MAX_AGE_DAYS = 7

CITY = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services"
HUD = "https://services.arcgis.com/VTyQ9soqVukalItT/ArcGIS/rest/services"
CITY_LICENSE = "City of Philadelphia open data (OpenDataPhilly terms of use)"
FED_LICENSE = "Public domain (U.S. Government work)"

retrieved_dates: dict[str, set] = {}


# ---------------------------------------------------------------- http + cache

def fetch(url: str, params: dict | None = None, body: dict | None = None, tag: str = "misc", as_json: bool = True):
    """GET (or POST JSON when body is given) with retry/backoff; raw response cached on disk."""
    key = hashlib.sha1(json.dumps([url, params, body], sort_keys=True).encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{tag}_{key}.{'json' if as_json else 'txt'}"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < CACHE_MAX_AGE_DAYS * 86400
    if not (fresh and not REFRESH):
        last = None
        for attempt in range(5):
            try:
                if body is not None:
                    r = requests.post(url, json=body, params=params, headers={**UA, "Content-Type": "application/json"}, timeout=120)
                else:
                    r = requests.get(url, params=params, headers=UA, timeout=120)
                r.raise_for_status()
                text = r.text
                if as_json:
                    json.loads(text)  # validate before caching
                path.write_text(text, encoding="utf-8")
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 * (attempt + 1) ** 2)
        else:
            raise RuntimeError(f"fetch failed: {url} {params} -> {last}")
    retrieved_dates.setdefault(tag, set()).add(dt.date.fromtimestamp(path.stat().st_mtime).isoformat())
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if as_json else text


def arcgis_layer_info(url: str, tag: str) -> dict:
    return fetch(url, {"f": "json"}, tag=tag)


def arcgis_query(url: str, tag: str, where: str = "1=1", out_fields: str = "*", around: tuple | None = None,
                 radius: float | None = None, page: int = 2000) -> list[dict]:
    """Paginated GeoJSON query; optional point+distance spatial filter (EPSG:4326 in/out)."""
    feats, offset = [], 0
    while True:
        p = {"where": where, "outFields": out_fields, "outSR": 4326, "f": "geojson",
             "resultOffset": offset, "resultRecordCount": page, "returnGeometry": "true"}
        if around:
            p.update({"geometry": f"{around[0]},{around[1]}", "geometryType": "esriGeometryPoint", "inSR": 4326,
                      "spatialRel": "esriSpatialRelIntersects", "distance": radius, "units": "esriSRUnit_Meter"})
        d = fetch(url.rstrip("/") + "/query", p, tag=tag)
        if "error" in d:
            raise RuntimeError(f"ArcGIS error {url}: {d['error']}")
        fs = d.get("features", [])
        feats += fs
        more = d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit")
        if not fs or (not more and len(fs) < page):
            break
        offset += len(fs)
    return feats


def arcgis_query_sites(url: str, tag: str, radius: float, where: str = "1=1", out_fields: str = "*", id_field: str | None = None) -> list[dict]:
    """Union of distance queries around each of the six sites, de-duplicated by object id."""
    seen, out = set(), []
    for s in SITES:
        for f in arcgis_query(url, tag, where, out_fields, (s["lng"], s["lat"]), radius):
            fid = f.get("id") if id_field is None else (f.get("properties") or {}).get(id_field)
            if fid is None:
                fid = json.dumps(f.get("properties"), sort_keys=True)
            if fid in seen:
                continue
            seen.add(fid)
            out.append(f)
    return out


def epoch_date(ms) -> str:
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


# ---------------------------------------------------------------- geo helpers

def hav(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def site_dists(lon, lat) -> dict:
    return {s["slug"]: hav(lat, lon, s["lat"], s["lng"]) for s in SITES}


def within(lon, lat, radius) -> bool:
    return lon is not None and lat is not None and min(site_dists(lon, lat).values()) <= radius


def point_of(geom) -> tuple | None:
    if not geom:
        return None
    if geom.get("type") == "Point":
        x, y = geom["coordinates"][:2]
        return (x, y) if x is not None and y is not None else None
    try:
        p = shape(geom).representative_point()
        return (p.x, p.y)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- text helpers

ACRONYMS = {"PNC", "TD", "BMO", "USA", "US", "PA", "FCU", "CU", "PHA", "LLC", "LP", "INC", "CDC", "HUD", "HELP", "WCRP",
            "SI", "ERRL", "VA", "CHOP", "SEPTA", "YMCA", "PEC", "OIC", "ATM", "WPRE", "LCIP", "AME", "HACE", "APM", "NE",
            "NW", "SE", "SW", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV",
            "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "NHS", "RDA", "PHDC", "ACHIEVE", "ECO", "DVPC", "NSA", "FMFCU",
            "MABC", "M.A.B.C.", "E.R.R.L.", "WBEC", "SBDC", "PIDC", "CCP", "RISE", "KB", "LIHTC"}
SMALL = {"OF", "AND", "THE", "AT", "FOR", "IN", "ON", "A", "AN", "TO", "BY", "@"}
SPECIAL = {"UPENN": "UPenn", "MCMICHAEL": "McMichael"}
ORD = re.compile(r"^(\d+)(ST|ND|RD|TH)$")


def clean(v) -> str:
    if v is None:
        return ""
    s = " ".join(str(v).replace("®", "").split())
    return "" if s.upper() in {"NONE", "NULL", "NAN", "N/A"} else s


def smart_title(v) -> str:
    s = clean(v)
    if not s or s != s.upper() or not re.search(r"[A-Z]", s):
        return s
    words = s.split(" ")
    out = []
    for i, w in enumerate(words):
        core = w.strip(",.()&;:")
        if core in ACRONYMS:
            out.append(w)
        elif ORD.match(core):
            out.append(w.lower())
        elif core in SMALL and i > 0:
            out.append(w.lower())
        elif core in SPECIAL:
            out.append(w.replace(core, SPECIAL[core]))
        else:
            t = re.sub(r"[A-Z]+", lambda m: m.group(0).capitalize(), w)
            t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
            t = re.sub(r"'S\b", "'s", t)
            out.append(t)
    return " ".join(out)


def fmt_phone(v) -> str:
    d = re.sub(r"\D", "", clean(v))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else clean(v)


def fmt_web(v) -> str:
    s = clean(v)
    if s and s == s.upper():
        s = s.lower()
    if s and not s.lower().startswith("http"):
        s = "https://" + s
    return s


def fmt_addr(street, city="Philadelphia", state="PA", zip_="") -> str:
    st = smart_title(street).rstrip(",. ")
    c = smart_title(city) or "Philadelphia"
    c = "Philadelphia" if c.lower() in {"phila", "phila.", "philadelphia"} else c
    return f"{st}, {c}, {state} {clean(zip_)[:5]}".strip().rstrip(",")


def num(v):
    try:
        f = float(v)
        return "" if math.isnan(f) else (str(int(f)) if f == int(f) else str(f))
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------- output

def asset(lon, lat, kind, name, address="", phone="", website="", detail="", source_id="") -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {"category": "economic", "kind": kind, "name": name, "address": address, "phone": phone,
                           "website": website, "detail": detail, "source_id": source_id}}


def dedupe_name(feats: list[dict], meters: float = 40) -> list[dict]:
    keep: list[dict] = []
    for f in feats:
        n = (f["properties"].get("name") or "").lower()
        x, y = f["geometry"]["coordinates"]
        dup = any((g["properties"].get("name") or "").lower() == n and hav(y, x, g["geometry"]["coordinates"][1], g["geometry"]["coordinates"][0]) <= meters for g in keep)
        if not dup:
            keep.append(f)
    return keep


def numify(feats: list[dict], keys) -> list[dict]:
    """Context datasets: integer counts/years (null when unknown) so the map can size or filter by them."""
    for f in feats:
        for k in keys:
            v = f["properties"].get(k)
            f["properties"][k] = int(float(v)) if v not in (None, "") else None
    return feats


def write(ds_id: str, feats: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    feats = sorted(feats, key=lambda f: (f["properties"].get("name") or f["properties"].get("address") or ""))
    (OUT / f"{ds_id}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")


def retrieved(*tags) -> str:
    ds = set().union(*(retrieved_dates.get(t, set()) for t in tags))
    return min(ds) if ds else dt.date.today().isoformat()


manifest: list[dict] = []
summary: list[tuple] = []
failures: list[str] = []


def count_near(feats, slug, radius=R10) -> int:
    s = next(x for x in SITES if x["slug"] == slug)
    return sum(1 for f in feats if hav(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0], s["lat"], s["lng"]) <= radius)


def record(ds_id: str, feats: list[dict], meta: dict) -> None:
    write(ds_id, feats)
    entry = {"id": ds_id, **meta, "records": len(feats)}
    manifest.append(entry)
    summary.append((ds_id, len(feats), count_near(feats, "wagner"), count_near(feats, "blankenburg")))


# ================================================================ ASSETS

def fdic_banks() -> None:
    tag = "fdic"
    url = "https://api.fdic.gov/banks/locations"
    fields = "NAME,OFFNAME,ADDRESS,CITY,STALP,ZIP,COUNTY,LATITUDE,LONGITUDE,SERVTYPE,SERVTYPE_DESC,MAINOFF,CERT,UNINUM,RUNDATE,MDI_STATUS_DESC"
    d = fetch(url, {"filters": 'STALP:PA AND COUNTY:("Philadelphia" OR "Montgomery" OR "Delaware")', "fields": fields,
                    "limit": 10000, "format": "json"}, tag=tag)
    rows = [r["data"] for r in d["data"]]
    keep_types = {11, 12, 23, 28}  # full service brick & mortar / retail, limited-service drive-thru / retail
    rows = [r for r in rows if r.get("SERVTYPE") in keep_types and within(r.get("LONGITUDE"), r.get("LATITUDE"), R15)]
    certs = sorted({str(r["CERT"]) for r in rows})
    web = {}
    if certs:
        inst = fetch("https://api.fdic.gov/banks/institutions", {"filters": f"CERT:({' OR '.join(certs)})", "fields": "CERT,NAME,WEBADDR",
                                                                  "limit": 1000, "format": "json"}, tag=tag)
        web = {str(i["data"]["CERT"]): fmt_web(i["data"].get("WEBADDR")) for i in inst["data"]}
    feats = []
    for r in rows:
        office = smart_title(r.get("OFFNAME"))
        bits = [f"{office} office" if office and "office" not in office.lower() and "branch" not in office.lower() else office]
        if r.get("MAINOFF") == 1:
            bits.append("main office")
        if r.get("SERVTYPE") in (23, 28):
            bits.append(smart_title(r.get("SERVTYPE_DESC")).replace("Limited Service - ", "limited service: ").lower())
        mdi = clean(r.get("MDI_STATUS_DESC"))
        if mdi and mdi.upper() != "NONE":
            bits.append("minority depository institution")
        addr = fmt_addr(r["ADDRESS"], r["CITY"], r["STALP"], r["ZIP"])
        feats.append(asset(r["LONGITUDE"], r["LATITUDE"], "Bank branch", clean(r["NAME"]), addr, "", web.get(str(r["CERT"]), ""),
                           " · ".join(b for b in bits if b), "fdic_bank_branches"))
    feats = dedupe_name(feats)
    record("fdic_bank_branches", feats, {
        "title": "FDIC-Insured Bank Branch Locations", "categories": ["economic"],
        "publisher": "Federal Deposit Insurance Corporation (FDIC) BankFind Suite",
        "landing_url": "https://banks.data.fdic.gov/bankfind-suite/",
        "api_url": "https://api.fdic.gov/banks/locations",
        "license": FED_LICENSE, "retrieved": retrieved(tag),
        "data_date": (d.get("meta", {}).get("index", {}).get("createTimestamp") or "")[:10],
        "notes": "All FDIC-insured bank offices in Philadelphia, Montgomery and Delaware counties within 1.5 mi of a site; kept full-service "
                 "brick-and-mortar/retail offices and limited-service drive-thru/retail facilities, dropped trust, administrative, "
                 "messenger, mobile/seasonal and loan-production offices. Website is the institution's FDIC-listed web address."})


def ncua_credit_unions() -> None:
    tag = "ncua"
    url = "https://mapping.ncua.gov/api/Search/GetSearchLocations"
    sites = {}
    for s in SITES:
        skip = 0
        while True:
            body = {"searchText": f"{s['address']}, Philadelphia, PA", "rdSearchType": "address", "rdSearchRadiusList": "2",
                    "skip": skip, "take": 100, "sort_item": "", "sort_direction": ""}
            d = fetch(url, body=body, tag=tag)
            lst = d.get("list") or []
            for x in lst:
                sites[x["siteIdAndCUNumber"]] = x
            if len(lst) < 100:
                break
            skip += 100
    rows = [x for x in sites.values() if within(x.get("addressLongitude"), x.get("addressLatitude"), R15)]
    # drop ATM-only sites (functions list ATM but not member services)
    rows = [x for x in rows if not ("ATM" in (x.get("siteFunctions") or "") and "Member Services" not in (x.get("siteFunctions") or ""))]
    details = {}
    for n in sorted({x["creditUnionNumber"] for x in rows}):
        details[n] = fetch(f"https://mapping.ncua.gov/api/CreditUnionDetails/GetCreditUnionDetails/{n}", tag=tag)
    feats = []
    for x in rows:
        det = details.get(x["creditUnionNumber"], {})
        base = smart_title(x.get("creditUnionName"))
        ctype = clean(det.get("creditUnionType"))
        name = f"{base} {'Federal Credit Union' if ctype == 'FCU' else 'Credit Union'}"
        site = clean(x.get("creditUnionSiteName"))
        funcs = [f for f in (x.get("siteFunctions") or "").split(";") if f]
        bits = []
        squash = lambda t: re.sub(r"[^A-Z]", "", t.upper().replace("FEDERAL CREDIT UNION", "").replace("FCU", ""))  # noqa: E731
        if site and squash(site) not in squash(base) and squash(base) not in squash(site):
            st = smart_title(site)
            bits.append(st if re.search(r"branch|office|center|site", st, re.I) else f"{st} site")
        if x.get("isMainOffice"):
            bits.append("main office")
        if funcs:
            bits.append(", ".join(funcs).lower().replace("atm", "ATM"))
        fom = clean(det.get("creditUnionFom"))
        if fom:
            f0, _, f1 = fom.partition(" - ")
            f1 = f1.replace("primarily ", "").strip()
            if f0.lower().startswith("community"):
                bits.append("community charter (open to area residents/workers)")
            elif f0.lower().startswith("multiple"):
                bits.append(f"membership: select groups ({f1.lower()})" if f1 else "membership: select groups")
            elif f0.lower().startswith("single"):
                bits.append(f"membership: single sponsor group ({f1.lower()})" if f1 else "membership: single sponsor group")
            elif f0.lower().startswith("associational"):
                bits.append(f"membership: association ({f1.lower()})" if f1 else "membership: association")
            else:
                bits.append(f"membership: {fom.lower()}")
        if x.get("isMdi"):
            bits.append("minority depository institution")
        addr = fmt_addr(x.get("street"), x.get("city"), clean(x.get("state")) or "PA", x.get("zipcode"))
        feats.append(asset(x["addressLongitude"], x["addressLatitude"], "Credit union", name, addr,
                           fmt_phone(x.get("phone") or det.get("creditUnionPhone")), fmt_web(x.get("url") or det.get("creditUnionWebsite")),
                           " · ".join(bits), "ncua_credit_union_sites"))
    feats = dedupe_name(feats)
    record("ncua_credit_union_sites", feats, {
        "title": "Credit Union Offices (NCUA Credit Union Locator)", "categories": ["economic"],
        "publisher": "National Credit Union Administration (NCUA)",
        "landing_url": "https://mapping.ncua.gov/",
        "api_url": "https://mapping.ncua.gov/api/Search/GetSearchLocations",
        "license": FED_LICENSE, "retrieved": retrieved(tag), "data_date": "",
        "notes": "Federally insured credit union sites returned by NCUA's locator within 2 mi of each site address, kept within 1.5 mi; "
                 "ATM-only sites dropped. Many are workplace or church-based credit unions with restricted membership; "
                 "the field of membership is in the detail line. Credit union type and website from NCUA's credit union profile."})


def careerlink() -> None:
    tag = "careerlink"
    url = "https://pacareerlinkphl.org/wp-json/wpgmza/v1/markers"
    d = fetch(url, {"filter": json.dumps({"map_id": "2"})}, tag=tag)
    feats = []
    for m in d:
        try:
            lat, lon = float(m["lat"]), float(m["lng"])
        except (TypeError, ValueError):
            continue
        if not within(lon, lat, R15):
            continue
        title = clean(m.get("title"))
        desc = clean(re.sub(r"<[^>]+>", " ", (m.get("description") or "").replace("&nbsp;", " ")))
        desc = re.sub(r"\bSchedule an Appointment\b", "", desc).strip()
        custom = {c["name"]: clean(c["value"]) for c in m.get("custom_field_data") or []}
        sched = " ".join(v for v in [custom.get("Business days", ""), custom.get("Open", "")] if v)
        text = f"{sched} {desc}"
        if "careerlink" in title.lower():
            kind, name = "PA CareerLink center", title
        elif "open only" in text.lower():
            kind, name = "PA CareerLink outreach site", f"PA CareerLink outreach site – {title}"
        else:
            kind, name = "PA CareerLink partner site", f"PA CareerLink partner site – {title}"
        svc = re.search(r"Services:\s*(.*)", desc)
        svc_txt = re.sub(r"\s*/\s*", ", ", svc.group(1).replace("Seach", "Search")).strip() if svc else ""
        extra = re.sub(r"Services:.*", "", desc).strip()
        bits = [b for b in [sched, extra if extra and extra.lower() not in sched.lower() else "", svc_txt] if b]
        raw = clean(m.get("address"))
        mz = re.match(r"(.*?)[,\s]+Philadelphia[,\s]+PA[,\s]+(\d{5})", raw)
        addr = fmt_addr(mz.group(1), "Philadelphia", "PA", mz.group(2)) if mz else raw
        feats.append(asset(lon, lat, kind, name, addr, fmt_phone(custom.get("Phone Number")), "https://pacareerlinkphl.org/contact-us/",
                           " · ".join(bits), "pa_careerlink_phl_sites"))
    feats = dedupe_name(feats)
    record("pa_careerlink_phl_sites", feats, {
        "title": "PA CareerLink Philadelphia Centers and Outreach Sites", "categories": ["economic"],
        "publisher": "Philadelphia Works, Inc. (PA CareerLink® Philadelphia)",
        "landing_url": "https://pacareerlinkphl.org/contact-us/",
        "api_url": url + '?filter={"map_id":"2"}',
        "license": "Published on pacareerlinkphl.org; no open license stated", "retrieved": retrieved(tag), "data_date": "",
        "notes": "Marker list behind the 'Career Centers' map on PA CareerLink Philadelphia's contact page: the four full-time comprehensive "
                 "centers, the Northeast Hub, part-time outreach sites (mostly in Free Library branches) and partner sites. "
                 "Used instead of data.pa.gov's CareerLink Locations (6p38-7dgx, last updated 2022), which still lists the old West Philadelphia address."})


def obme_workforce() -> None:
    tag = "obme"
    url = f"{CITY}/Black_Male_Engagement_Resources/FeatureServer/0"
    info = arcgis_layer_info(url, tag)
    fs = arcgis_query(url, tag, where="public_yn='Y'")
    feats = []
    for f in fs:
        p = f["properties"]
        svc = clean(p.get("services_offered"))
        if not re.search(r"workforce|employment", svc, re.I):
            continue
        pt = point_of(f.get("geometry")) or ((p.get("lon"), p.get("lat")) if p.get("lat") else None)
        if not pt or not within(pt[0], pt[1], R15):
            continue
        svcs = sorted({s.strip().capitalize() for s in svc.split(",") if s.strip()}, key=lambda s: (not re.search("workforce|employment", s, re.I), s))
        services = ", ".join(svcs[:4]) + (f" + {len(svcs) - 4} more" if len(svcs) > 4 else "")
        name = clean(p.get("organization_name"))
        web = fmt_web(p.get("website"))
        if "dvrpc.org" in web.lower() and "regional planning" not in name.lower():
            web = ""  # source error: the Delaware Valley Peace Commission entry links to the regional planning commission (DVRPC)
        addr = fmt_addr(clean(p.get("address")).rstrip("."), "Philadelphia", "PA", p.get("zip_code"))
        feats.append(asset(pt[0], pt[1], "Workforce / employment program", name, addr,
                           fmt_phone(p.get("phone")), web, f"Services listed: {services}",
                           "phl_obme_workforce_resources"))
    feats = dedupe_name(feats)
    record("phl_obme_workforce_resources", feats, {
        "title": "Workforce and Employment Resources (Office of Black Male Engagement Directory)", "categories": ["economic"],
        "publisher": "City of Philadelphia, Office of Black Male Engagement",
        "landing_url": "https://www.arcgis.com/home/item.html?id=c901b5701b3e42a69b1d2167d9732161",
        "api_url": url + "/query", "license": CITY_LICENSE, "retrieved": retrieved(tag),
        "data_date": epoch_date((info.get("editingInfo") or {}).get("lastEditDate")),
        "notes": "Organizations in the City's public resource directory (public_yn = Y) whose listed services include workforce development or "
                 "employment; most are multi-service nonprofits rather than job centers. Emails dropped."})


# ================================================================ CONTEXT

PUBLIC_OWNERS = [
    (r"LAND BANK", "Philadelphia Land Bank"),
    (r"REDEVELOPMENT AUTH|REDEVEL AUTH|^PHILA(DELPHIA)? REDEVEL|\bRDA\b", "Philadelphia Redevelopment Authority"),
    (r"PHILA(DELPHIA)? HOUSING DEV|\bPHDC\b", "Philadelphia Housing Development Corp."),
    (r"HOUSING AUTH|^PHILADELPHIA HOUSING$|^PHILA HOUSING$", "Philadelphia Housing Authority"),
    (r"SCHOOL DIST|BOARD OF (PUBLIC )?EDUCATION", "School District of Philadelphia"),
    (r"FAIRMOUNT PARK COMM", "City of Philadelphia (Fairmount Park)"),
    (r"^CITY OF PHILA|^PHILADELPHIA CITY OF|^PHILA CITY OF|^THE CITY OF PHILA", "City of Philadelphia"),
    (r"AUTH(ORITY)? FOR IND|AUTH IND DEV|INDUSTRIAL DEV(ELOPMENT)? AUTH", "Philadelphia Authority for Industrial Development"),
    (r"^PHILA(DELPHIA)? PARKING AUTH", "Philadelphia Parking Authority"),
    (r"^PHILA(DELPHIA)? GAS WORKS", "Philadelphia Gas Works (City-owned)"),
    (r"SOUTHEASTERN PE?N?N?(SYLVANI)?A? ?TRANS|\bSEPTA\b|SOUTHEASTERN PA TRANS", "SEPTA"),
    (r"^COMMONWEALTH OF P|^COMMONWEALTH OF PA|DEPT OF TRANSPORTATION|DEPARTMENT OF TRANSPORTATION|^PENNDOT", "Commonwealth of Pennsylvania"),
    (r"^UNITED STATES|^U S A\b|^USA\b|^SEC(T|RETARY)? OF HOUSING|^SECRETARY OF HUD", "Federal government"),
]


def classify_owner(o1, o2) -> tuple[str, str]:
    a = clean(o1).upper()
    both = f"{a} {clean(o2).upper()}".strip()
    if not a:
        return "", ""
    for pat, label in PUBLIC_OWNERS:
        if re.search(pat, a) or (pat.startswith("^") is False and re.search(pat, both)):
            return "public", label
    return "private", ""


def vacant_land() -> None:
    tag_v, tag_o = "vacant_indicators", "opa_landbank"
    url = f"{CITY}/Vacant_Indicators_Land/FeatureServer/0"
    info = arcgis_layer_info(url, tag_v)
    fs = arcgis_query_sites(url, tag_v, R10, out_fields="objectid,address,owner1,owner2,bldg_desc,opa_id,zoningbasedistrict,date_update")
    by_opa: dict[str, dict] = {}
    max_upd = 0
    for f in fs:
        p = f["properties"]
        pt = point_of(f.get("geometry"))
        if not pt or not within(pt[0], pt[1], R10):
            continue
        max_upd = max(max_upd, p.get("date_update") or 0)
        otype, agency = classify_owner(p.get("owner1"), p.get("owner2"))
        key = clean(p.get("opa_id")) or f"vi{p.get('objectid')}"
        if key in by_opa:
            continue
        by_opa[key] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 6), round(pt[1], 6)]},
                       "properties": {"address": smart_title(p.get("address")), "opa_id": clean(p.get("opa_id")), "owner_type": otype,
                                      "public_owner": agency, "land_use": smart_title(p.get("bldg_desc")),
                                      "zoning": clean(p.get("zoningbasedistrict")), "source": "vacant_indicator",
                                      "source_id": "vacant_land"}}
    n_vi = len(by_opa)
    # Philadelphia Land Bank-held parcels from OPA (Carto), within 1 mile of any site
    carto = "https://phl.carto.com/api/v2/sql"
    rows = {}
    for s in SITES:
        q = ("SELECT parcel_number, location, owner_1, owner_2, category_code_description, building_code_description, zoning, "
             "ST_X(the_geom) AS lng, ST_Y(the_geom) AS lat FROM opa_properties_public "
             "WHERE owner_1 ILIKE '%LAND BANK%' AND the_geom IS NOT NULL AND "
             f"ST_DWithin(the_geom::geography, ST_SetSRID(ST_MakePoint({s['lng']}, {s['lat']}), 4326)::geography, {R10})")
        d = fetch(carto, {"q": q}, tag=tag_o)
        if "error" in d:
            raise RuntimeError(f"Carto error: {d['error']}")
        for r in d["rows"]:
            rows[r["parcel_number"]] = r
    n_lb_only = n_lb_both = 0
    for pn, r in rows.items():
        if pn in by_opa:
            by_opa[pn]["properties"]["source"] = "vacant_indicator+land_bank"
            by_opa[pn]["properties"]["owner_type"], by_opa[pn]["properties"]["public_owner"] = "public", "Philadelphia Land Bank"
            n_lb_both += 1
            continue
        n_lb_only += 1
        by_opa[pn] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r["lng"], 6), round(r["lat"], 6)]},
                      "properties": {"address": smart_title(r.get("location")), "opa_id": pn, "owner_type": "public",
                                     "public_owner": "Philadelphia Land Bank",
                                     "land_use": smart_title(r.get("building_code_description") or r.get("category_code_description")),
                                     "zoning": clean(r.get("zoning")), "source": "land_bank", "source_id": "vacant_land"}}
    feats = list(by_opa.values())
    pub = sum(1 for f in feats if f["properties"]["owner_type"] == "public")
    record("vacant_land", feats, {
        "title": "Vacant Land and Land Bank Parcels (within 1 mile)", "categories": [], "context": True,
        "publisher": "City of Philadelphia (Dept. of Planning & Development / L&I Vacant Property Indicators; Office of Property Assessment)",
        "landing_url": "https://opendataphilly.org/datasets/vacant-property-indicators/",
        "api_url": url + "/query", "license": CITY_LICENSE, "retrieved": retrieved(tag_v, tag_o),
        "data_date": epoch_date(max_upd or (info.get("editingInfo") or {}).get("lastEditDate")),
        "notes": f"Parcels the City's Vacant Property Indicators model flags as likely vacant land ({n_vi}), plus Philadelphia Land Bank-owned "
                 f"parcels from OPA ({n_lb_only} not flagged vacant, {n_lb_both} in both), within 1 mile of a site; polygons reduced to an interior point. "
                 f"owner_type is derived from the OPA owner name (public = City, Land Bank, PRA, PHA, PHDC, School District, state, federal, SEPTA etc.; "
                 f"{pub} public); private owner names are not kept. 'Likely vacant' is a model result, not a field survey.",
        "sources": [
            {"title": "Vacant Property Indicators - Land", "publisher": "City of Philadelphia", "api_url": url + "/query",
             "landing_url": "https://opendataphilly.org/datasets/vacant-property-indicators/", "records": n_vi},
            {"title": "OPA Properties (owner = Philadelphia Land Bank)", "publisher": "City of Philadelphia, Office of Property Assessment",
             "api_url": carto, "landing_url": "https://opendataphilly.org/datasets/philadelphia-properties-and-assessment-history/",
             "records": n_lb_only + n_lb_both}]})


SENSITIVE = re.compile(r"GAUDENZIA|WOMEN AGAINST ABUSE|SOJOURNER|EMERGENCY|SHELTER|RECOVERY|DEPAUL|ST\.? RAYMOND|HELP PHILADELPHIA|"
                       r"\bHELP PA\b|SAFE HAVEN|TRANSITIONAL", re.I)


def merge_housing(feats: list[dict]) -> list[dict]:
    """Merge same-name records within 40 m (e.g. a PHA development that also has LIHTC, or one LIHTC project listed twice),
    and fold a PHA senior site into a nearby (<=300 m) PHA development whose name starts the same way."""
    def key5(n):
        w = re.sub(r"[^a-z ]", "", n.lower()).split()
        return w[0][:5] if w else ""

    def xy(f):
        return f["geometry"]["coordinates"]

    out: list[dict] = []
    for f in sorted(feats, key=lambda f: f["properties"]["source"] == "pha_senior_sites"):
        p = f["properties"]
        tgt = None
        for g in out:
            q = g["properties"]
            d = hav(xy(f)[1], xy(f)[0], xy(g)[1], xy(g)[0])
            if q["name"].lower() == p["name"].lower() and d <= 40:
                tgt = g
                break
            if p["source"] == "pha_senior_sites" and q["source"].startswith("hud_public_housing") and d <= 300 and key5(q["name"]) == key5(p["name"]):
                tgt = g
                break
        if tgt is None:
            out.append(f)
            continue
        q = tgt["properties"]
        if p["source"] == q["source"]:
            q["units"] = num((float(q["units"] or 0) + float(p["units"] or 0)) or "")
        elif p["units"]:
            q["units"] = num(max(float(q["units"] or 0), float(p["units"])))
        progs = [x for x in (q["program"].split("; ") + [p["program"]]) if x]
        q["program"] = "; ".join(dict.fromkeys(progs))
        q["year"] = q["year"] or p["year"]
        extra = f"PHA senior site: {p['name']}" if p["source"] == "pha_senior_sites" and p["name"].lower() != q["name"].lower() else p["detail"]
        q["detail"] = "; ".join(dict.fromkeys(x for x in [q["detail"], extra] if x))
        q["source"] = "+".join(dict.fromkeys(q["source"].split("+") + [p["source"]]))
    return out


def public_housing() -> None:
    tag_p, tag_s, tag_l = "hud_phd", "pha_senior", "hud_lihtc"
    feats = []
    # HUD Public Housing Developments, Philadelphia Housing Authority (PA002)
    url_p = f"{HUD}/Public_Housing_Developments/FeatureServer/0"
    info_p = arcgis_layer_info(url_p, tag_p)
    fs = arcgis_query_sites(url_p, tag_p, R15, where="PARTICIPANT_CODE='PA002'",
                            out_fields="OBJECTID,DEVELOPMENT_CODE,PROJECT_NAME,SCATTERED_SITE_IND,TOTAL_DWELLING_UNITS,TOTAL_UNITS,STD_ADDR,STD_CITY,STD_ZIP5,LAST_UPDT_DTTM")
    n_p = 0
    phd_upd = 0
    for f in fs:
        p = f["properties"]
        pt = point_of(f.get("geometry"))
        if not pt or not within(pt[0], pt[1], R15):
            continue
        n_p += 1
        phd_upd = max(phd_upd, p.get("LAST_UPDT_DTTM") or 0)
        scattered = clean(p.get("SCATTERED_SITE_IND")) == "Y"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 6), round(pt[1], 6)]},
                      "properties": {"name": smart_title(p.get("PROJECT_NAME")),
                                     "address": fmt_addr(p.get("STD_ADDR"), p.get("STD_CITY"), "PA", p.get("STD_ZIP5")),
                                     "units": num(p.get("TOTAL_DWELLING_UNITS") or p.get("TOTAL_UNITS")),
                                     "program": "Public housing (PHA)" + (" – scattered sites" if scattered else ""),
                                     "year": "", "detail": f"HUD development {clean(p.get('DEVELOPMENT_CODE'))}" + (
                                         "; point marks one building of a scattered-site development" if scattered else ""),
                                     "source": "hud_public_housing_developments", "source_id": "public_housing"}})
    # City-hosted PHA Senior Sites
    url_s = f"{CITY}/PHA_Senior_Sites/FeatureServer/0"
    info_s = arcgis_layer_info(url_s, tag_s)
    n_s = 0
    for f in arcgis_query(url_s, tag_s):
        p = f["properties"]
        pt = point_of(f.get("geometry"))
        if not pt or not within(pt[0], pt[1], R15):
            continue
        n_s += 1
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 6), round(pt[1], 6)]},
                      "properties": {"name": clean(p.get("Name")), "address": fmt_addr(p.get("Address"), "Philadelphia", "PA", p.get("Zip")),
                                     "units": "", "program": "PHA senior site", "year": "", "detail": "",
                                     "source": "pha_senior_sites", "source_id": "public_housing"}})
    # HUD LIHTC properties
    url_l = f"{HUD}/LIHTC/FeatureServer/0"
    info_l = arcgis_layer_info(url_l, tag_l)
    fs = arcgis_query_sites(url_l, tag_l, R15, out_fields="OBJECTID,HUD_ID,PROJECT,PROJ_ADD,PROJ_CTY,PROJ_ST,PROJ_ZIP,N_UNITS,LI_UNITS,YR_PIS,YR_ALLOC,TRGT_HML,TRGT_ELD")
    n_l = n_l_drop = 0
    max_pis = 0
    for f in fs:
        p = f["properties"]
        pt = point_of(f.get("geometry"))
        if not pt or not within(pt[0], pt[1], R15):
            continue
        if clean(p.get("TRGT_HML")) == "1" or SENSITIVE.search(clean(p.get("PROJECT"))):
            n_l_drop += 1
            continue
        n_l += 1
        yr = clean(p.get("YR_PIS"))
        yr = "" if yr in {"8888", "9999", "0"} else yr
        if yr.isdigit():
            max_pis = max(max_pis, int(yr))
        units, li = num(p.get("N_UNITS")), num(p.get("LI_UNITS"))
        name = smart_title(p.get("PROJECT"))
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 6), round(pt[1], 6)]},
                      "properties": {"name": name, "address": fmt_addr(p.get("PROJ_ADD"), p.get("PROJ_CTY"), clean(p.get("PROJ_ST")) or "PA", p.get("PROJ_ZIP")),
                                     "units": units, "program": "LIHTC" + (" – senior" if clean(p.get("TRGT_ELD")) == "1" else ""),
                                     "year": yr, "detail": (f"{li} low-income units" if li and li != units else "") ,
                                     "source": "hud_lihtc", "source_id": "public_housing"}})
    feats = numify(merge_housing(feats), ("units", "year"))
    cnt = {k: sum(1 for f in feats if k in f["properties"]["source"]) for k in ("hud_public_housing_developments", "pha_senior_sites", "hud_lihtc")}
    both = sum(1 for f in feats if "hud_public_housing_developments" in f["properties"]["source"] and "hud_lihtc" in f["properties"]["source"])
    record("public_housing", feats, {
        "title": "Public Housing and LIHTC Properties", "categories": [], "context": True,
        "publisher": "U.S. Dept. of Housing and Urban Development (HUD eGIS); City of Philadelphia (PHA Senior Sites layer)",
        "landing_url": "https://hudgis-hud.opendata.arcgis.com/datasets/HUD::public-housing-developments",
        "api_url": url_p + "/query", "license": f"{FED_LICENSE}; PHA Senior Sites: {CITY_LICENSE}",
        "retrieved": retrieved(tag_p, tag_s, tag_l),
        "data_date": f"PHA developments {epoch_date(phd_upd or (info_p.get('editingInfo') or {}).get('lastEditDate'))}; "
                     f"LIHTC: latest placed-in-service year among these records {max_pis or '?'} (HUD layer updated {epoch_date((info_l.get('editingInfo') or {}).get('lastEditDate'))})",
        "notes": f"Philadelphia Housing Authority developments from HUD ({n_p}; one point per development at its largest building), City-hosted PHA "
                 f"senior sites ({n_s}; merged into the matching development where one is nearby) and HUD LIHTC properties ({n_l}) within 1.5 mi; "
                 f"same-name records within 40 m are merged ({both} PHA developments also carry LIHTC, units not summed across programs). "
                 f"HUD's public housing layer omits PHA properties converted to Section 8 under RAD. {n_l_drop} LIHTC properties targeted to "
                 f"homeless households or named as recovery/DV/emergency housing were left out per the sensitive-location rule. "
                 f"Old LIHTC projects (1987-2000s) may be past their affordability period. Feature counts by source: {cnt}.",
        "sources": [
            {"title": "Public Housing Developments", "publisher": "HUD eGIS", "api_url": url_p + "/query",
             "landing_url": "https://hudgis-hud.opendata.arcgis.com/datasets/HUD::public-housing-developments", "records": n_p},
            {"title": "PHA Senior Sites", "publisher": "City of Philadelphia (ArcGIS Online, maps.phl.data)", "api_url": url_s + "/query",
             "landing_url": "https://www.arcgis.com/home/item.html?id=967816c094614742bb101508e334f453", "records": n_s,
             "data_date": epoch_date((info_s.get("editingInfo") or {}).get("lastEditDate"))},
            {"title": "Low-Income Housing Tax Credit Properties", "publisher": "HUD eGIS (HUD LIHTC database)", "api_url": url_l + "/query",
             "landing_url": "https://hudgis-hud.opendata.arcgis.com/datasets/HUD::low-income-housing-tax-credit-properties", "records": n_l}]})


def affordable_housing() -> None:
    tag = "dpd_ahp"
    url = f"{CITY}/AffordableHousingProduction/FeatureServer/0"
    src_note = ""
    try:
        info = arcgis_layer_info(url, tag)
        fs = arcgis_query(url, tag)
        data_date = epoch_date((info.get("editingInfo") or {}).get("lastEditDate"))
    except Exception as e:  # noqa: BLE001
        local = next(LOCAL_DS.rglob("affordable_housing_production_dpd.geojson"))
        fs = json.loads(local.read_text())["features"]
        data_date, src_note = "", f" Live service failed ({e}); used studio copy {local.name}."
        failures.append(f"AffordableHousingProduction live query: {e}")
    feats, dropped = [], 0
    for f in fs:
        p = f["properties"]
        pt = point_of(f.get("geometry"))
        if not pt or not within(pt[0], pt[1], R15):
            continue
        ptype = clean(p.get("project_type"))
        if "special needs" in ptype.lower() or SENSITIVE.search(clean(p.get("project_name")) + " " + clean(p.get("developer_name"))):
            dropped += 1
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 6), round(pt[1], 6)]},
                      "properties": {"name": clean(p.get("project_name")), "address": fmt_addr(p.get("address")),
                                     "units": num(p.get("total_units")), "status": clean(p.get("status")),
                                     "year": num(p.get("fiscal_year_complete")), "type": ptype.replace(";", ", "),
                                     "development": clean(p.get("development_type")).replace("NULL", "").replace(";", ", "),
                                     "source": "dpd_affordable_housing_production", "source_id": "affordable_housing"}})
    feats = numify(dedupe_name(feats), ("units", "year"))
    record("affordable_housing", feats, {
        "title": "City-Funded Affordable Housing Production", "categories": [], "context": True,
        "publisher": "City of Philadelphia, Dept. of Planning & Development, Division of Housing and Community Development",
        "landing_url": "https://opendataphilly.org/datasets/affordable-housing-production/",
        "api_url": url + "/query", "license": CITY_LICENSE, "retrieved": retrieved(tag), "data_date": data_date,
        "notes": f"DHCD-funded rental, homeownership and mixed-use projects (complete and under construction) within 1.5 mi; year is the "
                 f"fiscal year completed (blank when under construction). {dropped} 'Special Needs' (supportive, recovery, shelter-type) "
                 f"projects were left out per the sensitive-location rule.{src_note}"})


# ================================================================ main

def main() -> None:
    steps = [fdic_banks, ncua_credit_unions, careerlink, obme_workforce, vacant_land, public_housing, affordable_housing]
    for step in steps:
        try:
            step()
            print(f"ok   {step.__name__}")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{step.__name__}: {e}")
            print(f"FAIL {step.__name__}: {e}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\ndataset                          records  <=1mi Wagner  <=1mi Blankenburg")
    for ds, n, w, b in summary:
        print(f"{ds:32s} {n:7d} {w:12d} {b:17d}")
    if failures:
        print("\nFailures:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
