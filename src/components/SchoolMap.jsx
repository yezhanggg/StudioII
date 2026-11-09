/**
 * The community asset map (the Market Analysis Tool's MarketAnalyzer): owns all state, loads each file the
 * first time it is needed, merges per-school layers across the schools on the map, and hands the
 * presentational pieces what they need.
 */
import React, { useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MapContainer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AssetLayer, Basemap, Choropleth, RcoFocus, GeoLayer, MapBridge, Panes, RadiusLayer, SiteLayer, ZoomClass, makeNearest, milesBetween } from './MapLayers';
import { LayersRail, Legend, MapControls, RadiusCard, RcoChip, SchoolBar, SourcesModal } from './Chrome';
import SitePanel from './SitePanel';
import { GROUP, KEY_FIELD, LAYERS, RCO_NAMES, TYPE, TYPES, quantiles } from '../lib/layers';

const DEFAULT_TYPES = Object.fromEntries(TYPES.map((t) => [t.id, GROUP[t.group].on]));
const DEFAULT_ON = Object.fromEntries(LAYERS.filter((l) => l.defaultOn).map((l) => [l.id, true]));
const isWide = () => typeof window !== 'undefined' && window.innerWidth >= 900;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
const csvCell = (v) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const fcOf = (features) => ({ type: 'FeatureCollection', features });

