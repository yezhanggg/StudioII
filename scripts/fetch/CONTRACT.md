# Asset research contract (shared by the five domain agents)

## Purpose
The map is an evidence base for deciding the reuse of two closed school sites, **Wagner** and **Blankenburg**
(Philadelphia), with four other candidate schools for comparison. It must show what community assets exist
around each site, where they are, and where they come from. It recommends nothing. Your job is to collect
every relevant asset from **official, verifiable sources**, document each source, and make the pull
re-runnable.

## The six sites
`scripts/fetch/schools.json` (slug, name, lat, lng). Collect everything within **1.5 miles (2,414 m)** of ANY
of the six centers (the map uses up to 1 mile; community organizations up to 2 miles, so for the
`community_orgs` category collect within **2 miles**).

## Category ids (use exactly these in the `category` property)
| family | category id | what belongs |
|---|---|---|
| learning | `schools` | K-12 schools of every type (district, charter, private, parochial) |
| learning | `early_childhood` | licensed child care centers / group / family homes, PHLpreK, Head Start / Early Head Start |
| learning | `libraries` | public library branches (Free Library), other public libraries |
| learning | `youth` | out-of-school-time / after-school programs, youth centers, YMCA/Boys & Girls Clubs, PAL centers |
| learning | `higher_ed` | colleges, universities, community college sites, adult education / literacy sites |
| health | `health_care` | hospitals, City and federally qualified health centers, clinics, dental clinics, behavioral health outpatient sites |
| health | `pharmacies` | pharmacies |
| health | `older_adults` | senior centers, older adult centers, PCA sites, adult day services |
| health | `social_services` | WIC offices, Neighborhood Energy Centers, benefits / housing counseling, family centers, legal aid, food stamp (DHS CAO) offices |
| green | `food` | supermarkets, grocery stores, SNAP retailers that sell fresh food, farmers markets, food pantries, free meal sites |
| green | `gardens_farms` | community gardens, urban farms, PHS / PPR urban agriculture |
| green | `parks_rec` | parks (as a point at the park), recreation centers, playgrounds, pools, spraygrounds, courts, athletic fields, trails heads |
| civic | `arts_culture` | museums, galleries, theaters, arts centers, murals (Mural Arts), public art |
| civic | `historic` | Philadelphia Register / National Register historic sites and landmarks (points) |
| civic | `civic_safety` | police districts, fire stations, City service centers, polling places, community / neighborhood centers run by the City |
| civic | `community_orgs` | RCOs (as their office point), CDCs, Neighborhood Advisory Committees, park friends groups, civic associations |
| civic | `economic` | banks and credit unions, workforce / job centers (PA CareerLink, Philadelphia Works), small business support centers |
| faith | `worship` | places of worship |

## Output (write only inside your domain folder)
`scripts/fetch/out/<domain>/`:

- `<dataset_id>.geojson` — one file per source dataset. FeatureCollection, EPSG:4326, **Point** geometry
  (polygons → a point inside the polygon). Properties, all strings except `source_id`, empty string when unknown:
  `category` (id above), `kind` (short type, e.g. "Charter school", "Pharmacy", "Recreation center"),
  `name`, `address`, `phone` (organization phone only), `website`, `detail` (one short line, optional, e.g.
  "Grades K-8 · 412 students"), `source_id` (= dataset_id).
- `manifest.json` — a JSON array, one object per dataset:
  ```json
  {"id": "phl_ppr_program_sites", "title": "PPR Program Sites", "categories": ["parks_rec"],
   "publisher": "Philadelphia Parks & Recreation", "landing_url": "https://opendataphilly.org/datasets/...",
   "api_url": "https://services.arcgis.com/.../query", "license": "...",
   "retrieved": "2026-11-09", "data_date": "as the publisher states it, or ''",
   "records": 123, "notes": "what was included / excluded and why, in one or two plain sentences"}
  ```
- Context datasets that are areas rather than assets (only the housing/land agent): polygons are fine; put
  `"context": true` in the manifest entry and use the property schema that dataset needs (keep it small).

## Script
`scripts/fetch/<domain>.py`, re-runnable with
`uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/<domain>.py`
It downloads (cache raw responses under `scripts/.cache/fetch/<domain>/`), filters to the 1.5-mile area
(2 miles for community_orgs), standardizes, de-duplicates within each dataset, and writes the outputs.
Run it and make sure it finishes.

## Rules
- **Official first.** City of Philadelphia (OpenDataPhilly; most layers are ArcGIS services under
  `https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/<Name>/FeatureServer/0/query`; the
  service directory lists them: `https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services?f=json`),
  Commonwealth of Pennsylvania (data.pa.gov), federal (HRSA, USDA, NCES, IMLS, HUD). **OpenStreetMap** via
  Overpass (`https://overpass-api.de/api/interpreter`, send header `User-Agent: studio-community-maps/1.0`,
  retry with backoff, mirror `https://overpass.kumi.systems/api/interpreter`) to fill gaps; label it as OSM.
- **Never invent a URL or a field.** Query each endpoint, look at what comes back, and only record sources
  you actually pulled. If a dataset you expected does not exist or is down, say so in your report.
- Local copies the studio already downloaded may be used (cite the original publisher):
  `~/Desktop/FW 2026/Studio/Pre-Mid Review/Data_Sources/` and `~/Desktop/FW 2026/Studio/Pre-Mid Review/9.21.26/`.
- **No people.** Do not keep names, emails or phones of private individuals (RCO contacts, owners). Leave out
  sensitive locations: domestic-violence shelters, addiction-treatment residences, homeless shelters' exact
  addresses, and anything a source marks confidential.
- Stay in your categories; another agent covers the others. If you find something for another domain, mention
  it in your report rather than writing it.
- Within a dataset, drop exact duplicates (same name within 40 m). Across datasets the build de-duplicates.
- Keep names readable (title case if the source is ALL CAPS; keep acronyms).

## Report back (short)
Datasets written (id, records within 1 mile of Wagner / Blankenburg), sources you tried that failed, and any
caveat a planner should know (coverage gaps, stale dates).
