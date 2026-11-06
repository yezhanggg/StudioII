/**
 * One school's community map (the Market Analysis Tool's MarketAnalyzer): owns all state, loads each
 * layer's file the first time it is turned on, and hands presentational pieces what they need.
 */
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MapContainer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AssetLayer, Basemap, Choropleth, GeoLayer, MapBridge, MeasureLayer, Panes, PinLayer, SiteLayer, SiteShape, pathMiles } from './MapLayers';
import { Header, LayersRail, Legend, MapControls, MeasureChip, ZoomBar } from './Chrome';
import SitePanel from './SitePanel';
import { CATEGORIES, LAYERS, LAYER, assetPopup, popupHtml, quantiles, rcoPopup } from '../lib/layers';

const ALL_CATS = Object.fromEntries(CATEGORIES.map((c) => [c.id, true]));
const DEFAULT_ON = Object.fromEntries(LAYERS.filter((l) => l.defaultOn).map((l) => [l.id, true]));
const VIEWS = [
  { id: 'site', label: 'School site' }, { id: 'half', label: '½ mile' }, { id: 'mile', label: '1 mile' },
  { id: 'walk', label: '15-min walk' }, { id: 'neighborhood', label: 'Neighborhood' }, { id: 'tracts', label: 'Study tracts' },
];
// Search covers these files once loaded (assets always are).
const SEARCHABLE = {
  businesses: { label: 'Business', swatch: LAYER.businesses.swatch, layer: 'businesses', sub: (p) => [p.kind, p.address].filter(Boolean).join(' · '), popup: LAYER.businesses.popup },
  transit_stops: { label: 'Stop', swatch: LAYER.transit_stops.swatch, layer: 'transit_stops', sub: (p) => `${p.mode} stop · ${p.departures ?? '?'} weekday departures`, popup: LAYER.transit_stops.popup },
  affordable_housing: { label: 'Housing', swatch: LAYER.affordable_housing.swatch, layer: 'affordable_housing', sub: (p) => `Affordable housing · ${p.units ?? '?'} units`, popup: LAYER.affordable_housing.popup },
  parks: { label: 'Park', swatch: LAYER.parks.swatch, layer: 'parks', sub: () => 'Park', popup: LAYER.parks.popup },
  corridors: { label: 'Corridor', swatch: LAYER.corridors.swatch, layer: 'corridors', sub: () => 'Commercial corridor', popup: LAYER.corridors.popup },
  rco: { label: 'RCO', swatch: LAYER.rco_covers.swatch, layer: null, sub: (p) => `Registered community organization${p.covers ? ' · covers the site' : ''}`, popup: rcoPopup },
};
const isWide = () => typeof window !== 'undefined' && window.innerWidth >= 900;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function featureCenter(f) {
  if (f.geometry.type === 'Point') return [f.geometry.coordinates[1], f.geometry.coordinates[0]];
  const c = L.geoJSON(f).getBounds().getCenter();
  return [c.lat, c.lng];
}

