/**
 * The map's floating UI, in the Market Analysis Tool's design language, written for people who have never used
 * a map tool: a school bar along the top, "How far to look" above a left panel of five large groups and a few
 * map layers, a legend under it, basemaps and zoom bottom-right, a first-visit guide, and the Sources & data
 * window. Presentational only.
 */
import React, { useEffect, useState } from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { FLOAT_BTN, FoldIcon, GLASS, ICON_BTN, InfoTip, PANEL, SCROLL, SPRING_PANEL, SPRING_TAB, Segmented, Spinner, cx } from '../lib/ui';
import { ASSET_GROUPS, GROUP, ICONS, KEYED, LAYERS, MEASURE, MEASURES, RAMP, TYPE, TYPES, fmtInt, fmtRadius, href } from '../lib/layers';
import { BASEMAPS } from './MapLayers';

export const RAIL_W = 'w-[320px] xl:w-[340px]';

// ── swatches ──────────────────────────────────────────────────────────────
export function Glyph({ icon, color, size = 18 }) {
  return (
    <span className="grid shrink-0 place-items-center rounded-full ring-[1.5px] ring-white" style={{ width: size, height: size, background: color, boxShadow: '0 0 0 1px rgba(30,30,28,.4)' }}>
      <svg viewBox="0 0 24 24" style={{ width: size * 0.62, height: size * 0.62 }} fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[icon]} /></svg>
    </span>
  );
}
export const TypeGlyph = ({ type, size = 18 }) => (TYPE[type] ? <Glyph icon={TYPE[type].icon} color={TYPE[type].color} size={size} /> : null);
const GROUP_ICON = { food: 'cart', health: 'plus', learning: 'book', community: 'tree', more: 'dots' };
export const GroupGlyph = ({ group, size = 18 }) => <Glyph icon={GROUP_ICON[group]} color={GROUP[group].color} size={size} />;

export function Swatch({ s }) {
  if (!s) return null;
  if (s.kind === 'line') {
    const style = s.dash === 'dots' ? 'dotted' : s.dash === 'dash' ? 'dashed' : 'solid';
    return <span className="inline-block w-4 shrink-0" style={{ borderTop: `2.5px ${style} ${s.color}` }} />;
  }
  if (s.kind === 'dot') return <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-white" style={{ background: s.color, boxShadow: '0 0 0 1px rgba(30,30,28,.35)' }} />;
  if (s.kind === 'ring') return <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-white" style={{ boxShadow: `inset 0 0 0 1.5px ${s.color}` }} />;
  return <span className="h-3 w-4 shrink-0 rounded-sm" style={{ background: s.color, border: `1.5px ${s.dash ? 'dashed' : 'solid'} ${s.line || s.color}` }} />;
}
export const SchoolDot = ({ color, size = 10 }) => <span className="shrink-0 rounded-full ring-2 ring-white" style={{ width: size, height: size, background: color, boxShadow: '0 0 0 1px rgba(30,30,28,.3)' }} />;

