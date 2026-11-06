/**
 * Every layer the maps can draw: what it is, which file it comes from, how it looks, what its
 * tooltip and popup say. SchoolMap reads this list and nothing else to build the rail, the legend
 * and the Leaflet layers, so a new layer is one entry here (plus its file from scripts/build_data.py).
 */

// ── colours ───────────────────────────────────────────────────────────────
// Studio style (Final Two School/_doc/Style/style.py)
export const PAL = {
  lavender: '#C9CCDF', stone: '#C6C4AF', cream: '#EFE2D1', mist: '#C8D7D0', sage: '#659075', blush: '#DDA196',
  terracotta: '#D7826D', brick: '#944131', pine: '#3F746A', indigo: '#393864', ochre: '#BE731F',
  ink: '#1E1E1C', ink2: '#57564E', muted: '#8C8A7C',
};

// Asset families: the studio's hues stepped to screen strength. Checked with the dataviz validator
// (lightness band, chroma floor, CVD and normal-vision separation all pass). Colour names the family;
// the white glyph inside the marker names the category, so identity is never colour alone.
export const FAMILY = {
  learning: { label: 'Learning', color: '#3F5FBF' },
  civic: { label: 'Civic', color: '#D99A1E' },
  green: { label: 'Parks & food', color: '#16907A' },
  health: { label: 'Health & aging', color: '#D0553C' },
  faith: { label: 'Faith', color: '#9A57A6' },
};

// Glyphs (24×24, stroked white)
export const ICONS = {
  school: 'M2 9.5 12 5l10 4.5L12 14 2 9.5Z M6 11.5V16c3.5 2.5 8.5 2.5 12 0v-4.5',
  child: 'M12 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z M8 21l1.5-7.5h5L16 21 M6.5 11.5 9.5 10h5l3 1.5',
  book: 'M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5v-15Z M4 19.5A1.5 1.5 0 0 0 5.5 21H20',
  tree: 'M12 2.5 18 11h-3.5l4 6h-13l4-6H6l6-8.5Z M12 17v4.5',
  food: 'M7 2.5v7a2 2 0 0 0 4 0v-7 M9 9.5v12 M17 21.5V2.5c-2 0-3.5 3-3.5 6.5s1.5 4 3.5 4',
  cross: 'M12 5v14 M5 12h14',
  heart: 'M12 20s-7.5-4.6-7.5-10.2A4 4 0 0 1 12 7.6a4 4 0 0 1 7.5 2.2C19.5 15.4 12 20 12 20Z',
  people: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5 M16 5.2a3 3 0 0 1 0 5.6 M18 14.6c2 .7 3 2.6 3 5.4',
  shield: 'M12 3 19.5 6v5.5c0 4.7-3.2 8-7.5 9.5-4.3-1.5-7.5-4.8-7.5-9.5V6L12 3Z',
  worship: 'M12 2v5 M9.5 4.5h5 M5.5 21.5v-9L12 7l6.5 5.5v9H5.5Z M10 21.5V17h4v4.5',
};

export const CATEGORIES = [
  { id: 'Schools', family: 'learning', icon: 'school' },
  { id: 'Child care', family: 'learning', icon: 'child' },
  { id: 'Libraries', family: 'learning', icon: 'book' },
  { id: 'Parks and recreation', family: 'green', icon: 'tree' },
  { id: 'Food access', family: 'green', icon: 'food' },
  { id: 'Health care', family: 'health', icon: 'cross' },
  { id: 'Older adult centers', family: 'health', icon: 'heart' },
  { id: 'Community organizations', family: 'civic', icon: 'people' },
  { id: 'Fire and police', family: 'civic', icon: 'shield' },
  { id: 'Places of worship', family: 'faith', icon: 'worship' },
];
export const CATEGORY = Object.fromEntries(CATEGORIES.map((c) => [c.id, { ...c, color: FAMILY[c.family].color }]));

