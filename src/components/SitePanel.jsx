/**
 * Right-hand panel (the Market Analysis Tool's boundary panel): the schools on the map side by side, one
 * school's summary, and a clicked tract's profile. Numbers: profile from 03_profile.py's method, counts from
 * the community asset tables, walk reach from the 15-minute walk method, ratings from the SDP Facilities
 * Master Plan (sites.csv).
 */
import React from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { FLOAT_BTN, FoldIcon, ICON_BTN, PANEL, Rows, SCROLL, SPRING_PANEL, SPRING_TAB, Section, Segmented, cx } from '../lib/ui';
import { CATEGORIES, CATEGORY, MEASURES, fmtInt, fmtMoney, fmtPct, fmtRadius, href } from '../lib/layers';
import { AssetGlyph, SchoolDot } from './Chrome';

const W = 'w-[350px] xl:w-[370px]';
const PROFILE_ROWS = [
  ['Population', fmtInt], ['Households', fmtInt], ['Median household income', fmtMoney], ['Median home value', fmtMoney],
  ['Poverty rate', fmtPct], ['Unemployment rate', fmtPct], ["Bachelor's degree or higher", fmtPct], ['Renter-occupied', fmtPct], ['Black', fmtPct],
];
const LABEL = { Black: 'Black residents', 'Renter-occupied': 'Renter households' };
const RATING_TONE = (r = '') => (/unsatisf|severe|high risk/i.test(r) ? 'bg-rose-50 text-rose-700 ring-rose-200/80'
  : /poor|moderate/i.test(r) ? 'bg-amber-50 text-amber-800 ring-amber-200/80'
    : /fair|low risk/i.test(r) ? 'bg-stone-100 text-slate-700 ring-stone-200'
      : 'bg-emerald-50 text-emerald-700 ring-emerald-200/80');
const FMP = [['building', 'Building condition'], ['program', 'Educational program'], ['utilization', 'Utilization'], ['vulnerability', 'Vulnerability']];

function Rating({ label, value }) {
  const [score, rating] = value || [];
  if (!rating) return null;
  return (
    <div className="rounded-lg bg-white px-2.5 py-1.5 ring-1 ring-stone-200/80">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 flex items-center gap-1.5">
        <span className={cx('rounded-full px-1.5 py-px text-[11.5px] font-semibold ring-1', RATING_TONE(rating))}>{rating}</span>
        {score && <span className="text-[11.5px] tabular-nums text-slate-500">{score}</span>}
      </div>
    </div>
  );
}

