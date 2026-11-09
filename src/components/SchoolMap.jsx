/**
 * The six-school community map (the Market Analysis Tool's MarketAnalyzer): owns all state, loads each
 * layer's file the first time it is needed, merges per-school layers across the schools on the map, and
 * hands the presentational pieces what they need.
 */
import React, { useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MapContainer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AssetLayer, Basemap, Choropleth, GeoLayer, MapBridge, MeasureLayer, Panes, PinLayer, RadiusLayer, SiteLayer, ZoomClass, makeNearest, milesBetween, pathMiles } from './MapLayers';
import { LayersRail, Legend, MapControls, MeasureChip, Notice, SchoolBar, ZoomBar } from './Chrome';
import SitePanel from './SitePanel';
import { CATEGORIES, KEY_FIELD, LAYERS, LAYER, assetPopup, popupHtml, quantiles, rcoPopup } from '../lib/layers';

const ALL_CATS = Object.fromEntries(CATEGORIES.map((c) => [c.id, true]));
const DEFAULT_ON = Object.fromEntries(LAYERS.filter((l) => l.defaultOn).map((l) => [l.id, true]));
const VIEWS = [
  { id: 'site', label: 'School site' }, { id: 'radius', label: 'Radius' }, { id: 'walk', label: '15-min walk' },
  { id: 'catchment', label: 'Catchment' }, { id: 'neighborhood', label: 'Neighborhood' }, { id: 'tracts', label: 'Study tracts' },
];
const SEARCHABLE = {
  'ctx/businesses': { layer: 'businesses', sub: (p) => [p.kind, p.address].filter(Boolean).join(' · ') },
  'ctx/transit_stops': { layer: 'transit_stops', sub: (p) => `${p.mode} stop · routes ${p.routes}` },
  'ctx/affordable_housing': { layer: 'affordable_housing', sub: (p) => `Affordable housing · ${p.units ?? '?'} units` },
  'ctx/parks': { layer: 'parks', sub: () => 'Park' },
  'ctx/corridors': { layer: 'corridors', sub: () => 'Commercial corridor' },
  'ctx/rail_stations': { layer: 'rail_stations', sub: (p) => `${p.mode} station` },
};
const isWide = () => typeof window !== 'undefined' && window.innerWidth >= 900;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
const featureCenter = (f) => {
  if (f.geometry.type === 'Point') return [f.geometry.coordinates[1], f.geometry.coordinates[0]];
  const c = L.geoJSON(f).getBounds().getCenter();
  return [c.lat, c.lng];
};
const csvCell = (v) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const fcOf = (features) => ({ type: 'FeatureCollection', features });

