/**
 * The map's floating UI, after the Market Analysis Tool (MarketMapChrome.jsx): a compact title row with an
 * (i) card, a "Zoom to" card above a foldable left rail of tinted sections and switches, a legend docked
 * under the rail, and address search bottom-right. Presentational only: SchoolMap owns the state.
 */
import React, { useEffect, useState } from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { ActionChip, FLOAT_BTN, FoldIcon, GLASS, ICON_BTN, InfoTip, PANEL, RadioRow, SCROLL, SPRING_PANEL, SPRING_TAB, Section, Segmented, Spinner, ToggleRow, cx } from '../lib/ui';
import { CATEGORIES, CATEGORY, CATEGORY_INFO, FAMILY, GROUPS, ICONS, KEYED, LAYERS, MEASURE, MEASURES, RAMP } from '../lib/layers';
import { BASEMAPS } from './MapLayers';

export const RAIL_W = 'w-[330px] xl:w-[350px]';
const BTN = 'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition';
const BTN_QUIET = `${BTN} bg-white text-slate-700 shadow-sm ring-1 ring-stone-200 hover:bg-stone-50 hover:text-slate-900`;

// ── swatches ──────────────────────────────────────────────────────────────
export function AssetGlyph({ category, size = 18 }) {
  const c = CATEGORY[category];
  return (
    <span className="grid shrink-0 place-items-center rounded-full ring-[1.5px] ring-white" style={{ width: size, height: size, background: c.color, boxShadow: '0 0 0 1px rgba(30,30,28,.45)' }}>
      <svg viewBox="0 0 24 24" style={{ width: size * 0.6, height: size * 0.6 }} fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[c.icon]} /></svg>
    </span>
  );
}
export function Swatch({ s }) {
  if (!s) return null;
  if (s.kind === 'line') {
    const style = s.dash === 'dots' ? 'dotted' : s.dash === 'dash' ? 'dashed' : 'solid';
    return <span className="inline-block w-4 shrink-0" style={{ borderTop: `2.5px ${style} ${s.color}` }} />;
  }
  if (s.kind === 'dot') return <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-white" style={{ background: s.color, boxShadow: '0 0 0 1px rgba(30,30,28,.35)' }} />;
  if (s.kind === 'ring') return <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-white" style={{ boxShadow: `inset 0 0 0 1.5px ${s.color}` }} />;
  return <span className="h-3 w-4 shrink-0 rounded-sm" style={{ background: s.color, boxShadow: `inset 0 0 0 1.5px ${s.line || s.color}`, ...(s.dash ? { outline: `1px dashed ${s.line}`, outlineOffset: -1, boxShadow: 'none' } : null) }} />;
}

// ── title row ─────────────────────────────────────────────────────────────
export function Header({ site, slug, onSchool, measuring, onMeasure, onDownload, onHome }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-200/80 bg-white px-3 py-2 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <button type="button" onClick={onHome} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-600 text-white shadow-sm hover:bg-accent-700" title="All maps" aria-label="All maps">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12Z" /><circle cx="12" cy="9" r="2.5" /></svg>
        </button>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h1 className="truncate text-[17px] font-bold leading-tight text-ink">{site ? `${site.school} Community Map` : 'Community Map'}</h1>
            <InfoTip label="About this map">
              <span className="block font-semibold text-slate-900">How to use this map</span>
              <span className="mt-1 block">Turn layers on from the panel at left; each one says what it is under its (i). Hover anything for its name, click for details and its distance from the school.</span>
              <span className="mt-2 block">Shade census tracts by a measure under <b>Census tracts</b>; click a tract to compare it with the study area and Philadelphia.</span>
              <span className="mt-2 block text-slate-500">Data: the studio's Community Asset, Background, Transportation and Economic work (City of Philadelphia open data, ACS 5-year, SEPTA, PennDOT).</span>
            </InfoTip>
          </div>
          {site && <div className="truncate text-[12px] text-ink-2">{site.address} · Philadelphia</div>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented value={slug} onChange={onSchool} options={[{ value: 'wagner', label: 'Wagner' }, { value: 'blankenburg', label: 'Blankenburg' }]} />
        <button type="button" onClick={onMeasure} className={measuring ? `${BTN} bg-accent-600 text-white shadow-sm hover:bg-accent-700` : BTN_QUIET} title="Click points on the map to measure a distance">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0Z" /><path d="m14.5 12.5 2-2M11.5 9.5l2-2M8.5 6.5l2-2M17.5 15.5l2-2" /></svg>
          <span className="hidden sm:inline">Measure</span>
        </button>
        <button type="button" onClick={onDownload} className={BTN_QUIET} title="Download the community assets shown on the map as a CSV">
          <svg className="h-4 w-4 text-accent-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></svg>
          <span className="hidden sm:inline">Assets CSV</span>
        </button>
      </div>
    </header>
  );
}