function AssetBars({ inRadius, counts, radius, onOnly }) {
  const max = Math.max(1, ...CATEGORIES.map((c) => Math.max(counts[c.id]?.mile || 0, inRadius[c.id] || 0)));
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-slate-600" />within {fmtRadius(radius)}</span>
        {radius < 1 && <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-slate-300" />to 1 mile</span>}
      </div>
      <ul className="space-y-1">
        {CATEGORIES.map((c) => {
          const r = inRadius[c.id] || 0;
          const mile = counts[c.id]?.mile || 0;
          const col = CATEGORY[c.id].color;
          return (
            <li key={c.id}>
              <button type="button" onClick={() => onOnly(c.id)} title={`Show only ${c.id.toLowerCase()} on the map`} className="group flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left hover:bg-stone-50">
                <AssetGlyph category={c.id} size={16} />
                <span className="w-[118px] shrink-0 truncate text-[12.5px] text-slate-700 group-hover:text-slate-900">{c.id}</span>
                <span className="relative flex h-2.5 flex-1 overflow-hidden rounded-r-[3px]">
                  <span style={{ width: `${(r / max) * 100}%`, background: col }} className="h-full" />
                  {radius < 1 && <span style={{ width: `${(Math.max(0, mile - r) / max) * 100}%`, background: col, opacity: 0.32, marginLeft: r ? 2 : 0 }} className="h-full rounded-r-[3px]" />}
                </span>
                <span className="w-[46px] shrink-0 text-right text-[12px] tabular-nums text-slate-600"><b className="text-slate-900">{r}</b>{radius < 1 ? ` · ${mile}` : ''}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-1.5 text-[11.5px] text-slate-500">Click a category to show only it on the map.</p>
    </div>
  );
}

function SchoolSummary({ s, inRadius, radius, onOnly }) {
  const pr = s.profile;
  const total = Object.values(inRadius).reduce((a, b) => a + b, 0);
  const dash = href(s.dashboard);
  return (
    <div className="space-y-2.5">
      <div className="overflow-hidden rounded-xl bg-white ring-1 ring-stone-200/80">
        <div className="h-1.5" style={{ background: s.color }} />
        <div className="px-3 py-2.5">
          <div className="text-[15px] font-bold leading-tight text-slate-900">{s.name}</div>
          <div className="mt-0.5 text-[12px] text-slate-500">{s.address}{s.area_name ? ` · ${s.area_name}` : ''} · grades {s.grades}</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5">{FMP.map(([k, l]) => <Rating key={k} label={l} value={s.fmp[k]} />)}</div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12px]">
            <span className="text-slate-500">SDP Facilities Master Plan ratings</span>
            {dash && <a href={dash} target="_blank" rel="noopener noreferrer" className="font-semibold text-accent-600 hover:underline">SDP dashboard ↗</a>}
          </div>
        </div>
      </div>

      <div className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-stone-200/80">
        <div className="text-[13px] font-semibold text-slate-900">Attendance catchment</div>
        <div className="mt-0.5 text-[12.5px] leading-snug text-slate-600">
          {s.catchment
            ? <>Grades {s.catchment.grades} {s.catchment.varies ? '(the grades vary across the area)' : ''} · {s.catchment.sq_mi} sq mi (SDP, 2024)</>
            : <>None. {s.short} admits students citywide, so no addresses are assigned to it.</>}
        </div>
      </div>

      <Section title={`${s.short} study area`} subtitle="Half-mile area vs Philadelphia · ACS 2020–2024" tone="card">
        <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <span className="flex-1" /><span className="text-right">Study area</span><span className="w-[72px] text-right">Philadelphia</span>
        </div>
        <Rows items={PROFILE_ROWS.filter(([k]) => pr[k]).map(([k, f]) => ({ label: LABEL[k] || k, value: f(pr[k].school), sub: f(pr[k].city) }))} />
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">
          Census tracts around the school, each weighted by the share of its residents inside the half mile; medians by the aggregate median method.
          {s.studio ? ' From the studio\'s Background analysis.' : ' Same method as the studio\'s Wagner and Blankenburg profiles.'}
        </p>
      </Section>

      {s.walk?.length > 0 && (
        <Section title="Walk reach" subtitle="Residents within a 5, 10 and 15-minute walk (2020 Census)" tone="card">
          <div className="grid grid-cols-3 gap-1.5">
            {s.walk.map((w) => (
              <div key={w.minutes} className="rounded-lg bg-stone-50 px-2 py-2 text-center ring-1 ring-stone-200/70">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{w.minutes} min</div>
                <div className="text-[17px] font-bold tabular-nums text-slate-900">{fmtInt(w.residents_2020)}</div>
                <div className="text-[11px] tabular-nums text-slate-500">{w.area_sq_mi} sq mi</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Community assets" subtitle={`${fmtInt(total)} places within ${fmtRadius(radius)}, by category`} tone="card">
        <AssetBars inRadius={inRadius} counts={s.asset_counts} radius={radius} onOnly={onOnly} />
      </Section>

      <Section title="Registered community organizations" subtitle={`${s.rcos.filter((r) => r.covers).length} cover the site · ${s.rcos.length} reach the half mile`} tone="card" defaultOpen={false}>
        <ul className="divide-y divide-stone-100">
          {s.rcos.map((r) => (
            <li key={r.name} className="py-1.5">
              <div className="flex items-start gap-2">
                <span className={cx('mt-1 h-2.5 w-2.5 shrink-0 rounded-sm', r.covers ? 'bg-accent-600' : 'bg-accent-200')} />
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold leading-snug text-slate-900">{r.name}{r.cdc && <span className="ml-1.5 rounded bg-accent-50 px-1 py-px text-[10.5px] font-bold text-accent-700 ring-1 ring-accent-100">CDC</span>}</div>
                  <div className="text-[12px] text-slate-500">{r.type}{r.covers ? ' · covers the school' : ''}</div>
                  {r.meets && <div className="text-[12px] text-slate-600">Meets: {r.meets}</div>}
                  {href(r.website) && <a className="text-[12px] font-semibold text-accent-600 hover:underline" href={href(r.website)} target="_blank" rel="noopener noreferrer">{r.website.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '')}</a>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Compare({ schools, inRadiusOf, radius, onFocus }) {
  return (
    <div className="space-y-2">
      <p className="px-0.5 text-[12px] leading-snug text-slate-500">The schools on the map, side by side. Places are counted within {fmtRadius(radius)}; the rest is each school's half-mile study area.</p>
      {schools.map((s) => {
        const n = Object.values(inRadiusOf(s.slug)).reduce((a, b) => a + b, 0);
        const pr = s.profile;
        const walk = s.walk?.find((w) => w.minutes === 15);
        return (
          <button key={s.slug} type="button" onClick={() => onFocus(s.slug)} className="block w-full overflow-hidden rounded-xl bg-white text-left ring-1 ring-stone-200/80 transition hover:ring-accent-200 hover:shadow-sm">
            <div className="flex items-center gap-2 px-3 pt-2.5">
              <SchoolDot color={s.color} size={11} />
              <span className="text-[14px] font-bold text-slate-900">{s.short}</span>
              <span className="truncate text-[12px] text-slate-500">grades {s.grades}{s.area_name ? ` · ${s.area_name}` : ''}</span>
              <span className="ml-auto shrink-0 text-[12px] font-semibold text-accent-600">Summary →</span>
            </div>
            <dl className="grid grid-cols-4 gap-1 px-3 pb-2 pt-1.5">
              {[['Places', fmtInt(n)], ['Income', pr['Median household income'] ? fmtMoney(pr['Median household income'].school) : 'n/a'],
                ['Poverty', pr['Poverty rate'] ? fmtPct(pr['Poverty rate'].school) : 'n/a'], ['15-min walk', walk ? fmtInt(walk.residents_2020) : 'n/a']].map(([k, v]) => (
                <div key={k}><dt className="text-[10.5px] text-slate-500">{k}</dt><dd className="text-[13.5px] font-bold tabular-nums text-slate-900">{v}</dd></div>
              ))}
            </dl>
            <div className="flex flex-wrap gap-1 border-t border-stone-100 px-3 py-1.5">
              {[['Building', s.fmp.building[1]], ['Use', s.fmp.utilization[1]], ['Vulnerability', s.fmp.vulnerability[1]]].filter(([, r]) => r).map(([k, r]) => (
                <span key={k} className={cx('rounded-full px-1.5 py-px text-[11px] font-semibold ring-1', RATING_TONE(r))}>{k}: {r}</span>
              ))}
              <span className="rounded-full bg-stone-100 px-1.5 py-px text-[11px] font-semibold text-slate-600 ring-1 ring-stone-200">{s.catchment ? `Catchment ${s.catchment.grades}` : 'Citywide admission'}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function TractDetail({ tract, school, onClear }) {
  const pr = school?.profile || {};
  return (
    <div className="space-y-2.5">
      <div className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-stone-200/80">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[15px] font-bold text-slate-900">Census tract {tract.name}</div>
            <div className="text-[12px] text-slate-500">GEOID {tract.geoid}{tract._short ? ` · study tract of ${tract._short}` : ''}</div>
          </div>
          <button type="button" onClick={onClear} className="text-[12px] font-semibold text-accent-600 hover:underline">Close</button>
        </div>
      </div>
      <Section title="Tract profile" subtitle="ACS 2020–2024 5-year estimates" tone="card">
        <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <span className="flex-1" /><span>Tract</span><span className="w-[64px] text-right">{school ? school.short.split(' ')[0] : 'Study'}</span><span className="w-[56px] text-right">City</span>
        </div>
        <ul className="divide-y divide-stone-100">
          {MEASURES.map((m) => {
            const p = m.profile && pr[m.profile];
            return (
              <li key={m.id} className="flex items-center gap-3 py-1.5 text-[13px]">
                <span className="min-w-0 flex-1 text-slate-600">{m.label}</span>
                <span className="font-semibold tabular-nums text-slate-900">{m.fmt(tract[m.id])}</span>
                <span className="w-[64px] text-right tabular-nums text-slate-500">{p ? m.fmt(p.school) : '—'}</span>
                <span className="w-[56px] text-right tabular-nums text-slate-500">{p ? m.fmt(p.city) : '—'}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">The middle column is {school ? `${school.short}'s` : 'the'} half-mile study area. Tract estimates carry wide margins of error; read differences of a few points as noise.</p>
      </Section>
    </div>
  );
}

export default function SitePanel({ schools, focusSchool, onFocus, inRadiusOf, radius, tract, onClearTract, open, setOpen, tab, setTab, onOnly, top = 12 }) {
  const tabs = [{ value: 'schools', label: schools.length > 1 ? `Schools (${schools.length})` : 'Schools' }];
  if (focusSchool) tabs.push({ value: 'school', label: focusSchool.short });
  tabs.push({ value: 'tract', label: tract ? `Tract ${tract.name}` : 'Tract' });
  const active = tab === 'school' && !focusSchool ? 'schools' : tab;
  return (
    <AnimatePresence initial={false} mode="popLayout">
      {open ? (
        <motion.aside
          key="panel"
          style={{ transformOrigin: 'top right', top, maxHeight: `calc(100% - ${top + 12}px - 150px)` }}
          initial={{ opacity: 0, scale: 0.9, x: 14, filter: 'blur(6px)' }}
          animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: 14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }}
          transition={SPRING_PANEL}
          className={cx('absolute right-3 z-[510] flex max-w-[calc(100%-24px)] flex-col', W, PANEL)}
        >
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-2.5">
            <Segmented size="xs" value={active} onChange={setTab} options={tabs} />
            <button type="button" onClick={() => setOpen(false)} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="right" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 overflow-y-auto px-3 pb-3', SCROLL)}>
            {active === 'tract'
              ? tract ? <TractDetail tract={tract} school={focusSchool || schools[0]} onClear={onClearTract} /> : <p className="rounded-xl bg-stone-50 px-3 py-4 text-center text-[13px] text-slate-500 ring-1 ring-stone-200/70">Click a census tract on the map: turn on <b>Study census tracts</b>, or shade tracts under <b>Census tracts</b>.</p>
              : active === 'school' && focusSchool
                ? <SchoolSummary s={focusSchool} inRadius={inRadiusOf(focusSchool.slug)} radius={radius} onOnly={onOnly} />
                : <Compare schools={schools} inRadiusOf={inRadiusOf} radius={radius} onFocus={onFocus} />}
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
