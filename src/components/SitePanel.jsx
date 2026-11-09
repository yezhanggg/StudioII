/**
 * Right-hand panel for the selected school: what is around it (each kind of place, how many within the radius
 * and how far the nearest is), its facility ratings and catchment, its study census tracts against
 * Philadelphia, and the RCOs covering it. It reports; it does not recommend.
 */
import React from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { FLOAT_BTN, FoldIcon, ICON_BTN, PANEL, Rows, SCROLL, Section, cx } from '../lib/ui';
import { ASSET_GROUPS, TYPES, fmtInt, fmtMiles, fmtMoney, fmtPct, fmtRadius, href } from '../lib/layers';
import { GroupGlyph, LinkIcons, Switch, TypeGlyph } from './Chrome';

const W = 'w-[350px] xl:w-[370px]';
const PROFILE_ROWS = [
  ['Population', fmtInt], ['Median household income', fmtMoney], ['Poverty rate', fmtPct], ['Unemployment rate', fmtPct],
  ['Median home value', fmtMoney], ['Renter-occupied', fmtPct], ["Bachelor's degree or higher", fmtPct],
];
const LABEL = { 'Renter-occupied': 'Renter households' };
const TONE = (r = '') => (/unsatisf|severe|high risk/i.test(r) ? 'bg-rose-50 text-rose-700 ring-rose-200/80'
  : /poor|moderate/i.test(r) ? 'bg-amber-50 text-amber-800 ring-amber-200/80'
    : /fair|low risk/i.test(r) ? 'bg-stone-100 text-slate-700 ring-stone-200' : 'bg-emerald-50 text-emerald-700 ring-emerald-200/80');
const FMP = [['building', 'Building condition'], ['program', 'Educational program'], ['utilization', 'Utilization'], ['vulnerability', 'Vulnerability']];

function TypeRow({ t, st, onOnly }) {
  const x = st || { n: 0, nearest: null };
  return (
    <button type="button" onClick={() => onOnly(t.id)} title={`Show only ${t.label.toLowerCase()} on the map`} className="flex w-full items-center gap-2 rounded-md px-1 py-[3px] text-left hover:bg-stone-50">
      <TypeGlyph type={t.id} size={16} />
      <span className="min-w-0 flex-1 truncate text-[12.5px] text-slate-700">{t.label}</span>
      <span className={cx('w-[44px] text-right text-[13px] tabular-nums', x.n ? 'font-bold text-slate-900' : 'text-slate-400')}>{x.n || 'none'}</span>
      <span className={cx('w-[60px] text-right text-[12px] tabular-nums', x.nearest != null ? 'text-slate-600' : 'text-slate-400')}>{x.nearest == null ? '> 1½ mi' : x.nearest < 0.03 ? 'on site' : fmtMiles(x.nearest)}</span>
    </button>
  );
}

function Around({ stats, radius, onOnly }) {
  return (
    <div>
      <div className="flex items-center gap-2 px-1 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-slate-400">
        <span className="flex-1">Place</span><span className="w-[44px] text-right">Within {fmtRadius(radius)}</span><span className="w-[60px] text-right">Nearest</span>
      </div>
      {ASSET_GROUPS.map((g) => {
        const rows = TYPES.filter((t) => t.group === g.id).map((t) => <TypeRow key={t.id} t={t} st={stats[t.id]} onOnly={onOnly} />);
        const head = <span className="flex items-center gap-1.5 text-[12.5px] font-bold text-slate-900"><GroupGlyph group={g.id} size={16} />{g.label}</span>;
        return g.id === 'more' ? (
          <details key={g.id} className="mt-2 rounded-lg px-1 py-1 ring-1 ring-stone-200/70">
            <summary className="cursor-pointer select-none list-none px-0.5">{head}<span className="ml-[22px] block text-[11.5px] text-slate-500">Worship, community groups, services, arts, history… (tap to open)</span></summary>
            <div className="mt-1">{rows}</div>
          </details>
        ) : (
          <div key={g.id} className="mb-1.5"><div className="px-1 pb-0.5 pt-1.5">{head}</div>{rows}</div>
        );
      })}
      <p className="mt-2 px-1 text-[11.5px] leading-snug text-slate-500">Distances are straight lines from the school. "On site" means inside the school building or on its lot. Tap a row to show only that type on the map.</p>
    </div>
  );
}

