// scenes-1.jsx — Chapters: Intro, Pipeline, Data sources, Modules tour, AI agents.
// Each scene assumes it is rendered inside a <Sprite> (uses useSprite localTime via Reveal).

/* global React, useSprite, useTime, Easing, interpolate, clamp,
   C, FONT, MONO, Reveal, useReveal, SceneBG, Eyebrow, Chip, Card,
   DashboardMock, CodeWindow, FlowArrow */

// ════════════════════════════════════════════════════════════════════════════
// SCENE 0 — INTRO
// ════════════════════════════════════════════════════════════════════════════
function SceneIntro() {
  const r1 = useReveal(0.2, 0.7);
  return (
    <SceneBG>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <Reveal at={0.1} dur={0.6} y={10}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, justifyContent: 'center', marginBottom: 26 }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: C.green, boxShadow: `0 0 14px ${C.green}` }} />
            <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '3px', color: C.green, textTransform: 'uppercase' }}>Live dashboard · Overdracht</span>
          </div>
        </Reveal>
        <Reveal at={0.35} dur={0.7} y={20}>
          <div style={{ fontSize: 68, fontWeight: 800, color: C.text, lineHeight: 1.06, letterSpacing: '-1.5px' }}>
            Marketing Intelligence
          </div>
          <div style={{ fontSize: 68, fontWeight: 800, color: C.green, lineHeight: 1.1, letterSpacing: '-1.5px' }}>
            dakdekkersgids.nl
          </div>
        </Reveal>
        <Reveal at={0.85} dur={0.6} y={14}>
          <div style={{ fontSize: 23, color: C.muted, marginTop: 26, maxWidth: 760, lineHeight: 1.5 }}>
            De complete instructiegids: hoe het dashboard werkt, wat je ermee kan,
            en hoe je het overzet naar een nieuwe website.
          </div>
        </Reveal>
        <Reveal at={1.3} dur={0.6} y={12}>
          <div style={{ display: 'flex', gap: 10, marginTop: 34, justifyContent: 'center' }}>
            {['Hoe het werkt', '9 AI-agenten', 'Nieuwe site toevoegen'].map((t, i) => (
              <Chip key={i} color={[C.green, C.purple, C.amber][i]}>{t}</Chip>
            ))}
          </div>
        </Reveal>
      </div>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SCENE 1 — PIPELINE (Wat is dit?)
// ════════════════════════════════════════════════════════════════════════════
const PIPE = [
  { icon: '📡', t: 'Data ophalen', s: 'GSC · GA4 · Mangools\nClarity · Concurrenten', c: C.blue },
  { icon: '📊', t: 'Visualiseren', s: 'Rankings · Clusters\nTrends · Concurrenten', c: C.cyan },
  { icon: '🤖', t: 'AI analyseren', s: '9 gespecialiseerde\nAI-agenten', c: C.purple },
  { icon: '✅', t: 'Actiepunten', s: 'Taken · Briefings\nRapporten · Mails', c: C.green },
];
function ScenePipeline() {
  const cardW = 232, gap = 70, startX = (1280 - (cardW * 4 + gap * 3)) / 2, cy = 360;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={10} style={{ position: 'absolute', top: 96, left: 0, right: 0, textAlign: 'center' }}>
        <Eyebrow dot={false} color={C.green}>01 · Wat is dit?</Eyebrow>
        <div style={{ fontSize: 44, fontWeight: 800, color: C.text, marginTop: 12, letterSpacing: '-1px' }}>
          Eén plek voor alle SEO- &amp; leadgen-data
        </div>
      </Reveal>

      {/* arrows behind cards */}
      {[0, 1, 2].map(i => {
        const fx = startX + cardW * (i + 1) + gap * i + 8;
        const p = clamp((useSprite().localTime - (1.0 + i * 0.5)) / 0.5, 0, 1);
        return <FlowArrow key={i} from={{ x: fx, y: cy + 70 }} to={{ x: fx + gap - 16, y: cy + 70 }} progress={p} color={C.faint} />;
      })}

      {PIPE.map((p, i) => (
        <Reveal key={i} at={0.7 + i * 0.5} dur={0.55} y={26} scaleFrom={0.9}
          style={{ position: 'absolute', left: startX + (cardW + gap) * i, top: cy, width: cardW }}>
          <Card glow accent={p.c} style={{ padding: '26px 22px', textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 14 }}>{p.icon}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: C.text, marginBottom: 9 }}>{p.t}</div>
            <div style={{ fontSize: 14.5, color: C.muted, lineHeight: 1.6, whiteSpace: 'pre-line' }}>{p.s}</div>
            <div style={{ marginTop: 16, height: 3, borderRadius: 2, background: p.c, opacity: 0.8 }} />
          </Card>
        </Reveal>
      ))}

      <Reveal at={3.2} dur={0.6} y={14} style={{ position: 'absolute', bottom: 60, left: 0, right: 0, textAlign: 'center' }}>
        <div style={{ fontSize: 22, color: C.dim }}>
          Eén doel: <span style={{ color: C.green, fontWeight: 700 }}>meer leads</span> voor de dakdekkers.
        </div>
      </Reveal>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SCENE 2 — DATA SOURCES