export default function SchoolMap({ initialSlug }) {
  const [meta, setMeta] = useState(null);
  const [sites, setSites] = useState(null);
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState({});
  const [loadingFiles, setLoadingFiles] = useState({});
  const [visible, setVisible] = useState(null);
  const [focus, setFocus] = useState(initialSlug || null);
  const [radius, setRadius] = useState(0.5);
  const [radiusOnly, setRadiusOnly] = useState(true);
  const [on, setOn] = useState(DEFAULT_ON);
  const [types, setTypes] = useState(DEFAULT_TYPES);
  const [measure, setMeasure] = useState(null);
  const [basemap, setBasemap] = useState('light');
  const [panelOpen, setPanelOpen] = useState(isWide);
  const [docsOpen, setDocsOpen] = useState(false);
  const [map, setMap] = useState(null);
  const barRef = useRef(null);
  const legendRef = useRef(null);
  const [railTop, setRailTop] = useState(150);
  const [legendH, setLegendH] = useState(120);

  // ── what every view needs: the schools, their sites, their assets, the source list ──
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
    getJSON('/data/sources.json').then((d) => alive && setSources(d)).catch(() => {});
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
  const sourceTitle = useMemo(() => Object.fromEntries((sources?.assets || []).map((d) => [d.id, `${d.title} (${d.publisher})`])), [sources]);
  const city = all[0]?.profile;

  const needs = useCallback((l) => (l.scope === 'ctx' ? [`ctx/${l.file}`] : l.scope === 'school' ? shown.map((s) => `${s.slug}/${l.file}`) : []), [shown]);
  useEffect(() => {
    if (!meta) return;
    LAYERS.forEach((l) => on[l.id] && needs(l).forEach(ensure));
    if (measure) ensure('ctx/tracts');
  }, [meta, on, measure, needs, ensure]);

  // the address bar follows the selection: /wagner for one school, / for several
  useEffect(() => {
    if (!visible) return;
    const path = visible.length === 1 ? `/${visible[0]}` : '/';
    if (window.location.pathname !== path) window.history.replaceState(null, '', path);
    document.title = !visible.length ? 'Community Asset Map' : visible.length === 1 ? `${all.find((s) => s.slug === visible[0])?.short} · Community Asset Map` : 'Community Asset Map · Six Schools';
  }, [visible, all]);

  useLayoutEffect(() => {
    const ro = new ResizeObserver(() => {
      if (barRef.current) setRailTop(barRef.current.offsetTop + barRef.current.offsetHeight + 8);
      if (legendRef.current) setLegendH(legendRef.current.offsetHeight + 20);
    });
    if (barRef.current) ro.observe(barRef.current);
    if (legendRef.current) ro.observe(legendRef.current);
    return () => ro.disconnect();
  }, [meta]);

  // ── context layers, merged across the schools on the map ───────────────
  const lagRadius = useDeferredValue(radius); // rings follow the slider at once; markers and RCO boundaries catch up
  const tag = (f, s) => ({ ...f, properties: { ...f.properties, _slug: s.slug, _short: s.short, _color: s.color } });
  const layerData = useMemo(() => {
    const out = {};
    for (const l of LAYERS) {
      if (!on[l.id]) continue;
      if (l.scope === 'ctx') out[l.id] = files[`ctx/${l.file}`];
      else if (l.scope === 'site' && sites) {
        out[l.id] = fcOf(sites.features.filter((f) => f.properties.kind === l.kind && visible?.includes(f.properties.slug)).map((f) => tag(f, all.find((s) => s.slug === f.properties.slug))));
      } else if (l.scope === 'school') {
        const parts = shown.filter((s) => files[`${s.slug}/${l.file}`]);
        if (!parts.length) continue;
        let feats = parts.flatMap((s) => files[`${s.slug}/${l.file}`].features.map((f) => tag(f, s)));
        if (l.file === 'rco') {
          // each RCO once (measured from its nearest school on the map), and only those reaching the distance set
          const by = new Map();
          for (const f of feats) {
            if (l.withinRadius && f.properties.miles > lagRadius + 1e-9) continue;
            const prev = by.get(f.properties.name);
            if (!prev || f.properties.miles < prev.properties.miles) by.set(f.properties.name, f);
          }
          feats = [...by.values()];
        }
        out[l.id] = fcOf(feats);
      }
    }
    return out;
  }, [on, files, sites, visible, shown, all, lagRadius]);
  const loading = useMemo(() => Object.fromEntries(LAYERS.map((l) => [l.id, needs(l).some((k) => loadingFiles[k])])), [loadingFiles, needs]);
  const scale = useMemo(() => (measure && files['ctx/tracts'] ? quantiles(files['ctx/tracts'].features.map((f) => f.properties[measure])) : null), [measure, files]);
  const present = useMemo(() => Object.fromEntries(Object.entries(KEY_FIELD).filter(([f]) => files[`ctx/${f}`]).map(([f, k]) => [f, new Set(files[`ctx/${f}`].features.map((x) => x.properties[k]))])), [files]);
  const parcels = useMemo(() => Object.fromEntries((sites?.features || []).filter((f) => f.properties.kind === 'parcel').map((f) => [f.properties.slug, f.geometry])), [sites]);

  // ── community assets of the schools on the map, once each, measured from the nearest school ──
  const assetRadius = lagRadius;
  const assetPool = useMemo(() => {
    const seen = new Map();
    for (const s of shown) {
      for (const f of files[`${s.slug}/assets`]?.features || []) {
        const [lng, lat] = f.geometry.coordinates;
        const k = `${f.properties.type}|${f.properties.name}|${lat.toFixed(4)}|${lng.toFixed(4)}`;
        if (seen.has(k)) continue;
        let mi = Infinity; let near = null;
        for (const t of shown) { const m = milesBetween(t.center, [lat, lng]); if (m < mi) { mi = m; near = t; } }
        seen.set(k, { lat, lng, p: f.properties, mi, school: near?.short, near: mi <= assetRadius });
      }
    }
    return [...seen.values()];
  }, [files, shown, assetRadius]);
  const assetItems = useMemo(() => assetPool.filter((a) => types[a.p.type] && (!radiusOnly || a.near)), [assetPool, types, radiusOnly]);
  const assetCounts = useMemo(() => {
    const c = {};
    for (const a of assetPool) if (!radiusOnly || a.near) c[a.p.type] = (c[a.p.type] || 0) + 1;
    return c;
  }, [assetPool, radiusOnly]);
  const statsOf = useCallback((slug) => {
    const st = {};
    const center = all.find((x) => x.slug === slug)?.center;
    for (const f of files[`${slug}/assets`]?.features || []) {
      const c = f.properties.type;
      // measured the same way as the map (exact, not the file's rounded miles), so the panel and the rail agree
      const miles = center ? milesBetween(center, [f.geometry.coordinates[1], f.geometry.coordinates[0]]) : f.properties.miles;
      const x = st[c] || (st[c] = { n: 0, nearest: null });
      if (miles <= radius + 1e-9) x.n += 1;
      if (x.nearest == null || miles < x.nearest) x.nearest = miles;
    }
    return st;
  }, [files, radius, all]);

  // ── map helpers ─────────────────────────────────────────────────────────
  const pad = useCallback(() => (isWide() ? { paddingTopLeft: [360, 70], paddingBottomRight: [panelOpen ? 400 : 40, 50] } : { padding: [24, 24] }), [panelOpen]);
  const ringBounds = useCallback((list, miles = radius) => {
    let b = null;
    for (const s of list) { const x = L.latLng(s.center).toBounds(miles * 2 * 1609.344); b = b ? b.extend(x) : x; }
    return b;
  }, [radius]);
  const fitBounds = useCallback((b, maxZoom = 17) => { if (map && b?.isValid()) map.fitBounds(b, { ...pad(), maxZoom }); }, [map, pad]);
  const home = useCallback(() => fitBounds(ringBounds(targets)), [fitBounds, ringBounds, targets]);

  const firstFit = useRef(false);
  useEffect(() => {
    if (map && meta && shown.length && !firstFit.current) { firstFit.current = true; map.invalidateSize(); fitBounds(ringBounds(shown)); }
  }, [map, meta, shown, fitBounds, ringBounds]);


  // ── school selection ───────────────────────────────────────────────────
  // a second click on the selected button clears the map of schools
  const onAll = () => {
    if (visible.length === all.length) { setVisible([]); setFocus(null); return; }
    setVisible(all.map((s) => s.slug)); setFocus(null); fitBounds(ringBounds(all));
  };
  const onOnly = (slug) => {
    if (visible.length === 1 && visible[0] === slug) { setVisible([]); setFocus(null); return; }
    setVisible([slug]); setFocus(slug); if (isWide()) setPanelOpen(true);
    fitBounds(ringBounds([all.find((x) => x.slug === slug)]));
  };
  const onFocus = useCallback((slug) => {
    const s = all.find((x) => x.slug === slug);
    setVisible((v) => (v.includes(slug) ? v : all.map((x) => x.slug).filter((x) => v.includes(x) || x === slug)));
    setFocus(slug); setPanelOpen(true);
    if (s && map) map.flyToBounds(L.latLng(s.center).toBounds(radius * 2 * 1609.344), { ...pad(), duration: 0.8, maxZoom: 17 });
  }, [all, map, radius, pad]);

  // ── one RCO's boundary, from the panel or a community group's popup ────
  const [rcoFocus, setRcoFocus] = useState(null);
  useEffect(() => { RCO_NAMES.clear(); (meta?.schools || []).forEach((s) => (s.rcos || []).forEach((r) => RCO_NAMES.add(r.name))); }, [meta]);
  const showRco = useCallback((name) => {
    all.filter((s) => (s.rcos || []).some((r) => r.name === name)).forEach((s) => ensure(`${s.slug}/rco`));
    map?.closePopup();
    setRcoFocus((cur) => (cur === name ? null : name));
  }, [all, ensure, map]);
  const rcoFeature = useMemo(() => {
    if (!rcoFocus) return null;
    for (const s of all) {
      const f = files[`${s.slug}/rco`]?.features.find((x) => x.properties.name === rcoFocus);
      if (f) return { ...f, properties: { ...f.properties, _short: s.short } };
    }
    return null;
  }, [rcoFocus, files, all]);
  const fitted = useRef(null);
  useEffect(() => {
    if (!rcoFeature || !map || fitted.current === rcoFocus) return;
    fitted.current = rcoFocus;
    map.fitBounds(L.geoJSON(rcoFeature).getBounds(), { ...pad(), maxZoom: 16 });
  }, [rcoFeature, rcoFocus, map, pad]);
  useEffect(() => { if (!rcoFocus) fitted.current = null; }, [rcoFocus]);
  useEffect(() => {
    if (!map) return undefined;
    const el = map.getContainer();
    const onClick = (e) => { const b = e.target.closest?.('[data-rco]'); if (b) { e.preventDefault(); showRco(b.getAttribute('data-rco')); } };
    el.addEventListener('click', onClick);
    return () => el.removeEventListener('click', onClick);
  }, [map, showRco]);

  const EXCLUSIVE = { zoning: 'land_use', land_use: 'zoning' };
  const toggleLayer = (id) => setOn((s) => { const n = { ...s, [id]: !s[id] }; if (n[id] && EXCLUSIVE[id]) n[EXCLUSIVE[id]] = false; return n; });

  const selectionLabel = shown.length === 1 ? shown[0].short : shown.length === all.length ? 'All six schools' : shown.map((s) => s.short).join(', ');
  const download = () => {
    const cols = ['name', 'address', 'detail', 'phone', 'website', 'instagram', 'facebook'];
    const lines = [['group', 'type', 'kind', ...cols, 'source', 'nearest_school', 'miles_to_nearest_school', `within_${radius}_mile`, 'latitude', 'longitude'].join(',')];
    for (const a of assetItems) {
      const t = TYPE[a.p.type];
      lines.push([csvCell(GROUP[t?.group]?.label), csvCell(t?.label), csvCell(a.p.kind), ...cols.map((c) => csvCell(a.p[c])), csvCell(sourceTitle[a.p.source_id] || a.p.source_id), csvCell(a.school), a.mi.toFixed(2), a.near, a.lat, a.lng].join(','));
    }
    const el = document.createElement('a');
    el.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    el.download = `${shown.length === 1 ? shown[0].short.replace(/\s+/g, '_') : 'Schools'}_places${radiusOnly ? `_within_${radius}mi` : ''}.csv`;
    el.click();
    setTimeout(() => URL.revokeObjectURL(el.href), 1000);
  };

  if (error) return <div className="grid h-full place-items-center p-6 text-center text-slate-600">Could not load the map data ({error}).</div>;

  return (
    <div className="relative h-full">
      <MapContainer center={[40.0, -75.17]} zoom={12} zoomControl={false} className="h-full w-full" maxZoom={20} attributionControl={false}>
        <Panes />
        <ZoomClass />
        <MapBridge onReady={setMap} />
        <Basemap id={basemap} />
        {meta && (
          <>
            {measure && files['ctx/tracts'] && <Choropleth data={files['ctx/tracts']} measure={measure} city={city} />}
            {LAYERS.filter((l) => l.scope !== 'radius' && layerData[l.id]).map((l) => <GeoLayer key={l.id} def={l} data={layerData[l.id]} nearest={nearest} />)}
            {on.radius && <RadiusLayer schools={shown} miles={radius} />}
            <SiteLayer schools={shown} parcels={parcels} focus={focusSchool?.slug} onFocus={onFocus} />
            <RcoFocus feature={rcoFeature} />
            <AssetLayer items={assetItems} nearest={nearest} sourceTitle={sourceTitle} />
          </>
        )}
      </MapContainer>

      {!meta && <div className="pointer-events-none absolute inset-0 z-[700] grid place-items-center"><div className="rounded-xl bg-white/95 px-4 py-2 text-[13px] font-semibold text-slate-600 shadow-lg">Loading map…</div></div>}

      {meta && visible && (
        <>
          <SchoolBar schools={all} visible={visible} onAll={onAll} onOnly={onOnly} onClear={() => { setVisible([]); setFocus(null); }} onSources={() => setDocsOpen(true)} />
          <RadiusCard radius={radius} onRadius={setRadius} barRef={barRef} />
          <LayersRail
            top={railTop} reserveBottom={legendH} defaultOpen={isWide()} radius={radius}
            typeCounts={assetCounts} types={types}
            onType={(id) => setTypes((c) => ({ ...c, [id]: !c[id] }))}
            onGroup={(gid, v) => setTypes((c) => ({ ...c, ...Object.fromEntries(TYPES.filter((t) => t.group === gid).map((t) => [t.id, v])) }))}
            radiusOnly={radiusOnly} onRadiusOnly={setRadiusOnly}
            measure={measure} onMeasure={setMeasure} on={on} onToggle={toggleLayer} loading={loading}
          />
          <Legend schools={shown} types={types} on={on} measure={measure} scale={scale} present={present} legendRef={legendRef} />
          <RcoChip name={rcoFocus} onClose={() => setRcoFocus(null)} />
          {focusSchool && <SitePanel school={focusSchool} statsOf={statsOf} radius={radius} onRco={showRco} rcoFocus={rcoFocus}
            open={panelOpen} setOpen={setPanelOpen} top={64}
            onOnly={(id) => { setTypes(Object.fromEntries(TYPES.map((t) => [t.id, t.id === id]))); setRadiusOnly(false); }} />}
          <MapControls basemap={basemap} onBasemap={setBasemap} onZoomIn={() => map?.zoomIn()} onZoomOut={() => map?.zoomOut()} onHome={home} />
          <SourcesModal open={docsOpen} onClose={() => setDocsOpen(false)} sources={sources} schools={all} onDownload={download} selectionLabel={selectionLabel} />
        </>
      )}
    </div>
  );
}
