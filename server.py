import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


def _gmail_stuur(aan, onderwerp, html):
    """Stuur een mail via de Gmail API (werkt op Railway, geen SMTP nodig)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    # Token laden: eerst env var (Railway), dan lokaal bestand
    token_json = os.getenv("GMAIL_TOKEN_JSON", "").strip()
    if token_json:
        token_data = json.loads(token_json)
    else:
        token_path = os.path.join(BASE_DIR, "gmail_token.json")
        if not os.path.exists(token_path):
            raise FileNotFoundError(
                "Gmail niet geconfigureerd: stel GMAIL_TOKEN_JSON in als Railway env var "
                "of voer setup_gmail_token.py uit om gmail_token.json aan te maken."
            )
        with open(token_path, encoding="utf-8") as f:
            token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.send"]),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    afzender = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")
    ontvangers = [a.strip() for a in aan] if isinstance(aan, list) else [aan]

    service = build("gmail", "v1", credentials=creds)
    for ontvanger in ontvangers:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = onderwerp
        msg["From"]    = afzender
        msg["To"]      = ontvanger
        msg.attach(MIMEText(html, "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Zorg dat data-map altijd bestaat (Railway heeft geen persistent FS)
os.makedirs(DATA_DIR, exist_ok=True)

# Schrijf Google credentials vanuit env var als het bestand er niet is (Railway)
_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if _creds_json:
    _creds_dir  = os.path.join(BASE_DIR, "credentials")
    _creds_path = os.path.join(_creds_dir, "credentials.json")
    os.makedirs(_creds_dir, exist_ok=True)
    if not os.path.exists(_creds_path):
        with open(_creds_path, "w", encoding="utf-8") as _f:
            _f.write(_creds_json)


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Serveer het dashboard
@app.route("/")
def dashboard():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "dashboard.html")


# Alle GSC data
@app.route("/api/gsc")
def gsc():
    return jsonify(load_json("gsc_data.json"))


# Alle GA4 data
@app.route("/api/ga4")
def ga4():
    return jsonify(load_json("ga4_data.json"))


# Gecombineerde data voor één pagina
@app.route("/api/pagina")
def pagina():
    path = request.args.get("path", "").strip("/")
    if not path:
        return jsonify({"error": "Geen pagina opgegeven"}), 400

    gsc_data = load_json("gsc_data.json")
    ga4_data = load_json("ga4_data.json")

    # GSC: zoek pagina in top_pages
    gsc_pagina = next(
        (p for p in gsc_data.get("top_pages", [])
         if path in p.get("page", "")),
        None
    )

    # GSC: zoek keywords voor deze pagina
    gsc_keywords = [
        k for k in gsc_data.get("top_keywords", [])
        if path in k.get("query", "")
    ]

    # GA4: zoek pagina in top_pages
    ga4_pagina = next(
        (p for p in ga4_data.get("top_pages", [])
         if path in p.get("pagePath", "")),
        None
    )

    # GA4: offerteaanvragen voor deze pagina
    aanvragen = next(
        (a for a in ga4_data.get("offerteaanvragen", {}).get("deze_week", [])
         if path in a.get("landing_page", "")),
        None
    )

    return jsonify({
        "pagina": f"/{path}/",
        "gsc": gsc_pagina,
        "ga4": ga4_pagina,
        "keywords": gsc_keywords,
        "offerteaanvragen": aanvragen.get("aanvragen", 0) if aanvragen else 0
    })


def _extract_file_text(file_storage):
    import io
    naam = file_storage.filename.lower()
    data = file_storage.read()
    if naam.endswith(".pdf"):
        import pdfplumber
        tekst = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    tekst.append(t)
        return "\n\n".join(tekst)
    elif naam.endswith(".docx"):
        import docx, io as _io
        doc = docx.Document(_io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:  # txt, csv, md etc.
        return data.decode("utf-8", errors="replace")


# Chat met AI
@app.route("/api/chat", methods=["POST"])
def chat():
    if request.content_type and "multipart" in request.content_type:
        import json as _json
        body = _json.loads(request.form.get("data", "{}"))
        bestand = request.files.get("file")
    else:
        body = request.json or {}
        bestand = None

    history = body.get("messages", [])
    tab = body.get("tab", "strategie")
    pagina = body.get("pagina", "")
    instructies = body.get("instructies", "").strip()

    if not history or history[-1].get("role") != "user":
        return jsonify({"error": "Geen vraag opgegeven"}), 400

    if bestand:
        try:
            bestand_tekst = _extract_file_text(bestand)[:12000]
            history[-1]["content"] = (
                f"Ik heb een bestand geüpload ({bestand.filename}):\n\n"
                f"---\n{bestand_tekst}\n---\n\n"
                f"{history[-1]['content']}"
            )
        except Exception as e:
            return jsonify({"error": f"Bestand kon niet worden gelezen: {e}"}), 400

    gsc = load_json("gsc_data.json")
    ga4 = load_json("ga4_data.json")
    leads = load_json("leads_week.json")
    competitors = load_json("competitor_data.json")
    clarity = load_json("clarity_data.json")
    trends = load_json("trends_data.json")

    pagina_context = f"\nDe gebruiker bekijkt op dit moment de '{pagina}'-sectie van het dashboard." if pagina else ""

    # ── GSC ──
    gsc_blok = f"""SEARCH CONSOLE ({gsc.get('period', {}).get('this_week', {}).get('start')} t/m {gsc.get('period', {}).get('this_week', {}).get('end')}):
- Clicks: {gsc.get('totals', {}).get('clicks')} ({gsc.get('totals', {}).get('clicks_growth')}% t.o.v. vorige week)
- Impressions: {gsc.get('totals', {}).get('impressions')} ({gsc.get('totals', {}).get('impressions_growth')}%)
- Gemiddelde positie: {gsc.get('totals', {}).get('position')}
- Top keywords (pos, clicks, impressies, CTR): {json.dumps(gsc.get('top_keywords', [])[:20], ensure_ascii=False)}
- Top pagina's (clicks, impressies, CTR, positie): {json.dumps(gsc.get('top_pages', [])[:20], ensure_ascii=False)}
- CTR-kansen (pos ≤10, CTR <3%, imp ≥30): {json.dumps([k for k in gsc.get('top_keywords', []) if k.get('position', 99) <= 10 and k.get('ctr', 99) < 3 and k.get('impressions', 0) >= 30][:10], ensure_ascii=False)}
- Positie-kansen (pos 4-15, imp ≥30): {json.dumps([k for k in gsc.get('top_keywords', []) if 4 <= k.get('position', 99) <= 15 and k.get('impressions', 0) >= 30][:10], ensure_ascii=False)}"""

    # ── GA4 ──
    ga4_blok = f"""GOOGLE ANALYTICS 4:
- Sessies: {ga4.get('totals', {}).get('sessions')} ({ga4.get('totals', {}).get('sessions_growth')}% t.o.v. vorige week)
- Actieve gebruikers: {ga4.get('totals', {}).get('active_users')}
- Bouncepercentage: {ga4.get('totals', {}).get('bounce_rate')}%
- Offerteaanvragen deze week: {ga4.get('offerteaanvragen', {}).get('totaal_deze_week')} ({ga4.get('offerteaanvragen', {}).get('groei')}% t.o.v. vorige week)
- Aanvragen per pagina: {json.dumps(ga4.get('offerteaanvragen', {}).get('deze_week', []), ensure_ascii=False)}
- Kanalen: {json.dumps(ga4.get('channels', []), ensure_ascii=False)}
- Top pagina's (GA4): {json.dumps(ga4.get('top_pages', [])[:15], ensure_ascii=False)}"""

    # ── LEADS ──
    cl = leads.get('cluster_attributie', {})
    leads_blok = f"""LEADS & CLUSTERS:
- Directe leads deze week: {leads.get('directe_leads', {}).get('totaal_deze_week')} (vorige week: {leads.get('directe_leads', {}).get('totaal_vorige_week')})
- Leads per kanaal: {json.dumps(leads.get('directe_leads', {}).get('per_kanaal', []), ensure_ascii=False)}
- Leads per pagina: {json.dumps(leads.get('directe_leads', {}).get('per_pagina', [])[:10], ensure_ascii=False)}
- Cluster attributie deze week: {json.dumps(cl.get('deze_week', {}), ensure_ascii=False)}
- Cluster attributie cumulatief: {json.dumps(cl.get('cumulatief', {}), ensure_ascii=False)}"""

    # ── CONCURRENTEN ──
    if competitors:
        sam = competitors.get("samenvatting", {})
        dreigingen_top = competitors.get("dreigingen", [])[:15]
        concurrent_overzicht = "\n".join(
            f"- {c['naam']} ({c['domein']}): {c['dak_paginas']} dak-pagina's, keywords: {', '.join(c['keywords'][:10])}"
            for c in competitors.get("concurrenten", [])
        )
        dreigingen_txt = "\n".join(
            f"- '{d['keyword']}': wij pos {d.get('onze_positie') or 'n/a'} | imp {d.get('onze_impressies',0)} | "
            f"volume {d.get('sv','?')} | diff {d.get('seo','?')} | concurrenten: {', '.join(d['concurrenten'])}"
            for d in dreigingen_top
        )
        competitor_blok = f"""CONCURRENTENANALYSE (gegenereerd: {competitors.get('gegenereerd','?')}):
Geanalyseerde concurrenten: homedeal.nl, mijn-dakdekker.nl, kosten-dakdekker.nl
Totaal concurrent-keywords: {sam.get('totaal_concurrent_keywords',0)} | Overlap met ons: {sam.get('overlap_met_ons',0)} | Op meerdere concurrenten: {sam.get('meerdere_concurrenten',0)}

Concurrentprofiel:
{concurrent_overzicht}

Top dreigingen (keyword → onze positie | impressies | Mangools volume | difficulty | wie heeft content):
{dreigingen_txt}"""
    else:
        competitor_blok = "CONCURRENTENANALYSE: Nog geen data beschikbaar. Voer eerst een scan uit via /api/fetch-competitors."

    # ── CLARITY ──
    if clarity and isinstance(clarity, dict) and clarity.get("metrics"):
        m = clarity["metrics"]
        pop_paginas = "\n".join(
            f"  - {p.get('url', p.get('pad','?'))}: {p.get('bezoeken','?')} bezoeken"
            for p in (m.get("populaire_paginas", []) if isinstance(m.get("populaire_paginas"), list) else [])[:10]
        )
        apparaten = "\n".join(
            f"  - {a.get('naam','?')}: {a.get('sessies','?')} sessies"
            for a in (m.get("apparaten", []) if isinstance(m.get("apparaten"), list) else [])
        )
        clarity_blok = f"""MICROSOFT CLARITY (gedragsdata, periode: {clarity.get('periode','?')}):
- Sessies: {m.get('sessies',0)} | Unieke gebruikers: {m.get('gebruikers',0)}
- Pagina's per sessie: {m.get('paginas_per_sessie',0)} | Actieve tijd: {round(m.get('actieve_tijd_sec',0)/60,1)} min | Totale tijd: {round(m.get('totale_tijd_sec',0)/60,1)} min
- Scroll diepte: {m.get('scroll_diepte',0)}%
- Dead clicks: {m.get('dead_click_pct',0)}% ({m.get('dead_click_paginas',0)} pagina's) | Rage clicks: {m.get('rage_click_pct',0)}% | Quick back: {m.get('quickback_pct',0)}% ({m.get('quickback_paginas',0)} pagina's) | Script errors: {m.get('script_error_pct',0)}%
- Apparaten:
{apparaten}
- Verwijzers: {json.dumps([v.get('url','?') for v in (m.get('verwijzers',[]) if isinstance(m.get('verwijzers'), list) else [])][:8], ensure_ascii=False)}
- Populaire pagina's:
{pop_paginas}"""
    else:
        clarity_blok = "MICROSOFT CLARITY: Nog geen data beschikbaar."

    # ── TRENDS (historisch, laatste 8 weken) ──
    if trends and isinstance(trends, list):
        trends_regels = "\n".join(
            f"- Week {t.get('week','?')} ({t.get('start','')}/{t.get('end','')}): "
            f"clicks {t.get('gsc',{}).get('clicks','?')} | imp {t.get('gsc',{}).get('impressions','?')} | "
            f"pos {t.get('gsc',{}).get('position','?')} | sessies {t.get('ga4',{}).get('sessions','?')}"
            for t in trends[-8:]
        )
        trends_blok = f"""HISTORISCHE TRENDS (laatste {len(trends[-8:])} weken):
{trends_regels}"""
    else:
        trends_blok = "HISTORISCHE TRENDS: Nog geen data beschikbaar."

    # ── GECOMBINEERDE DATABROK ──
    alle_data_blok = f"""{gsc_blok}

{ga4_blok}

{leads_blok}

{competitor_blok}

{clarity_blok}

{trends_blok}"""

    extra_instructies = f"\n\nEXTRA INSTRUCTIES VAN DE GEBRUIKER:\n{instructies}" if instructies else ""
    suggestie_instructie = "\n\nSluit je antwoord af met exact 3 korte vervolgvragen, in dit formaat op een nieuwe regel:\n[VRAGEN]\nvraag 1\nvraag 2\nvraag 3\n[/VRAGEN]"

    if tab == "seo":
        systeem = f"""# SEO Analysis Agent — Strategic Insight Engine

## Rol & Missie
Je bent een senior SEO-strateeg met 15+ jaar ervaring bij toonaangevende digitale marketingbureaus. Je taak is NIET het opsommen van observaties — je identificeert de 3–7 meest impactvolle kansen of problemen in de data en vertelt de marketeer exact wat hij moet doen.

Je denkt als een businessconsultant, niet als een checklist-tool.

## Sitedoel — dakdekkersgids.nl
Niche-website van LeadGen Group. Bezoekers die een dakdekker zoeken koppelen aan een erkend bedrijf via een leadformulier. Elke ingevulde aanvraag is directe businesswaarde. Een pagina met 100 bezoekers en 5 leads is altijd waardevoller dan 1.000 bezoekers en 0 leads.

Zoekwoordunivers:
- Commercieel (hoogste waarde): "dakdekker [stad]", "dakdekker nodig", "dakdekker offerte", "dak laten repareren"
- Informationeel (ondersteunend): "wat kost een nieuw dak", "dakbedekking soorten", "plat dak onderhoud"
- Seizoensgevoelig: storm- en vorstschade zoekwoorden pieken in najaar/winter

Geografische focus: heel Nederland, extra aandacht voor Amsterdam, Rotterdam, Den Haag, Utrecht, Eindhoven.

## Analysekader
Voordat je iets uitvoert, doorloop je intern deze vijf lenzen:

1. **Momentum shifts** — Wat beweegt snel (omhoog of omlaag) dat 30–90 dagen geleden nog niet speelde?
2. **Value gaps** — Waar zijn impressies hoog maar clicks laag? Waar is verkeer hoog maar conversie nul?
3. **Quick wins vs. strategische speelruimte** — Wat kost < 1 week, wat kost > 1 maand?
4. **Kannibalisme & verwarring** — Concurreren meerdere pagina's op dezelfde zoekintentie?
5. **Competitieve kwetsbaarheid** — Waar zijn we kwetsbaar, of waar bloeden concurrenten?

## Outputformaat

Elk actiepunt krijgt een prioriteitslabel:
- 🔴 Kritiek — Omzet/zichtbaarheid in gevaar, actie binnen 7 dagen
- 🟡 Hoge impact — Significante groeikans, actie binnen 30 dagen
- 🟢 Strategisch — Samengesteld rendement over 60–90 dagen

### Structuur per actiepunt (herhaal per bevinding):

**[NUMMER]. [Pakkende titel die de kern van de inzicht vangt]**

**Wat zie je in de data:**
[2–4 zinnen. Beschrijf het specifieke patroon, de anomalie of de trend. Noem exacte pagina's, zoekwoorden of metrics. Niet generaliseren — chirurgisch.]

**Waarom dit belangrijk is:**
[1–2 zinnen. Wat is de businessconsequentie als dit genegeerd wordt, of de upside als erop gehandeld wordt? Koppel aan verkeer, leads of omzet.]

**Wat de marketeer moet doen:**
Stap 1: [Concrete actie — wie doet wat, in welk tool]
Stap 2: [Volgende stap]
Stap 3: [Opvolging of meting]

**Verwacht resultaat:**
[Realistische schatting van impact, bijv. "+15–25% CTR op deze pagina's binnen 6 weken"]

**KPI om bij te houden:**
[De ene metric die bevestigt dat dit werkt]

## Regels die je altijd volgt

- **Geen wollige taal.** Nooit "het kan interessant zijn om te kijken naar". Wees direct.
- **Geen micro-issues.** Als een fix 10 minuten kost en < 1% verschil maakt, sla het over.
- **Geen generiek advies.** Elk actiepunt moet herleidbaar zijn naar specifieke data uit het dashboard.
- **Prioriteer op impact, niet op gemak.** Het moeilijkste te fixen probleem is vaak het belangrijkste.
- **Maximaal 7 actiepunten.** Combineer of schrap de zwakste als je er meer ziet.
- **Één duidelijke eigenaar per actie.** Specificeer: SEO-specialist / copywriter / developer / marketeer.
- **Sluit altijd af met een "Grote Vraag"** — één strategische vraag die de data opwerpt en die de marketeer met zijn team moet bespreken.

## Toon
Schrijf in het Nederlands. Direct, zelfverzekerd en commercieel. Schrijf voor een marketeer die slim is maar weinig tijd heeft. Geen academisch taalgebruik. Geen lijdende vorm. Praat als een strateeg in een boardroom, niet als een rapportgenerator.{pagina_context}{extra_instructies}

## Dashboarddata

{alle_data_blok}{suggestie_instructie}

## Begin

Analyseer de dashboarddata hierboven. Geef je bevindingen nu."""

    elif tab == "leads":
        systeem = f"""Je bent een conversie- en leadgen-analist voor dakdekkersgids.nl. Je taak: analyseer de data en geef concrete actiepunten om meer offerteaanvragen te genereren. Focus op welke pagina's en clusters converteren, welke kanalen presteren, en waar kansen liggen. Wees direct en bondig.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "content_gap":
        systeem = f"""Je bent een Content Gap specialist voor dakdekkersgids.nl. Analyseer welke zoekwoorden ontbreken in de huidige content en geef concrete aanbevelingen voor nieuwe pagina's of uitbreidingen die het meeste leadvolume kunnen opleveren.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "anomalie":
        systeem = f"""Je bent een Anomalie Detective voor dakdekkersgids.nl. Analyseer de data op onverwachte pieken of dalingen in verkeer, CTR, leads of gebruikersgedrag. Geef een heldere verklaring en concrete vervolgstappen.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "rapportage":
        systeem = f"""Je bent de Hoofd-Rapportage Agent van dakdekkersgids.nl — een niche-leadgensite voor dakdekkers in Nederland. Je beschikt over de gecombineerde expertise van zes specialisten en hebt toegang tot het volledige dashboard.