function csvCell(v) {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export default function SchoolMap({ slug, onSchool, onHome }) {
  const [site, setSite] = useState(null);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState({});          // file name -> FeatureCollection (for this school)
  const [loadingFiles, setLoadingFiles] = useState({});
  const [on, setOn] = useState(DEFAULT_ON);
  const [categories, setCategories] = useState(ALL_CATS);
  const [halfOnly, setHalfOnly] = useState(false);
  const [measure, setMeasure] = useState(null);
  const [basemap, setBasemap] = useState('soft');
  const [tract, setTract] = useState(null);
  const [panelOpen, setPanelOpen] = useState(isWide);
  const [tab, setTab] = useState('site');
  const [query, setQuery] = useState('');
  const [pin, setPin] = useState(null);
  const [geocoding, setGeocoding] = useState(false);
  const [candidates, setCandidates] = useState(null);
  const [measuring, setMeasuring] = useState(false);
  const [mPoints, setMPoints] = useState([]);
  const [map, setMap] = useState(null);
  const barRef = useRef(null);
  const legendRef = useRef(null);
  const [railTop, setRailTop] = useState(100);
  const [legendH, setLegendH] = useState(120);

  // ── load the school ─────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    setSite(null); setFiles({}); setLoadingFiles({}); setTract(null); setPin(null); setCandidates(null); setQuery(''); setMPoints([]); setError(null);
    Promise.all([getJSON(`/data/${slug}/site.json`), getJSON(`/data/${slug}/assets.json`)])
      .then(([s, a]) => { if (alive) { setSite(s); setFiles({ assets: a }); document.title = `${s.school} Community Map`; } })
      .catch((e) => alive && setError(String(e)));
    return () => { alive = false; };
  }, [slug]);

  const ensure = useCallback((file) => {
    if (!file || files[file] || loadingFiles[file]) return;
    setLoadingFiles((s) => ({ ...s, [file]: true }));
    getJSON(`/data/${slug}/${file}.json`)
      .then((d) => setFiles((s) => ({ ...s, [file]: d })))
      .catch((e) => console.error(e))
      .finally(() => setLoadingFiles((s) => ({ ...s, [file]: false })));
  }, [files, loadingFiles, slug]);

  // Files the current view needs
  useEffect(() => {
    if (!site) return;
    LAYERS.forEach((l) => on[l.id] && l.file && ensure(l.file));
    if (measure) ensure('tracts');
    if (query.length >= 2) ensure('rco');
  }, [site, on, measure, query, ensure]);

  // ── layout: rail starts under the Zoom-to card and stops above the legend ──
  useLayoutEffect(() => {
    const ro = new ResizeObserver(() => {
      if (barRef.current) setRailTop(barRef.current.offsetTop + barRef.current.offsetHeight + 8);
      if (legendRef.current) setLegendH(legendRef.current.offsetHeight + 20);
    });
    if (barRef.current) ro.observe(barRef.current);
    if (legendRef.current) ro.observe(legendRef.current);
    return () => ro.disconnect();
  }, [site]);

  // ── map helpers ─────────────────────────────────────────────────────────
  const pad = useCallback(() => (isWide()
    ? { paddingTopLeft: [380, 30], paddingBottomRight: [panelOpen ? 390 : 30, 30] }
    : { padding: [20, 20] }), [panelOpen]);
  const fit = useCallback((geo) => { if (map && geo) map.fitBounds(L.geoJSON(geo).getBounds(), { ...pad(), maxZoom: 17 }); }, [map, pad]);
  const home = useCallback(() => site && fit(site.half_mile), [site, fit]);

  useEffect(() => { if (map && site) { map.invalidateSize(); home(); } }, [map, site]); // eslint-disable-line react-hooks/exhaustive-deps

  const pendingZoom = useRef(null);
  const onZoom = (id) => {
    if (!site || !map) return;
    if (id === 'site') map.flyTo(site.center, 18, { duration: 0.8 });
    if (id === 'half') fit(site.half_mile);
    if (id === 'mile') fit(site.one_mile);
    if (id === 'neighborhood') { setOn((s) => ({ ...s, neighborhood: true })); fit(site.neighborhood); }
    if (id === 'walk') { setOn((s) => ({ ...s, walk: true })); if (files.walk) fit(files.walk); else { pendingZoom.current = 'walk'; ensure('walk'); } }
    if (id === 'tracts') {
      setOn((s) => ({ ...s, study_tracts: true }));
      if (files.tracts) fit({ type: 'FeatureCollection', features: files.tracts.features.filter((f) => f.properties.study) });
      else { pendingZoom.current = 'tracts'; ensure('tracts'); }
    }
  };
  useEffect(() => {
    const z = pendingZoom.current;
    if (z === 'walk' && files.walk) { pendingZoom.current = null; fit(files.walk); }
    if (z === 'tracts' && files.tracts) { pendingZoom.current = null; fit({ type: 'FeatureCollection', features: files.tracts.features.filter((f) => f.properties.study) }); }
  }, [files, fit]);

  // ── derived ─────────────────────────────────────────────────────────────
  const featureCounts = useMemo(() => Object.fromEntries(LAYERS.filter((l) => l.file && files[l.file]).map((l) => {
    const fs = files[l.file].features;
    return [l.id, l.filter ? fs.filter((f) => l.filter(f.properties)).length : fs.length];
  })), [files]);
  const loading = useMemo(() => Object.fromEntries(LAYERS.map((l) => [l.id, !!(l.file && loadingFiles[l.file])])), [loadingFiles]);
  // Which keyed classes (transit modes, zoning groups, land uses) exist here, so the legend lists only those.
  const present = useMemo(() => {
    const field = { transit_lines: 'mode', zoning: 'group', land_use: 'use' };
    return Object.fromEntries(Object.entries(field).filter(([f]) => files[f]).map(([f, k]) => [f, new Set(files[f].features.map((x) => x.properties[k]))]));
  }, [files]);
  const scale = useMemo(() => (measure && files.tracts ? quantiles(files.tracts.features.map((f) => f.properties[measure])) : null), [measure, files.tracts]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const out = [];
    const hit = (p) => `${p.name || ''} ${p.address || ''} ${p.kind || ''}`.toLowerCase().includes(q);
    files.assets?.features.forEach((f, i) => {
      const p = f.properties;
      if (hit(p)) out.push({ key: `a${i}`, name: p.name, sub: [p.kind, p.address].filter(Boolean).join(' · '), category: p.category, f, html: assetPopup(p) });
    });
    Object.entries(SEARCHABLE).forEach(([file, s]) => files[file]?.features.forEach((f, i) => {
      const p = f.properties;
      if (p.name && hit(p)) out.push({ key: `${file}${i}`, name: p.name, sub: s.sub(p), swatch: s.swatch, f, html: s.popup ? s.popup(p) : popupHtml({ title: p.name }), layer: s.layer });
    }));
    return out.slice(0, 40);
  }, [query, files]);

  const onPick = (r) => {
    if (r.category) setCategories((c) => ({ ...c, [r.category]: true }));
    if (r.category && halfOnly && !r.f.properties.half) setHalfOnly(false);
    if (r.layer) setOn((s) => ({ ...s, [r.layer]: true }));
    const ll = featureCenter(r.f);
    setPin({ latlng: ll, label: r.name, html: r.html });
    map?.flyTo(ll, Math.max(map.getZoom(), 17), { duration: 0.8 });
  };

  const onGeocode = async (q) => {
    if (!site) return;
    setGeocoding(true); setCandidates(null);
    try {
      const u = new URL('https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates');
      u.search = new URLSearchParams({ f: 'json', SingleLine: /philadelphia|phila\b|, pa\b/i.test(q) ? q : `${q}, Philadelphia, PA`, maxLocations: '5', location: `${site.center[1]},${site.center[0]}`, outFields: 'Match_addr' }).toString();
      const d = await getJSON(u.toString());
      const cands = (d.candidates || []).filter((c) => c.score >= 80).map((c) => ({ label: c.address, latlng: [c.location.y, c.location.x] }));
      if (cands.length === 1) { pickCandidate(cands[0]); setCandidates(null); } else setCandidates(cands);
    } catch (e) {
      console.error(e); setCandidates([]);
    } finally { setGeocoding(false); }
  };
  const pickCandidate = (c) => {
    setCandidates(null);
    setPin({ latlng: c.latlng, label: c.label, kind: 'Searched address' });
    map?.flyTo(c.latlng, 17, { duration: 0.8 });
  };
  const clearPin = useCallback(() => { setPin(null); setCandidates(null); }, []);

  // Zoning and land use are both full-coverage fills; one at a time keeps the map readable.
  const EXCLUSIVE = { zoning: 'land_use', land_use: 'zoning' };
  const toggleLayer = (id) => setOn((s) => {
    const next = { ...s, [id]: !s[id] };
    if (next[id] && EXCLUSIVE[id]) next[EXCLUSIVE[id]] = false;
    return next;
  });
  const onTract = useCallback((p) => { setTract(p); setTab('tract'); setPanelOpen(true); }, []);
  const addPoint = useCallback((p) => setMPoints((s) => [...s, p]), []);

  const download = () => {
    if (!files.assets || !site) return;
    const cols = ['category', 'kind', 'name', 'address', 'detail', 'phone', 'website', 'miles', 'half', 'source'];
    const rows = files.assets.features.map((f) => f.properties).filter((p) => categories[p.category] && (!halfOnly || p.half));
    const lines = [[...cols.map((c) => (c === 'half' ? 'within_half_mile' : c)), 'latitude', 'longitude'].join(',')];
    files.assets.features.forEach((f) => {
      const p = f.properties;
      if (!rows.includes(p)) return;
      lines.push([...cols.map((c) => csvCell(p[c])), f.geometry.coordinates[1], f.geometry.coordinates[0]].join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${site.school}_Community_Assets${halfOnly ? '_half_mile' : ''}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  const siteStyles = useMemo(() => Object.fromEntries(['half_mile', 'one_mile', 'neighborhood'].map((id) => [id, LAYER[id].style])), []);

  if (error) return <div className="grid h-full place-items-center p-6 text-center text-slate-600">Could not load the map data ({error}).</div>;

  return (
    <div className="flex h-full flex-col">
      <Header site={site} slug={slug} onSchool={onSchool} onHome={onHome} measuring={measuring}
        onMeasure={() => { setMeasuring((m) => !m); setMPoints([]); }} onDownload={download} />
      <div className="relative min-h-0 flex-1">
        <MapContainer center={[39.99, -75.16]} zoom={13} zoomControl={false} className="h-full w-full" maxZoom={20} attributionControl>
          <Panes />
          <MapBridge onReady={setMap} />
          <Basemap id={basemap} />
          {site && (
            <>
              {measure && files.tracts && <Choropleth data={files.tracts} measure={measure} selectedId={tract?.geoid} onTract={onTract} />}
              {LAYERS.filter((l) => on[l.id] && l.file && files[l.file]).map((l) => (
                <GeoLayer key={l.id} def={l} data={files[l.file]} center={site.center} onTract={onTract} />
              ))}
              {['half_mile', 'one_mile', 'neighborhood'].map((id) => on[id] && <SiteShape key={id} geometry={site[id]} style={siteStyles[id]} />)}
              <SiteLayer site={site} />
              <AssetLayer data={files.assets} categories={categories} halfOnly={halfOnly} center={site.center} />
              <PinLayer pin={pin} center={site.center} />
              <MeasureLayer active={measuring} points={mPoints} onAdd={addPoint} />
            </>
          )}
        </MapContainer>

        {!site && <div className="pointer-events-none absolute inset-0 z-[700] grid place-items-center"><div className="rounded-xl bg-white/95 px-4 py-2 text-[13px] font-semibold text-slate-600 shadow-lg">Loading map…</div></div>}

        {site && (
          <>
            <ZoomBar views={VIEWS} onZoom={onZoom} barRef={barRef} />
            <LayersRail
              top={railTop} reserveBottom={legendH} defaultOpen={isWide()}
              assetCounts={site.asset_counts} categories={categories}
              onCategory={(id) => setCategories((c) => ({ ...c, [id]: !c[id] }))}
              onAllCategories={(v) => setCategories(Object.fromEntries(CATEGORIES.map((c) => [c.id, v])))}
              halfOnly={halfOnly} onHalfOnly={setHalfOnly}
              measure={measure} onMeasure={setMeasure} acsYear={site.acs_year}
              on={on} onToggle={toggleLayer} loading={loading} featureCounts={featureCounts}
              query={query} onQuery={setQuery} results={results} onPick={onPick}
            />
            <Legend categories={categories} on={on} measure={measure} scale={scale} present={present} legendRef={legendRef} />
            <SitePanel site={site} tract={tract} onClearTract={() => { setTract(null); setTab('site'); }} open={panelOpen} setOpen={setPanelOpen} tab={tab} setTab={setTab}
              onOnly={(id) => { setCategories(Object.fromEntries(CATEGORIES.map((c) => [c.id, c.id === id]))); }} />
            <MapControls basemap={basemap} onBasemap={setBasemap} onZoomIn={() => map?.zoomIn()} onZoomOut={() => map?.zoomOut()} onHome={home}
              onGeocode={onGeocode} geocoding={geocoding} candidates={candidates} onCandidate={pickCandidate} onClearPin={clearPin} hasPin={!!pin} />
            {measuring && (
              <MeasureChip miles={pathMiles(mPoints)} n={mPoints.length} onUndo={() => setMPoints((s) => s.slice(0, -1))} onClear={() => setMPoints([])} onDone={() => { setMeasuring(false); setMPoints([]); }} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