// ── "Zoom to" card ────────────────────────────────────────────────────────
export function ZoomBar({ views, onZoom, barRef }) {
  return (
    <div ref={barRef} className={cx('absolute left-3 top-3 z-[500] max-w-[calc(100%-24px)] rounded-xl p-2 shadow-lg', RAIL_W, GLASS)}>
      <div className="px-1 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Zoom to</div>
      <div className="grid grid-cols-3 gap-1.5">
        {views.map((v) => (
          <button key={v.id} type="button" onClick={() => onZoom(v.id)} className="flex h-9 items-center justify-center rounded-lg bg-white/70 px-1.5 text-[12.5px] font-semibold text-slate-700 ring-1 ring-stone-200 transition-colors hover:bg-accent-600 hover:text-white hover:ring-accent-600">
            <span className="truncate">{v.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── left rail ─────────────────────────────────────────────────────────────
function usePersisted(key, initial) {
  const [v, setV] = useState(() => {
    try { const s = localStorage.getItem(key); return s == null ? initial : JSON.parse(s); } catch { return initial; }
  });
  const set = (nv) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)); } catch { /* storage blocked */ } };
  return [v, set];
}

function SearchField({ value, onChange, placeholder }) {
  return (
    <label className="flex items-center gap-2 rounded-lg bg-white py-1.5 pl-2.5 pr-2 ring-1 ring-stone-300 transition-shadow focus-within:shadow-[0_0_0_4px_rgba(57,56,100,0.14)] focus-within:ring-accent-300 hover:ring-stone-400">
      <svg className="h-4 w-4 shrink-0 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="h-6 min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-slate-500" />
      {value && <button type="button" onClick={() => onChange('')} className="text-[12px] font-semibold text-slate-500 hover:text-slate-900">Clear</button>}
    </label>
  );
}

export function LayersRail({
  top, reserveBottom, defaultOpen,
  assetCounts, categories, onCategory, onAllCategories, halfOnly, onHalfOnly,
  measure, onMeasure, acsYear,
  on, onToggle, loading, featureCounts,
  query, onQuery, results, onPick,
}) {
  const [open, setOpen] = usePersisted('cmap.rail', defaultOpen);
  const [sec, setSec] = usePersisted('cmap.sections', { assets: true, census: false, study: true, places: false, mobility: false, economy: false, search: false });
  const toggleSec = (k) => (v) => setSec({ ...sec, [k]: v });
  const nCats = CATEGORIES.filter((c) => categories[c.id]).length;
  const totalShown = CATEGORIES.reduce((s, c) => s + (categories[c.id] ? (halfOnly ? assetCounts[c.id]?.half : assetCounts[c.id]?.all) || 0 : 0), 0);

  return (
    <AnimatePresence initial={false} mode="popLayout">
      {open ? (
        <motion.aside
          key="rail"
          style={{ transformOrigin: 'top left', top, maxHeight: `calc(100% - ${top + 12}px - ${reserveBottom}px)` }}
          initial={{ opacity: 0, scale: 0.9, x: -14, filter: 'blur(6px)' }}
          animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: -14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }}
          transition={SPRING_PANEL}
          className={cx('absolute left-3 z-[500] flex max-w-[calc(100%-24px)] flex-col', RAIL_W, PANEL)}
        >
          <div className="flex items-center justify-between px-3 pb-1 pt-2.5">
            <div className="text-[14px] font-bold text-slate-900">Layers &amp; search</div>
            <button type="button" onClick={() => setOpen(false)} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="left" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 pb-3 pt-1', SCROLL)}>
            <Section title="Community assets" subtitle={`${totalShown.toLocaleString('en-US')} places · ${nCats} of ${CATEGORIES.length} categories on`} open={sec.assets} onOpenChange={toggleSec('assets')}>
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <ActionChip onClick={() => onAllCategories(true)} active={nCats === CATEGORIES.length}>All</ActionChip>
                <ActionChip onClick={() => onAllCategories(false)} active={nCats === 0}>None</ActionChip>
                <span className="mx-1 h-4 w-px bg-stone-200" />
                <ActionChip onClick={() => onHalfOnly(!halfOnly)} active={halfOnly}>Within ½ mile only</ActionChip>
              </div>
              <div className="space-y-1.5">
                {CATEGORIES.map((c) => {
                  const n = assetCounts[c.id];
                  return (
                    <ToggleRow key={c.id} on={!!categories[c.id]} onClick={() => onCategory(c.id)} label={c.id} info={CATEGORY_INFO[c.id]}
                      swatch={<AssetGlyph category={c.id} />} count={n ? (halfOnly ? n.half : n.all) : 0} />
                  );
                })}
              </div>
              <p className="mt-2 text-[11.5px] leading-snug text-slate-500">Color is the family ({Object.values(FAMILY).map((f) => f.label).join(', ')}); the glyph is the category. Smaller markers are beyond the half mile.</p>
            </Section>

            <Section key="census" title="Census tracts" subtitle={measure ? `Shaded by ${MEASURE[measure].label.toLowerCase()}` : `ACS ${acsYear - 4}–${acsYear} · shade tracts by a measure`} open={sec.census} onOpenChange={toggleSec('census')}>
              <div className="space-y-0.5" role="radiogroup" aria-label="Shade tracts by">
                <RadioRow on={!measure} onClick={() => onMeasure(null)} label="No shading" />
                {MEASURES.map((m) => <RadioRow key={m.id} on={measure === m.id} onClick={() => onMeasure(m.id)} label={m.label} info={m.info} />)}
              </div>
            </Section>

            {GROUPS.map((g) => {
              const layers = LAYERS.filter((l) => l.group === g.id);
              const nOn = layers.filter((l) => on[l.id]).length;
              return (
                <Section key={g.id} title={g.title} subtitle={nOn ? `${nOn} on · ${g.subtitle.toLowerCase()}` : g.subtitle} open={sec[g.id]} onOpenChange={toggleSec(g.id)}>
                  <div className="space-y-1.5">
                    {layers.map((l) => (
                      <ToggleRow key={l.id} on={!!on[l.id]} onClick={() => onToggle(l.id)} label={l.label} info={l.info} swatch={<Swatch s={l.swatch} />}
                        count={loading[l.id] ? <Spinner /> : on[l.id] && featureCounts[l.id] != null ? featureCounts[l.id].toLocaleString('en-US') : null} />
                    ))}
                  </div>
                </Section>
              );
            })}

            <Section title="Find a place" subtitle="Search assets, businesses, stops and RCOs by name or address" open={sec.search} onOpenChange={toggleSec('search')}>
              <SearchField value={query} onChange={onQuery} placeholder="A school, church, business, street…" />
              {query.length >= 2 && results.length > 0 && (
                <div className={cx('mt-2 max-h-64 overflow-y-auto rounded-lg bg-white ring-1 ring-stone-200/80', SCROLL)}>
                  {results.map((r) => (
                    <button key={r.key} type="button" onClick={() => onPick(r)} className="flex w-full items-center gap-2 border-b border-stone-100 px-3 py-2 text-left last:border-0 hover:bg-accent-50/60">
                      {r.category ? <AssetGlyph category={r.category} size={16} /> : <Swatch s={r.swatch} />}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-semibold text-slate-900">{r.name}</span>
                        <span className="block truncate text-[12px] text-slate-500">{r.sub}</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {query.length >= 2 && results.length === 0 && <p className="mt-2 text-[12px] text-slate-500">No match. Businesses and stops are searched once their layer has been turned on.</p>}
            </Section>
          </div>
        </motion.aside>
      ) : (
        <motion.button key="tab" type="button" onClick={() => setOpen(true)} initial={{ opacity: 0, scale: 0.6, x: -8 }} animate={{ opacity: 1, scale: 1, x: 0 }} exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.12 } }}
          transition={SPRING_TAB} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }} style={{ top }} className={cx('absolute left-3 z-[500] text-slate-800', FLOAT_BTN)}>
          <span className="text-slate-600"><FoldIcon side="left" closed /></span>
          Layers &amp; search
        </motion.button>
      )}
    </AnimatePresence>
  );
}