GECOMBINEERDE EXPERTISE

Als SEO-strateeg zie je: welke keywords stijgen of dalen, CTR-kansen op positie 4–10, en intentie-mismatch tussen verkeer en leads.
Als Conversie-analist zie je: welke pagina's traffic genereren maar niet converteren, en welke kanalen de meeste offerteaanvragen opleveren.
Als Content Gap specialist zie je: zoekwoorden met impressies maar geen goede rankende pagina, en gaten in het zoekwoordunivers.
Als Anomalie Detective zie je: onverwachte dalingen of pieken in clicks, sessies of leads ten opzichte van vorige week.
Als Concurrentie-analist zie je: keywords waarop de positie verzwakt, als signaal dat concurrenten terrein winnen.
Als Plannings-agent zie je: seizoenspatronen en timing — zijn bepaalde zoekwoorden nu opkomend of juist aflopend?

TAAKOMSCHRIJVING

Wanneer de gebruiker vraagt om een dashboard-scan, analyseer je alle beschikbare data integraal. Je kruist de bronnen: een pagina die in GA4 goed presteert maar in GSC positie verliest, verdient andere aandacht dan een pagina die in GSC stijgt maar nul leads genereert.

OUTPUTFORMAAT — GEBRUIK ALTIJD DIT FORMAAT BIJ EEN SCAN

🔴 MEEST URGENT
[1–2 zaken die direct actie vereisen — met concrete cijfers en specifieke pagina of keyword]

🟡 OPVALLEND DEZE WEEK
[2–3 opvallende bewegingen in de data — positief of negatief]

✅ DIRECT TOEPASBARE ACTIES
[Maximaal 5 acties, elk op één regel, geprioriteerd op impact. Formaat: pagina of keyword → actie → verwacht effect]

📊 QUICK STATS
Clicks: X (±Y%) | Sessies: X (±Y%) | Leads: X (vorige week: X) | Gem. positie: X

