# Community Map · Six Schools

One interactive map for the studio's six candidate schools (Wagner, Blankenburg, Robeson, Pennypacker, Fitler,
AMY Northwest), in the Market Analysis Tool's design language (Deepblue-Dashboards): a school bar, a "Zoom to"
card with an adjustable radius, a foldable rail of layer switches, a docked legend, a compare / school / tract
panel on the right, and basemaps, tools and address search at bottom-right.

- `/` all six schools · `/wagner`, `/blankenburg`, `/robeson`, `/pennypacker`, `/fitler`, `/amynw` one school

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # static site in dist/ (vercel.json has the SPA rewrites)
node scripts/check_links.mjs   # requests every website / dashboard link the map shows
```

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
| Study area profile | studio `profile_2024.csv` | same method as `03_profile.py` (block-weighted tract shares, aggregate medians) |
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
- `src/components/SchoolMap.jsx` — state, lazy loading, merging across schools, radius, zoom-to, search, CSV.
- `src/components/Chrome.jsx` — school bar, Zoom-to + radius, rail, legend, bottom-right controls.
- `src/components/SitePanel.jsx` — compare cards, school summary, tract profile.
- `src/components/MapLayers.jsx` — Leaflet layers, panes, basemaps (Esri Gray default, City of Philadelphia, satellite).