function SchoolSummary({ s, stats, radius, onOnly, onRco, rcoOn, catchmentOn, onCatchment }) {
  const pr = s.tract_profile || {};
  const tracts = s.tracts || [];
  const rcos = (s.rcos || []).filter((r) => r.miles == null || r.miles <= radius + 1e-9);
  const dash = href(s.dashboard);
  const total = Object.values(stats).reduce((a, x) => a + x.n, 0);
  return (
    <div className="space-y-2.5">
      <div className="overflow-hidden rounded-xl bg-white ring-1 ring-stone-200/80">
        <div className="px-3 py-2.5">
          <div className="text-[15px] font-bold leading-tight text-slate-900">{s.name}</div>
          <div className="mt-0.5 text-[12px] text-slate-500">{s.address}{s.area_name ? ` · ${s.area_name}` : ''} · grades {s.grades}</div>
          {s.catchment ? (
            <button type="button" onClick={onCatchment} aria-pressed={catchmentOn} className="-mx-1 mt-1.5 flex w-[calc(100%+8px)] items-center gap-2 rounded-lg px-1 py-1 text-left hover:bg-stone-50">
              <span className="min-w-0 flex-1 text-[12.5px] text-slate-600"><b className="text-slate-900">Catchment:</b> grades {s.catchment.grades}{s.catchment.varies ? ' (varies by area)' : ''}, {s.catchment.sq_mi} sq mi</span>
              <Switch on={catchmentOn} />
            </button>
          ) : <div className="mt-2 text-[12.5px] text-slate-600"><b className="text-slate-900">Catchment:</b> none — admits students citywide</div>}
        </div>
      </div>

      <Section title={`What is around ${s.short}`} subtitle={`${fmtInt(total)} places within ${fmtRadius(radius)} of the school`} tone="card">
        <Around stats={stats} radius={radius} onOnly={onOnly} />
      </Section>

      <Section title="RCOs" subtitle={`Registered Community Organizations · ${rcos.length} reach ${fmtRadius(radius)}`} tone="card" defaultOpen={false}>
        {rcos.length ? (
          <ul className="-mx-1 divide-y divide-stone-100">
            {rcos.map((r) => (
              <li key={r.name}>
                <div role="switch" tabIndex={0} aria-checked={rcoOn.includes(r.name)} onClick={() => onRco(r.name)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onRco(r.name))}
                  title={rcoOn.includes(r.name) ? 'Hide its boundary' : 'Show its boundary'} className="flex cursor-pointer items-start gap-2 rounded-lg px-1 py-2 transition-colors hover:bg-stone-50">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-semibold leading-snug text-slate-900">{r.name}</span>
                    <span className="block text-[11.5px] leading-snug text-slate-500">
                      {[r.covers ? 'Covers the site' : `${fmtMiles(r.miles)} away`, r.type === 'Ward' ? 'Ward' : null, r.cdc ? 'CDC' : null].filter(Boolean).join(' · ')}
                    </span>
                    {r.meets && <span className="block truncate text-[11.5px] leading-snug text-slate-500" title={r.meets}>Meets: {r.meets}</span>}
                    <span className="mt-1 block"><LinkIcons p={r} size={24} /></span>
                  </span>
                  <span className="mt-0.5"><Switch on={rcoOn.includes(r.name)} /></span>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="text-[12.5px] text-slate-500">No RCO boundary reaches {fmtRadius(radius)} of the school.</p>}
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">Switch one on to see its boundary. <b>RCO boundaries</b> under Map layers shows them all.</p>
      </Section>

      <Section title="The building" subtitle="SDP Facilities Master Plan ratings" tone="card" defaultOpen={false}>
        <div className="grid grid-cols-2 gap-1.5">
          {FMP.map(([k, l]) => s.fmp[k]?.[1] && (
            <div key={k} className="rounded-lg bg-white px-2.5 py-1.5 ring-1 ring-stone-200/80">
              <div className="text-[11px] text-slate-500">{l}</div>
              <div className="mt-0.5 flex items-center gap-1.5"><span className={cx('rounded-full px-1.5 py-px text-[11.5px] font-semibold ring-1', TONE(s.fmp[k][1]))}>{s.fmp[k][1]}</span><span className="text-[11.5px] tabular-nums text-slate-500">{s.fmp[k][0]}</span></div>
            </div>
          ))}
        </div>
        {dash && <a href={dash} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[12px] font-semibold text-accent-600 hover:underline">SDP facilities dashboard ↗</a>}
      </Section>

      <Section title="Who lives nearby" subtitle={`${tracts.length} study census tracts vs Philadelphia · ACS 2020–2024`} tone="card" defaultOpen={false}>
        <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><span className="flex-1" /><span>Study tracts</span><span className="w-[72px] text-right">Philadelphia</span></div>
        <Rows items={PROFILE_ROWS.filter(([k]) => pr[k]).map(([k, f]) => ({ label: LABEL[k] || k, value: f(pr[k].group), sub: f(pr[k].city) }))} />
        <div className="mt-2 flex flex-wrap gap-1">
          {tracts.map((t) => (
            <span key={t.geoid} title={`Census tract ${t.name}: ${fmtInt(t.pop)} residents${t.site ? ' · the school is in this tract' : ''}`}
              className={cx('rounded-md px-1.5 py-0.5 text-[11.5px] tabular-nums ring-1', t.site ? 'bg-accent-50 font-semibold text-accent-700 ring-accent-200' : 'bg-stone-50 text-slate-600 ring-stone-200/70')}>
              Tract {t.name}
            </span>
          ))}
        </div>
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">The tracts are added together as one group; medians use the aggregate-median method. Highlighted: the tract the school is in.</p>
      </Section>

    </div>
  );
}

export default function SitePanel({ school, statsOf, radius, open, setOpen, onOnly, onRco, rcoOn, catchmentOn, onCatchment, top = 12 }) {
  return (
    <AnimatePresence initial={false} mode="popLayout">
      {open ? (
        <motion.aside key="panel" style={{ transformOrigin: 'top right', top, maxHeight: `calc(100% - ${top + 12}px - 56px)` }}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
          className={cx('absolute right-3 z-[510] flex max-w-[calc(100%-24px)] flex-col', W, PANEL)}>
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-2.5">
            <span className="text-[14px] font-bold text-slate-900">{school.short}</span>
            <button type="button" onClick={() => setOpen(false)} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="right" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 overflow-y-auto px-3 pb-3', SCROLL)}>
            <SchoolSummary s={school} stats={statsOf(school.slug)} radius={radius} onOnly={onOnly} onRco={onRco} rcoOn={rcoOn} catchmentOn={catchmentOn} onCatchment={onCatchment} />
          </div>
        </motion.aside>
      ) : (
        <motion.button key="tab" type="button" onClick={() => setOpen(true)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }} style={{ top }} className={cx('absolute right-3 z-[510] text-slate-800', FLOAT_BTN)}>
          {school.short} summary
          <span className="text-slate-600"><FoldIcon side="right" closed /></span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
