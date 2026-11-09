/**
 * The map's floating UI, in the Market Analysis Tool's design language, written for people who have never used
 * a map tool: a school bar along the top, "Radius" above a left panel of five large groups and a few
 * map layers, a legend under it, basemaps and zoom bottom-right, and the Sources & data window. Presentational only.
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
export function SchoolBar({ schools, visible, onAll, onOnly, onClear, onSources }) {
  const all = visible.length === schools.length;
  const only = visible.length === 1 ? visible[0] : null;
  const btn = (on) => cx('relative flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold transition-colors', on ? 'text-accent-700' : 'text-slate-700 hover:bg-stone-100 hover:text-slate-900');
  const School = ({ s, quiet }) => {
    const on = only === s.slug;
    return (
      <button type="button" role="radio" aria-checked={on} onClick={() => onOnly(s.slug)} title={s.name} className={btn(on)}>
        {on && (
          <motion.span layoutId="school-on" transition={SPRING_TAB} className="absolute inset-0 overflow-hidden rounded-lg"
            style={{ background: `color-mix(in srgb, ${s.color} 11%, white)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${s.color} 38%, transparent)` }}>
            <span className="absolute inset-x-2 bottom-0 h-[2.5px] rounded-full" style={{ background: s.color }} />
          </motion.span>
        )}
        <span className="relative flex items-center gap-1.5">
          <span className="shrink-0 rounded-full transition-all" style={{ width: on ? 10 : 9, height: on ? 10 : 9, background: s.color, boxShadow: on ? `0 0 0 3px color-mix(in srgb, ${s.color} 25%, transparent)` : '0 0 0 2px #fff, 0 0 0 3px rgba(30,30,28,.18)' }} />
          <span className={cx(on ? 'font-bold' : quiet && 'font-medium text-slate-500')} style={on ? { color: `color-mix(in srgb, ${s.color} 70%, #111)` } : undefined}>{s.short}</span>
        </span>
      </button>
    );
  };
  return (
    <div className={cx('absolute right-3 top-[172px] z-[520] flex w-fit max-w-[calc(100%-24px)] items-center gap-1 overflow-x-auto rounded-xl p-1 shadow-lg md:top-3 md:max-w-[calc(100%-364px)]', GLASS, SCROLL)} role="radiogroup" aria-label="Schools on the map">
      {schools.filter((s) => FINALISTS.includes(s.slug)).map((s) => <School key={s.slug} s={s} />)}
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      {schools.filter((s) => !FINALISTS.includes(s.slug)).map((s) => <School key={s.slug} s={s} quiet />)}
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      <button type="button" role="radio" aria-checked={all} onClick={onAll} className={btn(all)}>
        {all && (
          <motion.span layoutId="school-on" transition={SPRING_TAB} className="absolute inset-0 overflow-hidden rounded-lg bg-accent-50 ring-1 ring-inset ring-accent-200">
            <span className="absolute inset-x-2 bottom-0 h-[2.5px] rounded-full bg-accent-600" />
          </motion.span>
        )}
        <span className="relative">All six</span>
      </button>
      <button type="button" onClick={onClear} disabled={!visible.length} className="whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-stone-100 hover:text-slate-900 disabled:cursor-default disabled:text-slate-300 disabled:hover:bg-transparent">Clear</button>
      <span className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
      <button type="button" onClick={onSources} className="flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold text-accent-600 hover:bg-accent-50">
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
        Sources &amp; data
      </button>
    </div>
  );
}

// ── radius ───────────────────────────────────────────────────────
const PRESETS = [[0.25, '¼'], [0.5, '½'], [0.75, '¾'], [1, '1']];
export function RadiusCard({ radius, onRadius, barRef }) {
  return (
    <div ref={barRef} className={cx('absolute left-3 top-3 z-[500] max-w-[calc(100%-24px)] rounded-xl p-3 shadow-lg', RAIL_W, GLASS)}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor="radius" className="text-[13px] font-bold text-slate-900">Radius</label>
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
      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-slate-900">{l.label}</span>
      {loading ? <Spinner /> : <Switch on={on} />}
    </button>
  );
}

export function LayersRail({
  top, reserveBottom, defaultOpen, radius,
  typeCounts, types, onType, onGroup, radiusOnly, onRadiusOnly,
  measure, onMeasure, on, onToggle, loading,
}) {
  const [st, setSt] = usePersisted('cmap.rail5', { open: defaultOpen, openGroup: null, more: false, layers: true });
  const basic = LAYERS.filter((l) => l.basic);
  const more = LAYERS.filter((l) => !l.basic);
  const moreOn = more.filter((l) => on[l.id]).length + (measure ? 1 : 0);
  const layersOn = basic.filter((l) => on[l.id]).length + moreOn;

  return (
    <AnimatePresence initial={false} mode="popLayout">
      {st.open ? (
        <motion.aside key="rail" style={{ transformOrigin: 'top left', top, maxHeight: `calc(100% - ${top + 12}px - ${reserveBottom}px)` }}
          initial={{ opacity: 0, scale: 0.9, x: -14, filter: 'blur(6px)' }} animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: -14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }} transition={SPRING_PANEL}
          className={cx('absolute left-3 z-[500] flex max-w-[calc(100%-24px)] flex-col', RAIL_W, PANEL)}>
          <div className="flex items-center justify-between gap-2 px-3 pb-1.5 pt-2.5">
            <h2 className="text-[13px] font-bold text-slate-900">Places to show</h2>
            <span className="flex items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-slate-600">
                <input type="checkbox" checked={radiusOnly} onChange={() => onRadiusOnly(!radiusOnly)} className="h-3.5 w-3.5 accent-[#393864]" />
                only within {fmtRadius(radius)}
              </label>
              <button type="button" onClick={() => setSt({ ...st, open: false })} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="left" /></button>
            </span>
          </div>
          <div className={cx('min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-3', SCROLL)}>
            <div>
              <div className="space-y-2">
                {ASSET_GROUPS.map((g) => (
                  <GroupCard key={g.id} g={g} types={types} counts={typeCounts} onType={onType} onGroup={onGroup}
                    open={st.openGroup === g.id} onOpen={() => setSt({ ...st, openGroup: st.openGroup === g.id ? null : g.id })} />
                ))}
              </div>
            </div>

            <div>
              <button type="button" onClick={() => setSt({ ...st, layers: !st.layers })} aria-expanded={st.layers} className="mb-1 flex w-full items-center justify-between rounded-lg px-0.5 py-0.5 text-left">
                <span className="text-[13px] font-bold text-slate-900">Map layers{!st.layers && layersOn ? <span className="ml-1.5 font-semibold text-slate-500">· {layersOn} on</span> : null}</span>
                <span className="flex items-center gap-1 text-[12px] font-semibold text-accent-600">{st.layers ? 'Hide' : 'Show'}
                  <svg className={cx('h-3.5 w-3.5 transition-transform', st.layers && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
                </span>
              </button>
              {st.layers && <div className="rounded-xl bg-white p-1 ring-1 ring-stone-200">
                {basic.map((l) => <LayerRow key={l.id} l={l} on={!!on[l.id]} onToggle={onToggle} loading={loading[l.id]} />)}
                <button type="button" onClick={() => setSt({ ...st, more: !st.more })} aria-expanded={st.more} className="mt-0.5 w-full rounded-lg px-2 py-1.5 text-left text-[12px] font-semibold text-accent-600 hover:bg-stone-50">
                  {st.more ? 'Fewer layers' : `More layers${moreOn ? ` (${moreOn} on)` : ''}`}
                </button>
                {st.more && (
                  <div className="border-t border-stone-100 pt-1">
                    {more.map((l) => <LayerRow key={l.id} l={l} on={!!on[l.id]} onToggle={onToggle} loading={loading[l.id]} />)}
                    <label className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
                      <span className="h-3 w-4 shrink-0 rounded-sm" style={{ background: `linear-gradient(90deg, ${RAMP[0]}, ${RAMP[4]})` }} />
                      <span className="min-w-0 flex-1 text-[13px] font-semibold text-slate-900">Shade tracts by</span>
                      <select value={measure || ''} onChange={(e) => onMeasure(e.target.value || null)} className="w-[118px] rounded-md bg-stone-50 px-1 py-1 text-[12px] text-slate-700 ring-1 ring-stone-200 focus:outline-none">
                        <option value="">Nothing</option>
                        {MEASURES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                      </select>
                    </label>
                  </div>
                )}
              </div>}
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
  const [open, setOpen] = useState(false);
  const groups = ASSET_GROUPS.filter((g) => TYPES.some((t) => t.group === g.id && types[t.id]));
  const active = LAYERS.filter((l) => on[l.id]);
  const m = measure && MEASURE[measure];
  const fmt = m && (m.legend || m.fmt);
  const swatchOf = (l) => (['radius', 'catchment', 'neighborhood'].includes(l.id) ? { ...l.swatch, color: l.id === 'catchment' ? '#57564E14' : '#57564E', line: '#57564E' } : l.swatch);
  return (
    <div ref={legendRef} className={cx('absolute bottom-3 left-3 z-[500] flex max-h-[34%] max-w-[calc(100%-24px)] flex-col rounded-xl shadow-lg', RAIL_W, GLASS)}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-3.5 py-2 text-left">
        <span className="text-[13px] font-semibold text-slate-900">Legend</span>
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
          {schools.length > 0 && <Block title="Schools"><Grid>{schools.map((s) => <Key key={s.slug} label={s.short}><span className="h-3 w-3 rounded-sm" style={{ background: s.color }} /></Key>)}</Grid></Block>}
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

// ── Sources & data ────────────────────────────────────────────────────────
// Short publisher names: the first clause of the publisher field ("City of Philadelphia, Office of …" → "City of Philadelphia").
const pub = (p = '') => p.split(/[,;(]/)[0].trim();
const SRC_TABS = [{ value: 'places', label: 'Places' }, { value: 'layers', label: 'Map layers' }, { value: 'method', label: 'Method' }];
const METHOD = [
  ['What it is', 'An inventory of what exists near each school. It does not rank sites or suggest uses.'],
  ['Places', 'Official City, state and federal data first; OpenStreetMap only where they have nothing. Duplicates across sources are merged. Collected to 1½ miles of each school.'],
  ['Distance', 'Straight-line miles from the school. "On site" means on the school lot.'],
  ['Who lives nearby', 'ACS 2020–2024 5-year estimates for the study census tracts, added together as one group.'],
  ['Checked', 'Every link was tested; dead websites are left out.'],
];

function SrcRow({ title, sub, url }) {
  return (
    <li className="flex items-baseline gap-3 py-1.5">
      <span className="min-w-0 flex-1"><span className="text-[13px] text-slate-900">{title}</span><span className="ml-1.5 text-[12px] text-slate-500">{sub}</span></span>
      {href(url) && <a href={href(url)} target="_blank" rel="noopener noreferrer" className="shrink-0 text-[12px] font-semibold text-accent-600 hover:underline">Open ↗</a>}
    </li>
  );
}

export function SourcesModal({ open, onClose, sources, schools, onDownload, selectionLabel }) {
  const [tab, setTab] = useState('places');
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[2000] grid place-items-center bg-slate-900/30 p-3 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal="true" aria-label="Sources and data" onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }} transition={SPRING_PANEL}
            className="flex max-h-[84vh] w-full max-w-[600px] flex-col overflow-hidden rounded-2xl bg-white shadow-[0_24px_80px_-20px_rgba(15,23,42,0.45)] ring-1 ring-black/5">
            <div className="flex items-center justify-between gap-4 px-5 pb-1 pt-4">
              <h2 className="text-[18px] font-bold text-ink">Sources &amp; data</h2>
              <button type="button" onClick={onClose} className={ICON_BTN} aria-label="Close"><svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
            </div>
            <p className="px-5 text-[12.5px] text-slate-500">
              {sources ? `${sources.assets.length} datasets · ${sources.context.length} map layers${sources.built ? ` · updated ${sources.built}` : ''}` : 'Loading…'}
            </p>
            <div className="px-5 pt-3"><Segmented size="xs" value={tab} onChange={setTab} options={SRC_TABS} /></div>
            <div className={cx('min-h-0 flex-1 overflow-y-auto px-5 pb-4 pt-2', SCROLL)}>
              {sources && tab === 'places' && ASSET_GROUPS.map((g) => {
                const ds = sources.assets.filter((d) => (d.groups || []).includes(g.id));
                return ds.length > 0 && (
                  <section key={g.id} className="pt-2">
                    <h3 className="flex items-center gap-2 text-[13px] font-bold text-slate-900"><GroupGlyph group={g.id} size={16} />{g.label}</h3>
                    <ul className="divide-y divide-stone-100 pl-6">{ds.map((d) => <SrcRow key={d.id} title={d.title} sub={pub(d.publisher)} url={d.landing_url || d.api_url} />)}</ul>
                  </section>
                );
              })}
              {sources && tab === 'layers' && (
                <ul className="divide-y divide-stone-100">
                  {sources.context.map((d) => <SrcRow key={d.id} title={d.layer} sub={pub(d.publisher)} url={d.landing_url} />)}
                  <SrcRow title="Background maps" sub="© Mapbox · © OpenStreetMap contributors · Maxar · Leaflet" url="https://www.mapbox.com/about/maps/" />
                </ul>
              )}
              {tab === 'method' && (
                <dl className="space-y-2.5 pt-1 text-[13px] leading-snug">
                  {METHOD.map(([k, v]) => <div key={k}><dt className="font-semibold text-slate-900">{k}</dt><dd className="text-slate-600">{v}</dd></div>)}
                </dl>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-stone-100 px-5 py-3 text-[12.5px]">
              {selectionLabel && <button type="button" onClick={onDownload} className="rounded-lg bg-accent-600 px-3 py-1.5 font-semibold text-white hover:bg-accent-700">Download CSV · {selectionLabel}</button>}
              <span className="text-slate-500">Full data:</span>
              {schools.map((s) => <a key={s.slug} href={`/data/${s.slug}/assets.json`} download={`${s.slug}_places.geojson`} className="font-semibold text-accent-600 hover:underline">{s.short}</a>)}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
