/**
 * Small UI primitives in the Market Analysis Tool / County Screen design language
 * (white glass panels, tinted collapsible sections, switch rows), re-coloured to the studio's Indigo.
 */
import React, { useId, useState } from 'react';
import { createPortal } from 'react-dom';
// eslint-disable-next-line no-unused-vars
import { AnimatePresence, motion } from 'framer-motion';

export const cx = (...parts) => parts.filter(Boolean).join(' ');

export const GLASS = 'bg-white/95 ring-1 ring-black/5 backdrop-blur';
export const PANEL = `rounded-2xl ${GLASS} shadow-[0_10px_40px_-10px_rgba(15,23,42,0.25)]`;
export const FLOAT_BTN = `inline-flex items-center gap-2 rounded-xl ${GLASS} px-3 py-2 text-[13px] font-semibold text-slate-700 shadow-lg hover:bg-white hover:text-slate-900`;
export const ICON_BTN = 'rounded-lg p-1.5 text-slate-500 transition hover:bg-stone-100 hover:text-slate-900';
export const SCROLL = '[scrollbar-width:thin] [scrollbar-color:#d6d3d1_transparent]';

export const SPRING_PANEL = { type: 'spring', stiffness: 360, damping: 30, mass: 0.85 };
export const SPRING_TAB = { type: 'spring', stiffness: 520, damping: 26, mass: 0.7 };
export const SPRING_FOLD = { type: 'spring', stiffness: 380, damping: 38, mass: 0.9 };

export const Chevron = ({ open }) => (
  <motion.svg animate={{ rotate: open ? 90 : 0 }} transition={SPRING_TAB} className="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path d="M7.2 4.2a1 1 0 011.4 0l5 5a1 1 0 010 1.4l-5 5a1 1 0 11-1.4-1.4L11.5 10 7.2 5.6a1 1 0 010-1.4z" />
  </motion.svg>
);

/** Collapsible card. tone "section" = accent tint (rail groups); "card" = neutral. */
export function Section({ title, subtitle, action, tone = 'section', defaultOpen = true, open: openProp, onOpenChange, children, bodyClassName }) {
  const [openOwn, setOpenOwn] = useState(defaultOpen);
  const open = openProp ?? openOwn;
  const toggle = () => (onOpenChange ? onOpenChange(!open) : setOpenOwn(!open));
  const tinted = tone === 'section';
  return (
    <div className={cx('rounded-xl bg-white ring-1', tinted ? 'ring-accent-100/80' : 'ring-stone-200/80')}>
      <div
        className={cx(
          'flex items-center gap-2 rounded-xl px-3 py-2.5',
          tinted ? 'bg-accent-50/80' : 'bg-white',
          open && (tinted ? 'rounded-b-none border-b border-accent-50' : 'rounded-b-none border-b border-stone-100'),
        )}
      >
        <button type="button" onClick={toggle} aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className={tinted ? 'text-accent-600' : 'text-slate-500'}><Chevron open={open} /></span>
          <span className="min-w-0">
            <span className={cx('block text-[14px] font-semibold leading-tight', tinted ? 'text-accent-800' : 'text-slate-900')}>{title}</span>
            {subtitle && <span className={cx('mt-0.5 block text-[12px] leading-snug', tinted ? 'text-accent-700/70' : 'text-slate-500')}>{subtitle}</span>}
          </span>
        </button>
        {action}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div key="body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={SPRING_FOLD} className="overflow-hidden">
            <motion.div initial={{ y: -8 }} animate={{ y: 0 }} transition={SPRING_FOLD} className={cx('px-3 pb-3 pt-2.5', bodyClassName)}>
              {children}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Switch row with an optional swatch (any node) and a count on the right. */
export function ToggleRow({ on, onClick, label, caption, info, swatch, count, disabled }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        'flex w-full gap-3 rounded-xl bg-white px-3 py-2 text-left ring-1 transition disabled:opacity-50',
        caption ? 'items-start' : 'items-center',
        on ? 'bg-accent-50/50 ring-accent-100' : 'ring-stone-200/80 hover:ring-stone-300',
      )}
    >
      <span className={cx('relative inline-block h-5 w-9 shrink-0 rounded-full transition-colors', caption && 'mt-0.5', on ? 'bg-accent-600' : 'bg-stone-300')}>
        <span className={cx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[18px]' : 'translate-x-0.5')} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          {swatch}
          <span className="truncate text-[13px] font-semibold text-slate-900">{label}</span>
          {info && <InfoTip label={`About ${label}`}>{info}</InfoTip>}
          {count != null && <span className="ml-auto shrink-0 text-[12px] font-semibold tabular-nums text-slate-500">{count}</span>}
        </span>
        {caption && <span className="mt-0.5 block text-[12px] leading-snug text-slate-600">{caption}</span>}
      </span>
    </button>
  );
}

