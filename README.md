# Community Maps · Wagner & Blankenburg

Interactive community maps for the two Final Two School sites, built in the Market Analysis Tool's
design language (Deepblue-Dashboards): a "Zoom to" card, a foldable rail of layer switches, a docked
legend, a site/tract panel on the right, and address search with basemaps at bottom-right.

- `/` the two maps side by side · `/wagner` · `/blankenburg`

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # static site in dist/ (any static host; vercel.json has the SPA rewrites)
```

## Data

`scripts/build_data.py` reads the studio's own outputs from
`~/Desktop/FW 2026/Studio/Final Two School/MIDREVIEW` (override with `STUDIO=...`) and writes
`public/data/<school>/*.json`. Nothing is fetched from the internet.

```bash
npm run build:data   # needs uv; installs geopandas on the fly
```

| Rail section | Layers | Studio source |
|---|---|---|
| Community assets | 10 categories, ½ / 1 mile | Community Asset/Raw_Source/*_Community_Assets.csv |
| Census tracts | 9 ACS measures, tract click → profile | Background1/_source/data (acs_tracts_*, tracts_2020, tract_shares, profile_2024) |
| Study area | ½ & 1 mile, 15-min walk, neighborhood, study tracts, RCOs | Background1, Transportation1 walk_areas, Neighborhood Boundary, Community Asset RCOs |
| Parks & corridors | parks, commercial corridors, BIDs | Community Asset/_source/data, Data_Sources PPR properties |
| Mobility & safety | transit lines & stops, bike lanes, Indego, HIN, crashes, guards, cameras, curb ramps | Transportation1/_source/data (*.gpkg) |
| Economy & land | businesses, zoning, land use, OZ & redevelopment, affordable housing, storefront grants, food access | Economic1/_source/data/layers.gpkg |

RCO contact names, emails and phone numbers are left out of the public map on purpose.

## Where things live

- `src/lib/layers.js` — every layer: file, style, tooltip, popup, (i) text. Add a layer here.
- `src/components/SchoolMap.jsx` — state, lazy loading, zoom-to, search, geocoding, measure, CSV.
- `src/components/Chrome.jsx` — header, Zoom-to card, rail, legend, bottom-right controls.
- `src/components/SitePanel.jsx` — site summary and tract profile.
- `src/components/MapLayers.jsx` — Leaflet layers, panes and basemaps (City of Philadelphia, Esri; keyless).

Asset colors are the studio palette stepped to screen strength (checked for color-blind separation):
color = family, white glyph = category.
