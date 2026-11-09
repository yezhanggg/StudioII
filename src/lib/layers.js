/**
 * What the map can show. Community assets are the core: 18 categories in 5 families, collected from
 * official sources and OpenStreetMap (scripts/fetch, documented in public/data/sources.json). Around them, a
 * short list of context layers. The map documents what exists; it recommends nothing.
 *
 * Context layer scope:  'site'   sites.json (catchment, neighborhood), coloured by school
 *                       'school' public/data/<school>/<file>.json, merged across the schools on the map
 *                       'ctx'    public/data/ctx/<file>.json, the area around all six
 *                       'radius' drawn in the browser from the radius slider
 */

export const PAL = {
  lavender: '#C9CCDF', stone: '#C6C4AF', cream: '#EFE2D1', mist: '#C8D7D0', sage: '#659075', blush: '#DDA196',
  terracotta: '#D7826D', brick: '#944131', pine: '#3F746A', indigo: '#393864', ochre: '#BE731F',
  ink: '#1E1E1C', ink2: '#57564E', muted: '#8C8A7C',
};

// Five groups a first-time reader can follow: the four the studio asked for, plus everything else, off at
// first. Colours are the studio's hues at screen strength (dataviz validator: all checks pass); every type also
// has its own white glyph, so nothing rests on colour alone.
export const ASSET_GROUPS = [
  { id: 'food', label: 'Food', examples: 'Supermarkets, grocery stores, farmers markets, food pantries', color: '#16907A', on: true },
  { id: 'health', label: 'Health', examples: 'Pharmacies, community health centers, clinics, hospitals', color: '#D0553C', on: true },
  { id: 'learning', label: 'Children & learning', examples: 'Schools, child care, libraries, after-school programs', color: '#3F5FBF', on: true },
  { id: 'community', label: 'Community & recreation', examples: 'Parks, playgrounds, recreation centers, senior centers', color: '#D99A1E', on: true },
  { id: 'more', label: 'More places', examples: 'Places of worship, community groups, services, arts, history', color: '#9A57A6', on: false },
];
export const GROUP = Object.fromEntries(ASSET_GROUPS.map((g) => [g.id, g]));

