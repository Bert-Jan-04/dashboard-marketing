// scenes-core.jsx — shared visual system + primitives for the instruction video.
// Loaded after animations.jsx. Exports components to window for the scene files.

/* global React, useTime, useTimeline, useSprite, Sprite, Easing, interpolate, clamp */

// ── Design tokens (match the dakdekkersgids dashboard) ──────────────────────
const C = {
  bg:        '#0e0e0e',
  panel:     '#161616',
  card:      '#1c1c1c',
  card2:     '#121212',
  deep:      '#0b0b0b',
  border:    'rgba(255,255,255,0.09)',
  borderSoft:'rgba(255,255,255,0.05)',
  green:     '#02CE80',
  greenDim:  'rgba(2,206,128,0.09)',
  greenBd:   'rgba(2,206,128,0.40)',
  text:      '#ffffff',
  dim:       '#c0c0c0',
  muted:     '#8a8a8a',
  faint:     '#5a5a5a',
  faint2:    '#444444',
  blue:      '#4285f4',
  orange:    '#e37400',
  purple:    '#a78bfa',
  cyan:      '#06b6d4',
  amber:     '#f59e0b',
  pink:      '#ec4899',
  emerald:   '#10b981',
  red:       '#f87171',
};
const FONT = "'Segoe UI', 'Helvetica Neue', system-ui, sans-serif";
const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace";

// ── Reveal: fade + slide a block in, relative to the enclosing Sprite ────────
function Reveal({ at = 0, dur = 0.5, y = 16, x = 0, scaleFrom = 1, children, style = {} }) {
  const { localTime } = useSprite();
  const t = Easing.easeOutCubic(clamp((localTime - at) / dur, 0, 1));
  const sc = scaleFrom + (1 - scaleFrom) * t;
  return (
    <div style={{
      opacity: t,
      transform: `translate(${(1 - t) * x}px, ${(1 - t) * y}px) scale(${sc})`,
      willChange: 'transform, opacity',
      ...style,
    }}>
      {children}
    </div>
  );
}

// hold-aware value: 0→1 in [at, at+dur]
function useReveal(at = 0, dur = 0.5, ease = Easing.easeOutCubic) {
  const { localTime } = useSprite();
  return ease(clamp((localTime - at) / dur, 0, 1));
}

// ── Scene background (subtle vignette + grid) ───────────────────────────────
function SceneBG({ children, tone = C.bg }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, background: tone,
      fontFamily: FONT, overflow: 'hidden',
    }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(120% 90% at 50% 0%, rgba(2,206,128,0.05), transparent 55%)',
      }} />
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.5,
        backgroundImage: `linear-gradient(${C.borderSoft} 1px, transparent 1px), linear-gradient(90deg, ${C.borderSoft} 1px, transparent 1px)`,
        backgroundSize: '54px 54px',
        maskImage: 'radial-gradient(120% 120% at 50% 40%, #000 30%, transparent 80%)',
        WebkitMaskImage: 'radial-gradient(120% 120% at 50% 40%, #000 30%, transparent 80%)',
      }} />
      {children}
    </div>
  );
}

// ── Eyebrow (small uppercase label with green dot) ──────────────────────────
function Eyebrow({ children, color = C.green, x, y, dot = true }) {
  return (
    <div style={{
      position: x != null ? 'absolute' : 'relative', left: x, top: y,
      display: 'flex', alignItems: 'center', gap: 9,
      fontSize: 13, fontWeight: 700, letterSpacing: '2px',
      textTransform: 'uppercase', color,
    }}>
      {dot && <span style={{
        width: 8, height: 8, borderRadius: '50%', background: color,
        boxShadow: `0 0 12px ${color}`,
      }} />}
      {children}
    </div>
  );
}

