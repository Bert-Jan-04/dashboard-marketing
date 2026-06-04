// scenes-2.jsx — Chapter 5 (add a new website) sub-scenes + checklist + outro.

/* global React, useSprite, Easing, clamp,
   C, FONT, MONO, Reveal, useReveal, SceneBG, Eyebrow, Chip, Card, CodeWindow */

// ── small note card used on the right rail ──────────────────────────────────
function Note({ at, n, title, body, color = C.green }) {
  return (
    <Reveal at={at} dur={0.55} x={20} style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', gap: 13, alignItems: 'flex-start' }}>
        <div style={{ width: 30, height: 30, borderRadius: 8, background: `${color}1f`, border: `1px solid ${color}66`, color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, flexShrink: 0, fontFamily: MONO }}>{n}</div>
        <div>
          <div style={{ fontSize: 16.5, fontWeight: 700, color: C.text, marginBottom: 3 }}>{title}</div>
          <div style={{ fontSize: 14, color: C.muted, lineHeight: 1.55 }}>{body}</div>
        </div>
      </div>
    </Reveal>
  );
}

function SceneHead({ n, title }) {
  return (
    <Reveal at={0.1} dur={0.5} y={8} style={{ position: 'absolute', top: 60, left: 64 }}>
      <Eyebrow dot={false} color={C.amber}>05 · Nieuwe website toevoegen</Eyebrow>
      <div style={{ fontSize: 32, fontWeight: 800, color: C.text, marginTop: 8, letterSpacing: '-0.7px' }}>{title}</div>
    </Reveal>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5a — OVERVIEW: 3 layers
// ════════════════════════════════════════════════════════════════════════════
const LAYERS = [
  { n: '1', icon: '⌨️', t: 'Code aanpassen', d: 'Domein + property-ID’s in rules.py en de fetchers.', c: C.green },
  { n: '2', icon: '🔑', t: 'Sleutels (.env)', d: 'API-keys en credentials voor de nieuwe accounts.', c: C.amber },
  { n: '3', icon: '🔗', t: 'Externe toegang', d: 'Google, Clarity & lead-events koppelen aan de site.', c: C.blue },
];
function SceneNewIntro() {
  const cardW = 320, gap = 34, startX = (1280 - (cardW * 3 + gap * 2)) / 2;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={10} style={{ position: 'absolute', top: 110, left: 0, right: 0, textAlign: 'center' }}>
        <Eyebrow dot={false} color={C.amber}>05 · Nieuwe website toevoegen</Eyebrow>
        <div style={{ fontSize: 46, fontWeight: 800, color: C.text, marginTop: 12, letterSpacing: '-1px' }}>Eén dashboard, elke website</div>
        <div style={{ fontSize: 21, color: C.muted, marginTop: 14 }}>Het werkt in <span style={{ color: C.amber, fontWeight: 700 }}>3 lagen</span> — sla er geen over.</div>
      </Reveal>
      {LAYERS.map((l, i) => (
        <Reveal key={i} at={0.7 + i * 0.45} dur={0.6} y={26} scaleFrom={0.9}
          style={{ position: 'absolute', left: startX + (cardW + gap) * i, top: 332, width: cardW }}>
          <Card glow accent={l.c} style={{ padding: '28px 26px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
              <div style={{ fontSize: 34 }}>{l.icon}</div>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: `${l.c}22`, border: `1px solid ${l.c}66`, color: l.c, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 20, fontFamily: MONO }}>{l.n}</div>
            </div>
            <div style={{ fontSize: 23, fontWeight: 800, color: C.text, marginBottom: 10 }}>{l.t}</div>
            <div style={{ fontSize: 16, color: C.muted, lineHeight: 1.6 }}>{l.d}</div>
          </Card>
        </Reveal>
      ))}
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5b — rules.py (central config)
// ════════════════════════════════════════════════════════════════════════════
function SceneRules() {
  const lines = [
    { t: '# rules.py — de centrale configuratie', k: 'comment' },
    { t: '' },
    { t: 'PROPERTY_ID      = "355158317"', k: 'del' },
    { t: 'PROPERTY_ID      = "<nieuw GA4 property-ID>"', k: 'add' },
    { t: '' },
    { t: 'SITE_URL         = "https://dakdekkersgids.nl/"', k: 'del' },
    { t: 'SITE_URL         = "https://nieuwesite.nl/"', k: 'add' },
    { t: '' },
    { t: 'SITE_URL_ENCODED = "sc-domain:dakdekkersgids.nl"', k: 'del' },
    { t: 'SITE_URL_ENCODED = "sc-domain:nieuwesite.nl"', k: 'add' },
    { t: '' },
    { t: 'CLUSTERS  = ["/daklekkage/", "/dakreparatie/", …]', k: 'del' },
    { t: 'CLUSTERS  = ["/jouw-cluster/", "/cluster-2/", …]', k: 'add' },
    { t: '' },
    { t: 'LEAD_EVENT       = "dakdekker_lead"', k: 'del' },
    { t: 'LEAD_EVENT       = "<jouw GA4 lead-event>"', k: 'add' },
  ];
  return (
    <SceneBG>
      <SceneHead title="Stap 1 — rules.py: de centrale config" />
      <CodeWindow file="rules.py" lines={lines} x={64} y={150} width={736} at={0.6} perLine={0.13} fontSize={15} />
      <div style={{ position: 'absolute', left: 838, top: 196, width: 378 }}>
        <Note at={0.8} n="A" color={C.green} title="PROPERTY_ID" body="Het GA4 property-ID van de nieuwe site (Beheer → Property-instellingen)." />
        <Note at={1.3} n="B" color={C.green} title="SITE_URL + _ENCODED" body="Het domein in Search Console — meestal de sc-domain: variant." />
        <Note at={1.9} n="C" color={C.green} title="CLUSTERS" body="De content-clusters waarop je leads wilt toeschrijven." />
        <Note at={2.5} n="D" color={C.green} title="LEAD_EVENT" body="De naam van het conversie-event dat in GA4 is ingesteld." />
      </div>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5c — Duplicates + find & replace
// ════════════════════════════════════════════════════════════════════════════
const DUP_FILES = [
  { f: 'fetchers/trends.py', d: 'SITE_URL + PROPERTY_ID — staan hier nóg een keer hardcoded' },
  { f: 'fetchers/gsc.py', d: 'SITE_URL + .replace("https://dakdekkersgids.nl", …)' },
  { f: 'fetchers/clarity.py', d: '.replace("https://dakdekkersgids.nl", …)' },
  { f: 'fetchers/sitemap.py', d: 'SITEMAP_INDEX-URL + .replace(…) + content-prefixen' },
  { f: 'server.py', d: 'AI-prompts noemen de site + .replace(…) op meerdere plekken' },
];
function SceneDuplicates() {
  const lt = useSprite().localTime;
  return (
    <SceneBG>
      <SceneHead title="Stap 2 — let op de duplicaten" />
      <Reveal at={0.4} dur={0.5} x={16} style={{ position: 'absolute', left: 64, top: 158, width: 700 }}>
        <div style={{ fontSize: 16.5, color: C.dim, lineHeight: 1.6, marginBottom: 18 }}>
          Het domein staat niet alleen in <span style={{ fontFamily: MONO, color: C.amber }}>rules.py</span>. Dezelfde waarden zijn op een paar plekken herhaald:
        </div>
      </Reveal>
      <div style={{ position: 'absolute', left: 64, top: 224, width: 700 }}>
        {DUP_FILES.map((d, i) => (
          <Reveal key={i} at={0.7 + i * 0.3} dur={0.5} x={16} style={{ marginBottom: 11 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, background: C.card, border: `1px solid ${C.border}`, borderRadius: 11, padding: '13px 16px' }}>
              <span style={{ fontFamily: MONO, fontSize: 14.5, fontWeight: 700, color: C.amber, minWidth: 168 }}>{d.f}</span>
              <span style={{ fontSize: 13.5, color: C.muted, lineHeight: 1.45 }}>{d.d}</span>
            </div>
          </Reveal>
        ))}
      </div>
      <Reveal at={2.5} dur={0.6} x={20} style={{ position: 'absolute', left: 800, top: 224, width: 416 }}>
        <Card glow accent={C.green} style={{ padding: '24px 24px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.green, letterSpacing: '0.8px', textTransform: 'uppercase', marginBottom: 14 }}>De snelste route</div>
          <div style={{ fontSize: 18, color: C.text, fontWeight: 700, marginBottom: 10 }}>Zoek &amp; vervang in het hele project:</div>
          <div style={{ background: C.deep, border: `1px solid ${C.border}`, borderRadius: 9, padding: '14px 16px', fontFamily: MONO, fontSize: 14.5 }}>
            <div style={{ color: C.red }}>– dakdekkersgids.nl</div>
            <div style={{ color: C.green }}>+ nieuwesite.nl</div>
          </div>
          <div style={{ fontSize: 14, color: C.muted, lineHeight: 1.55, marginTop: 14 }}>
            Loop daarna rules.py en de fetchers na voor property-ID, clusters en event-namen die niet het domein bevatten.
          </div>
        </Card>
      </Reveal>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5d — competitors.py
// ════════════════════════════════════════════════════════════════════════════
function SceneCompetitors() {
  const lines = [
    { t: '# fetchers/competitors.py', k: 'comment' },
    { t: '' },
    { t: 'CONCURRENTEN = [', k: 'del' },
    { t: '  {"naam": "HomeDeal", "domein": "homedeal.nl", …},', k: 'del' },
    { t: '  {"naam": "Mijn Dakdekker", "domein": "mijn-…"},', k: 'del' },
    { t: ']', k: 'del' },
    { t: 'CONCURRENTEN = [', k: 'add' },
    { t: '  {"naam": "Concurrent A", "domein": "site-a.nl",', k: 'add' },
    { t: '   "basis": "https://www.site-a.nl",', k: 'add' },
    { t: '   "start": "https://www.site-a.nl/"},', k: 'add' },
    { t: ']', k: 'add' },
    { t: '' },
    { t: 'DAK_WOORDEN = ["dak", "plat", "pannen", "goot", …]', k: 'del' },
    { t: 'DAK_WOORDEN = ["<kernwoorden van jouw sector>"]', k: 'add' },
  ];
  return (
    <SceneBG>
      <SceneHead title="Stap 3 — concurrenten & sectorwoorden" />
      <CodeWindow file="fetchers/competitors.py" lines={lines} x={64} y={150} width={736} at={0.6} perLine={0.12} fontSize={14.5} />
      <div style={{ position: 'absolute', left: 838, top: 200, width: 378 }}>
        <Note at={0.9} n="①" color={C.amber} title="CONCURRENTEN" body="De directe concurrenten van de nieuwe site — hun sitemaps worden geanalyseerd." />
        <Note at={1.6} n="②" color={C.amber} title="DAK_WOORDEN" body="De woorden waarmee relevante pagina’s worden herkend. Pas aan naar de nieuwe sector." />
        <Reveal at={2.3} dur={0.6} x={18} style={{ marginTop: 6 }}>
          <div style={{ background: C.greenDim, border: `1px solid ${C.greenBd}`, borderRadius: 11, padding: '15px 17px', fontSize: 14.5, color: C.dim, lineHeight: 1.6 }}>
            Tip: ook de content-prefixen in <span style={{ fontFamily: MONO, color: C.green }}>rules.py</span> en <span style={{ fontFamily: MONO, color: C.green }}>sitemap.py</span> bepalen welke pagina’s als “content” tellen.
          </div>
        </Reveal>
      </div>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5e — .env secrets
// ════════════════════════════════════════════════════════════════════════════
const ENVS = [
  { k: 'GOOGLE_CREDENTIALS_JSON', v: '{ service-account … }', d: 'Google service-account → GA4 + GSC', c: C.green },
  { k: 'OPENAI_API_KEY', v: 'sk-proj-••••••••', d: 'AI-agenten & dagmails', c: C.purple },
  { k: 'MANGOOLS_API_KEY', v: '••••••••', d: 'Keyword-volume / difficulty', c: C.amber },
  { k: 'CLARITY_API_TOKEN', v: 'eyJ••••••••', d: 'Microsoft Clarity UX-data', c: C.cyan },
  { k: 'CLARITY_PROJECT_ID', v: '••••••', d: 'Clarity project', c: C.cyan },
  { k: 'GMAIL_ADDRESS / _APP_PASSWORD', v: '••••••', d: 'Afzender van de dagmails', c: C.blue },
  { k: 'MAIL_ONTVANGERS', v: 'a@x.nl, b@x.nl', d: 'Wie de mails ontvangt', c: C.blue },
  { k: 'MEDEWERKERS', v: 'Naam=email, …', d: 'Team in het Kantoor-tabblad', c: C.emerald },
];
function SceneEnv() {
  return (
    <SceneBG>
      <SceneHead title="De sleutels — .env (nooit in git!)" />
      <div style={{ position: 'absolute', left: 64, top: 152, width: 1152 }}>
        <Reveal at={0.3} dur={0.5} x={14} style={{ fontSize: 16, color: C.dim, marginBottom: 16, lineHeight: 1.55 }}>
          Elke databron heeft een eigen sleutel. Vul ze voor de nieuwe accounts in — lokaal in <span style={{ fontFamily: MONO, color: C.green }}>.env</span>, op Railway als environment-variabelen.
        </Reveal>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {ENVS.map((e, i) => (
            <Reveal key={i} at={0.6 + i * 0.14} dur={0.45} y={14}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, background: C.card, border: `1px solid ${C.border}`, borderRadius: 11, padding: '13px 16px' }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: e.c, flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontFamily: MONO, fontSize: 13.5, color: C.text, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.k}</div>
                  <div style={{ fontSize: 12.5, color: C.muted, marginTop: 3 }}>{e.d}</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 12.5, color: e.c, opacity: 0.85, whiteSpace: 'nowrap' }}>{e.v}</span>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5f — External access (no code)
// ════════════════════════════════════════════════════════════════════════════
const EXT = [
  { n: '1', t: 'Service-account toegang geven', d: 'Voeg het service-account-e-mailadres toe als gebruiker in de nieuwe GA4-property én in Search Console.', c: C.green },
  { n: '2', t: 'Lead-event instellen in GA4', d: 'Maak (of kies) het conversie-event en zet diezelfde naam bij LEAD_EVENT in rules.py.', c: C.amber },
  { n: '3', t: 'Microsoft Clarity koppelen', d: 'Start een Clarity-project voor de site en zet token + project-ID in .env.', c: C.cyan },
  { n: '4', t: 'Data verversen', d: 'Draai de fetchers één keer (of wacht op de wekelijkse run) zodat /data gevuld wordt.', c: C.blue },
];
function SceneExternal() {
  return (
    <SceneBG>
      <SceneHead title="Buiten de code — toegang & koppelingen" />
      <div style={{ position: 'absolute', left: 64, top: 168, right: 64 }}>
        {EXT.map((e, i) => (
          <Reveal key={i} at={0.5 + i * 0.4} dur={0.55} x={20} style={{ marginBottom: 16 }}>
            <Card accent={e.c} style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 22 }}>
              <div style={{ width: 48, height: 48, borderRadius: 12, background: `${e.c}1f`, border: `1px solid ${e.c}66`, color: e.c, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 22, flexShrink: 0, fontFamily: MONO }}>{e.n}</div>
              <div>
                <div style={{ fontSize: 21, fontWeight: 700, color: C.text, marginBottom: 5 }}>{e.t}</div>
                <div style={{ fontSize: 16, color: C.muted, lineHeight: 1.55 }}>{e.d}</div>
              </div>
            </Card>
          </Reveal>
        ))}
      </div>
    </SceneBG>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 6 — CHECKLIST + OUTRO
// ════════════════════════════════════════════════════════════════════════════
const CHECK = [
  'rules.py — PROPERTY_ID, SITE_URL, _ENCODED, CLUSTERS, LEAD_EVENT',
  'fetchers/trends.py & gsc.py — dezelfde SITE_URL + PROPERTY_ID',
  'Zoek & vervang "dakdekkersgids.nl" in het hele project',
  'competitors.py — CONCURRENTEN + sectorwoorden',
  '.env — Google, OpenAI, Mangools, Clarity, Gmail, team',
  'Service-account toegang tot GA4 + Search Console',
  'Lead-event in GA4 + Clarity-project koppelen',
  'Fetchers draaien → /data vullen',
];
function SceneChecklist() {
  const lt = useSprite().localTime;
  return (
    <SceneBG>
      <Reveal at={0.1} dur={0.5} y={8} style={{ position: 'absolute', top: 64, left: 64 }}>
        <Eyebrow dot={false} color={C.green}>06 · Overdracht</Eyebrow>
        <div style={{ fontSize: 34, fontWeight: 800, color: C.text, marginTop: 8, letterSpacing: '-0.8px' }}>Checklist nieuwe website</div>
      </Reveal>
      <div style={{ position: 'absolute', left: 64, top: 168, width: 1152, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '13px 28px' }}>
        {CHECK.map((c, i) => {
          const a = 0.5 + i * 0.28;
          const checked = lt > a + 0.45;
          return (
            <Reveal key={i} at={a} dur={0.45} x={16}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, background: C.card, border: `1px solid ${checked ? C.greenBd : C.border}`, borderRadius: 11, padding: '15px 18px', transition: 'border-color .3s' }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, flexShrink: 0, background: checked ? C.green : 'transparent', border: `1.5px solid ${checked ? C.green : C.faint}`, color: '#001b10', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 15, transition: 'all .3s' }}>{checked ? '✓' : ''}</span>
                <span style={{ fontSize: 14.5, color: C.dim, lineHeight: 1.4 }}>{c}</span>
              </div>
            </Reveal>
          );
        })}
      </div>
    </SceneBG>
  );
}

function SceneOutro() {
  return (
    <SceneBG>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
        <Reveal at={0.2} dur={0.7} y={18} scaleFrom={0.94}>
          <div style={{ fontSize: 52, fontWeight: 800, color: C.text, letterSpacing: '-1px' }}>Klaar voor overdracht.</div>
        </Reveal>
        <Reveal at={0.7} dur={0.6} y={12}>
          <div style={{ fontSize: 22, color: C.muted, marginTop: 20, maxWidth: 720, lineHeight: 1.55 }}>
            Alle technische details staan ook in <span style={{ fontFamily: MONO, color: C.green }}>CLAUDE.md</span> in de projectmap. Begin daar bij vragen.
          </div>
        </Reveal>
        <Reveal at={1.2} dur={0.6} y={10}>
          <div style={{ display: 'flex', gap: 10, marginTop: 32, justifyContent: 'center' }}>
            <Chip color={C.green} solid>Marketing Intelligence</Chip>
            <Chip color={C.muted}>dakdekkersgids.nl</Chip>
          </div>
        </Reveal>
      </div>
    </SceneBG>
  );
}

Object.assign(window, {
  SceneNewIntro, SceneRules, SceneDuplicates, SceneCompetitors, SceneEnv, SceneExternal,
  SceneChecklist, SceneOutro,
});
