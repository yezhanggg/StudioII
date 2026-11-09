// Check every link the map can show: websites on community assets, RCOs and BIDs, and each school's SDP
// dashboard. Links are normalised the same way the app does (src/lib/layers.js `href`).
// Run: node scripts/check_links.mjs [--json out.json]
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('../public/data/', import.meta.url).pathname;
const href = (u) => (!u ? '' : /^https?:\/\//i.test(u) ? u : /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(u.trim()) ? `https://${u.trim()}` : '');

const links = new Map(); // url -> [where]
const add = (raw, where) => {
  const u = href(String(raw || '').trim());
  if (!u) { if (raw && String(raw).trim()) (links.get(`UNUSABLE:${raw}`) || links.set(`UNUSABLE:${raw}`, []).get(`UNUSABLE:${raw}`)).push(where); return; }
  (links.get(u) || links.set(u, []).get(u)).push(where);
};
const walk = (dir) => readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]));
for (const f of walk(ROOT).filter((f) => f.endsWith('.json'))) {
  const d = JSON.parse(readFileSync(f, 'utf8'));
  const rel = f.slice(ROOT.length);
  for (const ft of d.features || []) if (ft.properties?.website) add(ft.properties.website, `${rel}: ${ft.properties.name}`);
  for (const a of [...(d.assets || []), ...(d.context || [])]) {          // sources.json: the documentation window
    if (a.landing_url) add(a.landing_url, `sources.json: ${a.title} (landing page)`);
  }
  for (const s of d.schools || []) {
    add(s.dashboard, `schools.json: ${s.short} SDP dashboard`);
    for (const r of s.rcos || []) if (r.website) add(r.website, `schools.json: ${s.short} RCO ${r.name}`);
  }
}

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36';
async function check(url) {
  for (const method of ['HEAD', 'GET']) {
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 15000);
      const r = await fetch(url, { method, redirect: 'follow', signal: ctl.signal, headers: { 'User-Agent': UA, Accept: 'text/html,*/*' } });
      clearTimeout(t);
      if (r.ok || method === 'GET') return { status: r.status, final: r.url };
    } catch (e) {
      if (method === 'GET') return { status: 0, error: e.cause?.code || e.name || String(e) };
    }
  }
  return { status: 0 };
}

const urls = [...links.keys()];
const out = [];
let i = 0;
await Promise.all(Array.from({ length: 8 }, async () => {
  while (i < urls.length) {
    const u = urls[i++];
    if (u.startsWith('UNUSABLE:')) { out.push({ url: u.slice(9), status: 'unusable', where: links.get(u) }); continue; }
    out.push({ url: u, ...(await check(u)), where: links.get(u) });
  }
}));
const bad = out.filter((r) => r.status === 'unusable' || !(r.status >= 200 && r.status < 400));
const blocked = bad.filter((r) => [401, 403, 405, 429, 999].includes(r.status));
const slow = bad.filter((r) => r.error === 'AbortError');           // no answer within 15 s: kept, not called dead
const broken = bad.filter((r) => !blocked.includes(r) && !slow.includes(r));
console.log(`${out.length} links: ${out.length - bad.length} work, ${blocked.length} refuse automated checks (likely fine in a browser), ${slow.length} slow to answer (kept), ${broken.length} broken or unusable`);
for (const r of broken) console.log(`  BROKEN ${r.status}${r.error ? ` ${r.error}` : ''}  ${r.url}  ← ${r.where[0]}${r.where.length > 1 ? ` (+${r.where.length - 1})` : ''}`);
for (const r of blocked) console.log(`  BLOCKED ${r.status}  ${r.url}  ← ${r.where[0]}`);
const j = process.argv.indexOf('--json');
if (j > 0) writeFileSync(process.argv[j + 1], JSON.stringify(out, null, 1));

// Dead links (not merely bot-blocked, not Facebook, which refuses scripts) are written for the build to drop.
// Dead links accumulate: once the build has dropped one it is no longer checked, so earlier finds are kept.
const deadFile = new URL('./broken_links.json', import.meta.url);
let earlier = [];
try { earlier = JSON.parse(readFileSync(deadFile, 'utf8')); } catch { /* first run */ }
const dead = [...new Set([...earlier, ...broken.filter((r) => !/facebook\.com/.test(r.url)).map((r) => r.url)])];
writeFileSync(deadFile, JSON.stringify(dead.sort(), null, 1));
console.log(`wrote scripts/broken_links.json (${dead.length} dead links the build leaves out)`);