/** Radio-style list row. */
export function RadioRow({ on, onClick, label, sub, info, right }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onClick}
      className={cx('flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition', on ? 'bg-accent-50/80 ring-2 ring-accent-500' : 'ring-1 ring-transparent hover:bg-stone-50')}
    >
      <span
        className={cx('h-3.5 w-3.5 shrink-0 rounded-full border-2', on ? 'border-accent-600' : 'border-stone-300')}
        style={on ? { background: 'radial-gradient(circle, #393864 45%, transparent 50%)' } : undefined}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="min-w-0 text-[13px] font-medium leading-snug text-slate-900">{label}</span>
          {info && <InfoTip label={`About ${label}`}>{info}</InfoTip>}
        </span>
        {sub && <span className="block truncate text-[12px] text-slate-500">{sub}</span>}
      </span>
      {right}
    </button>
  );
}

/** Segmented control with a sliding white pill. */
export function Segmented({ options, value, onChange, size = 'sm', full = false }) {
  const id = useId();
  return (
    <div className={cx('relative rounded-lg bg-stone-100 p-0.5 ring-1 ring-stone-200/70', full ? 'grid' : 'inline-flex')} style={full ? { gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` } : undefined}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={cx('relative whitespace-nowrap rounded-md font-medium transition-colors', size === 'xs' ? 'px-2 py-1 text-[12px]' : 'px-3 py-1.5 text-[13px]', on ? 'text-slate-900' : 'text-slate-600 hover:text-slate-900')}
          >
            {on && <motion.span layoutId={`seg-${id}`} transition={SPRING_TAB} className="absolute inset-0 rounded-md bg-white shadow-sm ring-1 ring-black/5" />}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function ActionChip({ onClick, active, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx('rounded-full px-2 py-0.5 text-[12px] font-semibold ring-1 transition', active ? 'bg-accent-600 text-white ring-accent-600' : 'bg-white text-accent-600 ring-accent-100 hover:bg-accent-50')}
    >
      {children}
    </button>
  );
}

/** Label / value rows. */
export function Rows({ items }) {
  return (
    <ul className="divide-y divide-stone-100">
      {items.filter(Boolean).map((it) => (
        <li key={it.label} className="flex items-start gap-3 py-1.5 text-[13px]">
          <span className="min-w-0 flex-1 text-slate-600">{it.label}</span>
          <span className={cx('max-w-[60%] text-right font-semibold tabular-nums text-slate-900', it.wrap ? 'whitespace-normal' : 'truncate')}>{it.value}</span>
          {it.sub != null && <span className="w-[72px] shrink-0 text-right tabular-nums text-slate-500">{it.sub}</span>}
        </li>
      ))}
    </ul>
  );
}

export function FoldIcon({ side = 'left', closed = false }) {
  const arrow = side === 'left' ? (closed ? 'm14 9 3 3-3 3' : 'm16 15-3-3 3-3') : (closed ? 'm10 15-3-3 3-3' : 'm8 9 3 3-3 3');
  const bar = side === 'left' ? 'M9 3v18' : 'M15 3v18';
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="18" height="18" x="3" y="3" rx="2" /><path d={bar} /><path d={arrow} />
    </svg>
  );
}

export function InfoTip({ children, label = 'More info' }) {
  const [pos, setPos] = useState(null);
  const show = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = r.right + 300 > window.innerWidth ? Math.max(8, r.left - 290) : r.right + 10;
    setPos({ x, y: r.top + r.height / 2 });
  };
  const hide = () => setPos(null);
  return (
    <>
      <span
        role="img"
        tabIndex={0}
        aria-label={label}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => e.stopPropagation()}
        className="inline-grid h-4 w-4 shrink-0 cursor-help place-items-center rounded-full text-slate-400 transition-colors hover:text-accent-600 focus:text-accent-600 focus:outline-none"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
      </span>
      {pos && createPortal(
        <div role="tooltip" className="pointer-events-none fixed z-[1000] w-[280px] -translate-y-1/2 rounded-xl bg-white/95 p-3 text-[12px] leading-snug text-slate-700 shadow-[0_10px_40px_-10px_rgba(15,23,42,0.35)] ring-1 ring-black/5 backdrop-blur" style={{ left: pos.x, top: pos.y }}>
          {children}
        </div>,
        document.body,
      )}
    </>
  );
}

export const Spinner = () => (
  <svg className="h-3.5 w-3.5 animate-spin text-accent-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-label="Loading"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
);