Schrijf compact en scanbaar — dit rapport wordt rechtstreeks gemaild. Geen inleiding, geen afsluiting.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "concurrentie":
        systeem = f"""Je bent een Concurrentie-analist voor dakdekkersgids.nl met directe toegang tot sitemap-data van drie directe concurrenten én live data van onze eigen site.

Je drie concurrenten:
- homedeal.nl — groot leadgenplatform, brede dakdekker-coverage
- mijn-dakdekker.nl — niche-site direct gericht op dakdekkers zoeken
- kosten-dakdekker.nl — informationele site gericht op kostenvragen

ZO ANALYSEER JE

Dreigingsmatrix: een keyword is een echte dreiging als:
1. Meerdere concurrenten hebben er content over (ze investeren er bewust in)
2. Wij ranken op positie 4–20 (kwetsbare zone — makkelijk te verdringen)
3. Het keyword heeft commerciële intentie (dakdekker [stad], offerte, kosten)
4. Mangools-volume is hoog (> 500/maand)

Kansen-matrix: een keyword is een kans als:
1. Concurrent heeft er content over maar wij nog niet (of nauwelijks)
2. Mangools-difficulty is laag (< 30)
3. Het keyword past bij onze leadgenstrategie

ANTWOORDFORMAAT

🔴 DIRECTE DREIGINGEN
[Keywords + specifieke concurrent die ons aanvalt — met positie en volume]

🟡 CONTENT-GATEN DIE CONCURRENTEN VULLEN
[Wat zij publiceren dat wij niet hebben]

✅ CONCRETE ACTIES
[Max 4 acties: welke pagina maken/verbeteren, voor welk keyword, waarom nu]

Gebruik altijd cijfers. Combineer sitemap-data met GSC-posities. Geen algemene SEO-adviezen.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "planning":
        systeem = f"""Je bent een Plannings Agent voor dakdekkersgids.nl. Analyseer seizoenspatronen en historische trenddata en adviseer wanneer nieuwe content gepubliceerd moet worden of campagnes geïntensiveerd. Focus op timing voor maximale leadgen-impact.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    else:  # strategie
        systeem = f"""Je bent een strategisch analist voor dakdekkersgids.nl, een leadgen-site voor de dakdekkers-niche. Je combineert alle beschikbare data tot een duidelijk weekoverzicht met geprioriteerde actiepunten. Geef maximaal 3-5 concrete aanbevelingen, gerangschikt op impact. Wees bondig en direct — geen achtergrondinfo, direct de analyse.{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": systeem}] + history,
        max_tokens=1200
    )

    raw = response.choices[0].message.content
    match = re.search(r'\[VRAGEN\](.*?)\[/VRAGEN\]', raw, re.DOTALL)
    suggesties = []
    if match:
        suggesties = [v.strip() for v in match.group(1).strip().split('\n') if v.strip()][:3]
        antwoord = raw[:match.start()].strip()
    else:
        antwoord = raw

    return jsonify({"antwoord": antwoord, "suggesties": suggesties})


# Proactief signaal per dashboardpagina
@app.route("/api/signaal")
def signaal():
    pagina = request.args.get("pagina", "dashboard")

    gsc = load_json("gsc_data.json")
    ga4 = load_json("ga4_data.json")
    leads = load_json("leads_week.json")
    cl = leads.get('cluster_attributie', {})

    pagina_prompts = {
        "dashboard": f"Je bekijkt het hoofddashboard. Clicks: {gsc.get('totals',{}).get('clicks')} ({gsc.get('totals',{}).get('clicks_growth')}%), sessies: {ga4.get('totals',{}).get('sessions')} ({ga4.get('totals',{}).get('sessions_growth')}%), offerteaanvragen: {ga4.get('offerteaanvragen',{}).get('totaal_deze_week')}.",
        "searchconsole": f"Je bekijkt de Search Console. Top CTR-kansen: {json.dumps([k for k in gsc.get('top_keywords',[]) if k.get('position',99)<=10 and k.get('ctr',99)<3 and k.get('impressions',0)>=30][:5], ensure_ascii=False)}. Positie-kansen: {json.dumps([k for k in gsc.get('top_keywords',[]) if 4<=k.get('position',99)<=15 and k.get('impressions',0)>=30][:5], ensure_ascii=False)}.",
        "analytics": f"Je bekijkt Analytics. Bouncepercentage: {ga4.get('totals',{}).get('bounce_rate')}%, aanvragen per pagina: {json.dumps(ga4.get('offerteaanvragen',{}).get('deze_week',[])[:5], ensure_ascii=False)}, kanalen: {json.dumps(ga4.get('channels',[])[:5], ensure_ascii=False)}.",
        "leads": f"Je bekijkt de leads. Directe leads: {leads.get('directe_leads',{}).get('totaal_deze_week')} (vw: {leads.get('directe_leads',{}).get('totaal_vorige_week')}). Clusters deze week: {json.dumps(cl.get('deze_week',{}), ensure_ascii=False)}.",
        "clusters": f"Je bekijkt clusters. Cumulatief: {json.dumps(cl.get('cumulatief',{}), ensure_ascii=False)}. Deze week: {json.dumps(cl.get('deze_week',{}), ensure_ascii=False)}.",
        "trends": "Je bekijkt de trendspagina met zoekvolume-ontwikkeling.",
        "keywords": f"Je bekijkt keyword onderzoek. Top keywords in GSC: {json.dumps(gsc.get('top_keywords',[])[:8], ensure_ascii=False)}.",
        "analyse": f"Je bekijkt de analysepagina. Dalende pagina's en algemene prestaties.",
    }

    context = pagina_prompts.get(pagina, "Je bekijkt het dashboard.")
    systeem = f"""Je bent een data-analist voor dakdekkersgids.nl. Geef één concrete, opvallende observatie over de data die de gebruiker nu ziet. Maximaal 2 zinnen. Eindig met één gerichte vraag die je kunt stellen om verder te analyseren. Geen intro, direct de observatie."""

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": systeem},
            {"role": "user", "content": context}
        ],
        max_tokens=150
    )

    return jsonify({"signaal": response.choices[0].message.content})


# Data verversen
@app.route("/api/refresh", methods=["POST"])
def refresh():
    results = {}
    scripts = [os.path.join("fetchers", s) for s in ["gsc.py", "ga4.py", "trends.py", "clarity.py"]]
    for script in scripts:
        path = os.path.join(BASE_DIR, script)
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=60
        )
        results[script] = {
            "ok": result.returncode == 0,
            "output": result.stdout.strip() or result.stderr.strip()
        }
    return jsonify(results)


# Keyword onderzoek via Mangools
@app.route("/api/keywords/zoek", methods=["POST"])
def keywords_zoek():
    import requests as req

    seed = request.json.get("keyword", "").strip()
    if not seed:
        return jsonify({"error": "Geen keyword opgegeven"}), 400

    mangools_key = os.getenv("MANGOOLS_API_KEY")

    # Nederlandse variaties op het seed keyword
    variaties = [
        seed,
        f"{seed} kosten",
        f"{seed} prijzen",
        f"{seed} amsterdam",
        f"{seed} rotterdam",
        f"{seed} den haag",
        f"{seed} utrecht",
        f"goedkoop {seed}",
        f"beste {seed}",
        f"{seed} offerte",
        f"{seed} nederland",
        f"{seed} bedrijf",
        f"{seed} specialist",
    ]

    alle_keywords = variaties

    # Stap 2: zoekvolumes ophalen via import API
    imp_resp = req.post(
        "https://api.mangools.com/v3/kwfinder/keyword-imports",
        headers={"X-access-Token": mangools_key, "Content-Type": "application/json"},
        json={"keywords": alle_keywords, "location_id": 2528}
    )

    volumes = {}
    if imp_resp.status_code == 429:
        return jsonify({"error": "Rate limit bereikt — wacht even en probeer opnieuw"}), 429
    if imp_resp.ok:
        for item in imp_resp.json().get("keywords", []):
            volumes[item["kw"].lower()] = {
                "sv": item.get("sv", 0),
                "cpc": item.get("cpc", 0),
                "ppc": item.get("ppc", 0)
            }

    # Stap 3: GSC data → huidige posities + alle matches
    gsc = load_json("gsc_data.json")
    week_gsc  = gsc.get("content_keywords") or gsc.get("top_keywords", [])
    month_gsc = gsc.get("kw_month", [])
    # Week heeft voorrang; 30-dagen vult aan voor keywords met 0 impressies deze week
    gsc_week_map  = {k["query"].lower(): k for k in week_gsc}
    gsc_month_map = {k["query"].lower(): k for k in month_gsc}

    def gsc_lookup(kw_lower):
        return gsc_week_map.get(kw_lower) or gsc_month_map.get(kw_lower)

    resultaten = []
    for kw in alle_keywords:
        kw_lower = kw.lower().strip()
        g = gsc_lookup(kw_lower)
        vol = volumes.get(kw_lower, {})
        if vol.get("sv", 0) == 0 and not g:
            continue

        resultaten.append({
            "keyword":      kw,
            "zoekvolume":   vol.get("sv", 0),
            "cpc":          vol.get("cpc", 0),
            "concurrentie": vol.get("ppc", 0),
            "rankt":        g is not None,
            "positie":      g["position"]    if g else None,
            "clicks":       g["clicks"]      if g else 0,
            "impressies":   g["impressions"] if g else 0,
            "ctr":          g["ctr"]         if g else 0,
        })

    resultaten.sort(key=lambda x: (x["rankt"], -(x["zoekvolume"] or 0)))

    # GSC-matches: zoek in maanddata voor vollediger beeld
    alle_gsc_lookup = month_gsc if month_gsc else week_gsc
    gsc_matches = sorted(
        [k for k in alle_gsc_lookup if seed.lower() in k["query"].lower()],
        key=lambda x: -x["impressions"]
    )[:30]

    return jsonify({"resultaten": resultaten, "gsc_matches": gsc_matches})


# Leads & cluster attributie
@app.route("/api/leads")
def leads():
    return jsonify(load_json("leads_week.json"))


# Leads data verversen (aparte route: funnel API is traag)
@app.route("/api/refresh-leads", methods=["POST"])
def refresh_leads():
    path = os.path.join(BASE_DIR, "fetchers", "leads.py")
    result = subprocess.run(
        [sys.executable, path],
        capture_output=True, text=True, timeout=120
    )
    return jsonify({
        "ok": result.returncode == 0,
        "output": result.stdout.strip() or result.stderr.strip()
    })


# ── Dagelijkse mail scheduler ─────────────────────────────────────────────────
MAIL_UUR = 7  # verstuur elke dag om dit uur

SNAPSHOT_FILE  = os.path.join(DATA_DIR, "gsc_snapshot.json")
MAIL_DATUM_FILE = os.path.join(DATA_DIR, "mail_datum.json")


def _lees_mail_datum():
    if not os.path.exists(MAIL_DATUM_FILE):
        return None
    try:
        with open(MAIL_DATUM_FILE, encoding="utf-8") as f:
            d = json.load(f).get("datum")
        return date.fromisoformat(d) if d else None
    except Exception:
        return None


def _sla_mail_datum_op(d):
    with open(MAIL_DATUM_FILE, "w", encoding="utf-8") as f:
        json.dump({"datum": d.isoformat()}, f)

# Drempelwaarden voor signalering
POSITIE_DREMPEL      = 5     # keyword: plaatsen stijging of daling
GROTE_DALING_DREMPEL = 10    # pagina: grote daling (apart gesignaleerd)
CLICKS_DREMPEL       = 0.20  # 20% toe- of afname
LEADS_DREMPEL        = 0.30  # 30% afname

# Formaat env var: "Naam=email,Naam2=email2,Naam3" (email optioneel)
_mw_raw = os.getenv("MEDEWERKERS", "Sander,Lennard,Bert-Jan=bert-jan@daadkracht-marketing.nl")
MEDEWERKERS: dict[str, str | None] = {}
for _mw in _mw_raw.split(","):
    _mw = _mw.strip()
    if "=" in _mw:
        _naam, _email = _mw.split("=", 1)
        MEDEWERKERS[_naam.strip()] = _email.strip()
    elif _mw:
        MEDEWERKERS[_mw] = None

# Clarity drempelwaarden (statisch — geen snapshot nodig)
DEAD_CLICK_DREMPEL  = 15.0  # % sessies met dead clicks
RAGE_CLICK_DREMPEL  = 0.5   # % sessies met rage clicks
QUICKBACK_DREMPEL   = 8.0   # % sessies met quick back
SCRIPT_ERROR_DREMPEL = 2.0  # % sessies met script errors
SCROLL_DIEPTE_MIN   = 30.0  # % scroll diepte (onder = te laag)


def _sla_snapshot_op():
    gsc = load_json("gsc_data.json")
    snapshot = {
        "datum": date.today().isoformat(),
        "keywords": {k["query"]: k for k in gsc.get("top_keywords", [])},
        "paginas":  {p["page"]:  p for p in gsc.get("top_pages", [])},
        "clicks":   gsc.get("totals", {}).get("clicks", 0),
    }
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def _detect_signalen():
    """Detecteer signaleringen: top-10 entries, grote dalingen, click-wijzigingen, leads."""
    if not os.path.exists(SNAPSHOT_FILE):
        return []

    snap   = load_json("gsc_snapshot.json")
    gsc    = load_json("gsc_data.json")
    leads  = load_json("leads_week.json")
    signalen = []

    snap_kw = snap.get("keywords", {})
    snap_pg = snap.get("paginas", {})

    # Keyword positieveranderingen (≥5 plaatsen)
    for kw in gsc.get("top_keywords", []):
        q   = kw["query"]
        oud = snap_kw.get(q)
        if not oud:
            continue
        delta = oud["position"] - kw["position"]  # positief = gestegen
        if abs(delta) >= POSITIE_DREMPEL:
            richting = "gestegen" if delta > 0 else "gedaald"
            signalen.append({
                "type":   "keyword_positie",
                "niveau": "positief" if delta > 0 else "negatief",
                "tekst":  f"Keyword <strong>'{q}'</strong> is {abs(delta):.0f} plekken {richting}: "
                          f"positie {oud['position']:.0f} → {kw['position']:.0f} "
                          f"({kw['impressions']} impressies, {kw['clicks']} clicks)"
            })

    # Pagina: nieuw in top 10
    for pg in gsc.get("top_pages", []):
        url = pg["page"]
        oud = snap_pg.get(url)
        if not oud:
            continue
        if oud["position"] > 10 and pg["position"] <= 10:
            pad = url.replace("https://dakdekkersgids.nl", "") or "/"
            signalen.append({
                "type":   "top10_entry",
                "niveau": "positief",
                "tekst":  f"Pagina <strong>{pad}</strong> staat nu in de <strong>top 10</strong>! "
                          f"Positie {oud['position']:.0f} → {pg['position']:.0f} "
                          f"({pg['clicks']} clicks, {pg['impressions']} impressies)"
            })

    # Pagina: ≥10 posities gedaald
    for pg in gsc.get("top_pages", []):
        url = pg["page"]
        oud = snap_pg.get(url)
        if not oud:
            continue
        daling = pg["position"] - oud["position"]  # positief = gedaald
        if daling >= GROTE_DALING_DREMPEL:
            pad = url.replace("https://dakdekkersgids.nl", "") or "/"
            signalen.append({
                "type":   "grote_daling",
                "niveau": "negatief",
                "tekst":  f"Pagina <strong>{pad}</strong> is {daling:.0f} posities gedaald: "
                          f"positie {oud['position']:.0f} → {pg['position']:.0f} "
                          f"({pg['clicks']} clicks)"
            })

    # Totale clicks (±20%)
    oud_clicks = snap.get("clicks", 0)
    nw_clicks  = gsc.get("totals", {}).get("clicks", 0)
    if oud_clicks > 0:
        delta_pct = (nw_clicks - oud_clicks) / oud_clicks
        if abs(delta_pct) >= CLICKS_DREMPEL:
            richting = "gestegen" if delta_pct > 0 else "gedaald"
            signalen.append({
                "type":   "clicks_totaal",
                "niveau": "positief" if delta_pct > 0 else "negatief",
                "tekst":  f"Totale clicks zijn {abs(delta_pct)*100:.0f}% {richting}: "
                          f"{oud_clicks} → {nw_clicks}"
            })

    # Leads daling (≥30%)
    dl        = leads.get("directe_leads", {})
    oud_leads = dl.get("totaal_vorige_week", 0)
    nw_leads  = dl.get("totaal_deze_week", 0)
    if oud_leads > 0:
        delta_pct = (nw_leads - oud_leads) / oud_leads
        if delta_pct <= -LEADS_DREMPEL:
            signalen.append({
                "type":   "leads_daling",
                "niveau": "negatief",
                "tekst":  f"Leads zijn {abs(delta_pct)*100:.0f}% gedaald: "
                          f"{oud_leads} → {nw_leads} deze week"
            })

    # Clarity UX-signalen (vaste drempelwaarden)
    clarity = load_json("clarity_data.json")
    if clarity and isinstance(clarity.get("metrics"), dict):
        m = clarity["metrics"]
        dead = m.get("dead_click_pct", 0)
        rage = m.get("rage_click_pct", 0)
        qb   = m.get("quickback_pct", 0)
        err  = m.get("script_error_pct", 0)
        scroll = m.get("scroll_diepte", 100)

        if dead >= DEAD_CLICK_DREMPEL:
            signalen.append({
                "type":   "dead_clicks",
                "niveau": "negatief",
                "tekst":  f"Hoge dead-click rate: <strong>{dead}%</strong> van de sessies klikt op elementen die niets doen "
                          f"({m.get('dead_click_paginas', 0)} pagina's betrokken). Controleer CTA's en linkjes."
            })
        if rage >= RAGE_CLICK_DREMPEL:
            signalen.append({
                "type":   "rage_clicks",
                "niveau": "negatief",
                "tekst":  f"Hoge rage-click rate: <strong>{rage}%</strong> — gebruikers zijn gefrustreerd. "
                          f"Waarschijnlijk een kapot element of trage laadtijd."
            })
        if qb >= QUICKBACK_DREMPEL:
            signalen.append({
                "type":   "quickback",
                "niveau": "negatief",
                "tekst":  f"Hoge quick-back rate: <strong>{qb}%</strong> van bezoekers keert direct terug naar Google "
                          f"({m.get('quickback_paginas', 0)} pagina's). Content sluit mogelijk niet aan bij zoekintentie."
            })
        if err >= SCRIPT_ERROR_DREMPEL:
            signalen.append({
                "type":   "script_errors",
                "niveau": "negatief",
                "tekst":  f"Script errors op <strong>{err}%</strong> van de sessies — waarschijnlijk een JavaScript-fout die conversies blokkeert."
            })
        if scroll < SCROLL_DIEPTE_MIN:
            signalen.append({
                "type":   "lage_scroll",
                "niveau": "negatief",
                "tekst":  f"Lage gemiddelde scroll diepte: <strong>{scroll}%</strong>. "
                          f"Bezoekers zien de CTA of het formulier mogelijk niet."
            })

    return signalen


def _detect_anomalies():
    return _detect_signalen()


def _stuur_signalering_mail(signalen):
    if not signalen:
        return

    gmail_address = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")

    positief = [s for s in signalen if s["niveau"] == "positief"]
    negatief = [s for s in signalen if s["niveau"] == "negatief"]

    type_label = {
        "top10_entry":    "Nieuw in top 10",
        "grote_daling":   "Grote daling",
        "keyword_positie":"Keyword positie",
        "clicks_totaal":  "Clicks",
        "leads_daling":   "Leads",
        "dead_clicks":    "Dead clicks",
        "rage_clicks":    "Rage clicks",
        "quickback":      "Quick back",
        "script_errors":  "Script errors",
        "lage_scroll":    "Lage scroll diepte",
    }

    def rijen(items, kleur):
        return "".join(
            f'<div style="padding:10px 14px;border-left:3px solid {kleur};'
            f'margin-bottom:8px;background:#1e1e1e;border-radius:0 8px 8px 0;'
            f'font-size:13px;color:#c0c0c0;line-height:1.6">'
            f'<span style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;'
            f'color:{kleur};display:block;margin-bottom:4px">'
            f'{type_label.get(s["type"], s["type"])}</span>'
            f'{s["tekst"]}</div>'
            for s in items
        )

    secties = ""
    if negatief:
        secties += f"""
        <h2 style="font-size:12px;color:#f87171;text-transform:uppercase;
            letter-spacing:1px;margin:0 0 10px">Let op</h2>
        {rijen(negatief, '#f87171')}
        <div style="margin-bottom:20px"></div>"""
    if positief:
        secties += f"""
        <h2 style="font-size:12px;color:#02CE80;text-transform:uppercase;
            letter-spacing:1px;margin:0 0 10px">Positieve bewegingen</h2>
        {rijen(positief, '#02CE80')}"""

    rand_kleur = '#f87171' if negatief else '#02CE80'
    titel = "Let op — actie vereist" if negatief else "Positief nieuws"
    html = f"""
    <html><body style="margin:0;padding:0;background:#0e0e0e;font-family:'Segoe UI',Arial,sans-serif">
    <div style="max-width:600px;margin:32px auto;background:#1a1a1a;border-radius:18px;overflow:hidden;color:#fff">
      <div style="background:#1a1a1a;border-bottom:2px solid {rand_kleur};padding:24px 32px">
        <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">
          dakdekkersgids.nl — signalering</div>
        <h1 style="margin:0;font-size:20px;font-weight:700;color:#fff">{titel}</h1>
        <p style="margin:6px 0 0;font-size:12px;color:#555">
          {date.today().strftime('%d-%m-%Y')} — {len(signalen)} signaal{'en' if len(signalen) != 1 else ''} gedetecteerd</p>
      </div>
      <div style="padding:28px 32px">{secties}</div>
      <div style="padding:14px 32px;border-top:1px solid #2a2a2a;font-size:11px;color:#444;text-align:center">
        Automatisch signaal — dakdekkersgids.nl dashboard
      </div>
    </div>
    </body></html>"""

    onderwerp = f"{'⚠️ Signalering' if negatief else '📈 Signaal'} dakdekkersgids.nl — {date.today().strftime('%d-%m-%Y')}"
    ontvangers = [a.strip() for a in os.getenv("MAIL_ONTVANGERS", gmail_address).split(",")]
    _gmail_stuur(ontvangers, onderwerp, html)
    print(f"[scheduler] Signaleringsmail verstuurd — {len(signalen)} signalen.")


def _stuur_alert_mail(anomalieën):
    _stuur_signalering_mail(anomalieën)


def _genereer_taken(gsc, ga4, leads_data):
    """Vraag OpenAI om 3 concrete, geprioriteerde taken te genereren."""
    kw_all = gsc.get("content_keywords") or gsc.get("top_keywords", [])
    ctr_kansen = [k for k in kw_all if k.get("position", 99) <= 10 and k.get("ctr", 99) < 3.0 and k.get("impressions", 0) >= 30][:4]
    pos_kansen = [k for k in kw_all if 4 <= k.get("position", 99) <= 15 and k.get("impressions", 0) >= 30][:4]
    dl = leads_data.get("directe_leads", {})

    clarity = load_json("clarity_data.json")
    clarity_blok = ""
    if clarity and isinstance(clarity.get("metrics"), dict):
        m = clarity["metrics"]
        pop = [p.get("url", "") for p in m.get("populaire_paginas", [])[:5]]
        apparaten = {a["naam"]: a["sessies"] for a in m.get("apparaten", [])}
        clarity_blok = f"""