const I = {
  cart: 'M3 4h2.2l2.3 10.5h10.2L20 7.5H6.4 M9.5 19.5h.01 M16.5 19.5h.01',
  stall: 'M3.5 9.5h17 M4.5 9.5 6 5h12l1.5 4.5 M5.5 9.5v10h13v-10 M9.5 19.5v-5h5v5',
  food: 'M7 2.5v7a2 2 0 0 0 4 0v-7 M9 9.5v12 M17 21.5V2.5c-2 0-3.5 3-3.5 6.5s1.5 4 3.5 4',
  sprout: 'M12 21v-8 M12 13c0-4-3-6.5-7.5-6.5 0 4 3 6.5 7.5 6.5Z M12 11c0-3.5 2.5-6.5 7-6.5 0 3.5-2.5 6.5-7 6.5Z',
  pill: 'M10.5 20.5a5 5 0 0 1-7-7l6-6a5 5 0 0 1 7 7Z M7 10.5l6.5 6.5',
  plus: 'M12 5v14 M5 12h14',
  steth: 'M6 3v5a4 4 0 0 0 8 0V3 M10 12v3a4.5 4.5 0 0 0 9 0v-2 M19 13a1.8 1.8 0 1 0 0-.01',
  hospital: 'M4.5 3.5h15v17h-15Z M9.5 8v8 M14.5 8v8 M9.5 12h5',
  schoolhouse: 'M4 21V10l8-6 8 6v11 M9.5 21v-5.5h5V21 M12 4V1.8',
  bell: 'M5 21V10l7-5 7 5v11 M12 9v.01 M9 21v-4h6v4 M3 21h18',
  child: 'M12 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z M8 21l1.5-7.5h5L16 21 M6.5 11.5 9.5 10h5l3 1.5',
  book: 'M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5v-15Z M4 19.5A1.5 1.5 0 0 0 5.5 21H20',
  star: 'M12 3.2l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.6l-5.3 2.9 1.1-5.9-4.4-4.1 6-.8Z',
  cap: 'M2 9.5 12 5l10 4.5L12 14 2 9.5Z M6 11.5V16c3.5 2.5 8.5 2.5 12 0v-4.5 M21.5 9.8v5.5',
  tree: 'M12 2.5 18 11h-3.5l4 6h-13l4-6H6l6-8.5Z M12 17v4.5',
  swing: 'M4 21V4h16v17 M8.5 4v8 M15.5 4v8 M7.5 12h9',
  wave: 'M3 15.5c2 0 2-1.5 4.5-1.5S10 15.5 12 15.5s2-1.5 4.5-1.5 2.5 1.5 4.5 1.5 M3 19.5c2 0 2-1.5 4.5-1.5S10 19.5 12 19.5s2-1.5 4.5-1.5 2.5 1.5 4.5 1.5 M8 12V5.5a2 2 0 0 1 4 0 M16 12V5.5',
  ball: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M3.5 10c3.5 1 13.5 1 17 0 M3.5 14c3.5-1 13.5-1 17 0 M12 3v18',
  heart: 'M12 20s-7.5-4.6-7.5-10.2A4 4 0 0 1 12 7.6a4 4 0 0 1 7.5 2.2C19.5 15.4 12 20 12 20Z',
  worship: 'M12 2v5 M9.5 4.5h5 M5.5 21.5v-9L12 7l6.5 5.5v9H5.5Z M10 21.5V17h4v4.5',
  people: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5 M16 5.2a3 3 0 0 1 0 5.6 M18 14.6c2 .7 3 2.6 3 5.4',
  home: 'M3.5 11.5 12 4l8.5 7.5 M6 9.5V20h12V9.5 M12 17.5s-3-1.8-3-3.8a1.6 1.6 0 0 1 3-.7 1.6 1.6 0 0 1 3 .7c0 2-3 3.8-3 3.8Z',
  palette: 'M12 3a9 9 0 1 0 0 18c1.1 0 1.8-.8 1.8-1.7 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8.1-9-8.1Z M7.5 12h.01 M9.5 7.5h.01 M14.5 7.5h.01',
  columns: 'M3 9 12 4l9 5 M5.5 9.5v8.5 M10 9.5v8.5 M14 9.5v8.5 M18.5 9.5v8.5 M3 20.5h18',
  shield: 'M12 3 19.5 6v5.5c0 4.7-3.2 8-7.5 9.5-4.3-1.5-7.5-4.8-7.5-9.5V6L12 3Z',
  briefcase: 'M3.5 8h17v11.5h-17Z M9 8V5.2h6V8 M3.5 13h17',
  dots: 'M6 12h.01 M12 12h.01 M18 12h.01',
};
export const ICONS = I;

