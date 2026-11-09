/**
 * Leaflet layers, added imperatively inside react-leaflet's map so each layer controls its own pane,
 * style function, hover state and popup. Every component here renders nothing and cleans up on unmount.
 */
import { useEffect, useMemo } from 'react';
import { TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { TYPE, ICONS, esc, fmtInt, fmtMiles, walkMinutes, assetPopup, popupHtml, quantiles, MEASURE } from '../lib/layers';

// ── panes: stacking order of everything on the map ───────────────────────
const PANES = [
  ['choropleth', 340], ['areas', 380], ['lines', 420], ['labels', 460], ['points', 480], ['site', 640], ['assets', 650], ['sitelabel', 660], ['top', 700],
];
export function Panes() {
  const map = useMap();
  for (const [name, z] of PANES) {
    if (!map.getPane(name)) {
      const p = map.createPane(name);
      p.style.zIndex = String(z);
      if (name === 'labels') p.style.pointerEvents = 'none';
    }
  }
  return null;
}

export function MapBridge({ onReady }) {
  const map = useMap();
  useEffect(() => { onReady(map); if (import.meta.env.DEV) window.__map = map; }, [map, onReady]);
  return null;
}

/** Below zoom 14 the asset markers become small dots, so six schools' worth of places stays readable. */
export function ZoomClass() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const set = () => el.classList.toggle('z-low', map.getZoom() < 14);
    set();
    map.on('zoomend', set);
    return () => map.off('zoomend', set);
  }, [map]);
  return null;
}

