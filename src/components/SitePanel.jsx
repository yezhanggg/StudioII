/**
 * Right-hand panel (the Market Analysis Tool's boundary panel): the site summary, and a tract's profile
 * when one is clicked. Numbers are the studio's own: profile_2024.csv for the study area and Philadelphia,
 * the community asset table for counts, Walk_Area_Summary.csv for the walksheds.
 */
import React from 'react';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';
import { FLOAT_BTN, FoldIcon, ICON_BTN, PANEL, Rows, SCROLL, SPRING_PANEL, SPRING_TAB, Section, Segmented, cx } from '../lib/ui';
import { CATEGORIES, CATEGORY, MEASURES, fmtInt, fmtMoney, fmtPct } from '../lib/layers';
import { AssetGlyph } from './Chrome';

const W = 'w-[340px] xl:w-[360px]';
const PROFILE_ROWS = [
  ['Population', fmtInt], ['Households', fmtInt], ['Median household income', fmtMoney], ['Median home value', fmtMoney],
  ['Poverty rate', fmtPct], ['Unemployment rate', fmtPct], ["Bachelor's degree or higher", fmtPct], ['Renter-occupied', fmtPct], ['Black', fmtPct],
];

function CompareHead({ a, b }) {
  return (
    <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
      <span className="flex-1" /><span className="text-right">{a}</span><span className="w-[72px] text-right">{b}</span>
    </div>
  );
}