export const CATEGORY_INFO = {
  Schools: 'District, charter, private and Archdiocese schools within one mile (City of Philadelphia).',
  'Child care': 'Child care centers and family child care homes, from the 15-minute walk inventory.',
  Libraries: 'Free Library of Philadelphia branches.',
  'Parks and recreation': 'Philadelphia Parks & Recreation program sites: recreation centers, playgrounds, pools.',
  'Food access': 'Food pantries and free meal sites, farmers markets, community gardens, urban agriculture.',
  'Health care': 'City and community health centers and hospitals.',
  'Older adult centers': 'PPR older adult centers and Philadelphia Corporation for Aging senior centers.',
  'Community organizations': 'Park friends groups, Neighborhood Advisory Committees and community development corporations (within two miles).',
  'Fire and police': 'Fire stations and police district headquarters.',
  'Places of worship': 'Churches, mosques and other places of worship, from the 15-minute walk inventory.',
};

// Sequential ramp for the census choropleth: one hue, light to dark (Lavender → Indigo).
export const RAMP = ['#EDEDF5', '#C9CCDF', '#9A9CC2', '#686A9C', '#393864'];

// ── formatting ────────────────────────────────────────────────────────────
const ok = (v) => typeof v === 'number' && Number.isFinite(v);
export const fmtInt = (v) => (ok(v) ? Math.round(v).toLocaleString('en-US') : 'n/a');
export const fmtMoney = (v) => (ok(v) ? `$${Math.round(v).toLocaleString('en-US')}` : 'n/a');
export const fmtMoneyK = (v) => (ok(v) ? (v >= 1000 ? `$${Math.round(v / 1000)}K` : `$${Math.round(v)}`) : 'n/a');
export const fmtPct = (v, dp = 0) => (ok(v) ? `${(v * 100).toFixed(dp)}%` : 'n/a');
export const fmtMiles = (mi) => (mi < 0.19 ? `${Math.round(mi * 5280).toLocaleString('en-US')} ft` : `${mi.toFixed(2)} mi`);
export const walkMinutes = (mi) => Math.max(1, Math.round((mi * 1609.344) / 80)); // the studio's 80 m/min pace

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const link = (u) => {
  if (!u) return '';
  const href = /^https?:\/\//i.test(u) ? u : `https://${u}`;
  return `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, ''))}</a>`;
};
/** Popup HTML: title, kind, lines, source. Distance lines are added by the map. */
export function popupHtml({ title, kind, lines = [], source }) {
  const body = lines.filter(Boolean).map((l) => `<div>${l}</div>`).join('');
  return `<div class="pp"><div class="pp-t">${esc(title)}</div>${kind ? `<div class="pp-k">${esc(kind)}</div>` : ''}${body ? `<div class="pp-b">${body}</div>` : ''}${source ? `<div class="pp-s">Source: ${esc(source)}</div>` : ''}</div>`;
}
export const assetPopup = (p) => popupHtml({
  title: p.name, kind: p.kind,
  lines: [esc(p.detail), esc(p.address), esc(p.phone), link(p.website)],
  source: p.source,
});

// ── choropleth measures (tracts.json properties) ─────────────────────────
export const MEASURES = [
  { id: 'income', label: 'Median household income', fmt: fmtMoney, legend: fmtMoneyK, profile: 'Median household income', info: 'ACS 5-year median household income, in dollars of the survey year.' },
  { id: 'poverty', label: 'Poverty rate', fmt: (v) => fmtPct(v), profile: 'Poverty rate', info: 'Share of people whose income in the past year was below the federal poverty line.' },
  { id: 'unemployment', label: 'Unemployment rate', fmt: (v) => fmtPct(v), profile: 'Unemployment rate', info: 'Unemployed as a share of the civilian labor force.' },
  { id: 'home_value', label: 'Median home value', fmt: fmtMoney, legend: fmtMoneyK, profile: 'Median home value', info: 'Median value of owner-occupied homes, as owners estimate it.' },
  { id: 'renter', label: 'Renter households', fmt: (v) => fmtPct(v), profile: 'Renter-occupied', info: 'Share of occupied homes that are rented.' },
  { id: 'bachelors', label: "Bachelor's degree or higher", fmt: (v) => fmtPct(v), profile: "Bachelor's degree or higher", info: 'Adults 25 and over with at least a four-year degree.' },
  { id: 'children', label: 'Children under 18', fmt: (v) => fmtPct(v), info: 'Residents under 18 as a share of everyone.' },
  { id: 'black', label: 'Black residents', fmt: (v) => fmtPct(v), profile: 'Black', info: 'Black or African American alone, not Hispanic, as a share of everyone.' },
  { id: 'pop', label: 'Population', fmt: fmtInt, info: 'Total population. Tracts differ in size, so this reads as a count, not a density.' },
];
export const MEASURE = Object.fromEntries(MEASURES.map((m) => [m.id, m]));