// ── basemaps: Mapbox when a public token is set (VITE_MAPBOX_TOKEN), Esri otherwise ──────────
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || '';
const HAS_MAPBOX = MAPBOX_TOKEN.startsWith('pk.');
const mbx = (style) => `https://api.mapbox.com/styles/v1/mapbox/${style}/tiles/512/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`;
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
export const BASEMAPS = HAS_MAPBOX ? [
  { id: 'light', label: 'Light', base: mbx('light-v11'), mapbox: true },
  { id: 'streets', label: 'Streets', base: mbx('streets-v12'), mapbox: true },
  { id: 'satellite', label: 'Satellite', base: mbx('satellite-streets-v12'), mapbox: true },
] : [
  { id: 'light', label: 'Light', base: `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, maxNative: 16, labels: `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}` },
  { id: 'satellite', label: 'Satellite', base: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, labels: `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}` },
];
export function Basemap({ id }) {
  const bm = BASEMAPS.find((b) => b.id === id) || BASEMAPS[0];
  return (
    <>
      {bm.mapbox
        ? <TileLayer key={`b-${bm.id}`} url={bm.base} tileSize={512} zoomOffset={-1} maxZoom={20} maxNativeZoom={20} />
        : <TileLayer key={`b-${bm.id}`} url={bm.base} maxZoom={20} maxNativeZoom={bm.maxNative || 19} />}
      {bm.labels && <TileLayer key={`l-${bm.id}`} url={bm.labels} pane="labels" maxZoom={20} maxNativeZoom={bm.maxNative || 19} />}
    </>
  );
}

// ── distance to the nearest school on the map, for popups ─────────────────
/** schools: [{short, center}] → (latlng) => { mi, short } */
export function makeNearest(schools) {
  return (latlng) => {
    let best = null;
    for (const s of schools) {
      const mi = L.latLng(s.center).distanceTo(latlng) / 1609.344;
      if (!best || mi < best.mi) best = { mi, short: s.short };
    }
    return best;
  };
}
const distanceHtml = (latlng, nearest) => {
  const n = nearest?.(latlng);
  return n ? `<div class="pp-d">${fmtMiles(n.mi)} from ${esc(n.short)} · about ${walkMinutes(n.mi)} min walk in a straight line</div>` : '';
};
const withDistance = (html, latlng, nearest) => html.replace(/(<div class="pp-s">|<\/div>$)/, (m) => distanceHtml(latlng, nearest) + m);

// popups open clear of the left panel and the school panel on wide screens
const popupOpts = () => (window.innerWidth >= 900
  ? { maxWidth: 320, autoPanPaddingTopLeft: [350, 70], autoPanPaddingBottomRight: [400, 60] }
  : { maxWidth: 300, autoPanPadding: [16, 16] });

// ── a registry layer (layers.js) drawn from a FeatureCollection ───────────
export function GeoLayer({ def, data, nearest, onTract }) {
  const map = useMap();
  const pane = def.geom === 'point' ? 'points' : def.geom === 'line' || def.geom === 'mixed' ? 'lines' : 'areas';
  // SVG for anything clickable; a canvas over the panes below would swallow their clicks, so it is only for
  // thousands of dots that need to be seen and not clicked (`canvas: true`, `interactive: false`).
  const renderer = useMemo(() => (def.canvas ? L.canvas({ pane: 'points', padding: 0.3 }) : undefined), [def.canvas]);

  useEffect(() => {
    if (!data) return undefined;
    const features = def.filter ? data.features.filter((f) => def.filter(f.properties)) : data.features;
    const styleOf = (f) => ({
      ...((typeof def.style === 'function' ? def.style(f.properties) : def.style) || {}),
      // Large boundary overlays answer on their outline only, so the tracts and places inside stay clickable.
      ...(def.strokeOnly ? { className: 'stroke-only' } : null),
    });
    const interactive = def.interactive !== false;
    const layer = L.geoJSON({ type: 'FeatureCollection', features }, {
      pane,
      interactive,
      style: styleOf,
      pointToLayer: (f, ll) => L.circleMarker(ll, { ...(def.point ? def.point(f.properties) : { radius: 4 }), pane: 'points', renderer, interactive }),
      onEachFeature: (f, lyr) => {
        if (!interactive) return;
        const p = f.properties;
        const tip = def.tooltip ? def.tooltip(p) : null;
        if (tip) lyr.bindTooltip(esc(tip), { sticky: !lyr.getLatLng, direction: 'top', className: 'tt', offset: lyr.getLatLng ? [0, -6] : [0, -4] });
        if (!def.clickTract && (def.popup || tip)) {
          lyr.bindPopup(() => {
            const html = def.popup ? def.popup(p) : popupHtml({ title: tip });
            return lyr.getLatLng ? withDistance(html, lyr.getLatLng(), nearest) : html;
          }, popupOpts());
        }
        if (def.hover) {
          lyr.on('mouseover', () => lyr.setStyle?.(def.hover));
          lyr.on('mouseout', () => layer.resetStyle(lyr));
        }
        if (def.clickTract && onTract) lyr.on('click', () => onTract(p));
      },
    }).addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, def, data, pane, renderer, nearest, onTract]);
  return null;
}

// ── census tract shading (the whole city); a click shows the tract beside Philadelphia ──
const TRACT_ROWS = [['income', 'Median household income', 'Median household income'], ['poverty', 'Poverty rate', 'Poverty rate'],
  ['unemployment', 'Unemployment rate', 'Unemployment rate'], ['children', 'Children under 18', null], ['renter', 'Renter households', 'Renter-occupied']];
export function Choropleth({ data, measure, city }) {
  const map = useMap();
  const m = MEASURE[measure];
  const scale = useMemo(() => (data && m ? quantiles(data.features.map((f) => f.properties[m.id])) : null), [data, m]);
  useEffect(() => {
    if (!data || !m || !scale) return undefined;
    const base = (p) => ({ pane: 'choropleth', color: '#ffffff', weight: 0.7, opacity: 1, fillColor: scale.colorOf(p[m.id]), fillOpacity: 0.7 });
    const layer = L.geoJSON(data, {
      pane: 'choropleth',
      style: (f) => base(f.properties),
      onEachFeature: (f, lyr) => {
        const p = f.properties;
        lyr.bindTooltip(`<b>Tract ${esc(p.name)}</b><br>${esc(m.label)}: <b>${esc(m.fmt(p[m.id]))}</b>`, { sticky: true, className: 'tt', direction: 'top' });
        lyr.bindPopup(() => {
          const rows = TRACT_ROWS.map(([k, label, prof]) => {
            const mm = MEASURE[k];
            const c = prof && city?.[prof] ? mm.fmt(city[prof].city) : '';
            return `<tr><td>${esc(label)}</td><td class="n">${esc(mm.fmt(p[k]))}</td><td class="n c">${esc(c)}</td></tr>`;
          }).join('');
          return `<div class="pp"><div class="pp-t">Census tract ${esc(p.name)}</div><div class="pp-k">ACS 2020–2024 · ${fmtInt(p.pop)} residents</div><table class="pp-tbl"><tr><th></th><th>Tract</th><th>City</th></tr>${rows}</table><div class="pp-s">Source: US Census Bureau, American Community Survey 5-year</div></div>`;
        }, { maxWidth: 320 });
        lyr.on('mouseover', () => { lyr.setStyle({ weight: 2.5, color: '#1E1E1C' }); lyr.bringToFront(); });
        lyr.on('mouseout', () => lyr.setStyle(base(p)));
      },
    }).addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, data, m, scale, city]);
  return null;
}

// ── community assets: a white glyph on the family colour ──────────────────
const iconCache = new Map();
function assetIcon(type, near) {
  const key = `${type}|${near}`;
  if (!iconCache.has(key)) {
    const c = TYPE[type] || { color: '#57564E', icon: 'dots' };
    const size = near ? 24 : 20;
    iconCache.set(key, L.divIcon({
      className: 'am-wrap',
      html: `<div class="am${near ? '' : ' far'}" style="--c:${c.color}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[c.icon]}"/></svg></div>`,
      iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2], tooltipAnchor: [0, -size / 2],
    }));
  }
  return iconCache.get(key);
}

/** items: [{ lat, lng, p, near }] — already merged across schools and filtered */
export function AssetLayer({ items, nearest, sourceTitle = {} }) {
  const map = useMap();
  useEffect(() => {
    const group = L.layerGroup();
    for (const it of items) {
      const p = it.p;
      const mk = L.marker([it.lat, it.lng], { icon: assetIcon(p.type, it.near), pane: 'assets', riseOnHover: true, keyboard: true, title: p.name });
      mk.bindTooltip(`<b>${esc(p.name)}</b><br><span class="tt-k">${esc(p.kind || TYPE[p.type]?.label || '')}</span>`, { direction: 'top', className: 'tt' });
      mk.bindPopup(() => withDistance(assetPopup(p, sourceTitle[p.source_id]), mk.getLatLng(), nearest), popupOpts());
      group.addLayer(mk);
    }
    group.addTo(map);
    return () => { map.removeLayer(group); };
  }, [map, items, nearest, sourceTitle]);
  return null;
}

// ── the schools: parcel and name in the school's colour ───────────────────
export function SiteLayer({ schools, parcels, focus, onFocus }) {
  const map = useMap();
  useEffect(() => {
    const g = L.layerGroup().addTo(map);
    for (const s of schools) {
      const parcel = parcels[s.slug];
      const on = focus === s.slug;
      if (parcel) {
        // the selected school's lot glows: two soft strokes in its color under a crisp outline
        if (on) {
          L.geoJSON(parcel, { pane: 'site', interactive: false, style: { color: s.color, weight: 18, opacity: 0.14, fill: false, lineJoin: 'round' } }).addTo(g);
          L.geoJSON(parcel, { pane: 'site', interactive: false, style: { color: s.color, weight: 7, opacity: 0.32, fill: false, lineJoin: 'round' } }).addTo(g);
        }
        const poly = L.geoJSON(parcel, { pane: 'site', style: on ? { color: '#ffffff', weight: 2.5, fillColor: s.color, fillOpacity: 1 } : { color: '#ffffff', weight: 1.5, fillColor: s.color, fillOpacity: 0.85 } }).addTo(g);
        poly.on('click', () => onFocus(s.slug));
        poly.bindTooltip(`${esc(s.name)} · click for its summary`, { direction: 'top', className: 'tt', sticky: true });
      }
      const sub = on ? `<small>${esc(s.area_name || '')}${s.grades ? `${s.area_name ? ' · ' : ''}grades ${esc(s.grades)}` : ''}</small>` : '';
      const label = L.marker(s.center, {
        pane: 'sitelabel', // above the place markers, below popups
        zIndexOffset: on ? 1000 : 0,
        icon: L.divIcon({ className: 'site-label', html: `<span class="${on ? 'on' : ''}" style="--c:${s.color}"><i></i><em>${esc(s.short)}${sub}</em></span>`, iconSize: [0, 0] }),
      }).addTo(g);
      label.on('click', () => onFocus(s.slug));
    }
    return () => { map.removeLayer(g); };
  }, [map, schools, parcels, focus, onFocus]);
  return null;
}

/** One RCO's boundary, picked from the panel or a community group's popup. */
export function RcoFocus({ feature }) {
  const map = useMap();
  useEffect(() => {
    if (!feature) return undefined;
    const g = L.geoJSON(feature, { pane: 'lines', interactive: false, style: { color: '#393864', weight: 3, opacity: 1, fillColor: '#393864', fillOpacity: 0.08, lineJoin: 'round' } }).addTo(map);
    return () => { map.removeLayer(g); };
  }, [map, feature]);
  return null;
}

/** The radius ring around each school on the map. */
export function RadiusLayer({ schools, miles }) {
  const map = useMap();
  useEffect(() => {
    const g = L.layerGroup().addTo(map);
    for (const s of schools) {
      L.circle(s.center, { pane: 'lines', radius: miles * 1609.344, color: s.color, weight: 2.2, dashArray: '0.1 6', lineCap: 'round', fill: false, interactive: false }).addTo(g);
    }
    return () => { map.removeLayer(g); };
  }, [map, schools, miles]);
  return null;
}

// ── a searched address or place ───────────────────────────────────────────
export function PinLayer({ pin, nearest }) {
  const map = useMap();
  useEffect(() => {
    if (!pin) return undefined;
    const mk = L.marker(pin.latlng, {
      pane: 'top',
      icon: L.divIcon({ className: 'pin-wrap', html: '<div class="pin"></div>', iconSize: [26, 34], iconAnchor: [13, 32], popupAnchor: [0, -30] }),
    }).addTo(map);
    const html = pin.html || popupHtml({ title: pin.label, kind: pin.kind || 'Searched address' });
    mk.bindPopup(withDistance(html, L.latLng(pin.latlng), nearest), { maxWidth: 320 }).openPopup();
    return () => { map.removeLayer(mk); };
  }, [map, pin, nearest]);
  return null;
}

// ── measure: click to add points ──────────────────────────────────────────
export function MeasureLayer({ active, points, onAdd }) {
  const map = useMap();
  useEffect(() => {
    if (!active) return undefined;
    const el = map.getContainer();
    el.classList.add('measuring');
    map.doubleClickZoom.disable();
    const click = (e) => onAdd([e.latlng.lat, e.latlng.lng]);
    map.on('click', click);
    return () => { map.off('click', click); el.classList.remove('measuring'); map.doubleClickZoom.enable(); };
  }, [map, active, onAdd]);
  useEffect(() => {
    if (!points.length) return undefined;
    const g = L.layerGroup().addTo(map);
    L.polyline(points, { pane: 'top', color: '#1E1E1C', weight: 2.5, dashArray: '6 5', interactive: false }).addTo(g);
    points.forEach((p) => L.circleMarker(p, { pane: 'top', radius: 4.5, color: '#1E1E1C', weight: 2, fillColor: '#fff', fillOpacity: 1, interactive: false }).addTo(g));
    return () => { map.removeLayer(g); };
  }, [map, points]);
  return null;
}

export const pathMiles = (pts) => pts.slice(1).reduce((s, p, i) => s + L.latLng(pts[i]).distanceTo(p), 0) / 1609.344;
export const milesBetween = (a, b) => L.latLng(a).distanceTo(b) / 1609.344;