// ── legend (docked under the rail) ────────────────────────────────────────
// The legend decodes the map; the rail already names and switches every layer. So it shows the asset
// families (not the ten categories), one titled block per keyed layer, and every other active layer in a
// two-column grid under its group, each row the same height with its swatch in a fixed 16px slot.
const SHORT = {
  rco_other: 'Other RCOs', rco_covers: 'RCOs at the site', study_tracts: 'Study tracts', neighborhood: 'Neighborhood',
  bids: 'Improvement districts', transit_stops: 'Transit stop', crashes_ksi: 'Fatal / serious crash', crashes_all: 'Other crash',
  hin: 'High Injury Network', curb_ramps: 'Missing curb ramp', businesses: 'Business', affordable_housing: 'Affordable housing',
  storefront_grants: 'Storefront grant', food_access: 'Low food access', bike_share: 'Indego station', speed_cameras: 'Speed camera',
  crossing_guards: 'Crossing guard', corridors: 'Commercial corridor', parks: 'Park', bike_lanes: 'Bike lane',
};
const KEY_TITLE = { transit_lines: 'Transit lines', zoning: 'Zoning', land_use: 'Land use' };
const INCENTIVE_KEYS = [
  ['Opportunity Zone', { kind: 'fill', color: '#D99A1E22', line: '#BE731F', dash: 'dash' }],
  ['Redevelopment area', { kind: 'fill', color: '#9A57A60F', line: '#9A57A6' }],
];
const WALK_KEYS = [['5 min', '#16907A66'], ['10 min', '#16907A40'], ['15 min', '#16907A1F']];

