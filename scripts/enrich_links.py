"""Find each place's own links (website, Instagram, Facebook) and add them to public/data/<slug>/assets.json.

Runs after build_data.py. In order of trust:
  1. the link already in the place's source dataset;
  2. the School District's Master School List (a `Website` column) for public and charter schools, and
     Parks & Recreation's Finder (a page for each published park, rec center, pool, playground, older-adult center);
  3. OpenStreetMap: the nearest feature with a matching name that is tagged website / contact:website / url,
     facebook / contact:facebook, instagram / contact:instagram;
  4. scripts/place_links_searched.json: for places within ½ mile of Wagner and Blankenburg with none of the above,
     links found by web search and kept only where the page or listing showed the same name and address/phone;
  5. the place's own website, read once, for the Instagram and Facebook accounts it links to.
A social account shared by three or more differently named places (a chain's or a school district's account,
a website builder's footer) is left out: it is not that place's own. A website that no longer answers
(404, 410, no such host) is left out, as are links in scripts/broken_links.json.

Home-based child care (family and group child care homes) is never looked up: those are private homes.

Run: uv run --no-project --with requests python scripts/enrich_links.py
Caches in scripts/.cache/links (OpenStreetMap answer, the school list, each website read).
"""
import csv
import io
import json
import math
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public/data"
CACHE = Path(__file__).resolve().parent / ".cache/links"
CACHE.mkdir(parents=True, exist_ok=True)
SLUGS = ["wagner", "blankenburg", "robeson", "pennypacker", "fitler", "amynw"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
HOME_CARE = re.compile(r"family child care home|group child care home", re.I)
SDP_LIST = "https://cdn.philasd.org/offices/performance/Open_Data/School_Information/School_List/2025-2026%20Master%20School%20List%20(20251001).csv"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

# ── names ──────────────────────────────────────────────────────────────────
STOP = {"the", "of", "and", "inc", "llc", "co", "corp", "corporation", "company", "philadelphia", "philly", "pa", "at", "a", "in",
        "for", "st", "saint", "ltd", "dba", "phila"}
GENERIC = {"park", "playground", "school", "church", "center", "centre", "community", "recreation", "rec", "garden", "gardens",
           "library", "branch", "academy", "charter", "elementary", "high", "middle", "baptist", "temple", "ministries", "ministry",
           "house", "pharmacy", "market", "store", "food", "foods", "deli", "grocery", "mini", "club", "association", "field",
           "court", "courts", "pool", "tennis", "basketball", "learning", "child", "care", "children", "kids", "early", "daycare",
           "day", "pre", "k", "preschool", "of", "god", "christ", "holy", "new", "first", "second", "missionary", "worship",
           "health", "medical", "clinic", "services", "family", "development", "civic", "neighbors", "neighborhood", "new",
           "supermarket", "shop", "museum", "art", "arts", "memorial", "hall", "inn", "cafe", "restaurant", "bank", "credit", "union",
           "farm", "farms", "program", "programs", "site", "east", "west", "north", "south", "avenue", "ave", "street"}


def toks(name: str) -> set:
    n = (name or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    return {w for w in re.findall(r"[a-z0-9]+", n) if w not in STOP}


def similar(a: str, b: str) -> float:
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    shared = ta & tb
    if not (shared - GENERIC):                       # only words like "park" or "church" in common: not a match
        return 0.0
    overlap = len(shared) / min(len(ta), len(tb))
    seq = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return max(overlap * 0.9 + seq * 0.1, seq if seq > 0.92 else 0)


def metres(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    y = math.radians(la2 - la1)
    return 6371000 * math.hypot(x, y)


def best_match(name, at, candidates, key=lambda c: c["name"]):
    """The candidate with the most similar name, accepted only close by (closer for weaker name matches)."""
    best = None
    for c in candidates:
        d = metres(at, c["at"])
        if d > 500:
            continue
        s = similar(name, key(c))
        ok = (d <= 80 and s >= 0.5) or (d <= 220 and s >= 0.75) or (d <= 500 and s >= 0.99 and len(toks(name)) >= 2)
        if ok and (best is None or (s, -d) > (best[0], -best[1])):
            best = (s, d, c)
    return best[2] if best else None


# ── link shapes ────────────────────────────────────────────────────────────
FB_SKIP = {"sharer", "sharer.php", "share", "share.php", "dialog", "plugins", "tr", "login", "login.php", "policy", "privacy", "help",
           "events", "photo.php", "photo", "photos", "watch", "groups", "hashtag", "business", "legal", "ads", "v2.0", "v3.0", "home.php",
           "l.php", "story.php", "permalink.php", "media", "notes", "gaming", "marketplace", "terms", "about", "settings", "wix",
           "squarespace", "godaddy", "wordpress", "weebly", "facebook", "meta", "fbml", "connect", "2008", "pg", "search"}
IG_SKIP = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "about", "developer", "legal", "direct", "instagram", "wix",
           "squarespace", "godaddy", "wordpress", "weebly", "sharer", "share", "meta"}


def fb_url(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    if not re.search(r"facebook\.com|fb\.com", raw, re.I):
        raw = f"https://www.facebook.com/{raw.lstrip('@/')}"
    m = re.search(r"(?:facebook|fb)\.com/(.+)", raw, re.I)
    if not m:
        return None
    path = m.group(1)
    pid = re.search(r"profile\.php\?id=(\d+)", path)
    if pid:
        return f"https://www.facebook.com/profile.php?id={pid.group(1)}"
    path = re.split(r"[?#\"'<> ]", path)[0].strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts or parts[0].lower() in FB_SKIP or parts[0].lower().endswith(".php"):
        return None
    if parts[0].lower() in ("pages", "people") and len(parts) >= 2:
        return f"https://www.facebook.com/{'/'.join(parts[:3])}"
    if not re.fullmatch(r"[A-Za-z0-9.\-_%]{2,80}", parts[0]):
        return None
    return f"https://www.facebook.com/{parts[0]}"


def ig_url(raw: str):
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,30})", raw, re.I)
    handle = m.group(1) if m else (raw.lstrip("@") if re.fullmatch(r"@?[A-Za-z0-9_.]{2,30}", raw) else None)
    if not handle or handle.lower().strip(".") in IG_SKIP:
        return None
    return f"https://www.instagram.com/{handle.strip('.')}/"


def web_url(raw: str):
    if not raw:
        return None
    raw = raw.strip().split()[0].strip(";,")
    if not re.search(r"[a-z0-9-]+\.[a-z]{2,}", raw, re.I) or "@" in raw:
        return None
    return raw if re.match(r"https?://", raw, re.I) else f"https://{raw}"


def sort_link(url):
    """A 'website' that is really a Facebook or Instagram page goes in its own slot."""
    if not url:
        return {}
    if re.search(r"(?:facebook|fb)\.com/", url, re.I):
        return {"facebook": fb_url(url)} if fb_url(url) else {}
    if re.search(r"instagram\.com/", url, re.I):
        return {"instagram": ig_url(url)} if ig_url(url) else {}
    return {"website": url}


# ── sources ────────────────────────────────────────────────────────────────
def sdp_schools():
    path = CACHE / "sdp_master_2526.csv"
    if not path.exists():
        r = requests.get(SDP_LIST, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    rows = []
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))):
        m = re.match(r"\s*([-\d.]+),\s*([-\d.]+)", r.get("GPS Location") or "")
        if m and web_url(r.get("Website")):
            rows.append({"name": r["Publication Name"], "alt": r.get("Abbreviated Name") or "", "at": (float(m.group(1)), float(m.group(2))),
                         "website": web_url(r["Website"])})
    return rows