export const TYPES = [
  { id: 'grocery', group: 'food', label: 'Supermarkets & grocery stores', icon: 'cart', info: 'Supermarkets and grocery stores, from USDA SNAP retailers and OpenStreetMap. Many "grocery stores" are small corner stores.' },
  { id: 'market', group: 'food', label: 'Farmers markets', icon: 'stall', info: 'Farmers markets and produce vendors. Most are seasonal.' },
  { id: 'meals', group: 'food', label: 'Food pantries & free meals', icon: 'food', info: 'Food pantries, free meal sites, free grocery sites and community fridges.' },
  { id: 'garden', group: 'food', label: 'Community gardens & farms', icon: 'sprout', info: 'Community gardens and urban farms.' },
  { id: 'pharmacy', group: 'health', label: 'Pharmacies', icon: 'pill', info: 'Drugstores and pharmacies. Some chain stores have closed recently.' },
  { id: 'health_center', group: 'health', label: 'Community health centers', icon: 'steth', info: 'City health centers and federally funded community health centers, which see patients whatever they can pay.' },
  { id: 'clinic', group: 'health', label: 'Clinics & doctors', icon: 'plus', info: 'Clinics, urgent care, dentists, doctors and outpatient mental health.' },
  { id: 'hospital', group: 'health', label: 'Hospitals', icon: 'hospital', info: 'Hospitals.' },
  { id: 'public_school', group: 'learning', label: 'Public & charter schools', icon: 'schoolhouse', info: 'School District and charter schools.' },
  { id: 'private_school', group: 'learning', label: 'Private & Catholic schools', icon: 'bell', info: 'Private, Catholic and other independent schools.' },
  { id: 'childcare', group: 'learning', label: 'Child care & pre-K', icon: 'child', info: 'Licensed child care centers and homes, pre-K and Head Start.' },
  { id: 'library', group: 'learning', label: 'Libraries', icon: 'book', info: 'Free Library branches and other public libraries.' },
  { id: 'youth', group: 'learning', label: 'After-school & youth programs', icon: 'star', info: 'After-school programs, youth centers, PAL centers, Ys and Boys & Girls Clubs.' },
  { id: 'college', group: 'learning', label: 'Colleges', icon: 'cap', info: 'Colleges, universities and community college sites.' },
  { id: 'park', group: 'community', label: 'Parks', icon: 'tree', info: 'City parks, squares and natural areas, and other parks.' },
  { id: 'playground', group: 'community', label: 'Playgrounds & spraygrounds', icon: 'swing', info: 'Playgrounds, spraygrounds and sprinklers.' },
  { id: 'rec', group: 'community', label: 'Recreation centers & pools', icon: 'wave', info: 'Parks & Recreation recreation centers and pools.' },
  { id: 'sports', group: 'community', label: 'Sports fields & courts', icon: 'ball', info: 'Ball fields, basketball and tennis courts, tracks.' },
  { id: 'senior', group: 'community', label: 'Senior centers', icon: 'heart', info: 'Senior centers, older adult centers and adult day programs.' },
  { id: 'worship', group: 'more', label: 'Places of worship', icon: 'worship', info: 'Churches, mosques, synagogues and other places of worship.' },
  { id: 'groups', group: 'more', label: 'Community groups', icon: 'people', info: 'Registered Community Organizations, community development corporations, neighborhood advisory committees, park friends groups.' },
  { id: 'services', group: 'more', label: 'Help & social services', icon: 'home', info: 'WIC, energy assistance, benefits and housing counseling offices.' },
  { id: 'arts', group: 'more', label: 'Arts & culture', icon: 'palette', info: 'Museums, theaters, arts centers, murals and public art.' },
  { id: 'history', group: 'more', label: 'Historic places', icon: 'columns', info: 'Places on the Philadelphia or National Register, and state historical markers.' },
  { id: 'safety', group: 'more', label: 'Police, fire & polling places', icon: 'shield', info: 'Police district stations, fire stations and polling places.' },
  { id: 'money', group: 'more', label: 'Banks & job centers', icon: 'briefcase', info: 'Banks, credit unions and job centers.' },
];
export const TYPE = Object.fromEntries(TYPES.map((t) => [t.id, { ...t, color: GROUP[t.group].color }]));

export const RAMP = ['#EDEDF5', '#C9CCDF', '#9A9CC2', '#686A9C', '#393864'];

