/** The two maps, side by side, with the numbers that tell them apart. */
import React, { useEffect, useState } from 'react';
import { fmtInt, fmtMoney, fmtPct } from '../lib/layers';

const SCHOOLS = [
  { slug: 'wagner', blurb: 'Northwest Philadelphia', tone: '#DDA196' },
  { slug: 'blankenburg', blurb: 'West Philadelphia', tone: '#C9CCDF' },
];

export default function Landing({ onOpen }) {
  const [sites, setSites] = useState({});
  useEffect(() => {
    SCHOOLS.forEach(({ slug }) => fetch(`/data/${slug}/site.json`).then((r) => r.json()).then((s) => setSites((m) => ({ ...m, [slug]: s }))).catch(() => {}));
    document.title = 'Community Maps · Wagner & Blankenburg';
  }, []);
  return (
    <div className="min-h-full bg-[#faf9f6]">
      <div className="mx-auto max-w-5xl px-4 py-10 sm:py-16">
        <div className="text-[12px] font-semibold uppercase tracking-[0.14em] text-accent-500">Reimagining Closed Schools · Final Two School</div>
        <h1 className="mt-2 text-[30px] font-bold leading-tight text-ink sm:text-[38px]">Community maps</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
          One interactive map for each school site: community assets within a mile, the study area and its registered community organizations,
          census tracts, transit and street safety, and the economy and land around it.
        </p>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {SCHOOLS.map(({ slug, blurb, tone }) => {
            const s = sites[slug];
            const total = s ? Object.values(s.asset_counts).reduce((a, c) => a + c.mile, 0) : null;
            const half = s ? Object.values(s.asset_counts).reduce((a, c) => a + c.half, 0) : null;
            const pr = s?.profile || {};
            return (
              <button key={slug} type="button" onClick={() => onOpen(slug)} className="group overflow-hidden rounded-2xl bg-white text-left shadow-[0_10px_40px_-14px_rgba(15,23,42,0.3)] ring-1 ring-black/5 transition hover:-translate-y-0.5 hover:shadow-[0_18px_50px_-14px_rgba(15,23,42,0.35)]">
                <div className="h-2" style={{ background: tone }} />
                <div className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[22px] font-bold text-ink">{s?.school || slug[0].toUpperCase() + slug.slice(1)}</div>
                      <div className="text-[13px] text-ink-2">{s ? `${s.address} · ` : ''}{blurb}</div>
                    </div>
                    <span className="mt-1 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg bg-accent-600 px-3 py-1.5 text-[13px] font-semibold text-white shadow-sm group-hover:bg-accent-700">Open map →</span>
                  </div>
                  <dl className="mt-5 grid grid-cols-3 gap-3">
                    {[
                      ['Places within ½ mile', s ? fmtInt(half) : '…'],
                      ['Within 1 mile', s ? fmtInt(total) : '…'],
                      ['RCOs at the site', s ? fmtInt(s.rcos.filter((r) => r.covers).length) : '…'],
                      ['Median household income', pr['Median household income'] ? fmtMoney(pr['Median household income'].school) : '…'],
                      ['Poverty rate', pr['Poverty rate'] ? fmtPct(pr['Poverty rate'].school) : '…'],
                      ['15-min walk residents', s?.walk?.length ? fmtInt(s.walk[s.walk.length - 1].residents_2020) : '…'],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <dt className="text-[11.5px] leading-tight text-ink-muted">{k}</dt>
                        <dd className="mt-0.5 text-[18px] font-bold tabular-nums text-ink">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </button>
            );
          })}
        </div>
        <p className="mt-8 text-[12px] leading-relaxed text-ink-muted">
          Sources: the studio's Community Asset, Background, Transportation and Economic analyses, built from City of Philadelphia open data,
          the American Community Survey 5-year estimates, SEPTA GTFS and PennDOT crash data. Basemap © City of Philadelphia, Esri.
        </p>
      </div>
    </div>
  );
}