PPR_SQL = ("SELECT f.id, f.public_name, f.facility_type, ST_Y(l.the_geom) AS lat, ST_X(l.the_geom) AS lng FROM ppr_facilities f "
           "JOIN ppr_website_locatorpoints l ON l.linkid = f.website_locator_points_link_id WHERE f.facility_is_published = true")
PPR_TYPES = {"park", "playground", "rec", "sports", "senior", "garden", "youth", "history", "arts", "meals"}


def ppr_finder():
    """Parks & Recreation's own Finder: one page per published park, rec center, pool, playground and older-adult center."""
    path = CACHE / "ppr_finder.json"
    if not path.exists():
        r = requests.get("https://phl.carto.com/api/v2/sql", params={"q": PPR_SQL}, timeout=60)
        r.raise_for_status()
        path.write_text(r.text)
    return [{"name": r["public_name"], "at": (r["lat"], r["lng"]), "website": f"https://www.phila.gov/parks-rec-finder/#/location/{r['id']}"}
            for r in json.loads(path.read_text())["rows"] if r.get("lat")]


def osm_features(bbox):
    path = CACHE / "osm_links.json"
    if not path.exists():
        s, w, n, e = bbox
        q = f"""[out:json][timeout:240];
nwr["name"][~"^(website|contact:website|url|facebook|contact:facebook|instagram|contact:instagram)$"~"."]({s},{w},{n},{e});
out center tags;"""
        for attempt in range(6):
            try:
                r = requests.post(OVERPASS[attempt % 2], data={"data": q}, headers={"User-Agent": "studio-asset-map/1.0"}, timeout=300)
                r.raise_for_status()
                path.write_text(r.text)
                break
            except Exception as ex:                      # Overpass is often busy; try the mirror, then wait
                print("  overpass:", ex)
                time.sleep(10 * (attempt + 1))
        else:
            raise SystemExit("OpenStreetMap (Overpass) did not answer")
    out = []
    for el in json.loads(path.read_text())["elements"]:
        t = el.get("tags", {})
        # stations, stops and machines named after a nearby building are not that building
        if (t.get("amenity") in NOT_A_PLACE or any(k in t for k in ("highway", "public_transport", "railway", "route", "network:wikidata"))
                or re.search(r"rideindego|septa\.org", " ".join(t.get(k, "") for k in ("website", "contact:website", "url")), re.I)):
            continue
        at = (el["lat"], el["lon"]) if "lat" in el else (el["center"]["lat"], el["center"]["lon"]) if "center" in el else None
        if not at:
            continue
        links = {}
        for k in ("website", "contact:website", "url"):
            if web_url(t.get(k)):
                links.update({kk: vv for kk, vv in sort_link(web_url(t[k])).items() if kk not in links})
        for k in ("contact:facebook", "facebook"):
            if fb_url(t.get(k)):
                links.setdefault("facebook", fb_url(t[k]))
        for k in ("contact:instagram", "instagram"):
            if ig_url(t.get(k)):
                links.setdefault("instagram", ig_url(t[k]))
        if links:
            out.append({"name": t["name"], "at": at, **links, "osm": f"{el['type']}/{el['id']}"})
    return out