function Key({ swatch, label, children }) {
  return (
    <span className="flex min-w-0 items-center gap-2 text-[12px] leading-5 text-slate-600">
      <span className="flex w-4 shrink-0 justify-center">{children || <Swatch s={swatch} />}</span>
      <span className="truncate">{label}</span>
    </span>
  );
}
const Block = ({ title, note, children }) => (
  <div>
    <div className="mb-1 flex items-baseline gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
      {title}{note && <span className="normal-case tracking-normal text-slate-400/90">· {note}</span>}
    </div>
    {children}
  </div>
);
const Grid = ({ children }) => <div className="grid grid-cols-2 gap-x-3">{children}</div>;

export function Legend({ categories, on, measure, scale, present = {}, legendRef }) {
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth >= 900);
  const families = Object.entries(FAMILY).filter(([f]) => CATEGORIES.some((c) => c.family === f && categories[c.id]));
  const active = LAYERS.filter((l) => on[l.id]);
  const keyed = active.filter((l) => l.keyed);
  const m = measure && MEASURE[measure];
  const fmt = m && (m.legend || m.fmt);
  const plainKey = (l) => {
    if (l.id === 'incentives') return INCENTIVE_KEYS.map(([k, s]) => <Key key={k} swatch={s} label={k} />);
    if (l.id === 'walk') return WALK_KEYS.map(([k, c]) => <Key key={k} swatch={{ kind: 'fill', color: c, line: '#16907A' }} label={`${k} walk`} />);
    return <Key key={l.id} swatch={l.swatch} label={SHORT[l.id] || l.label} />;
  };
  const groups = [
    { id: 'study', title: 'Site & study area' }, { id: 'places', title: 'Parks & corridors' },
    { id: 'mobility', title: 'Mobility & safety' }, { id: 'economy', title: 'Economy & land' },
  ].map((g) => ({ ...g, layers: active.filter((l) => l.group === g.id && !l.keyed) }));

  return (
    <div ref={legendRef} className={cx('absolute bottom-3 left-3 z-[500] flex max-h-[42%] max-w-[calc(100%-24px)] flex-col rounded-xl shadow-lg', RAIL_W, GLASS)}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-3.5 py-2.5 text-left">
        <span className="text-[13px] font-semibold text-slate-900">Legend</span>
        <span className="flex items-center gap-1 text-[12px] font-semibold text-accent-600">
          {open ? 'Hide' : 'Show'}
          <svg className={cx('h-3.5 w-3.5 transition-transform', open ? 'rotate-180' : '')} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M5.3 12.7a1 1 0 0 1 0-1.4l4-4a1 1 0 0 1 1.4 0l4 4a1 1 0 0 1-1.4 1.4L10 9.4l-3.3 3.3a1 1 0 0 1-1.4 0Z" /></svg>
        </span>
      </button>
      {open && (
        <div className={cx('min-h-0 space-y-3 overflow-y-auto border-t border-stone-100 px-3.5 pb-3 pt-2.5', SCROLL)}>
          {m && scale && scale.breaks.length > 0 && (
            <Block title="Tract shading" note={m.label}>
              <div className="flex gap-0.5">
                {RAMP.map((c, i) => <span key={c} className={cx('h-2.5 flex-1', i === 0 && 'rounded-l-sm', i === RAMP.length - 1 && 'rounded-r-sm')} style={{ background: c }} />)}
              </div>
              <div className="mt-1 flex justify-between text-[10.5px] tabular-nums text-slate-500">
                <span>{fmt(scale.min)}</span>{scale.breaks.map((b, i) => <span key={i}>{fmt(b)}</span>)}<span>{fmt(scale.max)}</span>
              </div>
            </Block>
          )}

          <Block title="Site & study area">
            <Grid>
              <Key label="School parcel"><span className="h-3 w-4 rounded-sm bg-accent-600" /></Key>
              {groups[0].layers.map(plainKey)}
            </Grid>
          </Block>

          {families.length > 0 && (
            <Block title="Community assets" note="color = family, glyph = category">
              <Grid>
                {families.map(([f, v]) => (
                  <Key key={f} label={v.label}><span className="h-3 w-3 rounded-full ring-[1.5px] ring-white" style={{ background: v.color, boxShadow: '0 0 0 1px rgba(30,30,28,.45)' }} /></Key>
                ))}
                <Key label="Small = beyond ½ mile"><span className="h-2 w-2 rounded-full bg-slate-400 ring-1 ring-white" style={{ boxShadow: '0 0 0 1px rgba(30,30,28,.35)' }} /></Key>
              </Grid>
            </Block>
          )}

          {groups.slice(1).filter((g) => g.layers.length).map((g) => (
            <Block key={g.id} title={g.title}><Grid>{g.layers.map(plainKey)}</Grid></Block>
          ))}

          {keyed.map((l) => (
            <Block key={l.id} title={KEY_TITLE[l.keyed]}>
              <Grid>
                {Object.entries(KEYED[l.keyed]).filter(([k]) => !present[l.keyed] || present[l.keyed].has(k)).map(([k, c]) => (
                  <Key key={k} label={k.split('/')[0]} swatch={l.geom === 'line' ? { kind: 'line', color: c, dash: k === 'Regional Rail' ? 'dash' : null } : { kind: 'fill', color: c }} />
                ))}
              </Grid>
            </Block>
          ))}
        </div>
      )}
    </div>
  );
}

