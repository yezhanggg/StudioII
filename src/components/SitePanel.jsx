/**
 * Right-hand panel. One school: what is around it (each kind of asset, how many within the radius and how
 * far the nearest is), its facility ratings and catchment, the half-mile study area against Philadelphia,
 * walk reach and the RCOs covering it. Several schools: the same headline numbers side by side.
 * It reports; it does not recommend.
 */
import React from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { FLOAT_BTN, FoldIcon, ICON_BTN, PANEL, Rows, SCROLL, SPRING_PANEL, SPRING_TAB, Section, Segmented, cx } from '../lib/ui';
import { ASSET_GROUPS, TYPES, fmtInt, fmtMiles, fmtMoney, fmtPct, fmtRadius, href } from '../lib/layers';
import { GroupGlyph, SchoolDot, TypeGlyph } from './Chrome';

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

const EVERYDAY = TYPES.filter((t) => t.group !== 'more');

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

function SchoolSummary({ s, stats, radius, onOnly }) {
  const pr = s.profile;
  const dash = href(s.dashboard);
  const total = Object.values(stats).reduce((a, x) => a + x.n, 0);
  return (
    <div className="space-y-2.5">
      <div className="overflow-hidden rounded-xl bg-white ring-1 ring-stone-200/80">
        <div className="h-1.5" style={{ background: s.color }} />
        <div className="px-3 py-2.5">
          <div className="text-[15px] font-bold leading-tight text-slate-900">{s.name}</div>
          <div className="mt-0.5 text-[12px] text-slate-500">{s.address}{s.area_name ? ` · ${s.area_name}` : ''} · grades {s.grades}</div>
          <div className="mt-2 text-[12.5px] text-slate-600">
            <b className="text-slate-900">Catchment:</b> {s.catchment ? `grades ${s.catchment.grades}${s.catchment.varies ? ' (varies by area)' : ''}, ${s.catchment.sq_mi} sq mi` : 'none — admits students citywide'}
          </div>
        </div>
      </div>

      <Section title={`What is around ${s.short}`} subtitle={`${fmtInt(total)} places within ${fmtRadius(radius)} of the school`} tone="card">
        <Around stats={stats} radius={radius} onOnly={onOnly} />
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

      <Section title="Who lives nearby" subtitle="Half-mile study area vs Philadelphia · ACS 2020–2024" tone="card" defaultOpen={false}>
        <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><span className="flex-1" /><span>Study area</span><span className="w-[72px] text-right">Philadelphia</span></div>
        <Rows items={PROFILE_ROWS.filter(([k]) => pr[k]).map(([k, f]) => ({ label: LABEL[k] || k, value: f(pr[k].school), sub: f(pr[k].city) }))} />
        {s.walk?.length > 0 && (
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            {s.walk.map((w) => (
              <div key={w.minutes} className="rounded-lg bg-stone-50 px-2 py-1.5 text-center ring-1 ring-stone-200/70">
                <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{w.minutes}-min walk</div>
                <div className="text-[15px] font-bold tabular-nums text-slate-900">{fmtInt(w.residents_2020)}</div>
                <div className="text-[10.5px] text-slate-500">residents</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Registered community organizations" subtitle={`${s.rcos.filter((r) => r.covers).length} cover the site`} tone="card" defaultOpen={false}>
        <ul className="divide-y divide-stone-100">
          {s.rcos.filter((r) => r.covers).map((r) => (
            <li key={r.name} className="py-1.5">
              <div className="text-[13px] font-semibold leading-snug text-slate-900">{r.name}{r.cdc && <span className="ml-1.5 rounded bg-accent-50 px-1 py-px text-[10.5px] font-bold text-accent-700 ring-1 ring-accent-100">CDC</span>}</div>
              {r.meets && <div className="text-[12px] text-slate-600">Meets: {r.meets}</div>}
              {href(r.website) && <a className="text-[12px] font-semibold text-accent-600 hover:underline" href={href(r.website)} target="_blank" rel="noopener noreferrer">{r.website.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '')}</a>}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Compare({ schools, statsOf, radius, onFocus }) {
  return (
    <div className="space-y-2">
      {schools.map((s) => {
        const st = statsOf(s.slug);
        const n = Object.values(st).reduce((a, x) => a + x.n, 0);
        const none = EVERYDAY.filter((t) => !(st[t.id]?.n)).length;
        const pr = s.profile;
        return (
          <button key={s.slug} type="button" onClick={() => onFocus(s.slug)} className="block w-full overflow-hidden rounded-xl bg-white text-left ring-1 ring-stone-200/80 transition hover:shadow-sm hover:ring-accent-200">
            <div className="flex items-center gap-2 px-3 pt-2.5">
              <SchoolDot color={s.color} size={11} />
              <span className="text-[14px] font-bold text-slate-900">{s.short}</span>
              <span className="truncate text-[12px] text-slate-500">{s.area_name}</span>
              <span className="ml-auto shrink-0 text-[12px] font-semibold text-accent-600">Open →</span>
            </div>
            <dl className="grid grid-cols-4 gap-1 px-3 pb-2.5 pt-1.5">
              {[[`Places ≤${fmtRadius(radius)}`, fmtInt(n)], ['Types with none', `${none} of ${EVERYDAY.length}`],
                ['Income', pr['Median household income'] ? fmtMoney(pr['Median household income'].school) : 'n/a'], ['Poverty', pr['Poverty rate'] ? fmtPct(pr['Poverty rate'].school) : 'n/a']].map(([k, v]) => (
                <div key={k}><dt className="truncate text-[10.5px] text-slate-500">{k}</dt><dd className="text-[13.5px] font-bold tabular-nums text-slate-900">{v}</dd></div>
              ))}
            </dl>
          </button>
        );
      })}
      <p className="px-0.5 text-[11.5px] leading-snug text-slate-500">"Types with none" counts the everyday place types (the first four groups) with nothing inside the distance. Income and poverty are for each school's half-mile study area.</p>
    </div>
  );
}

export default function SitePanel({ schools, focusSchool, onFocus, statsOf, radius, open, setOpen, tab, setTab, onOnly, top = 12 }) {
  const many = schools.length > 1;
  const tabs = [];
  if (many) tabs.push({ value: 'schools', label: `Compare ${schools.length}` });
  if (focusSchool) tabs.push({ value: 'school', label: focusSchool.short });
  const active = focusSchool && (tab === 'school' || !many) ? 'school' : 'schools';
  return (
    <AnimatePresence initial={false} mode="popLayout">
      {open ? (
        <motion.aside key="panel" style={{ transformOrigin: 'top right', top, maxHeight: `calc(100% - ${top + 12}px - 56px)` }}
          initial={{ opacity: 0, scale: 0.9, x: 14, filter: 'blur(6px)' }} animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: 14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }} transition={SPRING_PANEL}
          className={cx('absolute right-3 z-[510] flex max-w-[calc(100%-24px)] flex-col', W, PANEL)}>
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-2.5">
            {tabs.length > 1 ? <Segmented size="xs" value={active} onChange={setTab} options={tabs} /> : <span className="text-[14px] font-bold text-slate-900">{focusSchool ? focusSchool.short : 'Schools'}</span>}
            <button type="button" onClick={() => setOpen(false)} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="right" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 overflow-y-auto px-3 pb-3', SCROLL)}>
            {active === 'school' && focusSchool
              ? <SchoolSummary s={focusSchool} stats={statsOf(focusSchool.slug)} radius={radius} onOnly={onOnly} />
              : <Compare schools={schools} statsOf={statsOf} radius={radius} onFocus={onFocus} />}
          </div>
        </motion.aside>
      ) : (
        <motion.button key="tab" type="button" onClick={() => setOpen(true)} initial={{ opacity: 0, scale: 0.6, x: 8 }} animate={{ opacity: 1, scale: 1, x: 0 }} exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.12 } }}
          transition={SPRING_TAB} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }} style={{ top }} className={cx('absolute right-3 z-[510] text-slate-800', FLOAT_BTN)}>
          {focusSchool ? `${focusSchool.short} summary` : 'Compare schools'}
          <span className="text-slate-600"><FoldIcon side="right" closed /></span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