- Clarity gedragsdata:
  - Dead clicks: {m.get('dead_click_pct', 0)}% ({m.get('dead_click_paginas', 0)} pagina's)
  - Rage clicks: {m.get('rage_click_pct', 0)}%
  - Quick back: {m.get('quickback_pct', 0)}% ({m.get('quickback_paginas', 0)} pagina's)
  - Scroll diepte: {m.get('scroll_diepte', 0)}%
  - Actieve tijd: {m.get('actieve_tijd_sec', 0)}s
  - Apparaten: {json.dumps(apparaten, ensure_ascii=False)}
  - Populaire pagina's in Clarity: {pop}"""

    prompt = f"""Je bent een SEO- en CRO-strateeg voor dakdekkersgids.nl (leadgen-site dakdekkers Nederland).

Data van vandaag:
- Clicks: {gsc.get('totals', {}).get('clicks')} ({gsc.get('totals', {}).get('clicks_growth')}% t.o.v. vorige week)
- Sessies: {ga4.get('totals', {}).get('sessions')} ({ga4.get('totals', {}).get('sessions_growth')}%)
- Leads deze week: {dl.get('totaal_deze_week')} (vorige week: {dl.get('totaal_vorige_week')})
- CTR-kansen (top 10, CTR < 3%): {json.dumps(ctr_kansen, ensure_ascii=False)}
- Positie-kansen (pos 4-15): {json.dumps(pos_kansen, ensure_ascii=False)}
- Top pagina's: {json.dumps(gsc.get('top_pages', [])[:5], ensure_ascii=False)}{clarity_blok}

Beschikbare medewerkers: {', '.join(MEDEWERKERS)}

Genereer precies 3 concrete uitvoerbare taken voor vandaag. Gebruik ook de Clarity gedragsdata als dat relevant is (bijv. lage scroll diepte = formulier niet zichtbaar, hoge dead clicks = gebroken elementen, mobiel dominant = mobile-first denken). Prioriteer op leadgen-impact.

Geef antwoord als JSON:
{{"taken": [
  {{"taak": "korte taaktitel (max 8 woorden)", "toelichting": "1-2 zinnen met concrete data erbij", "medewerker": "naam uit lijst", "prioriteit": "hoog|middel|laag"}},
  {{"taak": "...", "toelichting": "...", "medewerker": "...", "prioriteit": "..."}},
  {{"taak": "...", "toelichting": "...", "medewerker": "...", "prioriteit": "..."}}
]}}

Regels: elke taak direct uitvoerbaar, gebruik exacte keywords/pagina's of Clarity-inzichten, wijs elke taak aan een andere medewerker toe."""

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700
    )
    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        return data.get("taken", data) if isinstance(data, dict) else data
    except (json.JSONDecodeError, TypeError):
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return []


def _stuur_takenmail():
    """Stuur dagelijkse takenmail met 3 AI-gegenereerde actiepunten."""
    gsc        = load_json("gsc_data.json")
    ga4        = load_json("ga4_data.json")
    leads_data = load_json("leads_week.json")

    taken = _genereer_taken(gsc, ga4, leads_data)

    prio_kleur = {"hoog": "#f87171", "middel": "#fbbf24", "laag": "#02CE80"}

    taken_html = ""
    for t in taken[:3]:
        prio  = t.get("prioriteit", "middel").lower()
        kleur = prio_kleur.get(prio, "#fbbf24")
        mw    = t.get("medewerker", "?")
        taken_html += f"""
        <div style="background:#1e1e1e;border-radius:12px;padding:18px 20px;margin-bottom:12px;border-left:3px solid {kleur}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
            <div style="font-size:15px;font-weight:700;color:#fff;line-height:1.3;flex:1">{t.get('taak', '')}</div>
            <span style="font-size:10px;padding:3px 8px;border-radius:20px;background:{kleur}22;color:{kleur};
              border:1px solid {kleur}44;text-transform:uppercase;letter-spacing:0.5px;
              flex-shrink:0;margin-left:10px">{prio}</span>
          </div>
          <p style="margin:0 0 14px;font-size:13px;color:#a0a0a0;line-height:1.6">{t.get('toelichting', '')}</p>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="width:28px;height:28px;background:#02CE8022;border:1px solid #02CE8055;border-radius:50%;
              text-align:center;line-height:28px;color:#02CE80;font-size:12px;font-weight:700">{mw[0].upper()}</div>
            <span style="font-size:13px;color:#02CE80;font-weight:600">{mw}</span>
          </div>
        </div>"""

    if not taken_html:
        taken_html = '<p style="color:#828282;font-size:13px">Geen taken gegenereerd — ververs de data eerst.</p>'

    clicks         = gsc.get("totals", {}).get("clicks", 0)
    clicks_growth  = gsc.get("totals", {}).get("clicks_growth", 0)
    sessies        = ga4.get("totals", {}).get("sessions", 0)
    leads_nu       = leads_data.get("directe_leads", {}).get("totaal_deze_week", 0)
    groei_kleur_fn = lambda g: "#02CE80" if (g or 0) >= 0 else "#f87171"
    groei_teken_fn = lambda g: f"+{g}" if (g or 0) >= 0 else str(g)

    dag_nl = ["maandag","dinsdag","woensdag","donderdag","vrijdag","zaterdag","zondag"]
    mnd_nl = ["januari","februari","maart","april","mei","juni","juli","augustus","september","oktober","november","december"]
    nu     = date.today()
    datum_str = f"{dag_nl[nu.weekday()]} {nu.day} {mnd_nl[nu.month-1]} {nu.year}"

    html = f"""
    <html><body style="margin:0;padding:0;background:#0e0e0e;font-family:'Segoe UI',Arial,sans-serif">
    <div style="max-width:600px;margin:32px auto;background:#1a1a1a;border-radius:18px;overflow:hidden;color:#fff">

      <div style="background:#1a1a1a;border-bottom:2px solid #02CE80;padding:24px 32px">
        <div style="font-size:11px;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">dakdekkersgids.nl</div>
        <h1 style="margin:0;font-size:20px;font-weight:700;color:#fff">Taken voor vandaag</h1>
        <p style="margin:6px 0 0;font-size:12px;color:#555">{datum_str}</p>
      </div>

      <div style="padding:28px 32px">
        {taken_html}

        <div style="margin-top:24px;padding-top:20px;border-top:1px solid #2a2a2a">
          <div style="font-size:10px;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px">Snel overzicht</div>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="padding:0 4px 0 0">
                <div style="background:#2a2a2a;border-radius:8px;padding:12px;text-align:center">
                  <div style="font-size:22px;font-weight:700;color:#4285f4">{clicks}</div>
                  <div style="font-size:10px;color:#555;margin-top:3px">Clicks&nbsp;
                    <span style="color:{groei_kleur_fn(clicks_growth)}">{groei_teken_fn(clicks_growth)}%</span></div>
                </div>
              </td>
              <td style="padding:0 4px">
                <div style="background:#2a2a2a;border-radius:8px;padding:12px;text-align:center">
                  <div style="font-size:22px;font-weight:700;color:#a78bfa">{sessies:,}</div>
                  <div style="font-size:10px;color:#555;margin-top:3px">Sessies</div>
                </div>
              </td>
              <td style="padding:0 0 0 4px">
                <div style="background:#2a2a2a;border-radius:8px;padding:12px;text-align:center">
                  <div style="font-size:22px;font-weight:700;color:#02CE80">{leads_nu}</div>
                  <div style="font-size:10px;color:#555;margin-top:3px">Leads deze week</div>
                </div>
              </td>
            </tr>
          </table>
        </div>
      </div>

      <div style="padding:14px 32px;border-top:1px solid #2a2a2a;font-size:11px;color:#444;text-align:center">
        Dagelijkse taken — dakdekkersgids.nl dashboard
      </div>
    </div>
    </body></html>"""

    gmail_address  = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")
    basis          = [a.strip() for a in os.getenv("MAIL_ONTVANGERS", gmail_address).split(",")]
    mw_emails      = [e for e in MEDEWERKERS.values() if e]
    ontvangers     = list(dict.fromkeys(basis + mw_emails))  # dedupliceer, behoud volgorde
    onderwerp      = f"Taken voor {datum_str} — dakdekkersgids.nl"
    _gmail_stuur(ontvangers, onderwerp, html)
    print(f"[scheduler] Takenmail verstuurd naar {len(ontvangers)} ontvangers — {len(taken)} taken.")


def _dagelijkse_mail_loop():
    while True:
        try:
            nu      = datetime.now()
            vandaag = nu.date()
            if nu.hour >= MAIL_UUR and _lees_mail_datum() != vandaag:
                print(f"[scheduler {nu.strftime('%H:%M')}] Dagelijkse mails — data vernieuwen...")
                _sla_snapshot_op()
                for script in ["gsc.py", "ga4.py", "trends.py", "leads.py", "clarity.py"]:
                    subprocess.run(
                        [sys.executable, os.path.join(BASE_DIR, "fetchers", script)],
                        capture_output=True, timeout=120
                    )
                # 1. Takenmail — altijd
                _stuur_takenmail()
                # 2. Signaleringsmail — alleen bij detecties
                signalen = _detect_signalen()
                if signalen:
                    _stuur_signalering_mail(signalen)
                _sla_mail_datum_op(vandaag)
                print(f"[scheduler] Dagelijkse mails verstuurd.")
        except Exception as e:
            import traceback
            print(f"[scheduler] Fout: {e}")
            print(traceback.format_exc())
        time.sleep(300)  # check elke 5 minuten


_fetch_status = {}

FETCH_TIMEOUTS = {"trends.py": 300, "leads.py": 180}

def _run_fetcher(script):
    global _fetch_status
    timeout = FETCH_TIMEOUTS.get(script, 120)
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "fetchers", script)],
            capture_output=True, timeout=timeout
        )
        if result.returncode == 0:
            _fetch_status[script] = "ok"
            print(f"[startup] fetchers/{script}: ok")
        else:
            fout = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()[-300:]
            _fetch_status[script] = f"fout: {fout}"
            print(f"[startup] fetchers/{script}: FOUT\n{fout}")
    except subprocess.TimeoutExpired:
        _fetch_status[script] = f"timeout na {timeout}s"
        print(f"[startup] fetchers/{script}: TIMEOUT na {timeout}s")
    except Exception as e:
        _fetch_status[script] = f"exception: {e}"
        print(f"[startup] fetchers/{script}: EXCEPTION {e}")