// ── bottom-right: basemap, zoom, address search ───────────────────────────
export function MapControls({ basemap, onBasemap, onZoomIn, onZoomOut, onHome, onGeocode, geocoding, candidates, onCandidate, onClearPin, hasPin }) {
  const [q, setQ] = useState('');
  useEffect(() => { if (!q) onClearPin?.(); }, [q, onClearPin]);
  return (
    <div className="pointer-events-none absolute bottom-3 right-3 z-[500] flex max-w-[calc(100%-24px)] flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <div className={cx('pointer-events-auto flex gap-0.5 rounded-xl p-1 shadow-lg', GLASS)} role="radiogroup" aria-label="Basemap">
          {BASEMAPS.map((b) => (
            <button key={b.id} type="button" role="radio" aria-checked={basemap === b.id} onClick={() => onBasemap(b.id)}
              className={cx('whitespace-nowrap rounded-lg px-2 py-1 text-[12px] font-semibold transition', basemap === b.id ? 'bg-accent-600 text-white' : 'text-slate-600 hover:bg-stone-100 hover:text-slate-900')}>
              {b.label}
            </button>
          ))}
        </div>
        <div className="pointer-events-auto flex overflow-hidden rounded-xl shadow-lg ring-1 ring-black/5">
          {[['+', onZoomIn, 'Zoom in'], ['−', onZoomOut, 'Zoom out']].map(([t, fn, label]) => (
            <button key={t} type="button" onClick={fn} aria-label={label} className="h-8 w-8 border-r border-stone-200 bg-white/95 text-[17px] font-semibold leading-none text-slate-700 backdrop-blur hover:bg-white hover:text-slate-900">{t}</button>
          ))}
          <button type="button" onClick={onHome} aria-label="Back to the school" title="Back to the school" className="grid h-8 w-8 place-items-center bg-white/95 text-accent-600 hover:bg-white">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>
          </button>
        </div>
      </div>
      <div className={cx('pointer-events-auto w-[300px] max-w-full rounded-xl p-2 shadow-lg', GLASS)}>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) onGeocode(q.trim()); }} className="flex items-center gap-2 rounded-lg bg-white py-1.5 pl-2.5 pr-1.5 ring-1 ring-stone-300 focus-within:ring-accent-300">
          <svg className="h-4 w-4 shrink-0 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12Z" /><circle cx="12" cy="9" r="2.5" /></svg>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Drop a pin at an address…" className="h-6 min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-slate-500" aria-label="Address search" />
          {geocoding ? <Spinner /> : hasPin || q ? (
            <button type="button" onClick={() => setQ('')} className="px-1 text-[12px] font-semibold text-slate-500 hover:text-slate-900">Clear</button>
          ) : null}
          <button type="submit" className="rounded-md bg-accent-600 px-2 py-0.5 text-[12px] font-semibold text-white hover:bg-accent-700">Go</button>
        </form>
        {candidates?.length > 0 && (
          <div className="mt-1.5 max-h-48 overflow-y-auto">
            {candidates.map((c, i) => (
              <button key={i} type="button" onClick={() => onCandidate(c)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-[12.5px] text-slate-700 hover:bg-accent-50">{c.label}</button>
            ))}
          </div>
        )}
        {candidates && candidates.length === 0 && <p className="px-1 pt-1.5 text-[12px] text-slate-500">No address found in Philadelphia.</p>}
      </div>
    </div>
  );
}