// ── Chip / tag ──────────────────────────────────────────────────────────────
function Chip({ children, color = C.green, solid = false }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '5px 11px', borderRadius: 7, fontSize: 13, fontWeight: 600,
      fontFamily: FONT,
      color: solid ? '#001b10' : color,
      background: solid ? color : `${color}1a`,
      border: `1px solid ${solid ? color : color + '55'}`,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

// ── Card primitive ──────────────────────────────────────────────────────────
function Card({ children, style = {}, glow = false, accent = C.green }) {
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`, borderRadius: 16,
      boxShadow: glow ? `0 0 0 1px ${accent}33, 0 24px 60px rgba(0,0,0,0.45)` : '0 18px 44px rgba(0,0,0,0.35)',
      ...style,
    }}>
      {children}
    </div>
  );
}

// ── Dashboard mock frame: sidebar + header, content slot ────────────────────
const NAV = [
  { sec: 'Overzicht' },
  { k: 'home',          label: 'Home' },
  { k: 'dashboard',     label: 'Dashboard' },
  { k: 'kantoor',       label: 'Kantoor' },
  { sec: 'Data bronnen' },
  { k: 'searchconsole', label: 'Search Console' },
  { k: 'analytics',     label: 'Analytics' },
  { k: 'trends',        label: 'Trends' },
  { k: 'keywords',      label: 'Keyword Onderzoek' },
  { k: 'clusters',      label: 'Clusterprestaties' },
  { k: 'analyse',       label: 'Analyse' },
  { k: 'clarity',       label: 'Clarity' },
  { k: 'concurrenten',  label: 'Concurrenten' },
];

function DashboardMock({ active = 'dashboard', title = 'Marketing Intelligence', children, scale = 1, x = 0, y = 0, width = 1180, height = 600 }) {
  return (
    <div style={{
      position: 'absolute', left: x, top: y, width, height,
      transform: `scale(${scale})`, transformOrigin: 'top left',
      background: C.card2, border: `1px solid ${C.border}`, borderRadius: 14,
      overflow: 'hidden', display: 'flex', boxShadow: '0 30px 80px rgba(0,0,0,0.55)',
      fontFamily: FONT,
    }}>
      {/* Sidebar */}
      <div style={{ width: 214, background: C.panel, borderRight: `1px solid ${C.border}`, padding: '20px 0', flexShrink: 0 }}>
        <div style={{ padding: '0 20px 18px', borderBottom: `1px solid ${C.border}`, marginBottom: 14 }}>
          <div style={{ fontSize: 14.5, fontWeight: 800, color: C.text }}>Marketing<span style={{ color: C.green }}>Intelligence</span></div>
          <div style={{ fontSize: 9.5, color: C.muted, letterSpacing: '1px', textTransform: 'uppercase', marginTop: 3 }}>dakdekkersgids.nl</div>
        </div>
        {NAV.map((n, i) => n.sec ? (
          <div key={i} style={{ fontSize: 9, color: C.faint, letterSpacing: '1.1px', textTransform: 'uppercase', padding: '0 20px', margin: '14px 0 7px' }}>{n.sec}</div>
        ) : (
          <div key={i} style={{
            padding: '8px 20px', display: 'flex', alignItems: 'center', gap: 10,
            fontSize: 12, color: active === n.k ? C.text : C.muted,
            background: active === n.k ? C.greenDim : 'transparent',
            borderLeft: `3px solid ${active === n.k ? C.green : 'transparent'}`,
            transition: 'all 0.3s',
          }}>
            <span style={{ fontSize: 8, color: active === n.k ? C.green : C.faint2 }}>◼</span>{n.label}
          </div>
        ))}
      </div>
      {/* Main */}
      <div style={{ flex: 1, padding: '26px 30px', position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: C.text }}>{title}</div>
          <div style={{
            background: C.greenDim, border: `1px solid ${C.greenBd}`, color: C.green,
            padding: '7px 15px', borderRadius: 18, fontSize: 12, fontWeight: 500,
          }}>Week {38 + 0}</div>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Code window with line-by-line reveal + diff highlighting ────────────────
// lines: [{ t:'text', k:'plain'|'add'|'del'|'hi'|'comment', indent:0 }]
function CodeWindow({ file = 'rules.py', lines = [], x = 0, y = 0, width = 560, at = 0, perLine = 0.12, title, fontSize = 15, style = {} }) {
  const { localTime } = useSprite();
  return (
    <div style={{
      position: x != null && y != null ? 'absolute' : 'relative', left: x, top: y, width,
      background: C.deep, border: `1px solid ${C.border}`, borderRadius: 12,
      overflow: 'hidden', boxShadow: '0 28px 70px rgba(0,0,0,0.55)', fontFamily: MONO,
      ...style,
    }}>
      {/* titlebar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
        background: '#161616', borderBottom: `1px solid ${C.border}`,
      }}>
        <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#ff5f56' }} />
        <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#ffbd2e' }} />
        <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#27c93f' }} />
        <span style={{ marginLeft: 8, fontSize: 12.5, color: C.dim, fontFamily: MONO }}>{file}</span>
        {title && <span style={{ marginLeft: 'auto', fontSize: 11, color: C.faint, fontFamily: FONT }}>{title}</span>}
      </div>
      {/* body */}
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 3 }}>
        {lines.map((ln, i) => {
          const appear = clamp((localTime - at - i * perLine) / 0.32, 0, 1);
          const kind = ln.k || 'plain';
          const colorMap = { plain: C.dim, add: C.green, del: C.red, hi: C.amber, comment: C.faint };
          const bg = kind === 'add' ? 'rgba(2,206,128,0.10)' : kind === 'del' ? 'rgba(248,113,113,0.10)' : 'transparent';
          const marker = kind === 'add' ? '+ ' : kind === 'del' ? '- ' : '  ';
          return (
            <div key={i} style={{
              opacity: appear, transform: `translateX(${(1 - appear) * -8}px)`,
              fontSize, lineHeight: 1.55, whiteSpace: 'pre', color: colorMap[kind],
              background: bg, borderRadius: 4, padding: '0 6px', margin: '0 -6px',
              fontFamily: MONO, fontStyle: kind === 'comment' ? 'italic' : 'normal',
            }}>
              <span style={{ color: kind === 'add' ? C.green : kind === 'del' ? C.red : 'transparent', userSelect: 'none' }}>{marker}</span>
              {'  '.repeat(ln.indent || 0)}{ln.t}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Caption / subtitle track (reads absolute timeline) ──────────────────────
// cues: [{ t, text }] sorted by t. Renders the active line in a bottom bar.
function CaptionTrack({ cues }) {
  const time = useTime();
  let idx = -1;
  for (let i = 0; i < cues.length; i++) { if (time >= cues[i].t) idx = i; else break; }
  const cue = idx >= 0 ? cues[idx] : null;
  const since = cue ? time - cue.t : 0;
  const appear = clamp(since / 0.35, 0, 1);
  if (!cue || !cue.text) return null;
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, bottom: 30,
      display: 'flex', justifyContent: 'center', pointerEvents: 'none', padding: '0 90px',
    }}>
      <div style={{
        maxWidth: 880, textAlign: 'center',
        opacity: appear, transform: `translateY(${(1 - appear) * 8}px)`,
        background: 'rgba(8,8,8,0.78)', backdropFilter: 'blur(8px)',
        border: `1px solid ${C.border}`, borderRadius: 12,
        padding: '12px 22px', fontFamily: FONT,
        fontSize: 20, lineHeight: 1.45, fontWeight: 500, color: '#eaeaea',
        boxShadow: '0 14px 40px rgba(0,0,0,0.5)',
      }}>
        {cue.text}
      </div>
    </div>
  );
}

// ── Chapter rail (clickable) at the very top of the canvas ──────────────────
// Tracks the active chapter from the timeline and reports it upward.
// Behaves like CaptionTrack (a reliable context consumer); the rail itself
// then receives `active` as a plain prop so it always re-renders.
function ChapterTracker({ chapters, onChange }) {
  const time = useTime();
  let active = 0;
  for (let i = 0; i < chapters.length; i++) { if (time >= chapters[i].t) active = i; else break; }
  React.useEffect(() => { onChange(active); }, [active]);
  return null;
}

function ChapterRail({ chapters, active = 0 }) {
  const jump = (t) => { if (window.__jump) window.__jump(t); };
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, height: 46, zIndex: 50,
      display: 'flex', alignItems: 'center', gap: 4, padding: '0 16px',
      background: 'linear-gradient(180deg, rgba(8,8,8,0.92), rgba(8,8,8,0))',
      fontFamily: FONT,
    }}>
      <div style={{ fontSize: 11.5, fontWeight: 800, color: C.green, letterSpacing: '0.5px', marginRight: 10, display: 'flex', alignItems: 'center', gap: 7 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.green, boxShadow: `0 0 8px ${C.green}` }} />
        OVERDRACHT
      </div>
      {chapters.map((ch, i) => (
        <div key={i} onClick={() => jump(ch.t + 0.02)} style={{
          cursor: 'pointer', padding: '5px 10px', borderRadius: 7,
          fontSize: 11.5, fontWeight: active === i ? 700 : 500,
          color: active === i ? C.text : C.faint,
          background: active === i ? C.greenDim : 'transparent',
          border: `1px solid ${active === i ? C.greenBd : 'transparent'}`,
          display: 'flex', alignItems: 'center', gap: 6, transition: 'all .2s',
        }}>
          <span style={{ fontSize: 9.5, opacity: 0.7 }}>{String(i + 1).padStart(2, '0')}</span>
          {ch.label}
        </div>
      ))}
    </div>
  );
}

// ── Animated connector line (draws on with progress) ────────────────────────
function FlowArrow({ from, to, progress = 1, color = C.green, dashed = false }) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ang = Math.atan2(dy, dx) * 180 / Math.PI;
  return (
    <div style={{
      position: 'absolute', left: from.x, top: from.y, width: len * progress, height: 2,
      background: dashed ? `repeating-linear-gradient(90deg, ${color} 0 7px, transparent 7px 13px)` : color,
      transformOrigin: 'left center', transform: `rotate(${ang}deg)`,
      opacity: 0.75, borderRadius: 2,
    }} />
  );
}

Object.assign(window, {
  C, FONT, MONO, Reveal, useReveal, SceneBG, Eyebrow, Chip, Card,
  DashboardMock, NAV, CodeWindow, CaptionTrack, ChapterRail, ChapterTracker, FlowArrow,
});