/** Five quantile classes over the values present; returns { breaks, colorOf }. */
export function quantiles(values) {
  const v = values.filter(ok).sort((a, b) => a - b);
  if (!v.length) return { breaks: [], colorOf: () => '#e7e5e4' };
  const q = (t) => v[Math.min(v.length - 1, Math.floor(t * v.length))];
  const breaks = [q(0.2), q(0.4), q(0.6), q(0.8)];
  const colorOf = (x) => (ok(x) ? RAMP[breaks.filter((b) => x >= b).length] : '#f5f5f4');
  return { breaks, colorOf, min: v[0], max: v[v.length - 1] };
}

// ── overlay layers ────────────────────────────────────────────────────────
// geom: polygon | line | point. `site` layers come from site.json; the others load their file on first use.
// swatch: { kind: 'fill'|'line'|'dot'|'ring', color, line, dash } for the rail and legend.
const STOPS_MODE = { Bus: '#57564E', Trolley: '#16907A' };
const LINE_MODE = { Metro: '#D0553C', 'Regional Rail': '#393864', Trolley: '#16907A', Bus: '#57564E' };
const ZONING = {
  'Residential/Multi-Family/Residential Mixed-Use': '#EAD9A8',
  'Commercial/Commercial Mixed-Use': '#DDA196',
  'Industrial/Industrial Mixed-Use': '#A9A3C9',
  'Special Purpose': '#A9C7B8',
};
const LAND_USE = {
  Residential: '#EAD9A8', Commercial: '#DDA196', Industrial: '#A9A3C9', 'Civic and institutional': '#9DB4D6',
  'Culture and recreation': '#C3D7A4', 'Parks and open space': '#8FBF9A', Transportation: '#D6D3D1', Vacant: '#57564E', Water: '#A7CDE0',
};
export const KEYED = { zoning: ZONING, land_use: LAND_USE, transit_lines: LINE_MODE };

export const GROUPS = [
  { id: 'study', title: 'Study area', subtitle: 'Rings, walksheds, the neighborhood and its RCOs' },
  { id: 'places', title: 'Parks & corridors', subtitle: 'Areas from the community asset map' },
  { id: 'mobility', title: 'Mobility & safety', subtitle: 'Transit, bike network, crashes, school-zone safety' },
  { id: 'economy', title: 'Economy & land', subtitle: 'Businesses, zoning, land use, incentives, housing' },
];