NOT_A_PLACE = {"bicycle_rental", "parking", "parking_entrance", "charging_station", "vending_machine", "atm", "bus_station", "taxi",
               "car_sharing", "parcel_locker", "post_box", "telephone", "fuel"}
FB_RE = re.compile(r"(?:https?:)?//(?:www\.|m\.|web\.|business\.)?(?:facebook|fb)\.com/[^\"'\s<>)]+", re.I)
IG_RE = re.compile(r"(?:https?:)?//(?:www\.)?instagram\.com/[A-Za-z0-9_.]{2,30}", re.I)


def read_site(url):
    """Fetch a website once: does it answer, and which Facebook / Instagram accounts does it link to?"""
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"}, timeout=(8, 15), allow_redirects=True, stream=True)
        status = r.status_code
        body = ""
        if status < 400 and "html" in (r.headers.get("content-type") or "html"):
            body = r.raw.read(1_500_000, decode_content=True).decode(r.encoding or "utf-8", "ignore")
        r.close()
    except requests.exceptions.SSLError:
        return {"status": "ssl"}
    except requests.exceptions.ConnectionError as ex:
        return {"status": "dns" if "Name or service not known" in str(ex) or "nodename nor servname" in str(ex) or "getaddrinfo" in str(ex) else "conn"}
    except Exception as ex:
        return {"status": type(ex).__name__}
    fb = Counter(u for u in (fb_url(m) for m in FB_RE.findall(body)) if u)
    ig = Counter(u for u in (ig_url(m) for m in IG_RE.findall(body)) if u)
    return {"status": status, "final": r.url, "facebook": fb.most_common(1)[0][0] if fb else None,
            "instagram": ig.most_common(1)[0][0] if ig else None}