const Switch = ({ on }) => (
  <span className={cx('relative inline-block h-5 w-9 shrink-0 rounded-full transition-colors', on ? 'bg-accent-600' : 'bg-stone-300')}>
    <span className={cx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[18px]' : 'translate-x-0.5')} />
  </span>
);

// ── top: the schools, and the documentation ───────────────────────────────
const FINALISTS = ['wagner', 'blankenburg'];
export function SchoolBar({ schools, visible, onAll, onOnly, onSources }) {
  const all = visible.length === schools.length;
  const only = visible.length === 1 ? visible[0] : null;
  const btn = (on) => cx('relative flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold transition-colors', on ? 'text-white' : 'text-slate-700 hover:bg-stone-100 hover:text-slate-900');
  const School = ({ s, quiet }) => {
    const on = only === s.slug;
    return (
      <button type="button" role="radio" aria-checked={on} onClick={() => onOnly(s.slug)} title={s.name} className={btn(on)}>
        {on && <motion.span layoutId="school-on" transition={SPRING_TAB} className="absolute inset-0 rounded-lg shadow-sm" style={{ background: s.color }} />}
        <span className="relative flex items-center gap-1.5">{!on && <SchoolDot color={s.color} size={9} />}<span className={cx(!on && quiet && 'font-medium text-slate-500')}>{s.short}</span></span>
      </button>
    );
  };
  return (
    <div className={cx('absolute left-3 right-3 top-[172px] z-[520] flex w-fit max-w-[calc(100%-24px)] items-center gap-1 overflow-x-auto rounded-xl p-1 shadow-lg md:left-[352px] md:top-3 md:max-w-[calc(100%-364px)]', GLASS, SCROLL)} role="radiogroup" aria-label="Schools on the map">
      {schools.filter((s) => FINALISTS.includes(s.slug)).map((s) => <School key={s.slug} s={s} />)}
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      {schools.filter((s) => !FINALISTS.includes(s.slug)).map((s) => <School key={s.slug} s={s} quiet />)}
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      <button type="button" role="radio" aria-checked={all} onClick={onAll} className={btn(all)}>
        {all && <motion.span layoutId="school-on" transition={SPRING_TAB} className="absolute inset-0 rounded-lg bg-accent-600 shadow-sm" />}
        <span className="relative">All six</span>
      </button>
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      <button type="button" onClick={onSources} className="flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold text-accent-600 hover:bg-accent-50">
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
        Sources &amp; data
      </button>
    </div>
  );
}

// ── how far to look ───────────────────────────────────────────────────────
const PRESETS = [[0.25, '¼'], [0.5, '½'], [0.75, '¾'], [1, '1']];
const VIEWS = [['site', 'School'], ['radius', 'Ring'], ['catchment', 'Attendance'], ['walk', 'Walk']];
export function RadiusCard({ radius, onRadius, onZoom, barRef }) {
  return (
    <div ref={barRef} className={cx('absolute left-3 top-3 z-[500] max-w-[calc(100%-24px)] rounded-xl p-3 shadow-lg', RAIL_W, GLASS)}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor="radius" className="text-[13px] font-bold text-slate-900">How far to look</label>
        <span className="text-[12px] text-slate-500">about a {Math.round((radius * 1609.344) / 80)}-minute walk</span>
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        {PRESETS.map(([r, l]) => (
          <button key={r} type="button" onClick={() => onRadius(r)} className={cx('h-8 flex-1 rounded-lg text-[13px] font-semibold ring-1 transition', Math.abs(radius - r) < 0.001 ? 'bg-accent-600 text-white ring-accent-600' : 'bg-white text-slate-700 ring-stone-200 hover:ring-stone-300')}>
            {l} mile
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <input id="radius" type="range" min={0.1} max={1.5} step={0.05} value={radius} onChange={(e) => onRadius(Number(e.target.value))} className="radius-range min-w-0 flex-1" aria-label="Distance from the school in miles" />
        <span className="w-[52px] shrink-0 text-right text-[13px] font-bold tabular-nums text-slate-900">{fmtRadius(radius)}</span>
      </div>
      <div className="mt-2.5 flex items-center gap-1.5">
        <span className="shrink-0 text-[11.5px] font-semibold text-slate-500">Zoom to</span>
        {VIEWS.map(([id, label]) => (
          <button key={id} type="button" onClick={() => onZoom(id)} className="h-7 flex-auto whitespace-nowrap rounded-md bg-white/70 px-1.5 text-[11.5px] font-semibold text-slate-700 ring-1 ring-stone-200 transition-colors hover:bg-accent-600 hover:text-white hover:ring-accent-600">{label}</button>
        ))}
      </div>
    </div>
  );
}

// ── left panel: what to show ──────────────────────────────────────────────
function usePersisted(key, initial) {
  const [v, setV] = useState(() => {
    try { const s = localStorage.getItem(key); return s == null ? initial : { ...initial, ...JSON.parse(s) }; } catch { return initial; }
  });
  const set = (nv) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)); } catch { /* storage blocked */ } };
  return [v, set];
}