function AssetBars({ counts, onOnly }) {
  const max = Math.max(1, ...CATEGORIES.map((c) => counts[c.id]?.mile || 0));
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-slate-600" />within ½ mile</span>
        <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-slate-300" />½ to 1 mile</span>
      </div>
      <ul className="space-y-1">
        {CATEGORIES.map((c) => {
          const n = counts[c.id] || { half: 0, mile: 0 };
          const col = CATEGORY[c.id].color;
          return (
            <li key={c.id}>
              <button type="button" onClick={() => onOnly(c.id)} title={`Show only ${c.id.toLowerCase()} on the map`} className="group flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left hover:bg-stone-50">
                <AssetGlyph category={c.id} size={16} />
                <span className="w-[118px] shrink-0 truncate text-[12.5px] text-slate-700 group-hover:text-slate-900">{c.id}</span>
                <span className="relative flex h-2.5 flex-1 overflow-hidden rounded-r-[3px]">
                  <span style={{ width: `${(n.half / max) * 100}%`, background: col }} className="h-full" />
                  <span style={{ width: `${((n.mile - n.half) / max) * 100}%`, background: col, opacity: 0.32, marginLeft: n.half ? 2 : 0 }} className="h-full rounded-r-[3px]" />
                </span>
                <span className="w-[46px] shrink-0 text-right text-[12px] tabular-nums text-slate-600"><b className="text-slate-900">{n.half}</b> · {n.mile}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-1.5 text-[11.5px] text-slate-500">Click a category to show only it on the map.</p>
    </div>
  );
}

function SiteSummary({ site, onOnly }) {
  const pr = site.profile;
  return (
    <div className="space-y-2.5">
      <Section title={`${site.school} study area`} subtitle={`Study tracts vs Philadelphia · ACS ${site.acs_year - 4}–${site.acs_year}`} tone="card">
        <CompareHead a="Study area" b="Philadelphia" />
        <Rows items={PROFILE_ROWS.filter(([k]) => pr[k]).map(([k, f]) => ({ label: k === 'Black' ? 'Black residents' : k === 'Renter-occupied' ? 'Renter households' : k, value: f(pr[k].school), sub: f(pr[k].city) }))} />
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">The study area is the {site.study_tracts.length} census tracts around the school, weighted by the share of each tract's residents inside the half mile.</p>
      </Section>
      {site.walk?.length > 0 && (
        <Section title="Walk reach" subtitle="Residents within a 5, 10 and 15-minute walk (2020 Census)" tone="card">
          <div className="grid grid-cols-3 gap-1.5">
            {site.walk.map((w) => (
              <div key={w.minutes} className="rounded-lg bg-stone-50 px-2 py-2 text-center ring-1 ring-stone-200/70">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{w.minutes} min</div>
                <div className="text-[17px] font-bold tabular-nums text-slate-900">{fmtInt(w.residents_2020)}</div>
                <div className="text-[11px] tabular-nums text-slate-500">{w.area_sq_mi} sq mi</div>
              </div>
            ))}
          </div>
        </Section>
      )}
      <Section title="Community assets" subtitle="Places within one mile, by category" tone="card">
        <AssetBars counts={site.asset_counts} onOnly={onOnly} />
      </Section>
      <Section title="Registered community organizations" subtitle={`${site.rcos.filter((r) => r.covers).length} cover the site · ${site.rcos.length} reach the half mile`} tone="card" defaultOpen={false}>
        <ul className="divide-y divide-stone-100">
          {site.rcos.map((r) => (
            <li key={r.name} className="py-1.5">
              <div className="flex items-start gap-2">
                <span className={cx('mt-1 h-2.5 w-2.5 shrink-0 rounded-sm', r.covers ? 'bg-accent-600' : 'bg-accent-200')} />
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold leading-snug text-slate-900">{r.name}{r.cdc && <span className="ml-1.5 rounded bg-accent-50 px-1 py-px text-[10.5px] font-bold text-accent-700 ring-1 ring-accent-100">CDC</span>}</div>
                  <div className="text-[12px] text-slate-500">{r.type}{r.covers ? ' · covers the school' : ''}</div>
                  {r.meets && <div className="text-[12px] text-slate-600">Meets: {r.meets}</div>}
                  {r.website && <a className="text-[12px] font-semibold text-accent-600 hover:underline" href={/^https?:/i.test(r.website) ? r.website : `https://${r.website}`} target="_blank" rel="noopener noreferrer">{r.website.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '')}</a>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function TractDetail({ tract, site, onClear }) {
  const pr = site.profile;
  return (
    <div className="space-y-2.5">
      <div className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-stone-200/80">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[15px] font-bold text-slate-900">Census tract {tract.name}</div>
            <div className="text-[12px] text-slate-500">
              {tract.study ? `Study tract · ${tract.share != null ? `${Math.round(tract.share * 100)}% of its residents within the half mile` : 'in the study area'}` : 'Outside the study area'} · GEOID {tract.geoid}
            </div>
          </div>
          <button type="button" onClick={onClear} className="text-[12px] font-semibold text-accent-600 hover:underline">Close</button>
        </div>
      </div>
      <Section title="Tract profile" subtitle={`ACS ${site.acs_year - 4}–${site.acs_year} 5-year estimates`} tone="card">
        <div className="flex items-center gap-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <span className="flex-1" /><span>Tract</span><span className="w-[60px] text-right">Study</span><span className="w-[60px] text-right">City</span>
        </div>
        <ul className="divide-y divide-stone-100">
          {MEASURES.map((m) => {
            const p = m.profile && pr[m.profile];
            return (
              <li key={m.id} className="flex items-center gap-3 py-1.5 text-[13px]">
                <span className="min-w-0 flex-1 text-slate-600">{m.label}</span>
                <span className="font-semibold tabular-nums text-slate-900">{m.fmt(tract[m.id])}</span>
                <span className="w-[60px] text-right tabular-nums text-slate-500">{p ? m.fmt(p.school) : '—'}</span>
                <span className="w-[60px] text-right tabular-nums text-slate-500">{p ? m.fmt(p.city) : '—'}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">Tract estimates carry wide margins of error; read differences of a few points as noise.</p>
      </Section>
    </div>
  );
}

export default function SitePanel({ site, tract, onClearTract, open, setOpen, tab, setTab, onOnly, top = 12 }) {
  return (
    <AnimatePresence initial={false} mode="popLayout">
      {open ? (
        <motion.aside
          key="panel"
          style={{ transformOrigin: 'top right', top, maxHeight: `calc(100% - ${top + 12}px - 112px)` }}
          initial={{ opacity: 0, scale: 0.9, x: 14, filter: 'blur(6px)' }}
          animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.92, x: 14, filter: 'blur(6px)', transition: { duration: 0.18, ease: 'easeIn' } }}
          transition={SPRING_PANEL}
          className={cx('absolute right-3 z-[510] flex max-w-[calc(100%-24px)] flex-col', W, PANEL)}
        >
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-2.5">
            <Segmented size="xs" value={tab} onChange={setTab} options={[{ value: 'site', label: 'Site summary' }, { value: 'tract', label: tract ? `Tract ${tract.name}` : 'Tract' }]} />
            <button type="button" onClick={() => setOpen(false)} className={ICON_BTN} title="Hide panel" aria-label="Hide panel"><FoldIcon side="right" /></button>
          </div>
          <div className={cx('min-h-0 flex-1 overflow-y-auto px-3 pb-3', SCROLL)}>
            {tab === 'tract'
              ? tract ? <TractDetail tract={tract} site={site} onClear={onClearTract} /> : <p className="rounded-xl bg-stone-50 px-3 py-4 text-center text-[13px] text-slate-500 ring-1 ring-stone-200/70">Click a census tract on the map: turn on <b>Study census tracts</b>, or shade tracts under <b>Census tracts</b>.</p>
              : <SiteSummary site={site} onOnly={onOnly} />}
          </div>
        </motion.aside>
      ) : (
        <motion.button key="tab" type="button" onClick={() => setOpen(true)} initial={{ opacity: 0, scale: 0.6, x: 8 }} animate={{ opacity: 1, scale: 1, x: 0 }} exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.12 } }}
          transition={SPRING_TAB} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.95 }} style={{ top }} className={cx('absolute right-3 z-[510] text-slate-800', FLOAT_BTN)}>
          Site summary
          <span className="text-slate-600"><FoldIcon side="right" closed /></span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