def main():
    dead = set(json.loads((ROOT / "scripts/broken_links.json").read_text()))
    files = {s: json.loads((DATA / s / "assets.json").read_text()) for s in SLUGS}
    # the websites build_data.py wrote (from the source datasets) are kept aside, so running this again starts
    # from them and not from its own earlier additions
    for s, fc in files.items():
        side = CACHE / f"dataset_websites_{s}.json"
        if fc.get("links") != "enriched":
            side.write_text(json.dumps([ft["properties"].get("website") for ft in fc["features"]]))
        for ft, w in zip(fc["features"], json.loads(side.read_text())):
            ft["properties"]["website"] = w

    # every place once (the same place sits in several schools' files)
    places = {}
    for s, fc in files.items():
        for f in fc["features"]:
            p = f["properties"]
            lng, lat = f["geometry"]["coordinates"]
            k = (p["type"], p.get("name") or "", round(lat, 5), round(lng, 5))
            places.setdefault(k, {"p": p, "at": (lat, lng)})
    print(f"{len(places)} places")
    lats = [v["at"][0] for v in places.values()]
    lngs = [v["at"][1] for v in places.values()]
    bbox = (min(lats) - 0.01, min(lngs) - 0.01, max(lats) + 0.01, max(lngs) + 0.01)

    sdp = sdp_schools()
    ppr = ppr_finder()
    osm = osm_features(bbox)
    osm_by_cell = defaultdict(list)                     # a coarse grid so matching stays quick
    for o in osm:
        osm_by_cell[(round(o["at"][0], 2), round(o["at"][1], 2))].append(o)
    near = lambda at: [o for dy in (-0.01, 0, 0.01) for dx in (-0.01, 0, 0.01) for o in osm_by_cell.get((round(at[0] + dy, 2), round(at[1] + dx, 2)), [])]
    print(f"School District list: {len(sdp)} schools with a website · OpenStreetMap: {len(osm)} named features with links")

    searched_path = ROOT / "scripts/place_links_searched.json"
    searched = json.loads(searched_path.read_text()) if searched_path.exists() else {}
    found = {}
    origin = Counter()
    for k, v in places.items():
        p, at = v["p"], v["at"]
        if HOME_CARE.search(p.get("kind") or "") or re.search(r"polling", p.get("kind") or "", re.I):
            continue
        own = re.split(r"\s+(?:at|@)\s+", p.get("name") or "", maxsplit=1, flags=re.I)[0]
        links, how = {}, {}
        for kk, vv in sort_link(web_url(p.get("website"))).items():
            links[kk], how[kk] = vv, "dataset"
        if p["type"] in ("public_school", "childcare") and "website" not in links:
            m = best_match(own, at, sdp)
            if m:
                links["website"], how["website"] = m["website"], "sdp"
        if p["type"] in PPR_TYPES and "website" not in links:
            m = best_match(p.get("name"), at, ppr)       # "Playground at Morris Estate…": the host site's page is the right one
            if m:
                links["website"], how["website"] = m["website"], "ppr"
        o = best_match(own, at, near(at))
        if o:
            for kk in ("website", "facebook", "instagram"):
                if o.get(kk) and kk not in links:
                    links[kk], how[kk] = o[kk], "osm"
        hit = searched.get(f"{p['type']}|{p.get('name') or ''}|{at[0]:.5f}|{at[1]:.5f}")
        if hit:
            for kk, fn in (("website", web_url), ("facebook", fb_url), ("instagram", ig_url)):
                if hit.get(kk) and fn(hit[kk]) and kk not in links:
                    links[kk], how[kk] = fn(hit[kk]), "search"
        if links:
            found[k] = {"links": links, "how": how}

    # read each website once for its social accounts (and to see that it still answers)
    sites_path = CACHE / "sites.json"
    sites = json.loads(sites_path.read_text()) if sites_path.exists() else {}
    todo = sorted({f["links"]["website"] for f in found.values() if f["links"].get("website") and f["links"]["website"] not in sites
                   and f["how"].get("website") != "ppr"})
    print(f"reading {len(todo)} websites ({len(sites)} cached) …")
    with ThreadPoolExecutor(12) as ex:
        for url, res in zip(todo, ex.map(read_site, todo)):
            sites[url] = res
    sites_path.write_text(json.dumps(sites, indent=0))

    for f in found.values():
        url = f["links"].get("website")
        if not url:
            continue
        r = sites.get(url, {})
        st = r.get("status")
        if url in dead or st in (404, 410, "dns") or (f["how"]["website"] != "dataset" and st in ("conn", "ssl")):
            f["links"].pop("website")
            continue
        for kk in ("facebook", "instagram"):
            if r.get(kk) and kk not in f["links"]:
                f["links"][kk], f["how"][kk] = r[kk], "website"

    # a social account on three or more differently named places belongs to a chain, a district or a web builder
    owners = defaultdict(set)
    for (t, name, *_), f in found.items():
        for kk in ("facebook", "instagram"):
            if f["links"].get(kk):
                owners[f["links"][kk].lower()].add(" ".join(sorted(toks(name))))
    shared = {u for u, names in owners.items() if len(names) >= 3}
    for f in found.values():
        for kk in ("facebook", "instagram"):
            if f["links"].get(kk) and (f["links"][kk].lower() in shared or f["links"][kk] in dead):
                f["links"].pop(kk)
                f["how"].pop(kk, None)
        for kk, how in f["how"].items():
            if kk in f["links"]:
                origin[(kk, how)] += 1

    # write back
    for s, fc in files.items():
        for ft in fc["features"]:
            p = ft["properties"]
            lng, lat = ft["geometry"]["coordinates"]
            for kk in ("website", "facebook", "instagram"):
                p.pop(kk, None)
            f = found.get((p["type"], p.get("name") or "", round(lat, 5), round(lng, 5)))
            if f:
                p.update({kk: f["links"][kk] for kk in ("website", "facebook", "instagram") if f["links"].get(kk)})
        fc["links"] = "enriched"
        (DATA / s / "assets.json").write_text(json.dumps(fc, separators=(",", ":")))

    n = len(places)
    has = Counter()
    by_type = defaultdict(Counter)
    for k, v in places.items():
        f = found.get(k, {"links": {}})["links"]
        any_ = bool(f)
        has["any"] += any_
        for kk in ("website", "facebook", "instagram"):
            has[kk] += bool(f.get(kk))
        by_type[k[0]]["n"] += 1
        by_type[k[0]]["linked"] += any_
    print(f"links: {has['any']} of {n} places ({has['any'] / n:.0%}) · website {has['website']} · Facebook {has['facebook']} · Instagram {has['instagram']}")
    print("  where from:", ", ".join(f"{kk} {how} {c}" for (kk, how), c in sorted(origin.items())))
    print("  by type:", " · ".join(f"{t} {c['linked']}/{c['n']}" for t, c in sorted(by_type.items(), key=lambda x: -x[1]["n"])))
    print(f"  {len(shared)} shared social accounts left out (chains, districts, web builders)")


if __name__ == "__main__":
    main()