function GroupCard({ g, types, counts, onType, onGroup, open, onOpen }) {
  const list = TYPES.filter((t) => t.group === g.id);
  const nOn = list.filter((t) => types[t.id]).length;
  const on = nOn > 0;
  const total = list.reduce((s, t) => s + (counts[t.id] || 0), 0);
  return (
    <div className={cx('rounded-xl bg-white ring-1 transition', on ? 'ring-stone-200' : 'ring-stone-200/70')}>
      <button type="button" onClick={() => onGroup(g.id, !on)} aria-pressed={on} className="flex w-full items-center gap-2.5 px-3 pb-1.5 pt-2.5 text-left">
        <span className={cx('transition-opacity', !on && 'opacity-40')}><GroupGlyph group={g.id} size={28} /></span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5"><span className="text-[14.5px] font-bold text-slate-900">{g.label}</span><span className="text-[12px] font-semibold tabular-nums text-slate-500">{fmtInt(total)}</span></span>
          <span className="block truncate text-[12px] text-slate-500">{g.examples}</span>
        </span>
        <Switch on={on} />
      </button>
      <button type="button" onClick={onOpen} aria-expanded={open} className="flex w-full items-center gap-1 px-3 pb-2 pl-[50px] text-left text-[12px] font-semibold text-accent-600 hover:underline">
        {open ? 'Hide types' : `Choose types${nOn && nOn < list.length ? ` (${nOn} of ${list.length} on)` : ''}`}
      </button>
      {open && (
        <div className="space-y-0.5 border-t border-stone-100 px-2 py-1.5">
          {list.map((t) => (
            <label key={t.id} className="flex cursor-pointer items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-stone-50">
              <input type="checkbox" checked={!!types[t.id]} onChange={() => onType(t.id)} className="h-4 w-4 shrink-0 rounded accent-[#393864]" />
              <TypeGlyph type={t.id} size={18} />
              <span className="min-w-0 flex-1 truncate text-[13px] text-slate-800">{t.label}</span>
              <InfoTip label={`About ${t.label}`}>{t.info}</InfoTip>
              <span className="w-8 shrink-0 text-right text-[12px] font-semibold tabular-nums text-slate-500">{fmtInt(counts[t.id] || 0)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function LayerRow({ l, on, onToggle, loading }) {
  return (
    <button type="button" aria-pressed={on} onClick={() => onToggle(l.id)} className={cx('flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition', on ? 'bg-accent-50/60' : 'hover:bg-stone-50')}>
      <span className="flex w-4 shrink-0 justify-center"><Swatch s={l.swatch} /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-slate-900">{l.label}</span>
        {l.caption && <span className="block truncate text-[11.5px] text-slate-500">{l.caption}</span>}
      </span>
      {loading ? <Spinner /> : <Switch on={on} />}
    </button>
  );
}

export function LayersRail({
  top, reserveBottom, defaultOpen, radius,
  typeCounts, types, onType, onGroup, radiusOnly, onRadiusOnly,
  measure, onMeasure, on, onToggle, loading,
  query, onQuery, results, onPick,
}) {
  const [st, setSt] = usePersisted('cmap.rail4', { open: defaultOpen, openGroup: null, more: false, layers: true });
  const basic = LAYERS.filter((l) => l.basic);
  const more = LAYERS.filter((l) => !l.basic);
  const moreOn = more.filter((l) => on[l.id]).length + (measure ? 1 : 0);

  return (
    <AnimatePresence initial={false} mode="popLayout">
      {st.open ? (
        <motion.aside key="rail" style={{ transformOrigin: 'top left', top, maxHeight: `calc(100% - ${top + 12}px - ${reserveBottom}px)` }}
          initial={{ opacity: 0, scale: 0.9, x: -14, filter: 'blur(6px)' }} animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: -14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }} transition={SPRING_PANEL}
          className={cx('absolute left-3 z-[500] flex max-w-[calc(100%-24px)] flex-col', RAIL_W, PANEL)}>
          <div className="flex items-center gap-2 px-3 pb-2 pt-2.5">
            <label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg bg-white py-1.5 pl-2.5 pr-2 ring-1 ring-stone-300 focus-within:ring-accent-300">
              <svg className="h-4 w-4 shrink-0 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Find a place by name or street" className="h-6 min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-slate-500" />
              {query && <button type="button" onClick={() => onQuery('')} className="text-[12px] font-semibold text-slate-500 hover:text-slate-900">Clear</button>}
            </label>
            <button type="button" onClick={() => setSt({ ...st, open: false })} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="left" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-3', SCROLL)}>
            {query.length >= 2 && (
              <div className={cx('max-h-64 overflow-y-auto rounded-lg bg-white ring-1 ring-stone-200/80', SCROLL)}>
                {results.length ? results.map((r) => (
                  <button key={r.key} type="button" onClick={() => onPick(r)} className="flex w-full items-center gap-2 border-b border-stone-100 px-3 py-2 text-left last:border-0 hover:bg-accent-50/60">
                    <span className="flex w-4 shrink-0 justify-center">{r.type ? <TypeGlyph type={r.type} size={16} /> : <Swatch s={r.swatch} />}</span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold text-slate-900">{r.name}</span><span className="block truncate text-[12px] text-slate-500">{r.sub}</span></span>
                  </button>
                )) : <p className="px-3 py-2 text-[12px] text-slate-500">Nothing by that name near the schools on the map.</p>}
              </div>
            )}

            <div>
              <div className="mb-1.5 flex items-center justify-between px-0.5">
                <h2 className="text-[13px] font-bold text-slate-900">Places to show</h2>
                <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-slate-600">
                  <input type="checkbox" checked={radiusOnly} onChange={() => onRadiusOnly(!radiusOnly)} className="h-3.5 w-3.5 accent-[#393864]" />
                  only within {fmtRadius(radius)}
                </label>
              </div>
              <div className="space-y-2">
                {ASSET_GROUPS.map((g) => (
                  <GroupCard key={g.id} g={g} types={types} counts={typeCounts} onType={onType} onGroup={onGroup}
                    open={st.openGroup === g.id} onOpen={() => setSt({ ...st, openGroup: st.openGroup === g.id ? null : g.id })} />
                ))}
              </div>
            </div>

            <div>
              <h2 className="mb-1 px-0.5 text-[13px] font-bold text-slate-900">Map layers</h2>
              <div className="rounded-xl bg-white p-1 ring-1 ring-stone-200">
                {basic.map((l) => <LayerRow key={l.id} l={l} on={!!on[l.id]} onToggle={onToggle} loading={loading[l.id]} />)}
                <button type="button" onClick={() => setSt({ ...st, more: !st.more })} aria-expanded={st.more} className="mt-0.5 w-full rounded-lg px-2 py-1.5 text-left text-[12px] font-semibold text-accent-600 hover:bg-stone-50">
                  {st.more ? 'Fewer layers' : `More layers${moreOn ? ` (${moreOn} on)` : ''}: zoning, land use, housing, vacant land…`}
                </button>
                {st.more && (
                  <div className="border-t border-stone-100 pt-1">
                    {more.map((l) => <LayerRow key={l.id} l={l} on={!!on[l.id]} onToggle={onToggle} loading={loading[l.id]} />)}
                    <label className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
                      <span className="h-3 w-4 shrink-0 rounded-sm" style={{ background: `linear-gradient(90deg, ${RAMP[0]}, ${RAMP[4]})` }} />
                      <span className="min-w-0 flex-1"><span className="block text-[13px] font-semibold text-slate-900">Shade neighborhoods by</span><span className="block text-[11.5px] text-slate-500">Census figures for each tract</span></span>
                      <select value={measure || ''} onChange={(e) => onMeasure(e.target.value || null)} className="w-[118px] rounded-md bg-stone-50 px-1 py-1 text-[12px] text-slate-700 ring-1 ring-stone-200 focus:outline-none">
                        <option value="">Nothing</option>
                        {MEASURES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            </div>
          </div>
        </motion.aside>
      ) : (
        <motion.button key="tab" type="button" onClick={() => setSt({ ...st, open: true })} initial={{ opacity: 0, scale: 0.6, x: -8 }} animate={{ opacity: 1, scale: 1, x: 0 }} exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.12 } }}
          transition={SPRING_TAB} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }} style={{ top }} className={cx('absolute left-3 z-[500] text-slate-800', FLOAT_BTN)}>
          <span className="text-slate-600"><FoldIcon side="left" closed /></span>
          Places &amp; layers
        </motion.button>
      )}
    </AnimatePresence>
  );
}

// ── legend (under the left panel) ─────────────────────────────────────────
const KEY_TITLE = { transit_lines: 'Train & trolley lines', zoning: 'Zoning', land_use: 'Land use', housing: 'Housing' };
function Key({ swatch, label, children }) {
  return (
    <span className="flex min-w-0 items-center gap-2 text-[12px] leading-5 text-slate-600">
      <span className="flex w-4 shrink-0 justify-center">{children || <Swatch s={swatch} />}</span>
      <span className="truncate">{label}</span>
    </span>
  );
}
const Block = ({ title, children }) => (<div><div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">{title}</div>{children}</div>);
const Grid = ({ children }) => <div className="grid grid-cols-2 gap-x-3">{children}</div>;

export function Legend({ schools, types, on, measure, scale, present = {}, legendRef }) {
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth >= 900);
  const groups = ASSET_GROUPS.filter((g) => TYPES.some((t) => t.group === g.id && types[t.id]));
  const active = LAYERS.filter((l) => on[l.id]);
  const m = measure && MEASURE[measure];
  const fmt = m && (m.legend || m.fmt);
  const swatchOf = (l) => (['radius', 'catchment', 'neighborhood'].includes(l.id) ? { ...l.swatch, color: l.id === 'catchment' ? '#57564E14' : '#57564E', line: '#57564E' } : l.swatch);
  return (
    <div ref={legendRef} className={cx('absolute bottom-3 left-3 z-[500] flex max-h-[34%] max-w-[calc(100%-24px)] flex-col rounded-xl shadow-lg', RAIL_W, GLASS)}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-3.5 py-2 text-left">
        <span className="text-[13px] font-semibold text-slate-900">What the colors mean</span>
        <span className="text-[12px] font-semibold text-accent-600">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <div className={cx('min-h-0 space-y-2.5 overflow-y-auto border-t border-stone-100 px-3.5 pb-3 pt-2', SCROLL)}>
          <Block title="Places">
            <Grid>
              {groups.map((g) => <Key key={g.id} label={g.label}><GroupGlyph group={g.id} size={14} /></Key>)}
              <Key label="Small dot = farther away"><span className="h-2 w-2 rounded-full bg-slate-400 ring-1 ring-white" /></Key>
            </Grid>
          </Block>
          <Block title="Schools"><Grid>{schools.map((s) => <Key key={s.slug} label={s.short}><span className="h-3 w-3 rounded-sm" style={{ background: s.color }} /></Key>)}</Grid></Block>
          {m && scale && scale.breaks.length > 0 && (
            <Block title={`Shading · ${m.label}`}>
              <div className="flex gap-0.5">{RAMP.map((c, i) => <span key={c} className={cx('h-2.5 flex-1', i === 0 && 'rounded-l-sm', i === RAMP.length - 1 && 'rounded-r-sm')} style={{ background: c }} />)}</div>
              <div className="mt-1 flex justify-between text-[10.5px] tabular-nums text-slate-500"><span>{fmt(scale.min)}</span>{scale.breaks.map((b, i) => <span key={i}>{fmt(b)}</span>)}<span>{fmt(scale.max)}</span></div>
            </Block>
          )}
          {active.filter((l) => !l.keyed).length > 0 && <Block title="Map layers"><Grid>{active.filter((l) => !l.keyed).map((l) => <Key key={l.id} swatch={swatchOf(l)} label={l.label} />)}</Grid></Block>}
          {active.filter((l) => l.keyed).map((l) => (
            <Block key={l.id} title={KEY_TITLE[l.keyed]}>
              <Grid>
                {Object.entries(KEYED[l.keyed]).filter(([k]) => !present[l.keyed] || present[l.keyed].has(k)).map(([k, c]) => (
                  <Key key={k} label={k.split('/')[0]} swatch={l.geom === 'line' ? { kind: 'line', color: c, dash: k === 'Regional Rail' ? 'dash' : null } : l.geom === 'point' ? { kind: 'dot', color: c } : { kind: 'fill', color: c }} />
                ))}
              </Grid>
            </Block>
          ))}
        </div>
      )}
    </div>
  );
}

// ── bottom-right: basemap and zoom ────────────────────────────────────────
export function MapControls({ basemap, onBasemap, onZoomIn, onZoomOut, onHome }) {
  return (
    <div className="pointer-events-none absolute bottom-3 right-3 z-[500] flex items-center gap-2">
      <div className={cx('pointer-events-auto flex gap-0.5 rounded-xl p-1 shadow-lg', GLASS)} role="radiogroup" aria-label="Background map">
        {BASEMAPS.map((b) => (
          <button key={b.id} type="button" role="radio" aria-checked={basemap === b.id} onClick={() => onBasemap(b.id)}
            className={cx('whitespace-nowrap rounded-lg px-2 py-1 text-[12px] font-semibold transition', basemap === b.id ? 'bg-accent-600 text-white' : 'text-slate-600 hover:bg-stone-100 hover:text-slate-900')}>{b.label}</button>
        ))}
      </div>
      <div className="pointer-events-auto flex overflow-hidden rounded-xl shadow-lg ring-1 ring-black/5">
        {[['+', onZoomIn, 'Zoom in'], ['−', onZoomOut, 'Zoom out']].map(([t, fn, l]) => (
          <button key={t} type="button" onClick={fn} aria-label={l} className="h-8 w-8 border-r border-stone-200 bg-white/95 text-[17px] font-semibold leading-none text-slate-700 hover:bg-white">{t}</button>
        ))}
        <button type="button" onClick={onHome} aria-label="Back to the school" title="Back to the school" className="grid h-8 w-8 place-items-center bg-white/95 text-accent-600 hover:bg-white">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>
        </button>
      </div>
    </div>
  );
}

export function Notice({ text, onClose }) {
  useEffect(() => { if (!text) return undefined; const t = setTimeout(onClose, 5000); return () => clearTimeout(t); }, [text, onClose]);
  return (
    <AnimatePresence>
      {text && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className={cx('absolute left-1/2 top-16 z-[610] max-w-[min(520px,calc(100%-24px))] -translate-x-1/2 rounded-xl px-3.5 py-2 text-[13px] text-slate-700 shadow-lg', GLASS)}>{text}</motion.div>
      )}
    </AnimatePresence>
  );
}

// ── Sources & data ────────────────────────────────────────────────────────
const ext = (u) => (href(u) ? <a href={href(u)} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent-600 hover:underline">{u.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]} ↗</a> : null);

export function SourcesModal({ open, onClose, sources, schools, onDownload, selectionLabel }) {
  const [tab, setTab] = useState('assets');
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  const finalists = schools.filter((s) => FINALISTS.includes(s.slug));
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[2000] grid place-items-center bg-slate-900/30 p-3 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal="true" aria-label="Sources and data" onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }} transition={SPRING_PANEL}
            className="flex max-h-[88vh] w-full max-w-[920px] flex-col overflow-hidden rounded-2xl bg-white shadow-[0_24px_80px_-20px_rgba(15,23,42,0.45)] ring-1 ring-black/5">
            <div className="flex items-start justify-between gap-4 border-b border-stone-100 px-5 pb-3 pt-4">
              <div>
                <h2 className="text-[19px] font-bold text-ink">Sources &amp; data</h2>
                <p className="mt-1 max-w-[680px] text-[13px] leading-relaxed text-ink-2">
                  This map is an inventory, not a recommendation. It gathers what exists around Wagner and Blankenburg (and four other candidate schools for comparison) so the reuse of each site can be argued from evidence. Every place on it comes from one of the sources below.
                  {sources?.built && <span className="text-ink-muted"> Built {sources.built}.</span>}
                </p>
              </div>
              <button type="button" onClick={onClose} className={ICON_BTN} aria-label="Close"><svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
            </div>
            <div className="px-5 pt-3">
              <Segmented value={tab} onChange={setTab} options={[{ value: 'assets', label: 'Where the places come from' }, { value: 'context', label: 'Map layers' }, { value: 'methods', label: 'Methods & caveats' }, { value: 'download', label: 'Download' }]} />
            </div>
            <div className={cx('min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-3', SCROLL)}>
              {!sources && <p className="py-6 text-center text-[13px] text-slate-500">Loading…</p>}
              {sources && tab === 'assets' && (
                <div className="space-y-5">
                  {ASSET_GROUPS.map((g) => {
                    const ds = sources.assets.filter((d) => (d.groups || []).includes(g.id));
                    return (
                      <div key={g.id}>
                        <div className="mb-2 flex items-center gap-2"><GroupGlyph group={g.id} size={20} /><span className="text-[14px] font-bold text-slate-900">{g.label}</span><span className="text-[12px] text-slate-500">· {ds.length} source{ds.length === 1 ? '' : 's'}</span></div>
                        <div className="overflow-hidden rounded-xl ring-1 ring-stone-200/80">
                          <table className="w-full text-left text-[12.5px]">
                            <thead className="bg-stone-50 text-[11px] uppercase tracking-wider text-slate-500">
                              <tr>
                                <th className="px-3 py-2 font-semibold">Dataset</th>
                                <th className="hidden px-3 py-2 font-semibold sm:table-cell">Publisher</th>
                                {finalists.map((s) => <th key={s.slug} className="px-2 py-2 text-right font-semibold" title={`Places from this source within 1 mile of ${s.short}`}>{s.short}<span className="block normal-case tracking-normal text-slate-400">within 1 mi</span></th>)}
                                <th className="px-3 py-2 text-right font-semibold">Link</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-stone-100">
                              {ds.map((d) => (
                                <tr key={d.id} className="align-top">
                                  <td className="px-3 py-2">
                                    <span className="block text-slate-800">{d.title}</span>
                                    <span className="mt-0.5 block text-[11.5px] leading-snug text-slate-500">{[d.data_date && `Data: ${String(d.data_date).split(/[;(]/)[0].trim()}`, d.retrieved && `pulled ${d.retrieved}`].filter(Boolean).join(' · ')}</span>
                                    {(d.notes || d.license) && (
                                      <details className="mt-0.5 text-[11.5px] leading-snug text-slate-500">
                                        <summary className="cursor-pointer select-none font-semibold text-accent-600 hover:underline">Notes</summary>
                                        {d.notes && <p className="mt-1">{d.notes}</p>}
                                        {d.license && <p className="mt-1">License: {d.license}</p>}
                                        {d.data_date && <p className="mt-1">Data date: {d.data_date}</p>}
                                      </details>
                                    )}
                                  </td>
                                  <td className="hidden px-3 py-2 text-slate-600 sm:table-cell">{d.publisher}</td>
                                  {finalists.map((s) => <td key={s.slug} className="px-2 py-2 text-right tabular-nums text-slate-900">{fmtInt(d.near?.[s.slug]?.[g.id] ?? 0)}</td>)}
                                  <td className="px-3 py-2 text-right">{ext(d.landing_url || d.api_url)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {sources && tab === 'context' && (
                <div className="overflow-hidden rounded-xl ring-1 ring-stone-200/80">
                  <table className="w-full text-left text-[12.5px]">
                    <thead className="bg-stone-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-2 font-semibold">Layer · dataset</th><th className="px-3 py-2 font-semibold">Publisher</th><th className="px-3 py-2 text-right font-semibold">Link</th></tr></thead>
                    <tbody className="divide-y divide-stone-100">
                      {sources.context.map((d) => (
                        <tr key={d.id} className="align-top">
                          <td className="px-3 py-2"><b className="block text-slate-900">{d.layer}</b><span className="block text-slate-800">{d.title}</span>{d.notes && <details className="mt-0.5 text-[11.5px] leading-snug text-slate-500"><summary className="cursor-pointer select-none font-semibold text-accent-600 hover:underline">Notes</summary><p className="mt-1">{d.notes}</p></details>}</td>
                          <td className="px-3 py-2 text-slate-600">{d.publisher}</td>
                          <td className="px-3 py-2 text-right">{ext(d.landing_url)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {sources && tab === 'methods' && (
                <div className="space-y-4 text-[13px] leading-relaxed text-slate-700">
                  {sources.methods.map((m) => <div key={m.title}><h3 className="text-[13.5px] font-semibold text-slate-900">{m.title}</h3><p className="mt-0.5">{m.text}</p></div>)}
                </div>
              )}
              {sources && tab === 'download' && (
                <div className="space-y-3 text-[13px] text-slate-700">
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-stone-50 px-4 py-3 ring-1 ring-stone-200/70">
                    <div><b className="text-slate-900">Places on the map now</b><div className="text-[12px] text-slate-500">{selectionLabel} · spreadsheet (CSV) with group, type, source and distance to the school</div></div>
                    <button type="button" onClick={onDownload} className="rounded-lg bg-accent-600 px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-accent-700">Download CSV</button>
                  </div>
                  <div className="rounded-xl ring-1 ring-stone-200/80">
                    <div className="border-b border-stone-100 px-4 py-2 text-[12px] font-semibold uppercase tracking-wider text-slate-500">Full inventory per school (GeoJSON, to 1.5 miles)</div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-3">
                      {schools.map((s) => <a key={s.slug} href={`/data/${s.slug}/assets.json`} download={`${s.slug}_places.geojson`} className="flex items-center gap-2 font-semibold text-accent-600 hover:underline"><SchoolDot color={s.color} size={9} />{s.short}</a>)}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