// ════════════════════════════════════════════════════════════════════════════
const SOURCES = [
  { n: 'Search Console', c: C.blue,   d: 'Keywords · posities\nCTR · impressies' },
  { n: 'Analytics 4',    c: C.orange, d: 'Sessies · kanalen\nbounce · aanvragen' },
  { n: 'Mangools',       c: C.purple, d: 'Zoekvolume · difficulty\nCPC · KWFinder' },
  { n: 'Clarity',        c: C.cyan,   d: 'Rage / dead clicks\nUX · scroll depth' },
  { n: 'Concurrenten',   c: C.amber,  d: 'Sitemaps · keywords\ndreigingsscore' },
];
function SceneSources() {
  const lt = useSprite().localTime;
  const cx = 640, cy = 392;
  const cardW = 198, gap = 22, totalW = cardW * 5 + gap * 4, startX = (1280 - totalW) / 2, topY = 196;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={10} style={{ position: 'absolute', top: 96, left: 0, right: 0, textAlign: 'center' }}>
        <Eyebrow dot={false} color={C.green}>02 · Databronnen</Eyebrow>
        <div style={{ fontSize: 40, fontWeight: 800, color: C.text, marginTop: 12, letterSpacing: '-1px' }}>
          Vijf bronnen, automatisch opgehaald
        </div>
      </Reveal>

      {/* feed lines */}
      {SOURCES.map((s, i) => {
        const fx = startX + (cardW + gap) * i + cardW / 2;
        const p = clamp((lt - (0.7 + i * 0.35)) / 0.6, 0, 1);
        const dx = cx - fx, dy = cy - 56 - (topY + 120);
        const len = Math.sqrt(dx * dx + dy * dy);
        const ang = Math.atan2(dy, dx) * 180 / Math.PI;
        return <div key={'l' + i} style={{ position: 'absolute', left: fx, top: topY + 120, width: len * p, height: 2, background: s.c, opacity: 0.35, transformOrigin: 'left center', transform: `rotate(${ang}deg)` }} />;
      })}

      {SOURCES.map((s, i) => (
        <Reveal key={i} at={0.5 + i * 0.35} dur={0.5} y={20} scaleFrom={0.9}
          style={{ position: 'absolute', left: startX + (cardW + gap) * i, top: topY, width: cardW }}>
          <Card accent={s.c} style={{ padding: '18px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: s.c }} />
              <span style={{ fontSize: 15, fontWeight: 700, color: s.c }}>{s.n}</span>
            </div>
            <div style={{ fontSize: 13.5, color: C.muted, lineHeight: 1.65, whiteSpace: 'pre-line' }}>{s.d}</div>
          </Card>
        </Reveal>
      ))}

      {/* central store */}
      <Reveal at={2.4} dur={0.6} scaleFrom={0.8} style={{ position: 'absolute', left: cx - 110, top: cy - 4, width: 220 }}>
        <Card glow accent={C.green} style={{ padding: '20px 20px', textAlign: 'center' }}>
          <div style={{ fontFamily: MONO, fontSize: 17, color: C.green, fontWeight: 700 }}>/data</div>
          <div style={{ fontSize: 13, color: C.muted, marginTop: 6 }}>wekelijkse JSON-snapshots</div>
        </Card>
      </Reveal>
      <Reveal at={3.0} dur={0.5} y={10} style={{ position: 'absolute', bottom: 132, left: 0, right: 0, textAlign: 'center' }}>
        <div style={{ fontSize: 19, color: C.dim }}>Wekelijks ververst — het dashboard leest deze snapshots.</div>
      </Reveal>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SCENE 3 — MODULES TOUR
// ════════════════════════════════════════════════════════════════════════════
const MODULES = [
  { k: 'dashboard',     label: 'Dashboard',         c: C.green,  kind: 'kpi',     desc: 'Wekelijks KPI-overzicht: clicks, sessies en leads per cluster. Het startpunt van elke werkweek.' },
  { k: 'searchconsole', label: 'Search Console',    c: C.blue,   kind: 'table',   desc: 'Alle rankende keywords met positie en CTR — inclusief quick wins op positie 4–10.' },
  { k: 'analytics',     label: 'Analytics',         c: C.orange, kind: 'channels',desc: 'GA4: sessies per kanaal, bounce rate en offerteaanvragen per landingspagina.' },
  { k: 'trends',        label: 'Trends',            c: C.purple, kind: 'chart',   desc: '8 weken historische data — toont seizoenspatronen en langetermijn­bewegingen.' },
  { k: 'keywords',      label: 'Keyword Onderzoek', c: C.amber,  kind: 'keyword', desc: 'Typ een keyword en zie volume, difficulty en CPC, gekruist met je eigen GSC-posities.' },
  { k: 'clusters',      label: 'Clusterprestaties', c: C.emerald,kind: 'clusters',desc: 'Leadattributie per contentcluster: welke content genereert daadwerkelijk leads?' },
  { k: 'analyse',       label: 'Analyse',           c: C.cyan,   kind: 'chart',   desc: 'Positie-historiek en GSC-vs-GA4 vergelijking per pagina; seizoenspatronen per keyword.' },
  { k: 'clarity',       label: 'Clarity',           c: C.pink,   kind: 'clarity', desc: 'UX-gedrag: rage clicks, dead clicks, scroll depth en quick-back per pagina.' },
  { k: 'concurrenten',  label: 'Concurrenten',      c: C.amber,  kind: 'threat',  desc: 'Dreigingsmatrix: welke keywords pakken homedeal, mijn-dakdekker en kosten-dakdekker af?' },
];
const STEP = 4.6;

function SceneModules() {
  const lt = useSprite().localTime;
  const intro = 1.4;
  const idx = clamp(Math.floor((lt - intro) / STEP), 0, MODULES.length - 1);
  const m = MODULES[idx];
  const localInStep = (lt - intro) - idx * STEP;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={8} style={{ position: 'absolute', top: 60, left: 64 }}>
        <Eyebrow dot={false} color={C.green}>03 · Rondleiding</Eyebrow>
        <div style={{ fontSize: 34, fontWeight: 800, color: C.text, marginTop: 8, letterSpacing: '-0.8px' }}>De modules — wat je ermee kan</div>
      </Reveal>

      {/* dashboard frame */}
      <Reveal at={0.5} dur={0.7} y={26} scaleFrom={0.96} style={{ position: 'absolute', left: 64, top: 150 }}>
        <DashboardMock active={m.k} title={m.label} width={760} height={470}>
          <MiniContent kind={m.kind} color={m.c} k={localInStep} idx={idx} />
        </DashboardMock>
      </Reveal>

      {/* description panel (updates per module) */}
      <div style={{ position: 'absolute', left: 870, top: 196, width: 346 }}>
        <Reveal at={0.7} dur={0.6} x={20}>
          <Card style={{ padding: '24px 24px' }} accent={m.c} glow>
            <div key={idx} style={{ animation: 'fadein .4s ease' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 16 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: m.c, boxShadow: `0 0 10px ${m.c}88` }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: m.c, letterSpacing: '0.5px', textTransform: 'uppercase' }}>Module {idx + 1} / 9</span>
              </div>
              <div style={{ fontSize: 30, fontWeight: 800, color: C.text, marginBottom: 14, letterSpacing: '-0.5px' }}>{m.label}</div>
              <div style={{ fontSize: 17, color: C.dim, lineHeight: 1.6 }}>{m.desc}</div>
            </div>
          </Card>
        </Reveal>

        {/* progress dots */}
        <Reveal at={1.0} dur={0.5} style={{ marginTop: 22, display: 'flex', gap: 7, flexWrap: 'wrap' }}>
          {MODULES.map((mm, i) => (
            <span key={i} style={{
              width: i === idx ? 26 : 9, height: 9, borderRadius: 6,
              background: i === idx ? mm.c : (i < idx ? C.faint : C.faint2),
              transition: 'all .3s',
            }} />
          ))}
        </Reveal>
      </div>
    </SceneBG>
  );
}

// Mini content sketches per module
function MiniContent({ kind, color, k, idx }) {
  const rev = (d) => clamp((k - d) / 0.4, 0, 1);
  const row = (label, val, w, i) => (
    <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '9px 0', borderBottom: `1px solid ${C.borderSoft}`, opacity: rev(0.15 + i * 0.08), transform: `translateX(${(1 - rev(0.15 + i * 0.08)) * -10}px)` }}>
      <span style={{ fontSize: 12.5, color: C.dim }}>{label}</span>
      <span style={{ fontSize: 12.5, color: color, fontWeight: 600, fontFamily: MONO }}>{val}</span>
    </div>
  );

  if (kind === 'kpi') {
    const kpis = [['Clicks', '1.284', '+12%'], ['Sessies', '3.901', '+8%'], ['Leads', '47', '+19%'], ['Conv.', '1,2%', '+0,3']];
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {kpis.map((kp, i) => (
          <div key={i} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: '16px 18px', opacity: rev(i * 0.12), transform: `translateY(${(1 - rev(i * 0.12)) * 14}px)` }}>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>{kp[0]}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: C.text }}>{kp[1]}</div>
            <div style={{ fontSize: 12, color: C.green, marginTop: 4 }}>▲ {kp[2]}</div>
          </div>
        ))}
      </div>
    );
  }
  if (kind === 'table') {
    const rows = [['daklekkage repareren', '#3 · 6,2%'], ['dakpannen vervangen', '#5 · 4,1%'], ['kosten plat dak', '#8 · 2,9%'], ['dakreparatie prijs', '#4 · 5,0%'], ['groendak aanleggen', '#11 · 1,8%']];
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: C.muted, textTransform: 'uppercase', letterSpacing: '0.6px', paddingBottom: 8, borderBottom: `1px solid ${C.border}` }}>
          <span>Keyword</span><span>Positie · CTR</span>
        </div>
        {rows.map((r, i) => row(r[0], r[1], 0, i))}
      </div>
    );
  }
  if (kind === 'channels') {
    const ch = [['Organic Search', 78, C.green], ['Direct', 14, C.blue], ['Referral', 6, C.purple], ['Paid', 2, C.amber]];
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {ch.map((c, i) => (
          <div key={i} style={{ opacity: rev(i * 0.12) }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: C.dim, marginBottom: 6 }}><span>{c[0]}</span><span style={{ fontFamily: MONO }}>{c[1]}%</span></div>
            <div style={{ height: 8, background: C.card, borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${c[1] * rev(i * 0.12)}%`, height: '100%', background: c[2], borderRadius: 4 }} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (kind === 'chart') {
    const bars = [40, 52, 48, 63, 58, 72, 80, 76];
    return (
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 240, padding: '20px 6px 0' }}>
        {bars.map((b, i) => (
          <div key={i} style={{ flex: 1, height: `${b * rev(i * 0.07)}%`, background: `linear-gradient(180deg, ${color}, ${color}44)`, borderRadius: '5px 5px 0 0' }} />
        ))}
      </div>
    );
  }
  if (kind === 'keyword') {
    return (
      <div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 18, opacity: rev(0) }}>
          <div style={{ flex: 1, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, padding: '11px 14px', fontSize: 13, color: C.dim, fontFamily: MONO }}>dakkapel plaatsen<span style={{ color: color }}>|</span></div>
          <div style={{ background: color, color: '#001b10', borderRadius: 10, padding: '11px 18px', fontSize: 13, fontWeight: 700 }}>Zoek</div>
        </div>
        {[['Volume', '2.400/mnd'], ['Difficulty', '34 / 100'], ['CPC', '€ 3,80'], ['Jouw positie', '# 7']].map((r, i) => row(r[0], r[1], 0, i))}
      </div>
    );
  }
  if (kind === 'clusters') {
    const cl = [['/daklekkage/', 19, 78], ['/dakreparatie/', 13, 60], ['/keuzehulp/', 9, 42], ['/dakpannen/', 6, 30]];
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {cl.map((c, i) => (
          <div key={i} style={{ opacity: rev(i * 0.12) }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 6 }}><span style={{ color: C.dim, fontFamily: MONO }}>{c[0]}</span><span style={{ color: color, fontWeight: 700 }}>{c[1]} leads</span></div>
            <div style={{ height: 9, background: C.card, borderRadius: 5, overflow: 'hidden' }}>
              <div style={{ width: `${c[2] * rev(i * 0.12)}%`, height: '100%', background: color, borderRadius: 5 }} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (kind === 'clarity') {
    const tiles = [['Rage clicks', '2,1%', C.red], ['Dead clicks', '4,8%', C.amber], ['Scroll depth', '61%', C.green], ['Quick-back', '7,2%', C.cyan]];
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {tiles.map((t, i) => (
          <div key={i} style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: '16px 18px', opacity: rev(i * 0.1), transform: `scale(${0.94 + 0.06 * rev(i * 0.1)})` }}>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>{t[0]}</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: t[2] }}>{t[1]}</div>
          </div>
        ))}
      </div>
    );
  }
  if (kind === 'threat') {
    const th = [['dakdekker amsterdam', 'homedeal', 92], ['plat dak kosten', 'kosten-dakdekker', 78], ['dakpannen prijs', 'mijn-dakdekker', 64], ['dakgoot vervangen', 'homedeal', 51]];
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: C.muted, textTransform: 'uppercase', letterSpacing: '0.6px', paddingBottom: 8, borderBottom: `1px solid ${C.border}` }}>
          <span>Keyword · concurrent</span><span>Dreiging</span>
        </div>
        {th.map((r, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${C.borderSoft}`, opacity: rev(i * 0.1) }}>
            <div><div style={{ fontSize: 12.5, color: C.dim }}>{r[0]}</div><div style={{ fontSize: 11, color: C.faint, fontFamily: MONO }}>{r[1]}</div></div>
            <span style={{ fontSize: 12, fontWeight: 700, color: r[2] > 80 ? C.red : C.amber, fontFamily: MONO }}>{r[2]}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

// ════════════════════════════════════════════════════════════════════════════
// SCENE 4 — AI AGENTS + MAILS
// ════════════════════════════════════════════════════════════════════════════
const AGENTS = [
  { n: 'SEO Agent', t: 'Rankings & keywords', c: C.blue },
  { n: 'Conversie Agent', t: 'Traffic → leads', c: C.emerald },
  { n: 'Content Gap', t: 'Nieuwe kansen', c: C.amber },
  { n: 'Anomalie Detective', t: 'Pieken & dalingen', c: C.red },
  { n: 'Rapportage Agent', t: 'Rapporten & exports', c: C.purple },
  { n: 'Concurrentie Agent', t: 'SERP-analyse', c: C.orange },
  { n: 'Plannings Agent', t: 'Seizoen & timing', c: C.cyan },
  { n: 'Kansen Scout', t: 'Grootste groeikans', c: C.green },
  { n: 'Briefing Agent', t: 'Content-opdrachten', c: C.pink },
];
function SceneAgents() {
  const lt = useSprite().localTime;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={8} style={{ position: 'absolute', top: 62, left: 64 }}>
        <Eyebrow dot={false} color={C.green}>04 · Het Kantoor</Eyebrow>
        <div style={{ fontSize: 34, fontWeight: 800, color: C.text, marginTop: 8, letterSpacing: '-0.8px' }}>9 AI-agenten met live data-toegang</div>
      </Reveal>

      {/* agent grid */}
      <div style={{ position: 'absolute', left: 64, top: 168, width: 720, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 13 }}>
        {AGENTS.map((a, i) => (
          <Reveal key={i} at={0.5 + i * 0.13} dur={0.5} y={18} scaleFrom={0.9}>
            <Card accent={a.c} style={{ padding: '16px 16px', height: 92 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
                <span style={{ width: 9, height: 9, borderRadius: '50%', background: a.c, boxShadow: `0 0 9px ${a.c}88` }} />
                <span style={{ fontSize: 14.5, fontWeight: 700, color: C.text }}>{a.n}</span>
              </div>
              <div style={{ fontSize: 12.5, color: C.muted }}>{a.t}</div>
            </Card>
          </Reveal>
        ))}
      </div>

      {/* right rail: how + mails */}
      <div style={{ position: 'absolute', left: 820, top: 168, width: 396 }}>
        <Reveal at={1.6} dur={0.6} x={18}>
          <Card style={{ padding: '20px 22px', marginBottom: 16 }} accent={C.green}>
            <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 9 }}>💬 Chat in de rechterbalk</div>
            <div style={{ fontSize: 14.5, color: C.dim, lineHeight: 1.6 }}>Elke agent ziet álle live dashboard-data. Stel een vraag en krijg concrete actiepunten terug — geen losse cijfers.</div>
          </Card>
        </Reveal>
        <Reveal at={2.2} dur={0.6} x={18}>
          <Card style={{ padding: '20px 22px' }} accent={C.amber}>
            <div style={{ fontSize: 12, fontWeight: 700, color: C.amber, letterSpacing: '0.8px', textTransform: 'uppercase', marginBottom: 12 }}>Automatisch · elke dag 07:00</div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
              <div style={{ flex: 1, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: C.text }}>📋 Takenmail</div>
                <div style={{ fontSize: 11.5, color: C.muted, marginTop: 5, lineHeight: 1.5 }}>3 actiepunten per medewerker</div>
              </div>
              <div style={{ flex: 1, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: C.text }}>⚠️ Signalering</div>
                <div style={{ fontSize: 11.5, color: C.muted, marginTop: 5, lineHeight: 1.5 }}>alleen bij detecties</div>
              </div>
            </div>
          </Card>
        </Reveal>
      </div>
    </SceneBG>
  );
}

Object.assign(window, { SceneIntro, ScenePipeline, SceneSources, SceneModules, SceneAgents });
