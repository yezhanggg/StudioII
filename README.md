# Community Asset Map · Wagner, Blankenburg & four other schools

What is around each school, to inform the reuse of Wagner and Blankenburg. **An inventory, not a recommendation.**
Places are grouped the way a first-time reader looks for them: Food · Health · Children & learning · Community &
recreation · More places (off at first). Every place cites its source in its popup and in **Sources & data**.

One interactive map for the studio's six candidate schools (Wagner, Blankenburg, Robeson, Pennypacker, Fitler,
AMY Northwest), in the Market Analysis Tool's design language (Deepblue-Dashboards): a school bar (click the
selected school again to clear it), a Radius card (¼–1½ miles), a left panel of five place groups and a
collapsible list of map layers, a legend, a panel for the selected school (each type of place: how many within the
radius, how far the nearest; the building; who lives in its study census tracts; RCOs), and a short Sources & data
window.

- `/` all six schools · `/wagner`, `/blankenburg`, `/robeson`, `/pennypacker`, `/fitler`, `/amynw` one school

## Run

```bash
npm install
echo 'VITE_MAPBOX_TOKEN=pk....' > .env.local   # Mapbox basemaps (falls back to Esri without it)
npm run dev          # http://localhost:5173
npm run build        # static site in dist/ (vercel.json has the SPA rewrites)
node scripts/check_links.mjs   # requests every website / dashboard link the map shows
```

## Community assets: five research inventories

`scripts/fetch/{education,health,green,civic,economy}.py` pull every asset from official sources (City of
Philadelphia / OpenDataPhilly, data.pa.gov, HRSA, USDA, NCES, NPS, FDIC, NCUA, HUD, SAMHSA) and OpenStreetMap,
within 1.5 miles of the six schools, and write `scripts/fetch/out/<domain>/` + a source manifest
(`scripts/fetch/CONTRACT.md`). Re-run one with
`uv run --no-project --with geopandas --with pyogrio --with requests python scripts/fetch/<domain>.py`.
`build_data.py` merges them, removes duplicates across sources, sorts each place into a plain-language type, and
writes `public/data/sources.json` for the documentation window. `node scripts/check_links.mjs` checks every link;
dead ones go to `scripts/broken_links.json` and the next build leaves them out.

## Data

`scripts/build_data.py` writes `public/data/` from the studio folder (`~/Desktop/FW 2026/Studio`, override with
`STUDIO=...`). Fetched City / PA / OpenStreetMap data is cached in `scripts/.cache` (not committed).

```bash
npm run build:data   # needs uv; installs geopandas, osmnx on the fly
```

| | Wagner & Blankenburg | Robeson, Pennypacker, Fitler, AMY Northwest |
|---|---|---|
| Community assets | studio table (Community Asset/Raw_Source) | same method as `01_assets.py`: City services within 1 mi, PA DHS child care, OpenStreetMap worship |
| RCOs | studio extract | City RCO registry, boundaries reaching ½ mi |
| 15-minute walk | studio walk areas | same method as `01_walkshed.py` (OSM walk network, 80 m/min, 25 m buffer) |
| Who lives nearby | the team's study tracts, summed as one group (ACS 2020–2024, aggregate medians) | the study tracts below, summed the same way |
| Study tracts | the team's list | tracts with ≥ 20% of residents inside ½ mi, plus the school's tract |
| Neighborhood | studio boundary | Azavea neighborhood |

All six: SDP 2024 attendance catchments (Fitler, Robeson and AMY Northwest admit citywide and have none),
SDP Facilities Master Plan ratings (`Data_Sources/sites.csv`), and context layers built once around all six
(transit, bike network, High Injury Network, PennDOT crashes 2020–2024, crossing guards, speed cameras,
businesses, zoning, land use, Opportunity Zones, redevelopment areas, affordable housing, storefront grants,
food access, parks, corridors, BIDs, citywide census tracts).

The build ends with a check that runs the rebuilt methods on Wagner and Blankenburg and prints them beside the
studio's numbers. RCO contact names, emails and phone numbers are left out on purpose.

## Where things live

- `src/lib/layers.js` — every layer: scope, file, style, tooltip, popup, (i) text.
- `src/components/SchoolMap.jsx` — state, lazy loading, merging across schools, radius, zoom-to, CSV.
- `src/components/Chrome.jsx` — school bar, Zoom-to + radius, rail, legend, bottom-right controls.
- `src/components/SitePanel.jsx` — the selected school: places nearby, building, study-tract profile, RCOs.
- `src/components/MapLayers.jsx` — Leaflet layers, panes, basemaps (Esri Gray default, City of Philadelphia, satellite).