export default function SchoolMap({ initialSlug }) {
  const [meta, setMeta] = useState(null);
  const [sites, setSites] = useState(null);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState({});
  const [loadingFiles, setLoadingFiles] = useState({});
  const [visible, setVisible] = useState(null);
  const [focus, setFocus] = useState(initialSlug || null);
  const [radius, setRadius] = useState(0.5);
  const [radiusOnly, setRadiusOnly] = useState(false);
  const [on, setOn] = useState(DEFAULT_ON);
  const [categories, setCategories] = useState(ALL_CATS);
  const [measure, setMeasure] = useState(null);
  const [basemap, setBasemap] = useState('gray');
  const [tract, setTract] = useState(null);
  const [panelOpen, setPanelOpen] = useState(isWide);
  const [tab, setTab] = useState(initialSlug ? 'school' : 'schools');
  const [query, setQuery] = useState('');
  const [pin, setPin] = useState(null);
  const [geocoding, setGeocoding] = useState(false);
  const [candidates, setCandidates] = useState(null);
  const [measuring, setMeasuring] = useState(false);
  const [mPoints, setMPoints] = useState([]);
  const [notice, setNotice] = useState(null);
  const [map, setMap] = useState(null);
  const barRef = useRef(null);
  const legendRef = useRef(null);
  const [railTop, setRailTop] = useState(200);
  const [legendH, setLegendH] = useState(120);

  // ── load what every view needs: the six schools, their sites and their assets ──
  useEffect(() => {
    let alive = true;
    Promise.all([getJSON('/data/schools.json'), getJSON('/data/sites.json')])
      .then(async ([m, s]) => {
        if (!alive) return;
        const order = m.schools.map((x) => x.slug);
        setMeta(m); setSites(s);
        setVisible(initialSlug && order.includes(initialSlug) ? [initialSlug] : order);
        const assets = await Promise.all(order.map((slug) => getJSON(`/data/${slug}/assets.json`).then((d) => [`${slug}/assets`, d])));
        if (alive) setFiles((f) => ({ ...f, ...Object.fromEntries(assets) }));
      })
      .catch((e) => alive && setError(String(e)));
    return () => { alive = false; };
  }, [initialSlug]);

  const ensure = useCallback((key) => {
    if (!key || files[key] || loadingFiles[key]) return;
    setLoadingFiles((s) => ({ ...s, [key]: true }));
    getJSON(`/data/${key}.json`)
      .then((d) => setFiles((s) => ({ ...s, [key]: d })))
      .catch((e) => console.error(e))
      .finally(() => setLoadingFiles((s) => ({ ...s, [key]: false })));
  }, [files, loadingFiles]);

  const all = useMemo(() => meta?.schools || [], [meta]);
  const shown = useMemo(() => all.filter((s) => visible?.includes(s.slug)), [all, visible]);
  const focusSchool = shown.find((s) => s.slug === focus) || (shown.length === 1 ? shown[0] : null);
  const targets = focusSchool ? [focusSchool] : shown;
  const nearest = useMemo(() => makeNearest(shown), [shown]);

  // files each layer needs
  const needs = useCallback((l) => {
    if (l.scope === 'ctx') return [`ctx/${l.file}`];
    if (l.scope === 'school') return shown.map((s) => `${s.slug}/${l.file}`);
    if (l.scope === 'tracts') return ['ctx/tracts'];
    return [];
  }, [shown]);
  useEffect(() => {
    if (!meta) return;
    LAYERS.forEach((l) => on[l.id] && needs(l).forEach(ensure));
    if (measure) ensure('ctx/tracts');
    if (query.length >= 2) shown.forEach((s) => ensure(`${s.slug}/rco`));
  }, [meta, on, measure, query, shown, needs, ensure]);

  // the address bar follows the selection: /wagner for one school, / for several
  useEffect(() => {
    if (!visible) return;
    const path = visible.length === 1 ? `/${visible[0]}` : '/';
    if (window.location.pathname !== path) window.history.replaceState(null, '', path);
    document.title = visible.length === 1 ? `${all.find((s) => s.slug === visible[0])?.short} · Community Map` : 'Community Maps · Six Schools';
  }, [visible, all]);

  // ── layout: rail starts under the Zoom-to card and stops above the legend ──
  useLayoutEffect(() => {
    const ro = new ResizeObserver(() => {
      if (barRef.current) setRailTop(barRef.current.offsetTop + barRef.current.offsetHeight + 8);
      if (legendRef.current) setLegendH(legendRef.current.offsetHeight + 20);
    });
    if (barRef.current) ro.observe(barRef.current);
    if (legendRef.current) ro.observe(legendRef.current);
    return () => ro.disconnect();
  }, [meta]);

  // ── layer data, merged across the schools on the map ───────────────────
  const tag = (f, s, extra) => ({ ...f, properties: { ...f.properties, _slug: s.slug, _short: s.short, _color: s.color, ...extra } });
  const layerData = useMemo(() => {
    const out = {};
    for (const l of LAYERS) {
      if (!on[l.id]) continue;
      if (l.scope === 'ctx') out[l.id] = files[`ctx/${l.file}`];
      else if (l.scope === 'site' && sites) {
        out[l.id] = fcOf(sites.features.filter((f) => f.properties.kind === l.kind && visible?.includes(f.properties.slug))
          .map((f) => tag(f, all.find((s) => s.slug === f.properties.slug))));
      } else if (l.scope === 'school') {
        const parts = shown.filter((s) => files[`${s.slug}/${l.file}`]);
        if (!parts.length) continue;
        let feats = parts.flatMap((s) => files[`${s.slug}/${l.file}`].features.map((f) => tag(f, s)));
        if (l.file === 'rco') { // an RCO near two schools is drawn once; it "covers" if it covers either
          const by = new Map();
          for (const f of feats) {
            const k = f.properties.name; const prev = by.get(k);
            if (!prev || (f.properties.covers && !prev.properties.covers)) by.set(k, f);
          }
          feats = [...by.values()];
        }
        out[l.id] = fcOf(feats);
      } else if (l.scope === 'tracts' && files['ctx/tracts']) {
        const study = new Map();
        for (const s of shown) for (const [g, sh] of Object.entries(s.study_tracts || {})) if (!study.has(g) || study.get(g).share < sh) study.set(g, { share: sh, s });
        out[l.id] = fcOf(files['ctx/tracts'].features.filter((f) => study.has(f.properties.geoid))
          .map((f) => { const x = study.get(f.properties.geoid); return tag(f, x.s, { _share: x.share }); }));
      }
    }
    return out;
  }, [on, files, sites, visible, shown, all]);

  const featureCounts = useMemo(() => Object.fromEntries(LAYERS.map((l) => {
    if (l.scope === 'radius') return [l.id, shown.length];
    const d = layerData[l.id];
    if (!d) return [l.id, null];
    return [l.id, l.filter ? d.features.filter((f) => l.filter(f.properties)).length : d.features.length];
  })), [layerData, shown]);
  const loading = useMemo(() => Object.fromEntries(LAYERS.map((l) => [l.id, needs(l).some((k) => loadingFiles[k])])), [loadingFiles, needs]);
  const scale = useMemo(() => (measure && files['ctx/tracts'] ? quantiles(files['ctx/tracts'].features.map((f) => f.properties[measure])) : null), [measure, files]);
  const present = useMemo(() => Object.fromEntries(Object.entries(KEY_FIELD).filter(([f]) => files[`ctx/${f}`])
    .map(([f, k]) => [f, new Set(files[`ctx/${f}`].features.map((x) => x.properties[k]))])), [files]);
  const parcels = useMemo(() => Object.fromEntries((sites?.features || []).filter((f) => f.properties.kind === 'parcel').map((f) => [f.properties.slug, f.geometry])), [sites]);

  // ── community assets of the schools on the map, once each, measured from the nearest school ──
  const assetRadius = useDeferredValue(radius); // the rings follow the slider at once; the ~1,200 markers catch up
  const assetPool = useMemo(() => {
    const seen = new Map();
    for (const s of shown) {
      const d = files[`${s.slug}/assets`];
      if (!d) continue;
      for (const f of d.features) {
        const [lng, lat] = f.geometry.coordinates;
        const k = `${f.properties.name}|${lat.toFixed(4)}|${lng.toFixed(4)}`;
        if (seen.has(k)) continue;
        let mi = Infinity; let near = null;
        for (const t of shown) { const m = milesBetween(t.center, [lat, lng]); if (m < mi) { mi = m; near = t; } }
        seen.set(k, { lat, lng, p: f.properties, mi, school: near?.short, near: mi <= assetRadius });
      }
    }
    return [...seen.values()];
  }, [files, shown, assetRadius]);
  const assetItems = useMemo(() => assetPool.filter((a) => categories[a.p.category] && (!radiusOnly || a.near)), [assetPool, categories, radiusOnly]);
  const assetCounts = useMemo(() => {
    const c = {};
    for (const a of assetPool) if (!radiusOnly || a.near) c[a.p.category] = (c[a.p.category] || 0) + 1;
    return c;
  }, [assetPool, radiusOnly]);
  const inRadiusOf = useCallback((slug) => {
    const c = {};
    for (const f of files[`${slug}/assets`]?.features || []) if (f.properties.miles <= radius + 1e-9) c[f.properties.category] = (c[f.properties.category] || 0) + 1;
    return c;
  }, [files, radius]);

  // ── map helpers ─────────────────────────────────────────────────────────
  const pad = useCallback(() => (isWide()
    ? { paddingTopLeft: [380, 70], paddingBottomRight: [panelOpen ? 400 : 40, 40] }
    : { padding: [24, 24] }), [panelOpen]);
  const ringBounds = useCallback((list, miles = radius) => {
    let b = null;
    for (const s of list) { const x = L.latLng(s.center).toBounds(miles * 2 * 1609.344); b = b ? b.extend(x) : x; }
    return b;
  }, [radius]);
  const fitBounds = useCallback((b, maxZoom = 17) => { if (map && b?.isValid()) map.fitBounds(b, { ...pad(), maxZoom }); }, [map, pad]);
  const fitGeo = useCallback((geo) => { if (geo && (geo.features ? geo.features.length : true)) fitBounds(L.geoJSON(geo).getBounds()); }, [fitBounds]);
  const home = useCallback(() => fitBounds(ringBounds(targets)), [fitBounds, ringBounds, targets]);

  const firstFit = useRef(false);
  useEffect(() => {
    if (map && meta && shown.length && !firstFit.current) { firstFit.current = true; map.invalidateSize(); fitBounds(ringBounds(shown)); }
  }, [map, meta, shown, fitBounds, ringBounds]);

  const pendingZoom = useRef(null);
  const zoomTo = useCallback((id) => {
    if (!map || !targets.length) return;
    const names = (list) => list.map((s) => s.short).join(', ');
    if (id === 'site') {
      if (targets.length === 1) map.flyTo(targets[0].center, 17, { duration: 0.8 });
      else fitBounds(L.latLngBounds(targets.map((s) => s.center)).pad(0.15), 15);
    } else if (id === 'radius') {
      setOn((s) => ({ ...s, radius: true })); fitBounds(ringBounds(targets));
    } else if (id === 'catchment' || id === 'neighborhood') {
      setOn((s) => ({ ...s, [id]: true }));
      const feats = (sites?.features || []).filter((f) => f.properties.kind === id && targets.some((t) => t.slug === f.properties.slug));
      const missing = targets.filter((t) => !feats.some((f) => f.properties.slug === t.slug));
      if (feats.length) fitGeo(fcOf(feats));
      if (id === 'catchment' && missing.length) setNotice(`${names(missing)} ${missing.length > 1 ? 'admit' : 'admits'} students citywide, so ${missing.length > 1 ? 'they have' : 'it has'} no attendance catchment.`);
    } else if (id === 'walk') {
      setOn((s) => ({ ...s, walk: true }));
      const keys = targets.map((t) => `${t.slug}/walk`);
      if (keys.every((k) => files[k])) fitGeo(fcOf(keys.flatMap((k) => files[k].features)));
      else { pendingZoom.current = 'walk'; keys.forEach(ensure); }
    } else if (id === 'tracts') {
      setOn((s) => ({ ...s, study_tracts: true }));
      if (files['ctx/tracts']) {
        const ids = new Set(targets.flatMap((t) => Object.keys(t.study_tracts || {})));
        fitGeo(fcOf(files['ctx/tracts'].features.filter((f) => ids.has(f.properties.geoid))));
      } else { pendingZoom.current = 'tracts'; ensure('ctx/tracts'); }
    }
  }, [map, targets, sites, files, ensure, fitBounds, fitGeo, ringBounds]);
  useEffect(() => {
    const z = pendingZoom.current;
    if (!z) return;
    const ready = z === 'walk' ? targets.every((t) => files[`${t.slug}/walk`]) : !!files['ctx/tracts'];
    if (ready) { pendingZoom.current = null; zoomTo(z); }
  }, [files, targets, zoomTo]);

  // ── school selection ───────────────────────────────────────────────────
  const order = all.map((s) => s.slug);
  const onAll = () => { setVisible(order); setFocus(null); setTab('schools'); fitBounds(ringBounds(all)); };
  const onOnly = (slug) => {
    const s = all.find((x) => x.slug === slug);
    setVisible([slug]); setFocus(slug); setTab('school'); setPanelOpen(isWide() || panelOpen);
    fitBounds(ringBounds([s]));
  };
  const onToggleSchool = (slug) => setVisible((v) => {
    if (v.includes(slug)) { if (v.length === 1) return v; if (focus === slug) setFocus(null); return v.filter((x) => x !== slug); }
    return order.filter((x) => v.includes(x) || x === slug);
  });
  const onFocus = useCallback((slug) => {
    const s = all.find((x) => x.slug === slug);
    setVisible((v) => (v.includes(slug) ? v : all.map((x) => x.slug).filter((x) => v.includes(x) || x === slug)));
    setFocus(slug); setTab('school'); setPanelOpen(true);
    if (s && map) map.flyToBounds(L.latLng(s.center).toBounds(radius * 2 * 1609.344), { ...pad(), duration: 0.8, maxZoom: 17 });
  }, [all, map, radius, pad]);

  // ── search ─────────────────────────────────────────────────────────────
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const out = [];
    const hit = (p) => `${p.name || ''} ${p.address || ''} ${p.kind || ''}`.toLowerCase().includes(q);
    assetPool.forEach((a, i) => { if (hit(a.p)) out.push({ key: `a${i}`, name: a.p.name, sub: [a.p.kind, a.p.address].filter(Boolean).join(' · '), category: a.p.category, latlng: [a.lat, a.lng], html: assetPopup(a.p) }); });
    for (const s of shown) {
      files[`${s.slug}/rco`]?.features.forEach((f, i) => {
        if (hit(f.properties)) out.push({ key: `r${s.slug}${i}`, name: f.properties.name, sub: `RCO near ${s.short}`, swatch: LAYER.rco_covers.swatch, latlng: featureCenter(f), html: rcoPopup(f.properties), layer: f.properties.covers ? 'rco_covers' : 'rco_other' });
      });
    }
    for (const [key, s] of Object.entries(SEARCHABLE)) {
      files[key]?.features.forEach((f, i) => {
        const p = f.properties;
        if (p.name && hit(p)) out.push({ key: `${key}${i}`, name: p.name, sub: s.sub(p), swatch: LAYER[s.layer].swatch, latlng: featureCenter(f), html: LAYER[s.layer].popup ? LAYER[s.layer].popup(p) : popupHtml({ title: p.name, kind: s.sub(p) }), layer: s.layer });
      });
    }
    const seen = new Set();
    return out.filter((r) => { const k = `${r.name}|${r.latlng.join()}`; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 50);
  }, [query, assetPool, files, shown]);
  const onPick = (r) => {
    if (r.category) { setCategories((c) => ({ ...c, [r.category]: true })); setRadiusOnly(false); }
    if (r.layer) setOn((s) => ({ ...s, [r.layer]: true }));
    setPin({ latlng: r.latlng, label: r.name, html: r.html });
    map?.flyTo(r.latlng, Math.max(map.getZoom(), 17), { duration: 0.8 });
  };

  const onGeocode = async (q) => {
    const c0 = (focusSchool || shown[0])?.center;
    setGeocoding(true); setCandidates(null);
    try {
      const u = new URL('https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates');
      u.search = new URLSearchParams({ f: 'json', SingleLine: /philadelphia|phila\b|, pa\b/i.test(q) ? q : `${q}, Philadelphia, PA`, maxLocations: '5', ...(c0 ? { location: `${c0[1]},${c0[0]}` } : {}), outFields: 'Match_addr' }).toString();
      const d = await getJSON(u.toString());
      const cands = (d.candidates || []).filter((c) => c.score >= 80).map((c) => ({ label: c.address, latlng: [c.location.y, c.location.x] }));
      if (cands.length === 1) pickCandidate(cands[0]); else setCandidates(cands);
    } catch (e) { console.error(e); setCandidates([]); } finally { setGeocoding(false); }
  };
  const pickCandidate = (c) => { setCandidates(null); setPin({ latlng: c.latlng, label: c.label, kind: 'Searched address' }); map?.flyTo(c.latlng, 17, { duration: 0.8 }); };
  const clearPin = useCallback(() => { setPin(null); setCandidates(null); }, []);

  const onTract = useCallback((p) => { setTract(p); setTab('tract'); setPanelOpen(true); }, []);
  const addPoint = useCallback((p) => setMPoints((s) => [...s, p]), []);
  const EXCLUSIVE = { zoning: 'land_use', land_use: 'zoning' };
  const toggleLayer = (id) => setOn((s) => { const n = { ...s, [id]: !s[id] }; if (n[id] && EXCLUSIVE[id]) n[EXCLUSIVE[id]] = false; return n; });

  const download = () => {
    const cols = ['category', 'kind', 'name', 'address', 'detail', 'phone', 'website', 'source'];
    const lines = [[...cols, 'nearest_school', 'miles_to_nearest_school', `within_${radius}_mile`, 'latitude', 'longitude'].join(',')];
    for (const a of assetItems) lines.push([...cols.map((c) => csvCell(a.p[c])), csvCell(a.school), a.mi.toFixed(2), a.near, a.lat, a.lng].join(','));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const el = document.createElement('a');
    el.href = URL.createObjectURL(blob);
    el.download = `${shown.length === 1 ? shown[0].short.replace(/\s+/g, '_') : 'Six_Schools'}_Community_Assets${radiusOnly ? `_${radius}mi` : ''}.csv`;
    el.click();
    setTimeout(() => URL.revokeObjectURL(el.href), 1000);
  };

  if (error) return <div className="grid h-full place-items-center p-6 text-center text-slate-600">Could not load the map data ({error}).</div>;

  return (
    <div className="relative h-full">
      <MapContainer center={[40.0, -75.17]} zoom={12} zoomControl={false} className="h-full w-full" maxZoom={20} attributionControl>
        <Panes />
        <ZoomClass />
        <MapBridge onReady={setMap} />
        <Basemap id={basemap} />
        {meta && (
          <>
            {measure && files['ctx/tracts'] && <Choropleth data={files['ctx/tracts']} measure={measure} selectedId={tract?.geoid} onTract={onTract} />}
            {LAYERS.filter((l) => l.scope !== 'radius' && layerData[l.id]).map((l) => (
              <GeoLayer key={l.id} def={l} data={layerData[l.id]} nearest={nearest} onTract={onTract} />
            ))}
            {on.radius && <RadiusLayer schools={shown} miles={radius} />}
            <SiteLayer schools={shown} parcels={parcels} focus={focusSchool?.slug} onFocus={onFocus} />
            <AssetLayer items={assetItems} nearest={nearest} />
            <PinLayer pin={pin} nearest={nearest} />
            <MeasureLayer active={measuring} points={mPoints} onAdd={addPoint} />
          </>
        )}
      </MapContainer>

      {!meta && <div className="pointer-events-none absolute inset-0 z-[700] grid place-items-center"><div className="rounded-xl bg-white/95 px-4 py-2 text-[13px] font-semibold text-slate-600 shadow-lg">Loading map…</div></div>}

      {meta && visible && (
        <>
          <SchoolBar schools={all} visible={visible} onAll={onAll} onOnly={onOnly} />
          <ZoomBar views={VIEWS} onZoom={zoomTo} barRef={barRef} radius={radius} onRadius={setRadius} />
          <LayersRail
            top={railTop} reserveBottom={legendH} defaultOpen={isWide()}
            schools={all} visible={visible} onToggleSchool={onToggleSchool} onAllSchools={onAll} onFocus={onFocus}
            assetCounts={assetCounts} categories={categories}
            onCategory={(id) => setCategories((c) => ({ ...c, [id]: !c[id] }))}
            onAllCategories={(v) => setCategories(Object.fromEntries(CATEGORIES.map((c) => [c.id, v])))}
            radiusOnly={radiusOnly} onRadiusOnly={setRadiusOnly} radius={radius}
            measure={measure} onMeasure={setMeasure} acsYear={meta.acs_year}
            on={on} onToggle={toggleLayer} loading={loading} featureCounts={featureCounts}
            query={query} onQuery={setQuery} results={results} onPick={onPick}
          />
          <Legend schools={shown} categories={categories} on={on} measure={measure} scale={scale} present={present} legendRef={legendRef} />
          <SitePanel schools={shown} focusSchool={focusSchool} onFocus={onFocus} inRadiusOf={inRadiusOf} radius={radius}
            tract={tract} onClearTract={() => { setTract(null); setTab(focusSchool ? 'school' : 'schools'); }}
            open={panelOpen} setOpen={setPanelOpen} tab={tab} setTab={setTab} top={64}
            onOnly={(id) => setCategories(Object.fromEntries(CATEGORIES.map((c) => [c.id, c.id === id])))} />
          <MapControls basemap={basemap} onBasemap={setBasemap} onZoomIn={() => map?.zoomIn()} onZoomOut={() => map?.zoomOut()} onHome={home}
            onGeocode={onGeocode} geocoding={geocoding} candidates={candidates} onCandidate={pickCandidate} onClearPin={clearPin} hasPin={!!pin}
            measuring={measuring} onMeasure={() => { setMeasuring((m) => !m); setMPoints([]); }} onDownload={download} />
          {measuring && <MeasureChip miles={pathMiles(mPoints)} n={mPoints.length} onUndo={() => setMPoints((s) => s.slice(0, -1))} onClear={() => setMPoints([])} onDone={() => { setMeasuring(false); setMPoints([]); }} />}
          <Notice text={notice} onClose={() => setNotice(null)} />
        </>
      )}
    </div>
  );
}