export const LAYERS = [
  // study area
  { id: 'half_mile', group: 'study', label: 'Half-mile radius', site: 'half_mile', geom: 'line', defaultOn: true,
    style: { color: PAL.indigo, weight: 2.2, dashArray: '0.1 6', lineCap: 'round', fill: false }, swatch: { kind: 'line', color: PAL.indigo, dash: 'dots' },
    info: "The studio's half-mile study radius around the school parcel." },
  { id: 'one_mile', group: 'study', label: 'One-mile radius', site: 'one_mile', geom: 'line', defaultOn: true,
    style: { color: PAL.indigo, weight: 1.3, dashArray: '6 6', fill: false, opacity: 0.7 }, swatch: { kind: 'line', color: PAL.indigo, dash: 'dash' },
    info: 'One mile from the school: the reach of the community asset inventory.' },
  { id: 'walk', strokeOnly: true, group: 'study', label: '15-minute walk', file: 'walk', geom: 'polygon',
    style: (p) => ({ color: '#16907A', weight: 1.2, fillColor: '#16907A', fillOpacity: { 5: 0.22, 10: 0.13, 15: 0.07 }[p.minutes] ?? 0.08, opacity: 0.8 }),
    tooltip: (p) => `${p.minutes}-minute walk`, swatch: { kind: 'fill', color: '#16907A55', line: '#16907A' },
    info: 'Areas reachable on foot in 5, 10 and 15 minutes along the street and sidewalk network, at 80 m a minute (Transportation, 15-minute walk).' },
  { id: 'neighborhood', group: 'study', label: 'Neighborhood boundary', site: 'neighborhood', geom: 'line', defaultOn: true,
    style: { color: PAL.brick, weight: 2.4, fill: false, opacity: 0.9 }, swatch: { kind: 'line', color: PAL.brick },
    info: "The studio's neighborhood boundary for this school." },
  { id: 'study_tracts', group: 'study', label: 'Study census tracts', file: 'tracts', geom: 'polygon', filter: (p) => p.study,
    style: { color: PAL.indigo, weight: 1.2, fill: true, fillOpacity: 0, opacity: 0.9 }, hover: { fillOpacity: 0.1, fillColor: PAL.indigo },
    tooltip: (p) => `Census tract ${p.name}${p.share != null ? ` · ${Math.round(p.share * 100)}% of residents in the half mile` : ''}`,
    swatch: { kind: 'fill', color: 'transparent', line: PAL.indigo }, clickTract: true,
    info: 'The census tracts that make up the study area (2020 tracts). Click one for its profile.' },
  { id: 'rco_covers', strokeOnly: true, group: 'study', label: 'RCOs covering the site', file: 'rco', geom: 'polygon', filter: (p) => p.covers, defaultOn: true,
    style: { color: PAL.indigo, weight: 1.6, fillColor: PAL.indigo, fillOpacity: 0.03 }, hover: { weight: 3, fillOpacity: 0.1 },
    tooltip: (p) => p.name, popup: (p) => rcoPopup(p), swatch: { kind: 'fill', color: '#39386410', line: PAL.indigo },
    info: 'Registered Community Organizations whose boundary contains the school. Developers must meet with them on zoning applications.' },
  { id: 'rco_other', strokeOnly: true, group: 'study', label: 'Other RCOs reaching the half mile', file: 'rco', geom: 'polygon', filter: (p) => !p.covers,
    style: { color: '#7776a3', weight: 1.4, dashArray: '5 4', fillColor: PAL.lavender, fillOpacity: 0.03 }, hover: { weight: 2.6, fillOpacity: 0.12 },
    tooltip: (p) => p.name, popup: (p) => rcoPopup(p), swatch: { kind: 'fill', color: '#C9CCDF33', line: '#7776a3', dash: 'dash' },
    info: 'RCOs and wards whose boundary reaches the half mile but not the school itself.' },

  // parks & corridors
  { id: 'parks', group: 'places', label: 'Parks', file: 'parks', geom: 'polygon', defaultOn: true,
    style: { color: PAL.sage, weight: 0.8, fillColor: '#A9C7B8', fillOpacity: 0.55 }, hover: { fillOpacity: 0.75 },
    tooltip: (p) => p.name, popup: (p) => popupHtml({ title: p.name, kind: 'Park', lines: [p.acres ? `${p.acres.toLocaleString('en-US')} acres` : ''], source: 'Philadelphia Parks & Recreation' }),
    swatch: { kind: 'fill', color: '#A9C7B8', line: PAL.sage }, info: 'Parks & Recreation properties within one mile.' },
  { id: 'corridors', group: 'places', label: 'Commercial corridors', file: 'corridors', geom: 'polygon', defaultOn: true,
    style: { color: PAL.terracotta, weight: 1, fillColor: PAL.blush, fillOpacity: 0.45 }, hover: { fillOpacity: 0.65 },
    tooltip: (p) => p.name,
    popup: (p) => popupHtml({ title: p.name, kind: `Commercial corridor${p.type ? ` · type ${esc(p.type)}` : ''}`,
      lines: [p.storefronts != null ? `${fmtInt(p.storefronts)} storefronts${p.vacant != null ? `, ${fmtInt(p.vacant)} vacant` : ''}${p.year ? ` (${p.year} survey)` : ''}` : '', p.stage ? `Stage ${esc(p.stage)}` : ''],
      source: 'Philadelphia City Planning Commission' }),
    swatch: { kind: 'fill', color: PAL.blush, line: PAL.terracotta }, info: 'City Planning Commission commercial corridors, with their storefront and vacancy survey.' },
  { id: 'bids', strokeOnly: true, group: 'places', label: 'Business improvement districts', file: 'bids', geom: 'polygon',
    style: { color: PAL.muted, weight: 1.6, fillColor: PAL.stone, fillOpacity: 0.15 }, tooltip: (p) => p.name,
    popup: (p) => popupHtml({ title: p.name, kind: 'Business improvement district', lines: [esc(p.phone), link(p.website)], source: 'City of Philadelphia, Department of Commerce' }),
    swatch: { kind: 'fill', color: '#C6C4AF55', line: PAL.muted }, info: 'Special services districts funded by local property owners.' },

  // mobility & safety
  { id: 'transit_lines', group: 'mobility', label: 'Rail, metro & trolley lines', file: 'transit_lines', geom: 'line', defaultOn: true,
    style: (p) => ({ color: LINE_MODE[p.mode] || PAL.ink2, weight: p.mode === 'Regional Rail' ? 3 : 3.5, opacity: 0.85, dashArray: p.mode === 'Regional Rail' ? '8 4' : null }),
    hover: { weight: 6 }, tooltip: (p) => `${p.route} · ${p.mode}`, swatch: { kind: 'line', color: LINE_MODE.Metro },
    keyed: 'transit_lines', info: 'SEPTA metro, trolley and Regional Rail routes near the school (GTFS).' },
  { id: 'transit_stops', group: 'mobility', label: 'Stops near the school', file: 'transit_stops', geom: 'point', defaultOn: true,
    point: (p) => ({ radius: 3 + Math.sqrt(p.departures || 0) / 2.2, color: '#fff', weight: 1.5, fillColor: STOPS_MODE[p.mode] || PAL.ink2, fillOpacity: 0.95 }),
    tooltip: (p) => `${p.name} · ${p.departures ?? '?'} weekday departures`,
    popup: (p) => popupHtml({ title: p.name, kind: `${p.mode} stop`, lines: [
      p.departures != null ? `<b>${fmtInt(p.departures)}</b> weekday departures on ${p.routes} route${p.routes === 1 ? '' : 's'}` : '',
      p.feet != null ? `${fmtInt(p.feet)} ft walk from the school` : '',
      p.shelter != null ? (p.shelter ? 'Bus shelter within 100 ft' : 'No shelter within 100 ft') : '',
      p.accessible ? `Wheelchair accessible: ${esc(p.accessible)}` : ''], source: 'SEPTA GTFS; City bus shelters' }),
    swatch: { kind: 'dot', color: '#57564E' }, info: 'Bus and trolley stops within a short walk; dot size grows with weekday departures.' },
  { id: 'bike_lanes', group: 'mobility', label: 'Bike lanes', file: 'bike_lanes', geom: 'line',
    style: (p) => ({ color: '#16907A', weight: p.kind === 'Separated bike lane' ? 3.5 : 2.2, opacity: 0.9, dashArray: p.kind === 'Shared lane marking' ? '2 5' : null }),
    tooltip: (p) => p.kind, swatch: { kind: 'line', color: '#16907A' }, info: 'Separated (thick), painted (thin) and shared-lane (dotted) bike facilities.' },
  { id: 'bike_share', group: 'mobility', label: 'Indego bike share', file: 'bike_share', geom: 'point',
    point: () => ({ radius: 4.5, color: '#fff', weight: 1.5, fillColor: '#16907A', fillOpacity: 1 }),
    tooltip: (p) => `${p.name} · ${p.docks} docks`, swatch: { kind: 'dot', color: '#16907A' }, info: 'Indego stations and their dock counts.' },
  { id: 'hin', group: 'mobility', label: 'High Injury Network', file: 'hin', geom: 'line',
    style: { color: '#D0553C', weight: 5, opacity: 0.45, lineCap: 'round' }, hover: { opacity: 0.8 }, tooltip: (p) => `${p.street} · High Injury Network`,
    swatch: { kind: 'line', color: '#D0553C' }, info: "Vision Zero's High Injury Network: the 12% of streets where 80% of traffic deaths and serious injuries happen." },
  { id: 'crashes_ksi', group: 'mobility', label: 'Fatal & serious-injury crashes', file: 'crashes', geom: 'point', filter: (p) => p.ksi,
    point: (p) => ({ radius: p.killed ? 5.5 : 4, color: '#fff', weight: 1.2, fillColor: PAL.brick, fillOpacity: 0.95 }),
    tooltip: (p) => `${p.year} · ${p.killed ? `${p.killed} killed` : ''}${p.killed && p.serious ? ', ' : ''}${p.serious ? `${p.serious} seriously injured` : ''}${p.ped ? ' · pedestrian' : ''}${p.bike ? ' · cyclist' : ''}`,
    swatch: { kind: 'dot', color: PAL.brick }, info: 'Crashes where someone was killed or seriously injured (KSI), 2021–2025 (PennDOT).' },
  { id: 'crashes_all', group: 'mobility', label: 'All reported crashes', file: 'crashes', geom: 'point', filter: (p) => !p.ksi, canvas: true, interactive: false,
    point: (p) => ({ radius: 2.4, color: p.ped || p.bike ? '#D0553C' : '#8C8A7C', weight: 0, fillColor: p.ped || p.bike ? '#D0553C' : '#8C8A7C', fillOpacity: 0.45 }),
    tooltip: (p) => `${p.year} crash${p.ped ? ' · pedestrian' : ''}${p.bike ? ' · cyclist' : ''}`,
    swatch: { kind: 'dot', color: '#8C8A7C' }, info: 'Every other reportable crash 2021–2025, as a density of dots; pedestrian and cyclist crashes in red.' },
  { id: 'crossing_guards', group: 'mobility', label: 'Crossing guards', file: 'crossing_guards', geom: 'point',
    point: () => ({ radius: 3.6, color: '#fff', weight: 1.2, fillColor: '#D99A1E', fillOpacity: 1 }), tooltip: (p) => `Crossing guard · ${p.name}`,
    swatch: { kind: 'dot', color: '#D99A1E' }, info: 'Philadelphia Police crossing guard posts.' },
  { id: 'speed_cameras', group: 'mobility', label: 'Speed cameras', file: 'speed_cameras', geom: 'mixed',
    style: { color: '#9A57A6', weight: 4, opacity: 0.8 }, point: () => ({ radius: 5, color: '#fff', weight: 1.5, fillColor: '#9A57A6', fillOpacity: 1 }),
    tooltip: (p) => `${p.kind} · ${p.status}`, swatch: { kind: 'dot', color: '#9A57A6' }, info: 'School-zone speed cameras and speed-camera corridors (existing and upcoming).' },
  { id: 'curb_ramps', group: 'mobility', label: 'Missing curb ramps', file: 'curb_ramps', geom: 'point',
    point: () => ({ radius: 2.6, color: PAL.brick, weight: 1.2, fillColor: '#fff', fillOpacity: 1 }), tooltip: () => 'Missing curb ramp',
    swatch: { kind: 'ring', color: PAL.brick }, info: "Corners without a curb ramp in the City's curb ramp survey." },

  // economy & land
  { id: 'businesses', group: 'economy', label: 'Licensed businesses', file: 'businesses', geom: 'point',
    point: () => ({ radius: 3.4, color: '#fff', weight: 1, fillColor: PAL.ochre, fillOpacity: 0.9 }), tooltip: (p) => p.name,
    popup: (p) => popupHtml({ title: p.name, kind: p.kind, lines: [esc(p.address), esc(p.license)], source: 'City of Philadelphia, L&I business licenses' }),
    swatch: { kind: 'dot', color: PAL.ochre }, info: 'Food stores, restaurants and take-out, child care, auto businesses and others with an active license.' },
  { id: 'zoning', group: 'economy', label: 'Zoning', file: 'zoning', geom: 'polygon',
    style: (p) => ({ color: '#ffffff', weight: 0.5, fillColor: ZONING[p.group] || '#e7e5e4', fillOpacity: 0.6 }), hover: { weight: 2, color: PAL.ink },
    tooltip: (p) => `${p.code} · ${p.group}`, keyed: 'zoning', swatch: { kind: 'fill', color: ZONING['Commercial/Commercial Mixed-Use'] },
    info: 'Base zoning districts (Philadelphia Zoning Code). Hover a lot for its district.' },
  { id: 'land_use', group: 'economy', label: 'Land use', file: 'land_use', geom: 'polygon', interactive: false,
    style: (p) => ({ color: LAND_USE[p.use] || '#e7e5e4', weight: 0, fillColor: LAND_USE[p.use] || '#e7e5e4', fillOpacity: 0.62 }),
    keyed: 'land_use', swatch: { kind: 'fill', color: LAND_USE.Residential }, info: "City Planning's land use by lot, grouped into nine uses. Vacant land is dark." },
  { id: 'incentives', strokeOnly: true, group: 'economy', label: 'Opportunity zones & redevelopment areas', file: 'incentives', geom: 'polygon',
    style: (p) => p.layer === 'Opportunity Zone'
      ? { color: PAL.ochre, weight: 2, dashArray: '6 4', fillColor: '#D99A1E', fillOpacity: 0.08 }
      : { color: '#9A57A6', weight: 1.4, fillColor: '#9A57A6', fillOpacity: 0.06 },
    hover: { fillOpacity: 0.2 }, tooltip: (p) => `${p.layer}${p.name ? ` · ${p.name}` : ''}`,
    swatch: { kind: 'fill', color: '#D99A1E22', line: PAL.ochre, dash: 'dash' }, info: 'Federal Opportunity Zones (dashed, ochre) and certified redevelopment areas (plum).' },
  { id: 'affordable_housing', group: 'economy', label: 'Affordable housing', file: 'affordable_housing', geom: 'point',
    point: (p) => ({ radius: 3.5 + Math.sqrt(p.units || 1) / 2, color: '#fff', weight: 1.4, fillColor: '#9A57A6', fillOpacity: 0.9 }),
    tooltip: (p) => `${p.name} · ${p.units ?? '?'} units`,
    popup: (p) => popupHtml({ title: p.name, kind: `Affordable housing · ${p.status || ''}`, lines: [p.units ? `${fmtInt(p.units)} units` : '', p.year ? `Completed FY ${p.year}` : ''], source: 'Division of Housing and Community Development' }),
    swatch: { kind: 'dot', color: '#9A57A6' }, info: 'City-supported affordable housing developments; dot size grows with units.' },
  { id: 'storefront_grants', group: 'economy', label: 'Storefront grants', file: 'storefront_grants', geom: 'point',
    point: () => ({ radius: 3.6, color: '#fff', weight: 1.2, fillColor: '#D0553C', fillOpacity: 0.9 }),
    tooltip: (p) => `${p.name} · FY${p.year}${p.amount ? ` · ${fmtMoney(p.amount)}` : ''}`,
    swatch: { kind: 'dot', color: '#D0553C' }, info: 'Commerce Department storefront improvement grants by business and fiscal year.' },
  { id: 'food_access', group: 'economy', label: 'Low food access', file: 'food_access', geom: 'polygon', filter: (p) => p.access && p.access !== 'Moderate or High Access',
    style: (p) => ({ color: PAL.brick, weight: 0.8, fillColor: PAL.terracotta, fillOpacity: p.access === 'No Access' ? 0.5 : 0.3 }),
    tooltip: (p) => `${p.access} · ${p.hpss ?? 0} high-produce vs ${p.lpss ?? 0} low-produce stores${p.supermarket === 'No' ? ' · no supermarket' : ''}`,
    swatch: { kind: 'fill', color: '#D7826D55', line: PAL.brick }, info: "Block groups the Health Department rates as low or no access to high-produce supply stores." },
];
export const LAYER = Object.fromEntries(LAYERS.map((l) => [l.id, l]));

function rcoPopup(p) {
  return popupHtml({
    title: p.name,
    kind: `Registered community organization${p.type ? ` · ${p.type}` : ''}${p.cdc ? ' · CDC' : ''}`,
    lines: [p.covers ? '<b>Covers the school site</b>' : '', p.meets ? `Meets: ${esc(p.meets)}` : '', link(p.website), p.expires ? `Registration through ${esc(p.expires)}` : ''],
    source: 'City of Philadelphia, RCO registry',
  });
}
export { rcoPopup };