def _startup_fetch():
    global _fetch_status
    print("[startup] Data ophalen...")
    for script in ["gsc.py", "ga4.py", "trends.py", "leads.py", "clarity.py"]:
        _run_fetcher(script)
    print("[startup] Klaar.")


# Start scheduler en eenmalige startup-fetch
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    threading.Thread(target=_dagelijkse_mail_loop, daemon=True).start()
    threading.Thread(target=_startup_fetch, daemon=True).start()


# Mail rapport (volledig weekrapport, handmatig)
@app.route("/api/mail-rapport", methods=["POST"])
def mail_rapport():
    try:
        _stuur_mail_intern()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Takenmail handmatig triggeren (voor testen)
@app.route("/api/mail-taken", methods=["POST"])
def mail_taken():
    try:
        _stuur_takenmail()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Signaleringsmail handmatig triggeren (voor testen)
@app.route("/api/mail-signalering", methods=["POST"])
def mail_signalering():
    try:
        signalen = _detect_signalen()
        if signalen:
            _stuur_signalering_mail(signalen)
            return jsonify({"ok": True, "signalen": len(signalen), "details": [s["tekst"] for s in signalen]})
        return jsonify({"ok": True, "signalen": 0, "bericht": "Geen signalen gedetecteerd."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/fetch-status")
def fetch_status():
    data_bestanden = ["gsc_data.json", "ga4_data.json", "leads_week.json",
                      "trends_data.json", "clarity_data.json", "competitor_data.json"]
    bestanden = {
        f: os.path.exists(os.path.join(DATA_DIR, f))
        for f in data_bestanden
    }
    return jsonify({"fetch_log": _fetch_status, "data_bestanden": bestanden})


@app.route("/api/mail-test", methods=["POST"])
def mail_test():
    try:
        gmail = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")
        _gmail_stuur(gmail, "Test dakdekkersgids.nl dashboard", "<p>Gmail API verbinding werkt correct.</p>")
        return jsonify({"ok": True, "bericht": f"Testmail verstuurd naar {gmail}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _stuur_mail_intern():
    leads = load_json("leads_week.json")
    gsc   = load_json("gsc_data.json")
    ga4   = load_json("ga4_data.json")

    if not leads:
        raise ValueError("Geen leads data beschikbaar — ververs eerst de data via het dashboard")

    periode   = leads.get("periode", {})
    week_s    = periode.get("deze_week", {}).get("start", "")
    week_e    = periode.get("deze_week", {}).get("end", "")
    dl        = leads.get("directe_leads", {})
    cl        = leads.get("cluster_attributie", {})
    cum       = cl.get("cumulatief", {})
    week_cl   = cl.get("deze_week", {})

    # ── KPI waarden ───────────────────────────────────────────────────────
    totaal_week_leads = sum(d["leads"] for d in week_cl.values())
    totaal_cum_leads  = sum(d["leads"] for d in cum.values())
    direct_nu         = dl.get("totaal_deze_week", 0)
    direct_vw         = dl.get("totaal_vorige_week", 0)
    gsc_clicks        = gsc.get("totals", {}).get("clicks", 0)
    gsc_growth        = gsc.get("totals", {}).get("clicks_growth", 0)
    sessies           = ga4.get("totals", {}).get("sessions", 0)
    sessies_growth    = ga4.get("totals", {}).get("sessions_growth", 0)

    # ── Laaghangend fruit analyse ──────────────────────────────────────────
    # content_keywords = zonder bedrijfs-/plaatszoekopdrachten; val terug op top_keywords
    kw_all = gsc.get("content_keywords") or gsc.get("top_keywords", [])

    # CTR-kansen: al op positie 1-10 maar CTR < 3% en >= 30 impressies
    ctr_kansen = sorted(
        [k for k in kw_all if k["position"] <= 10 and k["ctr"] < 3.0 and k["impressions"] >= 30],
        key=lambda x: x["impressions"], reverse=True
    )[:6]

    # Positie-kansen: pos 4-15, >= 30 impressies — bijna op pagina 1
    pos_kansen = sorted(
        [k for k in kw_all if 4 <= k["position"] <= 15 and k["impressions"] >= 30],
        key=lambda x: x["impressions"], reverse=True
    )[:6]

    # ── Best presterende pagina's (GSC clicks) ────────────────────────────
    best_pages = sorted(gsc.get("top_pages", []), key=lambda x: x["clicks"], reverse=True)[:6]

    # ── Quick wins (max 3, automatisch gegenereerd) ───────────────────────
    quick_wins = []
    if ctr_kansen:
        k = ctr_kansen[0]
        quick_wins.append(
            f"Verbeter <strong>title + meta description</strong> voor '<em>{k['query']}</em>' "
            f"— staat al op positie {k['position']:.0f} met {k['impressions']} impressies "
            f"maar slechts {k['ctr']}% CTR. Betere titel = direct meer clicks zonder rankingwerk."
        )
    if pos_kansen:
        k = pos_kansen[0]
        quick_wins.append(
            f"Verdiep content voor '<em>{k['query']}</em>' "
            f"— positie {k['position']:.0f} met {k['impressions']} impressies. "
            f"Een extra paragraaf of FAQ-sectie kan dit naar de top-3 tillen."
        )
    leads_paginas = dl.get("per_pagina", [])
    if leads_paginas:
        top = leads_paginas[0]
        quick_wins.append(
            f"<strong>{top['pagina']}</strong> genereert de meeste directe leads ({top['leads']}x deze week). "
            f"Controleer of het formulier en de CTA direct zichtbaar zijn zonder te scrollen."
        )

    # ── HTML helpers ──────────────────────────────────────────────────────
    def sectie_titel(tekst):
        return f'<h2 style="font-size:13px;color:#828282;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;padding-top:28px;border-top:1px solid #2e2e2e">{tekst}</h2>'

    def tabel_header(*cols):
        ths = "".join(f'<th style="padding:9px 12px;text-align:left;font-size:10px;color:#828282;text-transform:uppercase;background:#2e2e2e">{c}</th>' for c in cols)
        return f"<tr>{ths}</tr>"

    def conv(l, b):
        return f"{l/b*100:.1f}%" if b > 0 else "—"

    def cluster_rijen(data):
        rows = ""
        for cluster, d in data.items():
            c = conv(d["leads"], d["bezoekers"])
            kleur = "#02CE80" if d["leads"] > 0 else "#828282"
            rows += (
                f'<tr>'
                f'<td style="padding:9px 12px;color:#02CE80;font-family:monospace;font-size:13px">{cluster}</td>'
                f'<td style="padding:9px 12px;text-align:center;font-size:13px">{d["bezoekers"]}</td>'
                f'<td style="padding:9px 12px;text-align:center;color:{kleur};font-weight:700;font-size:13px">{d["leads"]}</td>'
                f'<td style="padding:9px 12px;text-align:center;font-size:13px">{c}</td>'
                f'</tr>'
            )
        return rows

    def groei_kleur(g):
        return "#02CE80" if g >= 0 else "#f87171"

    def groei_teken(g):
        return f"+{g}" if g >= 0 else str(g)

    # ── Best pages HTML ───────────────────────────────────────────────────
    best_pages_rows = ""
    for p in best_pages:
        path = p["page"].replace("https://dakdekkersgids.nl", "") or "/"
        pos_kleur = "#02CE80" if p["position"] <= 3 else ("#fbbf24" if p["position"] <= 10 else "#f87171")
        best_pages_rows += (
            f'<tr>'
            f'<td style="padding:9px 12px;color:#02CE80;font-family:monospace;font-size:12px">{path}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-weight:700;font-size:13px">{p["clicks"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:13px">{p["impressions"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:13px">{p["ctr"]}%</td>'
            f'<td style="padding:9px 12px;text-align:center;color:{pos_kleur};font-weight:700;font-size:13px">#{p["position"]:.0f}</td>'
            f'</tr>'
        )

    # ── CTR-kansen HTML ───────────────────────────────────────────────────
    ctr_rows = ""
    for k in ctr_kansen:
        ctr_rows += (
            f'<tr>'
            f'<td style="padding:9px 12px;font-size:13px">{k["query"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:13px">{k["impressions"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;color:#fbbf24;font-weight:700;font-size:13px">#{k["position"]:.0f}</td>'
            f'<td style="padding:9px 12px;text-align:center;color:#f87171;font-size:13px">{k["ctr"]}%</td>'
            f'</tr>'
        )
    if not ctr_rows:
        ctr_rows = '<tr><td colspan="4" style="padding:12px;color:#828282;font-size:13px">Geen CTR-kansen gevonden deze week</td></tr>'

    # ── Positie-kansen HTML ───────────────────────────────────────────────
    pos_rows = ""
    for k in pos_kansen:
        pos_rows += (
            f'<tr>'
            f'<td style="padding:9px 12px;font-size:13px">{k["query"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:13px">{k["impressions"]}</td>'
            f'<td style="padding:9px 12px;text-align:center;color:#fbbf24;font-weight:700;font-size:13px">#{k["position"]:.0f}</td>'
            f'<td style="padding:9px 12px;text-align:center;font-size:13px">{k["clicks"]}</td>'
            f'</tr>'
        )
    if not pos_rows:
        pos_rows = '<tr><td colspan="4" style="padding:12px;color:#828282;font-size:13px">Geen positie-kansen gevonden deze week</td></tr>'

    # ── Quick wins HTML ───────────────────────────────────────────────────
    qw_html = ""
    for i, win in enumerate(quick_wins, 1):
        qw_html += (
            f'<div style="display:flex;gap:14px;margin-bottom:14px;align-items:flex-start">'
            f'<div style="min-width:26px;height:26px;background:#02CE8022;border:1px solid #02CE8055;'
            f'border-radius:50%;display:flex;align-items:center;justify-content:center;'
            f'color:#02CE80;font-weight:700;font-size:13px;text-align:center;line-height:26px">{i}</div>'
            f'<div style="font-size:13px;color:#c0c0c0;line-height:1.6;padding-top:2px">{win}</div>'
            f'</div>'
        )
    if not qw_html:
        qw_html = '<p style="color:#828282;font-size:13px">Geen quick wins gegenereerd — ververs de data eerst.</p>'

    # ── Kanalen HTML ──────────────────────────────────────────────────────
    kanalen_html = "".join(
        f'<tr>'
        f'<td style="padding:9px 12px;font-size:13px">{k["kanaal"]}</td>'
        f'<td style="padding:9px 12px;text-align:center;color:#02CE80;font-weight:700;font-size:13px">{k["leads"]}</td>'
        f'</tr>'
        for k in dl.get("per_kanaal", [])
    )

    # ── Volledige HTML email ──────────────────────────────────────────────
    html = f"""
    <html><body style="margin:0;padding:0;background:#0e0e0e;font-family:'Segoe UI',Arial,sans-serif">
    <div style="max-width:640px;margin:32px auto;background:#1a1a1a;border-radius:18px;overflow:hidden;color:#fff">

      <!-- HEADER -->
      <div style="background:#02CE80;padding:24px 32px">
        <div style="font-size:12px;color:#005c38;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">dakdekkersgids.nl</div>
        <h1 style="margin:0;font-size:22px;font-weight:700;color:#000">Weekrapport</h1>
        <p style="margin:6px 0 0;font-size:13px;color:#004d30">{week_s} t/m {week_e}</p>
      </div>

      <div style="padding:28px 32px">

        <!-- KPI BLOK -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px">
          <tr>
            <td width="25%" style="padding:0 6px 0 0">
              <div style="background:#2a2a2a;border-radius:12px;padding:16px;text-align:center">
                <div style="font-size:10px;color:#828282;text-transform:uppercase;margin-bottom:8px">Cluster leads (week)</div>
                <div style="font-size:32px;font-weight:700;color:#02CE80">{totaal_week_leads}</div>
                <div style="font-size:11px;color:#828282;margin-top:4px">cum: {totaal_cum_leads}</div>
              </div>
            </td>
            <td width="25%" style="padding:0 6px">
              <div style="background:#2a2a2a;border-radius:12px;padding:16px;text-align:center">
                <div style="font-size:10px;color:#828282;text-transform:uppercase;margin-bottom:8px">Directe leads</div>
                <div style="font-size:32px;font-weight:700;color:#fff">{direct_nu}</div>
                <div style="font-size:11px;color:#828282;margin-top:4px">vw: {direct_vw}</div>
              </div>
            </td>
            <td width="25%" style="padding:0 6px">
              <div style="background:#2a2a2a;border-radius:12px;padding:16px;text-align:center">
                <div style="font-size:10px;color:#828282;text-transform:uppercase;margin-bottom:8px">GSC Clicks</div>
                <div style="font-size:32px;font-weight:700;color:#4285f4">{gsc_clicks}</div>
                <div style="font-size:11px;color:{groei_kleur(gsc_growth)};margin-top:4px">{groei_teken(gsc_growth)}%</div>
              </div>
            </td>
            <td width="25%" style="padding:0 0 0 6px">
              <div style="background:#2a2a2a;border-radius:12px;padding:16px;text-align:center">
                <div style="font-size:10px;color:#828282;text-transform:uppercase;margin-bottom:8px">Sessies</div>
                <div style="font-size:32px;font-weight:700;color:#a78bfa">{sessies:,}</div>
                <div style="font-size:11px;color:{groei_kleur(sessies_growth)};margin-top:4px">{groei_teken(sessies_growth)}%</div>
              </div>
            </td>
          </tr>
        </table>

        <!-- QUICK WINS -->
        {sectie_titel("Quick wins — pak deze kansen deze week")}
        <div style="background:#02CE8008;border:1px solid #02CE8033;border-radius:12px;padding:18px 20px;margin-bottom:4px">
          {qw_html}
        </div>

        <!-- LAAGHANGEND FRUIT: CTR-KANSEN -->
        {sectie_titel("Laaghangend fruit — verbeter CTR (al op pagina 1, lage doorklik)")}
        <p style="font-size:12px;color:#828282;margin:0 0 12px">Deze keywords ranken al goed maar hebben een lage CTR. Betere title of meta description = direct meer clicks.</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden;margin-bottom:4px">
          {tabel_header("Keyword", "Impressies", "Positie", "CTR")}
          {ctr_rows}
        </table>

        <!-- LAAGHANGEND FRUIT: POSITIE-KANSEN -->
        {sectie_titel("Laaghangend fruit — bijna op pagina 1 (positie 4-15)")}
        <p style="font-size:12px;color:#828282;margin:0 0 12px">Een verdieping in content of extra interne links kan deze keywords naar de top-3 tillen.</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden;margin-bottom:4px">
          {tabel_header("Keyword", "Impressies", "Positie", "Clicks")}
          {pos_rows}
        </table>

        <!-- BEST PRESTERENDE PAGINA'S -->
        {sectie_titel("Best presterende pagina's — Google Search Console")}
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden;margin-bottom:4px">
          {tabel_header("Pagina", "Clicks", "Impressies", "CTR", "Positie")}
          {best_pages_rows if best_pages_rows else '<tr><td colspan="5" style="padding:12px;color:#828282;font-size:13px">Geen paginadata beschikbaar</td></tr>'}
        </table>

        <!-- CLUSTER ATTRIBUTIE -->
        {sectie_titel(f"Clusters — cumulatief (20 mrt t/m {week_e})")}
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden;margin-bottom:20px">
          {tabel_header("Cluster", "Bezoekers", "Leads", "Conv%")}
          {cluster_rijen(cum)}
        </table>

        {sectie_titel("Clusters — deze week")}
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden;margin-bottom:20px">
          {tabel_header("Cluster", "Bezoekers", "Leads", "Conv%")}
          {cluster_rijen(week_cl)}
        </table>

        {sectie_titel("Directe leads per kanaal")}
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#2a2a2a;border-radius:12px;overflow:hidden">
          {tabel_header("Kanaal", "Leads")}
          {kanalen_html if kanalen_html else '<tr><td colspan="2" style="padding:12px;color:#828282;font-size:13px">Geen data</td></tr>'}
        </table>

      </div>

      <!-- FOOTER -->
      <div style="padding:16px 32px;border-top:1px solid #2a2a2a;font-size:11px;color:#444;text-align:center">
        Gegenereerd op {date.today().strftime('%d-%m-%Y')} &middot; dakdekkersgids.nl dashboard
      </div>
    </div>
    </body></html>
    """

    # ── Versturen ──────────────────────────────────────────────────────────
    gmail_address = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")
    ontvangers = [a.strip() for a in os.getenv("MAIL_ONTVANGERS", gmail_address).split(",")]
    onderwerp  = f"Weekrapport dakdekkersgids.nl — {week_s} t/m {week_e}"
    _gmail_stuur(ontvangers, onderwerp, html)


# Mail AI rapport
@app.route("/api/mail-rapport-ai", methods=["POST"])
def mail_rapport_ai():
    try:
        body = request.json or {}
        tekst = body.get("tekst", "").strip()
        onderwerp = body.get("onderwerp", "Rapport dakdekkersgids.nl")
        if not tekst:
            return jsonify({"ok": False, "error": "Geen tekst opgegeven"}), 400

        gmail_address = os.getenv("GMAIL_ADDRESS", "russchenbertjan@gmail.com")
        ontvangers_ai = [a.strip() for a in os.getenv("MAIL_ONTVANGERS", gmail_address).split(",")]

        alineas = "".join(
            f"<p style='margin:0 0 10px;color:#333;font-size:14px;line-height:1.7'>{r}</p>"
            for r in tekst.replace("\r\n", "\n").split("\n") if r.strip()
        )
        html = f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',sans-serif;background:#f4f4f4;margin:0;padding:24px">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
  <div style="background:#111;padding:24px 28px">
    <div style="font-size:18px;font-weight:700;color:#fff">dakdekkersgids.nl</div>
    <div style="font-size:12px;color:#888;margin-top:4px">Rapportage Agent</div>
  </div>
  <div style="padding:28px">{alineas}</div>
  <div style="padding:16px 28px;background:#f9f9f9;border-top:1px solid #eee;font-size:11px;color:#aaa">
    Gegenereerd door Rapportage Agent — LeadGen Group
  </div>
</div></body></html>"""

        _gmail_stuur(ontvangers_ai, onderwerp, html)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Handmatige alertcheck (voor testen)
@app.route("/api/test-alert", methods=["POST"])
def test_alert():
    try:
        anomalieën = _detect_anomalies()
        if anomalieën:
            _stuur_alert_mail(anomalieën)
            return jsonify({"ok": True, "signalen": len(anomalieën), "details": [a["tekst"] for a in anomalieën]})
        return jsonify({"ok": True, "signalen": 0, "bericht": "Geen afwijkingen gedetecteerd — snapshot en huidige data komen overeen."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/snapshot", methods=["POST"])
def snapshot():
    try:
        _sla_snapshot_op()
        return jsonify({"ok": True, "bericht": "Snapshot opgeslagen van huidige GSC data."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Concurrenten scan
@app.route("/api/fetch-competitors", methods=["POST"])
def fetch_competitors_endpoint():
    try:
        import importlib
        from fetchers import competitors
        importlib.reload(competitors)
        result = competitors.main()
        return jsonify({"ok": True, "dreigingen": len(result.get("dreigingen", [])), "concurrenten": len(result.get("concurrenten", []))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/competitor-data")
def competitor_data():
    return jsonify(load_json("competitor_data.json") or {})


# Clarity data
@app.route("/api/clarity")
def clarity():
    return jsonify(load_json("clarity_data.json"))


# Trends data
@app.route("/api/trends")
def trends():
    return jsonify(load_json("trends_data.json"))


# Leads historiek (voor cluster trend chart)
@app.route("/api/leads-history")
def leads_history():
    return jsonify(load_json("leads_history.json") or [])


# Lijst van alle pagina's (sitemap als basis)
@app.route("/api/paginas")
def paginas():
    sitemap = load_json("sitemap_urls.json")
    return jsonify(sitemap.get("urls", []))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Dashboard draait op http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
