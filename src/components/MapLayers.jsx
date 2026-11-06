/**
 * Leaflet layers, added imperatively inside react-leaflet's map so each layer controls its own pane,
 * style function, hover state and popup. Every component here renders nothing and cleans up on unmount.
 */
import { useEffect, useMemo } from 'react';
import { TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { CATEGORY, ICONS, esc, fmtMiles, walkMinutes, assetPopup, popupHtml, quantiles, MEASURE } from '../lib/layers';

// ── panes: stacking order of everything on the map ───────────────────────
const PANES = [
  ['choropleth', 340], ['areas', 380], ['lines', 420], ['labels', 460], ['points', 480], ['site', 640], ['assets', 650], ['top', 700],
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

// ── basemaps (all keyless) ────────────────────────────────────────────────
const CITY = 'https://tiles.arcgis.com/tiles/fLeGjb7u4uXqeF9q/arcgis/rest/services';
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
export const BASEMAPS = [
  { id: 'soft', label: 'City · soft', base: `${CITY}/CityBasemap/MapServer/tile/{z}/{y}/{x}`, baseOpacity: 0.45, labels: `${CITY}/CityBasemap_Labels/MapServer/tile/{z}/{y}/{x}`, labelOpacity: 0.85, attribution: 'City of Philadelphia' },
  { id: 'city', label: 'City', base: `${CITY}/CityBasemap/MapServer/tile/{z}/{y}/{x}`, baseOpacity: 1, labels: `${CITY}/CityBasemap_Labels/MapServer/tile/{z}/{y}/{x}`, labelOpacity: 1, attribution: 'City of Philadelphia' },
  { id: 'gray', label: 'Gray', base: `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, maxNative: 16, labels: `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, attribution: 'Esri' },
  { id: 'satellite', label: 'Satellite', base: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, labels: `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, attribution: 'Esri, Maxar, Earthstar Geographics' },
];
export function Basemap({ id }) {
  const bm = BASEMAPS.find((b) => b.id === id) || BASEMAPS[0];
  return (
    <>
      <TileLayer key={`b-${bm.id}`} url={bm.base} opacity={bm.baseOpacity ?? 1} maxZoom={20} maxNativeZoom={bm.maxNative || 19} attribution={bm.attribution} />
      {bm.labels && <TileLayer key={`l-${bm.id}`} url={bm.labels} pane="labels" opacity={bm.labelOpacity ?? 1} maxZoom={20} maxNativeZoom={bm.maxNative || 19} />}
    </>
  );
}

// ── distance from the school, for popups ──────────────────────────────────
const distanceHtml = (latlng, center) => {
  if (!latlng || !center) return '';
  const mi = L.latLng(center).distanceTo(latlng) / 1609.344;
  return `<div class="pp-d">${fmtMiles(mi)} from the school · about ${walkMinutes(mi)} min walk in a straight line</div>`;
};
const withDistance = (html, latlng, center) => html.replace(/(<div class="pp-s">|<\/div>$)/, (m) => distanceHtml(latlng, center) + m);

// ── a registry layer (layers.js) drawn from a FeatureCollection ───────────
export function GeoLayer({ def, data, center, onTract }) {
  const map = useMap();
  const pane = def.geom === 'point' ? 'points' : def.geom === 'line' ? 'lines' : def.geom === 'mixed' ? 'lines' : 'areas';
  // SVG for everything that can be clicked; a canvas would sit over the panes below and swallow their clicks,
  // so it is kept for thousands of dots that only need to be seen (layers.js `canvas: true`, not interactive).
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
            return lyr.getLatLng ? withDistance(html, lyr.getLatLng(), center) : html;
          }, { maxWidth: 320, autoPanPadding: [40, 40] });
        }
        if (def.hover) {
          lyr.on('mouseover', () => lyr.setStyle?.(def.hover));
          lyr.on('mouseout', () => layer.resetStyle(lyr));
        }
        if (def.clickTract && onTract) lyr.on('click', () => onTract(p));
      },
    }).addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, def, data, pane, renderer, center, onTract]);
  return null;
}

// ── census tract choropleth ────────────────────────────────────────────────
export function Choropleth({ data, measure, selectedId, onTract }) {
  const map = useMap();
  const m = MEASURE[measure];
  const scale = useMemo(() => (data && m ? quantiles(data.features.map((f) => f.properties[m.id])) : null), [data, m]);

  useEffect(() => {
    if (!data || !m || !scale) return undefined;
    const base = (p) => ({
      pane: 'choropleth', color: '#ffffff', weight: p.geoid === selectedId ? 3 : 0.8, opacity: 1,
      fillColor: scale.colorOf(p[m.id]), fillOpacity: 0.72,
      ...(p.geoid === selectedId ? { color: '#1E1E1C' } : null),
    });
    const layer = L.geoJSON(data, {
      pane: 'choropleth',
      style: (f) => base(f.properties),
      onEachFeature: (f, lyr) => {
        const p = f.properties;
        lyr.bindTooltip(`<b>Tract ${esc(p.name)}</b>${p.study ? ' · study area' : ''}<br>${esc(m.label)}: <b>${esc(m.fmt(p[m.id]))}</b>`, { sticky: true, className: 'tt', direction: 'top' });
        lyr.on('mouseover', () => { lyr.setStyle({ weight: 2.5, color: '#1E1E1C' }); lyr.bringToFront(); });
        lyr.on('mouseout', () => lyr.setStyle(base(p)));
        lyr.on('click', () => onTract(p));
      },
    }).addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, data, m, scale, selectedId, onTract]);
  return null;
}

// ── community assets: a white glyph on the family colour ──────────────────
const iconCache = new Map();
function assetIcon(category, near) {
  const key = `${category}|${near}`;
  if (!iconCache.has(key)) {
    const c = CATEGORY[category] || { color: '#57564E', icon: 'people' };
    const size = near ? 24 : 20;
    iconCache.set(key, L.divIcon({
      className: 'am-wrap',
      html: `<div class="am${near ? '' : ' far'}" style="--c:${c.color}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[c.icon]}"/></svg></div>`,
      iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2], tooltipAnchor: [0, -size / 2],
    }));
  }
  return iconCache.get(key);
}

export function AssetLayer({ data, categories, halfOnly, center }) {
  const map = useMap();
  useEffect(() => {
    if (!data) return undefined;
    const group = L.layerGroup();
    for (const f of data.features) {
      const p = f.properties;
      if (!categories[p.category]) continue;
      if (halfOnly && !p.half) continue;
      const [lng, lat] = f.geometry.coordinates;
      const mk = L.marker([lat, lng], { icon: assetIcon(p.category, p.half), pane: 'assets', riseOnHover: true, keyboard: true, title: p.name });
      mk.bindTooltip(`<b>${esc(p.name)}</b><br><span class="tt-k">${esc(p.kind)}</span>`, { direction: 'top', className: 'tt' });
      mk.bindPopup(() => withDistance(assetPopup(p), mk.getLatLng(), center), { maxWidth: 320, autoPanPadding: [40, 40] });
      group.addLayer(mk);
    }
    group.addTo(map);
    return () => { map.removeLayer(group); };
  }, [map, data, categories, halfOnly, center]);
  return null;
}

// ── the school: parcel in Indigo with its name ────────────────────────────
export function SiteLayer({ site }) {
  const map = useMap();
  useEffect(() => {
    if (!site) return undefined;
    const g = L.layerGroup().addTo(map);
    L.geoJSON(site.parcel, { pane: 'site', interactive: false, style: { color: '#ffffff', weight: 2, fillColor: '#393864', fillOpacity: 1 } }).addTo(g);
    L.marker(site.center, { pane: 'site', interactive: false, icon: L.divIcon({ className: 'site-label', html: `<span>${esc(site.school)} School</span>`, iconSize: [0, 0] }) }).addTo(g);
    return () => { map.removeLayer(g); };
  }, [map, site]);
  return null;
}

/** A study-area outline stored in site.json (half mile, one mile, neighborhood). */
export function SiteShape({ geometry, style }) {
  const map = useMap();
  useEffect(() => {
    if (!geometry) return undefined;
    const layer = L.geoJSON(geometry, { pane: 'lines', interactive: false, style }).addTo(map);
    return () => { map.removeLayer(layer); };
  }, [map, geometry, style]);
  return null;
}

// ── a searched address or place ───────────────────────────────────────────
export function PinLayer({ pin, center }) {
  const map = useMap();
  useEffect(() => {
    if (!pin) return undefined;
    const mk = L.marker(pin.latlng, {
      pane: 'top',
      icon: L.divIcon({ className: 'pin-wrap', html: '<div class="pin"></div>', iconSize: [26, 34], iconAnchor: [13, 32], popupAnchor: [0, -30] }),
    }).addTo(map);
    const html = pin.html || popupHtml({ title: pin.label, kind: pin.kind || 'Searched address' });
    mk.bindPopup(withDistance(html, L.latLng(pin.latlng), center), { maxWidth: 320 }).openPopup();
    return () => { map.removeLayer(mk); };
  }, [map, pin, center]);
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