// ── formatting ────────────────────────────────────────────────────────────
const ok = (v) => typeof v === 'number' && Number.isFinite(v);
export const fmtInt = (v) => (ok(v) ? Math.round(v).toLocaleString('en-US') : 'n/a');
export const fmtMoney = (v) => (ok(v) ? `$${Math.round(v).toLocaleString('en-US')}` : 'n/a');
export const fmtMoneyK = (v) => (ok(v) ? (v >= 1000 ? `$${Math.round(v / 1000)}K` : `$${Math.round(v)}`) : 'n/a');
export const fmtPct = (v, dp = 0) => (ok(v) ? `${(v * 100).toFixed(dp)}%` : 'n/a');
export const fmtMiles = (mi) => (mi < 0.19 ? `${Math.round(mi * 5280).toLocaleString('en-US')} ft` : `${mi.toFixed(2)} mi`);
const FRAC = { 0.25: '¼', 0.5: '½', 0.75: '¾' };
export const fmtRadius = (r) => (FRAC[r] ? `${FRAC[r]} mi` : `${Number.isInteger(r) ? r : r.toFixed(2)} mi`);
export const walkMinutes = (mi) => Math.max(1, Math.round((mi * 1609.344) / 80)); // the studio's 80 m/min pace

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/** A usable link for a website field, or '' (scheme-less addresses get https://; anything else is dropped). */
export const href = (u) => (!u ? '' : /^https?:\/\//i.test(u) ? u : /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(String(u).trim()) ? `https://${String(u).trim()}` : '');
const link = (u) => {
  const h = href(u);
  return h ? `<a href="${esc(h)}" target="_blank" rel="noopener noreferrer">${esc(String(u).replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, ''))}</a>` : '';
};
export function popupHtml({ title, kind, lines = [], source, extra = '' }) {
  const body = lines.filter(Boolean).map((l) => `<div>${l}</div>`).join('');
  return `<div class="pp"><div class="pp-t">${esc(title)}</div>${kind ? `<div class="pp-k">${esc(kind)}</div>` : ''}${body ? `<div class="pp-b">${body}</div>` : ''}${extra}${source ? `<div class="pp-s">Source: ${esc(source)}</div>` : ''}</div>`;
}

// ── a place's own links, as small icon buttons ────────────────────────────
export const LINK_ICONS = {
  website: { label: 'Website', svg: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.2 3.4 8.5s-1.1 6.1-3.4 8.5c-2.3-2.4-3.4-5.2-3.4-8.5S9.7 5.9 12 3.5Z" fill="none" stroke="currentColor" stroke-width="1.8"/>' },
  instagram: { label: 'Instagram', svg: '<rect x="3.5" y="3.5" width="17" height="17" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3.9" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.2" cy="6.8" r="1.15" fill="currentColor"/>' },
  facebook: { label: 'Facebook', svg: '<path d="M13.6 20.5v-7h2.4l.4-2.9h-2.8V8.8c0-.8.3-1.4 1.4-1.4h1.5V4.8c-.3 0-1.2-.1-2.2-.1-2.2 0-3.6 1.3-3.6 3.8v2.1H8.3v2.9h2.4v7h2.9Z" fill="currentColor"/>' },
  maps: { label: 'Open in Google Maps', svg: '<path d="M12 20.5s-6.5-5.6-6.5-10.6a6.5 6.5 0 0 1 13 0c0 5-6.5 10.6-6.5 10.6Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="9.9" r="2.3" fill="none" stroke="currentColor" stroke-width="1.8"/>' },
  phone: { label: 'Call', svg: '<path d="M6.6 4h2.6l1.4 3.9-1.9 1.3a10.4 10.4 0 0 0 6.1 6.1l1.3-1.9 3.9 1.4v2.6A1.6 1.6 0 0 1 18.4 19 14.4 14.4 0 0 1 5 5.6 1.6 1.6 0 0 1 6.6 4Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>' },
};
const HOME_CARE = /family child care home|group child care home/i;   // private homes: no map search
export function placeLinks(p, { maps = true } = {}) {
  const out = [];
  for (const k of ['website', 'instagram', 'facebook']) if (href(p[k])) out.push({ kind: k, url: href(p[k]) });
  if (maps && p.name && !HOME_CARE.test(p.kind || '')) {
    const q = [p.name, p.address, p.address && /philadelphia/i.test(p.address) ? '' : 'Philadelphia, PA'].filter(Boolean).join(', ');
    out.push({ kind: 'maps', url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}` });
  }
  return out;
}
const telHref = (ph) => { const d = String(ph || '').replace(/\D/g, ''); return d.length >= 10 ? `tel:+1${d.slice(-10)}` : ''; };
export function linksHtml(p, opts) {
  const btn = ({ kind, url }) => `<a class="pp-ic" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="${LINK_ICONS[kind].label}" aria-label="${LINK_ICONS[kind].label}"><svg viewBox="0 0 24 24" aria-hidden="true">${LINK_ICONS[kind].svg}</svg></a>`;
  const icons = placeLinks(p, opts).map(btn).join('');
  const tel = telHref(p.phone);
  const phone = tel ? `<a class="pp-tel" href="${tel}"><svg viewBox="0 0 24 24" aria-hidden="true">${LINK_ICONS.phone.svg}</svg>${esc(p.phone)}</a>` : '';
  return icons || phone ? `<div class="pp-links">${icons}${phone}</div>` : '';
}

// RCOs with a boundary on the map (filled in by the map once schools.json loads), so a community group that is an
// RCO can offer to show its boundary
export const RCO_NAMES = new Set();
const rcoButton = (name) => (RCO_NAMES.has(name) ? `<button type="button" class="pp-act" data-rco="${esc(name)}">Show its boundary</button>` : '');

export const assetPopup = (p, sourceTitle) => popupHtml({
  title: p.name, kind: p.kind || TYPE[p.type]?.label,
  lines: [esc(p.detail), esc(p.address)], source: sourceTitle || p.source_id,
  extra: linksHtml(p) + (p.source_id === 'phl_rco_offices' ? rcoButton(p.name) : ''),
});

// ── census shading (ctx/tracts.json) ──────────────────────────────────────
export const MEASURES = [
  { id: 'income', label: 'Median household income', fmt: fmtMoney, legend: fmtMoneyK, profile: 'Median household income' },
  { id: 'poverty', label: 'Poverty rate', fmt: (v) => fmtPct(v), profile: 'Poverty rate' },
  { id: 'unemployment', label: 'Unemployment rate', fmt: (v) => fmtPct(v), profile: 'Unemployment rate' },
  { id: 'children', label: 'Children under 18', fmt: (v) => fmtPct(v) },
  { id: 'renter', label: 'Renter households', fmt: (v) => fmtPct(v), profile: 'Renter-occupied' },
  { id: 'home_value', label: 'Median home value', fmt: fmtMoney, legend: fmtMoneyK, profile: 'Median home value' },
  { id: 'bachelors', label: "Bachelor's degree or higher", fmt: (v) => fmtPct(v), profile: "Bachelor's degree or higher" },
];
export const MEASURE = Object.fromEntries(MEASURES.map((m) => [m.id, m]));

/** Five quantile classes over the city's tracts. */
export function quantiles(values) {
  const v = values.filter(ok).sort((a, b) => a - b);
  if (!v.length) return { breaks: [], colorOf: () => '#e7e5e4' };
  const q = (t) => v[Math.min(v.length - 1, Math.floor(t * v.length))];
  const breaks = [q(0.2), q(0.4), q(0.6), q(0.8)];
  const colorOf = (x) => (ok(x) ? RAMP[breaks.filter((b) => x >= b).length] : '#f5f5f4');
  return { breaks, colorOf, min: v[0], max: v[v.length - 1] };
}

// ── context layers (a short list) ─────────────────────────────────────────
const LINE_MODE = { Metro: '#D0553C', 'Regional Rail': '#393864', Trolley: '#16907A' };
const ZONING = {
  'Residential/Multi-Family/Residential Mixed-Use': '#EAD9A8', 'Commercial/Commercial Mixed-Use': '#DDA196',
  'Industrial/Industrial Mixed-Use': '#A9A3C9', 'Special Purpose': '#A9C7B8',
};
const LAND_USE = {
  Residential: '#EAD9A8', Commercial: '#DDA196', Industrial: '#A9A3C9', 'Civic and institutional': '#9DB4D6',
  'Culture and recreation': '#C3D7A4', 'Parks and open space': '#8FBF9A', Transportation: '#D6D3D1', Vacant: '#57564E', Water: '#A7CDE0',
};
const HOUSING = { 'Public housing': '#393864', 'Affordable housing': '#9A57A6', 'Tax credit housing': '#7776a3' };
export const KEYED = { zoning: ZONING, land_use: LAND_USE, transit_lines: LINE_MODE, housing: HOUSING };
export const KEY_FIELD = { zoning: 'group', land_use: 'use', transit_lines: 'mode', housing: 'program' };

export const rcoPopup = (p) => popupHtml({
  title: p.name,
  kind: `Registered Community Organization${p.type && p.type !== 'Other' ? ` · ${p.type}` : ''}${p.cdc ? ' · CDC' : ''}`,
  lines: [p.covers ? `<b>Its boundary covers the ${esc(p._short || 'school')} site</b>` : (p.miles != null ? `Boundary ${p.miles < 0.19 ? `${Math.round(p.miles * 5280)} ft` : `${p.miles.toFixed(2)} mi`} from ${esc(p._short || 'the school')}` : ''),
    p.meets ? `Meets: ${esc(p.meets)}` : '', p.expires ? `Registered through ${esc(p.expires)}` : ''],
  extra: linksHtml(p, { maps: false }),
  source: 'City of Philadelphia, RCO registry',
});

export const LAYERS = [
  { id: 'radius', scope: 'radius', label: 'Distance ring', caption: 'The distance you set, drawn around the school', basic: true, defaultOn: true,
    swatch: { kind: 'line', color: PAL.indigo, dash: 'dots' }, info: 'A ring at the radius you set, around each school on the map.' },
  { id: 'city', scope: 'ctx', file: 'city', label: 'Philadelphia boundary', caption: 'The city and county line', basic: true, geom: 'line', defaultOn: true, interactive: false,
    style: { color: '#8E9282', weight: 2, fill: false, opacity: 0.95 }, swatch: { kind: 'line', color: '#8E9282' },
    info: 'Philadelphia County, from the 2020 Census tracts merged into one outline.' },
  { id: 'catchment', scope: 'site', kind: 'catchment', label: 'School attendance area', caption: 'Where students living there are assigned to the school', basic: true, geom: 'polygon', defaultOn: true, strokeOnly: true,
    style: (p) => ({ color: p._color, weight: 2.2, dashArray: '9 5', fillColor: p._color, fillOpacity: 0.06, opacity: 0.95 }), hover: { fillOpacity: 0.15, weight: 3.2 },
    tooltip: (p) => `${p._short} attendance area · grades ${p.grades}`, swatch: { kind: 'fill', color: '#39386412', line: PAL.indigo, dash: 'dash' },
    info: "The School District's 2024 attendance boundary. Fitler, Robeson and AMY Northwest admit citywide and have none." },
  { id: 'walk', scope: 'school', file: 'walk', label: '15-minute walk', caption: 'How far you can walk in 5, 10 and 15 minutes', basic: true, geom: 'polygon', strokeOnly: true,
    style: (p) => ({ color: '#16907A', weight: 1.2, fillColor: '#16907A', fillOpacity: { 5: 0.2, 10: 0.12, 15: 0.06 }[p.minutes] ?? 0.08, opacity: 0.8 }),
    tooltip: (p) => `${p._short} · ${p.minutes}-minute walk`, swatch: { kind: 'fill', color: '#16907A55', line: '#16907A' },
    info: 'Reachable on foot in 5, 10 and 15 minutes along streets and paths, at 80 m a minute.' },
  { id: 'neighborhood', scope: 'site', kind: 'neighborhood', label: 'Neighborhood boundary', caption: 'The neighborhood the school is in', geom: 'line',
    style: (p) => ({ color: p._color, weight: 2.2, fill: false, opacity: 0.8 }), tooltip: (p) => `${p._short} neighborhood${p.source === 'azavea' ? ' (Azavea)' : ''}`,
    swatch: { kind: 'line', color: PAL.ink2 }, info: "The studio's boundary for Wagner and Blankenburg; the Azavea neighborhood for the other four." },
  { id: 'rco', scope: 'school', file: 'rco', label: 'RCO boundaries', basic: true, geom: 'polygon', strokeOnly: true, withinRadius: true,
    style: (p) => ({ color: PAL.indigo, weight: p.covers ? 2.4 : 1.3, opacity: p.covers ? 0.95 : 0.55, dashArray: p.covers ? null : '5 4', fillColor: PAL.indigo, fillOpacity: p.covers ? 0.04 : 0 }),
    hover: { weight: 3, opacity: 1, dashArray: null, fillOpacity: 0.08 },
    tooltip: (p) => p.name, popup: rcoPopup, swatch: { kind: 'line', color: PAL.indigo, dash: 'dash' },
    info: 'Registered Community Organizations whose boundary reaches the distance you set. They are consulted on zoning applications. Solid: covers the school site.' },
  { id: 'parks', scope: 'ctx', file: 'parks', label: 'Park land', caption: 'Land owned by Parks & Recreation', basic: true, geom: 'polygon', defaultOn: true,
    style: { color: PAL.sage, weight: 0.6, fillColor: '#A9C7B8', fillOpacity: 0.5 }, hover: { fillOpacity: 0.7 },
    tooltip: (p) => p.name, popup: (p) => popupHtml({ title: p.name, kind: 'Park', lines: [p.acres ? `${p.acres.toLocaleString('en-US')} acres` : ''], source: 'Philadelphia Parks & Recreation' }),
    swatch: { kind: 'fill', color: '#A9C7B8', line: PAL.sage }, info: 'Parks & Recreation property boundaries.' },
  { id: 'corridors', scope: 'ctx', file: 'corridors', label: 'Commercial corridors', caption: "The City's commercial corridors", basic: true, geom: 'polygon', defaultOn: true,
    style: { color: PAL.terracotta, weight: 1, fillColor: PAL.blush, fillOpacity: 0.4 }, hover: { fillOpacity: 0.6 }, tooltip: (p) => p.name,
    popup: (p) => popupHtml({ title: p.name, kind: 'Commercial corridor', lines: [p.storefronts != null ? `${fmtInt(p.storefronts)} storefronts${p.vacant != null ? `, ${fmtInt(p.vacant)} vacant` : ''}${p.year ? ` (${p.year} survey)` : ''}` : ''], source: 'Philadelphia City Planning Commission' }),
    swatch: { kind: 'fill', color: PAL.blush, line: PAL.terracotta }, info: 'City Planning Commission commercial corridors and their storefront survey.' },
  { id: 'transit_lines', scope: 'ctx', file: 'transit_lines', label: 'Train & trolley lines', caption: 'SEPTA rail, subway and trolley', basic: true, geom: 'line', filter: (p) => p.mode !== 'Bus',
    style: (p) => ({ color: LINE_MODE[p.mode] || PAL.ink2, weight: p.mode === 'Regional Rail' ? 3 : 3.5, opacity: 0.85, dashArray: p.mode === 'Regional Rail' ? '8 4' : null }),
    hover: { weight: 6 }, tooltip: (p) => `${p.route} · ${p.mode}${p.name && p.name !== p.route ? ` · ${p.name}` : ''}`, swatch: { kind: 'line', color: LINE_MODE.Metro },
    keyed: 'transit_lines', info: 'SEPTA metro, trolley and Regional Rail lines.' },
  { id: 'transit_stops', scope: 'ctx', file: 'transit_stops', label: 'Bus & trolley stops', caption: 'A bigger dot means more riders', basic: true, geom: 'point',
    point: (p) => ({ radius: 2.5 + Math.sqrt((p.ons || 0) + (p.offs || 0)) / 3.2, color: '#fff', weight: 1.2, fillColor: p.mode === 'Trolley' ? '#16907A' : '#57564E', fillOpacity: 0.9 }),
    tooltip: (p) => `${p.name} · ${fmtInt((p.ons || 0) + (p.offs || 0))} riders a weekday`,
    popup: (p) => popupHtml({ title: p.name, kind: `${p.mode} stop · route${String(p.routes).includes(',') ? 's' : ''} ${esc(p.routes)}`, lines: [`<b>${fmtInt(p.ons)}</b> boardings, <b>${fmtInt(p.offs)}</b> alightings on an average weekday`], source: 'SEPTA stop ridership, fall 2025' }),
    swatch: { kind: 'dot', color: '#57564E' }, info: 'Stops within ¾ mile of a school; size grows with weekday riders.' },
  { id: 'hin', scope: 'ctx', file: 'hin', label: 'Dangerous streets', caption: 'Streets with the most serious traffic crashes', geom: 'line',
    style: { color: '#D0553C', weight: 5, opacity: 0.4, lineCap: 'round' }, hover: { opacity: 0.8 }, tooltip: (p) => `${p.street} · one of the streets with the most serious crashes`,
    swatch: { kind: 'line', color: '#D0553C' }, info: "Vision Zero's streets with the most traffic deaths and serious injuries." },
  { id: 'housing', scope: 'ctx', file: 'housing', label: 'Public & affordable housing', caption: 'PHA, tax-credit and City-supported housing', geom: 'point',
    point: (p) => ({ radius: 3.5 + Math.sqrt(p.units || 1) / 2.2, color: '#fff', weight: 1.4, fillColor: HOUSING[p.program] || '#9A57A6', fillOpacity: 0.9 }),
    tooltip: (p) => `${p.name}${p.units ? ` · ${fmtInt(p.units)} units` : ''}`,
    popup: (p) => popupHtml({ title: p.name, kind: p.program, lines: [p.units ? `${fmtInt(p.units)} units` : '', esc(p.detail)], source: p.source }),
    keyed: 'housing', swatch: { kind: 'dot', color: '#9A57A6' }, info: 'PHA developments, tax-credit (LIHTC) properties and City-supported affordable housing; size grows with units.' },
  { id: 'vacant', scope: 'ctx', file: 'vacant', label: 'Vacant land', caption: 'Likely vacant lots; a ringed dot is publicly owned', geom: 'point',
    point: (p) => ({ radius: 2.6, color: p.public ? PAL.indigo : PAL.ink2, weight: 1, fillColor: p.public ? '#fff' : PAL.muted, fillOpacity: p.public ? 1 : 0.55 }),
    tooltip: (p) => `${p.address || 'Likely vacant lot'}${p.public ? ` · ${p.owner || 'publicly owned'}` : ''}${p.zoning ? ` · ${p.zoning}` : ''}`,
    swatch: { kind: 'ring', color: PAL.indigo }, info: 'Likely-vacant lots (City vacancy indicators) and Philadelphia Land Bank property; ringed dots are publicly owned.' },
  { id: 'zoning', scope: 'ctx', file: 'zoning', label: 'Zoning', caption: 'What the rules allow to be built', geom: 'polygon',
    style: (p) => ({ color: '#ffffff', weight: 0.5, fillColor: ZONING[p.group] || '#e7e5e4', fillOpacity: 0.6 }), hover: { weight: 2, color: PAL.ink },
    tooltip: (p) => `${p.code} · ${p.group}`, keyed: 'zoning', swatch: { kind: 'fill', color: ZONING['Commercial/Commercial Mixed-Use'] },
    info: 'Base zoning districts within a mile of a school. Hover a lot for its district.' },
  { id: 'land_use', scope: 'ctx', file: 'land_use', label: 'Land use', caption: 'How each lot is used today', geom: 'polygon', interactive: false,
    style: (p) => ({ color: LAND_USE[p.use] || '#e7e5e4', weight: 0, fillColor: LAND_USE[p.use] || '#e7e5e4', fillOpacity: 0.6 }),
    keyed: 'land_use', swatch: { kind: 'fill', color: LAND_USE.Residential }, info: "City Planning's land use by lot within a mile of a school, in nine uses." },
];
export const LAYER = Object.fromEntries(LAYERS.map((l) => [l.id, l]));