export function MeasureChip({ miles, n, onUndo, onClear, onDone }) {
  return (
    <div className={cx('absolute left-1/2 top-3 z-[600] flex -translate-x-1/2 items-center gap-3 rounded-xl px-3.5 py-2 shadow-lg', GLASS)}>
      <div className="text-[13px] text-slate-700">
        {n < 2 ? <span>Click the map to start measuring</span> : (
          <span><b className="tabular-nums text-slate-900">{miles < 0.19 ? `${Math.round(miles * 5280).toLocaleString('en-US')} ft` : `${miles.toFixed(2)} mi`}</b> · about <b className="tabular-nums text-slate-900">{Math.max(1, Math.round((miles * 1609.344) / 80))} min</b> walk</span>
        )}
      </div>
      <div className="flex gap-1">
        {n > 0 && <button type="button" onClick={onUndo} className="rounded-md px-2 py-0.5 text-[12px] font-semibold text-slate-600 hover:bg-stone-100">Undo</button>}
        {n > 0 && <button type="button" onClick={onClear} className="rounded-md px-2 py-0.5 text-[12px] font-semibold text-slate-600 hover:bg-stone-100">Clear</button>}
        <button type="button" onClick={onDone} className="rounded-md bg-accent-600 px-2 py-0.5 text-[12px] font-semibold text-white hover:bg-accent-700">Done</button>
      </div>
    </div>
  );
}
