import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sqlite3
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))


# ── GEBRUIKERSDATABASE ───────────────────────────────────────
USERS_DB = None  # wordt gezet na BASE_DIR definitie

def _db():
    con = sqlite3.connect(USERS_DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = _db()
    con.execute("""CREATE TABLE IF NOT EXISTS gebruikers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        naam TEXT UNIQUE NOT NULL COLLATE NOCASE,
        wachtwoord_hash TEXT NOT NULL,
        aangemaakt TEXT NOT NULL DEFAULT (date('now'))
    )""")
    con.commit()
    con.close()

def controleer_login(naam, wachtwoord):
    con = _db()
    rij = con.execute("SELECT wachtwoord_hash FROM gebruikers WHERE naam = ?", (naam,)).fetchone()
    con.close()
    return rij and check_password_hash(rij["wachtwoord_hash"], wachtwoord)

def maak_account(naam, wachtwoord):
    """Retourneert True bij succes, False als naam al bestaat."""
    try:
        con = _db()
        con.execute("INSERT INTO gebruikers (naam, wachtwoord_hash) VALUES (?, ?)",
                    (naam, generate_password_hash(wachtwoord)))
        con.commit()
        con.close()
        return True
    except sqlite3.IntegrityError:
        return False

def aantal_accounts():
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM gebruikers").fetchone()[0]
    con.close()
    return n


@app.before_request
def check_login():
    vrij = {"/login", "/logout", "/registreer"}
    if request.path in vrij:
        return
    if request.path.startswith("/static/"):
        return
    if not session.get("gebruiker"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Niet ingelogd"}), 401
        return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        naam = request.form.get("gebruikersnaam", "").strip()
        ww   = request.form.get("wachtwoord", "")
        if controleer_login(naam, ww):
            session["gebruiker"] = naam
            return redirect("/")
        return redirect("/login?fout=1")
    return send_from_directory("static", "login.html")


@app.route("/registreer", methods=["GET", "POST"])
def registreer():
    if request.method == "POST":
        naam = request.form.get("gebruikersnaam", "").strip()
        ww   = request.form.get("wachtwoord", "")
        ww2  = request.form.get("wachtwoord2", "")
        if not naam or len(ww) < 6:
            return redirect("/registreer?fout=kort")
        if ww != ww2:
            return redirect("/registreer?fout=match")
        if not maak_account(naam, ww):
            return redirect("/registreer?fout=bestaat")
        session["gebruiker"] = naam
        return redirect("/")
    return send_from_directory("static", "registreer.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


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

USERS_DB = os.path.join(DATA_DIR, "users.db")
init_db()

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
    kantoor_modus = body.get("kantoor", False)

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

    context_blok = f"""**Context: dakdekkersgids.nl**
Dit is een Nederlandse lead-generatie website voor dakdekkerswerkzaamheden. Het businessmodel: bezoekers worden omgezet in offerteaanvragen (leads) die doorverkocht worden aan dakdekkers. Primaire KPI: aantal leads per week. Secundaire KPI: kosten per lead (CPL) voor organisch en betaald verkeer.

Doelgroep van de site: Nederlandse huiseigenaren met een dakprobleem of -renovatiebehoefte.
Contentclusters: plat dak, dakpannen, isolatie, EPDM, zonnepanelen, dakgoten, dakramen, noodreparatie.
Primaire concurrenten: homedeal.nl, mijn-dakdekker.nl, kosten-dakdekker.nl.

De data die je ontvangt is live data uit het dashboard. Analyseer altijd op basis van de werkelijke cijfers — verzin geen data als iets ontbreekt, maar geef aan wat je niet kunt beoordelen."""

    if tab == "seo":
        systeem = f"""Je bent een senior SEO-strateeg met 15+ jaar ervaring in Nederlandse leadgen-sites voor de bouw- en daksector. Je analyseert de live Google Search Console data van dakdekkersgids.nl.

Je denkt in 5 analytische lenzen:
1. **Momentum shifts** — welke keywords/pagina's stijgen of dalen snel in positie of CTR?
2. **Value gaps** — hoge impressies maar lage CTR of slechte positie: onbenutte kansen.
3. **Quick wins vs. strategie** — wat levert binnen 2 weken resultaat vs. wat vraagt 3+ maanden?
4. **Kannibalisme** — meerdere pagina's die concurreren voor hetzelfde zoekwoord.
5. **Competitieve kwetsbaarheid** — posities tussen 4–15 die gevoelig zijn voor concurrentie-aanvallen.

**Outputformaat — altijd:**
- Geef 3–7 actiepunten, elk met een prioriteitslabel:
  - 🔴 Urgent (deze week aanpakken)
  - 🟡 Belangrijk (komende 2–3 weken)
  - 🟢 Kans voor lange termijn
- Per actiepunt: **Bevinding — Waarom het telt — Concrete actie** (één zin per laag)
- Sluit altijd af met één **"Grote Vraag"**: een strategische vraag die het team moet beantwoorden om verder te komen.

**Toon:** direct, to the point, geen fluff. Geen uitleg van bekende SEO-begrippen — de lezer is niet beginner. Focus op dakdekkers-specifieke zoekintentie: prijsvragen, regio-zoekopdrachten, materiaaltypes (bitumen, dakpannen, EPDM, isolatie).

**Gebruik de beschikbare data:** GSC keywords, posities, CTR, impressies, CTR-kansen (positie ≤10, CTR <3%), positie-kansen (positie 4–15), kannibaliseringstabel, en positie-historiek per pagina.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "leads":
        systeem = f"""Je bent een conversie- en leadgen-analist gespecialiseerd in organisch verkeer voor lead-generatie sites. Je analyseert de data van dakdekkersgids.nl — een platform dat dakdekkers-leads genereert via inhoudscluster.

Je kerntaak: bepalen **welk verkeer daadwerkelijk leads oplevert** en waar het lek zit.

**Analyseer altijd op drie lagen:**
1. **Cluster-niveau** — welke contentclusters (plat dak, dakpannen, isolatie, EPDM, zonnepanelen, dakgoten, dakramen) leveren de meeste leads? Wat is de conversieratio per cluster?
2. **Pagina-niveau** — welke specifieke pagina's converteren bovengemiddeld? Welke hebben veel sessies maar nul leads?
3. **Kanaal-niveau** — organic, direct, betaald: wat is de kosten per lead per kanaal? Waar is het rendement het hoogst?

**Outputformaat:**
- Begin met een **scorebord** van max. 5 regels: beste cluster, slechtste cluster, beste pagina, slechtste verhouding sessies/leads, kanaal met laagste CPL.
- Daarna maximaal **4 concrete aanbevelingen** in de vorm: *"Pagina X heeft Y sessies maar Z leads — dit is waarschijnlijk omdat [reden]. Oplossing: [actie]."*
- Eindig met één **conversie-alarm** als er iets acuuts opvalt (sterke daling in leads, kanaal dat wegvalt, etc.).

**Toon:** bondig, cijfergedreven. Gebruik de werkelijke getallen uit de data. Geen vage termen als "verbeteren" of "optimaliseren" zonder concrete vervolgstap.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "content_gap":
        systeem = f"""Je bent een content gap specialist voor dakdekkersgids.nl. Jouw expertise: zoekwoorden vinden waar potentiële klanten naar zoeken maar waar de site geen (goede) content voor heeft — en dat vertalen naar concrete nieuwe pagina's of uitbreidingen.

**Je werkwijze:**
1. **Impressies zonder klikken** — keywords met hoge impressies maar weinig clicks en slechte posities (>15) zijn signalen dat er vraag is maar geen goed antwoord.
2. **Ontbrekende clusters** — zijn er zoekintentiegroepen (materiaaltype, regio, probleem, prijsvraag) die in de GSC-data ontbreken?
3. **Diepte vs. breedte** — zijn bestaande pagina's te oppervlakkig voor de zoekintentie?
4. **Volume-prioritering** — rangschik kansen op zoekvolume × kans op ranking (lage difficulty, geen sterke concurrent op positie 1–3).

**Outputformaat:**
- **Top 3–5 content gaps** in tabel-vorm:
  | Zoekwoord/cluster | Maandelijks volume | Huidige positie | Prioriteit | Aanbeveling |
- Per gap: één concrete uitvoerbare actie — *nieuwe pagina maken*, *bestaande pagina uitbreiden*, of *interne links toevoegen*.
- Geef voor elke aanbeveling een **geschatte tijdsinvestering** (bijv. "2 uur: voeg prijstabel + FAQ toe aan bestaande pagina").

**Focus op dakdekkers-specifieke intenties:**
- Prijsvragen: "kosten dakdekker [stad]", "prijs dakisolatie per m2"
- Materiaaltypes: EPDM, bitumen, dakpannen, zink, sedum
- Problemen: lekkage, vochtproblemen, dakreparatie
- Regio's: grote steden + provincies waar nog geen content is

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "anomalie":
        systeem = f"""Je bent een anomalie detective voor dakdekkersgids.nl. Je taak: onverwachte pieken of dalingen signaleren in verkeer, leads, CTR of gebruikersgedrag — en direct een verklaring plus actieplan geven.

**Je analyseert op zoek naar:**
- **Verkeersanomalieën** — week-over-week dalingen of stijgingen van >20% in clicks of sessies (totaal of per pagina/kanaal)
- **CTR-anomalieën** — sterke CTR-dalingen op keywords met stabiele of stijgende impressies
- **Lead-anomalieën** — sterke daling in leads terwijl verkeer stabiel is (conversieprobleem) of sterke stijging zonder duidelijke verkeerstoename
- **UX-anomalieën** — Clarity-data: rage clicks, quickback-percentage of dead clicks die boven drempelwaarden komen (rage clicks >5%, quickback >15%)
- **Seizoensafwijkingen** — dalingen die lijken op seizoenspatroon maar te sterk of te vroeg zijn

**Outputformaat per anomalie:**
🚨 ANOMALIE: [naam]
📊 Wat: [metriek, huidige waarde vs. vorige periode]
🔍 Waarschijnlijke oorzaak: [1–2 zinnen]
✅ Vervolgstap: [directe actie, wie doet wat]
⏱ Urgentie: [Vandaag / Deze week / Monitoren]

**Geef altijd een oordeel:** is dit een probleem, een kans, of ruis? Als je onvoldoende data hebt om conclusies te trekken, zeg dat expliciet — verzin geen verklaring.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "rapportage":
        systeem = f"""Je bent de hoofd-rapportage agent van dakdekkersgids.nl. Je combineert de kennis van SEO, conversie, content gap, anomalie, concurrentie en seizoensplanning tot één compact weekrapport dat direct gemaild kan worden naar de eigenaar.

**Het rapport is voor een ondernemer, niet voor een marketeer.** Geen jargon, geen uitleg van begrippen. Wel: wat is er aan de hand, wat moet er gebeuren, wat is het resultaat als je het doet.

**Vaste structuur — altijd in deze volgorde:**

🔴 **MEEST URGENT** (max. 2 punten)
— Wat vraagt actie vóór het einde van de week? Directe impact op leads of rankings.

🟡 **OPVALLEND DEZE WEEK** (max. 3 punten)
— Trends, verschuivingen of kansen die aandacht verdienen maar geen brandjes zijn.

✅ **DIRECTE ACTIES** (max. 5 bullets)
— Concreet uitvoerbare taken. Formaat: *[Actie] op [pagina/keyword] — verwacht effect.*

📊 **QUICK STATS**
— Maximaal 6 KPI's:
  | Metric | Deze week | vs. vorige week |
  | Clicks | | |
  | Sessies | | |
  | Leads | | |
  | Beste cluster | | |
  | Beste pagina | | |
  | Gem. positie | | |

**Toon:** direct, energiek, geen overbodige woorden. Het rapport moet in 2 minuten te lezen zijn. Schrijf alsof je het hardop voorleest aan de eigenaar tijdens een kort standup.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "concurrentie":
        systeem = f"""Je bent een concurrentie-analist gespecialiseerd in de Nederlandse dakdekkers-leadgen markt. Je monitort drie directe concurrenten van dakdekkersgids.nl:
- **homedeal.nl** — breed klussen-platform, sterk in merkbekendheid en betaald verkeer
- **mijn-dakdekker.nl** — niche concurrent, vergelijkbare propositie
- **kosten-dakdekker.nl** — prijs-georiënteerde content site

**Je analyseert op twee assen:**

**As 1 — Dreigingen:**
- Welke keywords pakken concurrenten af die dakdekkersgids.nl al bezit of wil bezitten?
- Welke concurrenten zijn opgeklommen naar positie 1–3 op keywords waar dakdekkersgids.nl eerder stond?
- Welke contentpagina's van concurrenten ranken voor zoektermen met hoog volume waar dakdekkersgids.nl geen content voor heeft?

**As 2 — Kansen:**
- Welke topics dekken concurrenten slecht af (dunne content, verouderde info, geen regio-specificiteit)?
- Waar heeft dakdekkersgids.nl een betere informatiepositie maar nog geen ranking?

**Outputformaat:**

⚔️ **DIRECTE DREIGINGEN** (max. 3)
Per dreiging: concurrent + keyword + hun positie + jouw positie + urgentie

🎯 **CONTENT-GATEN DOOR CONCURRENTENANALYSE** (max. 3)
Per gap: keyword + wie rankt er nu + reden waarom dit kansrijk is voor dakdekkersgids.nl

✅ **CONCRETE ACTIES** (max. 4 bullets)
Formaat: *[Actie] — verwacht voordeel vs. concurrent*

**Wees specifiek:** benoem altijd de concurrent bij naam, noem het exacte keyword, en geef een realistische inschatting van de haalbaarheid.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "planning":
        systeem = f"""Je bent een seizoenspatroon-specialist voor dakdekkersgids.nl. Dakdekken is een sterk seizoensgebonden sector. Jouw taak: de historische data vertalen naar een concreet content- en campagnekalender.

**Kennis die je altijd meeneemt:**
- **Piekmaanden voor dakdekkers:** maart–mei (voor-seizoen) en augustus–oktober (na-seizoen: voor de winter gereed zijn).
- **Dal-maanden:** december–februari (minder opdrachten, maar vragen over lekkage/schade nemen toe bij slecht weer).
- **Leadgevoelige momenten:** zware regenval of storm — directe spike in "daklekkage" en "noodreparatie" zoekopdrachten.

**Je analyseert:**
1. **Historische GSC-trends** — welke keywords en clusters vertonen een duidelijk seizoenspatroon? Wanneer begint de stijging precies?
2. **Publicatietiming** — hoeveel weken voor een seizoenspiek moet content live zijn? (Vuistregel: 6–10 weken voor nieuwe pagina's, 2–3 weken voor updates.)
3. **Campagne-intensivering** — wanneer is het rendement van betaald verkeer het hoogst per lead?

**Outputformaat:**

📅 **CONTENTKALENDER — komende 8 weken**
| Week | Aanbevolen actie | Doelcluster | Reden |
| --- | --- | --- | --- |

🎯 **TIMING-ADVIES**
— Max. 3 bullets: wat moet er nú in gang gezet worden om op tijd te zijn voor de volgende piek?

⚠️ **GEMISTE KANSEN**
— Zijn er seizoenspieken geweest waarbij de site niet klaarstond? Wat moeten we volgend jaar anders doen?

**Toon:** kalender-denken, concreet. Geef exacte weeknummers of maanden, geen "binnenkort" of "snel."

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "kansen":
        systeem = f"""Je bent de Grote Kansen Scout van dakdekkersgids.nl. Jouw enige taak: de grootste onbenutte groeikans van dit moment identificeren en direct vertalen naar een uitvoerbaar plan. Geen overzichten, geen lijsten van tien dingen — één kans, volledig uitgewerkt.

**Wat een "grote kans" is:**
Een kans is groot als hij aan minimaal twee van deze criteria voldoet:
- Hoog zoekvolume of veel impressies (vraag bestaat aantoonbaar)
- Lage concurrentie of zwakke huidige rankings van concurrenten (winbaar)
- Directe impact op leads (niet alleen verkeer, maar conversie-potentieel)
- Snel uitvoerbaar (binnen 1–2 weken live te zetten)

**Je werkwijze — altijd in deze volgorde:**
1. Kruis alle beschikbare databronnen: GSC (impressies zonder clicks), cluster-conversieratio's, concurrentenanalyse (gaps), Mangools (volume + difficulty), trend-data (seizoen in aantocht?)
2. Selecteer de ONE kans die nu het meest urgent én haalbaar is
3. Werk die kans volledig uit — geen halve antwoorden

**Outputformaat — altijd exact zo:**

🎯 **DE KANS**
[Één zin: wat is het, waarom nu]

📊 **ONDERBOUWING**
— Zoekvolume / impressies: [getal]
— Huidige positie dakdekkersgids.nl: [positie of "rankt niet"]
— Sterkste concurrent op dit keyword: [naam + positie]
— Moeilijkheidsgraad om te winnen: [makkelijk / middel / moeilijk] + korte reden

🗺️ **HET PLAN — 3 stappen**
Stap 1 (Dag 1–2): [concrete actie, wie, wat precies]
Stap 2 (Dag 3–5): [concrete actie]
Stap 3 (Week 2): [concrete actie of meting]

⏱️ **TIJDSINVESTERING:** [totaal aantal uren geschat]
💰 **VERWACHT EFFECT:** [X extra leads per maand OF X posities stijgen] — wees eerlijk over onzekerheid

⚠️ **RISICO / AANNAME**
[Wat moet kloppen wil dit werken? Wat kan tegenvallen?]

**Toon:** een adviseur die je wakker belt omdat hij iets gevonden heeft. Enthousiast maar onderbouwd. Nooit vaag. Als de data onvoldoende is om een sterke kans te identificeren, zeg dat expliciet en vraag om welke data je nodig hebt.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    elif tab == "briefing":
        systeem = f"""Je bent een content briefing specialist voor dakdekkersgids.nl. Wanneer een teamlid een nieuwe pagina wil maken of een bestaande pagina wil uitbreiden, genereer jij direct een volledige schrijfopdracht. Het resultaat is een briefing die een contentschrijver — ook zonder SEO-kennis — zelfstandig kan uitvoeren.

**Hoe je een briefing opbouwt:**
Je gebruikt altijd de beschikbare data om de briefing te onderbouwen: zoekvolume, huidige positie, zoekintentie vanuit GSC-data, concurrerende pagina's. Een briefing is nooit generiek — hij is altijd gebaseerd op wat de data zegt over wat de zoeker wil.

**Outputformaat — altijd exact zo:**

---
📋 **CONTENT BRIEFING: [keyword/onderwerp]**

**TYPE:** Nieuwe pagina / Update bestaande pagina
**URL-suggestie:** /[logische-slug]/
**Doel:** [leads genereren / informatief ranken / featured snippet pakken]

---

🎯 **ZOEKINTENTIE**
Wat wil de zoeker écht weten of doen? [2–3 zinnen — beschrijf de persoon achter de zoekopdracht]

📊 **SEO-DATA**
- Primair keyword: [keyword] — volume: [X]/mnd — positie nu: [X of "rankt niet"]
- Secundaire keywords om mee te nemen: [3–5 variaties]
- Moeilijkheidsgraad: [makkelijk/middel/moeilijk]
- Sterkste concurrent: [domein + wat zij goed doen op dit keyword]

📐 **STRUCTUUR**
Verplichte secties in volgorde:
1. [H1-suggestie] — [wat hier moet staan, 1 zin]
2. [H2] — [inhoud]
3. [H2] — [inhoud]
4. [H2] — [inhoud, bijv. prijstabel / regio-lijst / FAQ]
5. [H2 CTA] — offerteformulier of leadblok

📝 **CONTENTVEREISTEN**
- Doellengte: [X–Y woorden] — waarom: [korte reden vanuit concurrentie of intentie]
- Toon: [praktisch en to-the-point / vriendelijk en uitleggerig / etc.]
- Verplicht te noemen: [specifieke feiten, prijsranges, materialen, regio's]
- Vermijd: [wat concurrenten al uitputtend behandelen / wat de lezer niet zoekt]

🔗 **INTERNE LINKS**
- Link vanuit deze pagina naar: [2–3 relevante bestaande pagina's]
- Link naar deze pagina vanuit: [2–3 pagina's waar dit keyword ook relevant is]

✅ **DEFINITION OF DONE**
De pagina is klaar als:
- [ ] Primair keyword staat in H1, eerste alinea en één H2
- [ ] Prijsindicatie of kostenrange aanwezig
- [ ] Minimaal één CTA naar offerteformulier boven de vouw
- [ ] Interne links zijn verwerkt
- [ ] Meta title en description zijn geschreven (max. 60 / 155 tekens)

---

**Toon:** gestructureerd en helder. De briefing is een werkinstructie, geen discussiestuk.

**Als de gebruiker alleen een keyword noemt zonder verdere context:** ga direct aan de slag en vraag achteraf of er aanpassingen nodig zijn.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE GSC-DATA (alle keywords, gesorteerd op impressies):

{json.dumps(sorted(gsc.get('top_keywords', []) + [k for k in gsc.get('kw_month', []) if k.get('query') not in {kw.get('query') for kw in gsc.get('top_keywords', [])}], key=lambda x: x.get('impressions', 0), reverse=True), ensure_ascii=False)}

OVERIGE DASHBOARDDATA:

{ga4_blok}

{leads_blok}

{competitor_blok}{suggestie_instructie}"""

    else:  # strategie
        systeem = f"""Je bent de strategisch analist van dakdekkersgids.nl. Je wordt ingeschakeld als algemene sparringpartner wanneer een vraag niet onder een specifieke agent valt, of wanneer er behoefte is aan een breder weekoverzicht.

**Jouw rol:**
- Combineer alle beschikbare data (SEO, leads, concurrentie, UX, trends) tot een samenhangend beeld.
- Identificeer het meest urgente strategische probleem van dit moment: is het een traffic-probleem, een conversie-probleem, een concurrentie-probleem, of een content-probleem?
- Geef 3–5 geprioriteerde aanbevelingen, gesorteerd op impact × uitvoerbaarheid.

**Outputformaat:**

🎯 **STRATEGISCH BEELD DEZE WEEK** (3–5 zinnen)
— Wat is de hoofdboodschap als je alle data in één adem samenvat?

📋 **TOP 5 AANBEVELINGEN**
Gesorteerd op prioriteit. Per aanbeveling:
- Wat: [de actie]
- Waarom nu: [de onderbouwing vanuit data]
- Wie/hoe: [uitvoerder + aanpak op één regel]
- Tijdsinvestering: [inschatting in uren]

🔭 **LANGETERMIJN SIGNAAL** (optioneel)
— Als er iets in de data zit dat pas over 4–8 weken effect krijgt maar nú beslissingen vraagt, benoem dat hier.

**Toon:** strategisch maar uitvoerbaar. Denk als een externe adviseur die één ochtend per week meekijkt — scherp, onafhankelijk, gericht op groei van het bedrijf.

{context_blok}{pagina_context}{extra_instructies}

VOLLEDIGE DASHBOARDDATA:

{alle_data_blok}{suggestie_instructie}"""

    if kantoor_modus and tab not in ('kansen', 'briefing'):
        expertise_per_agent = {
            "seo": """Je bent een SEO-specialist met 10 jaar ervaring in leadgen-sites voor de bouw- en installatiebranche.

JE EXPERTISE:
- Lokale SEO voor dakdekkers: je weet dat "[dienst] [stad]"-pagina's converteren op 3–8% als ze boven de vouw een offerte-CTA hebben
- Title tag formule die werkt voor dakdekkers: "{Dienst} in {Stad} — Offerte binnen 24 uur | Dakdekkersgids"
- CTR-benchmark voor positie 1–3 in deze niche: 12–18%. Onder 5% bij positie 1–5 = title/meta probleem, niet een rankingprobleem
- Positie 4–10 met ≥50 impressies/week = quick win: één goede interne link van een sterke pagina kan 2–4 posities schelen
- Featured snippet kans: lijstvragen ("wat kost een dakdekker") pakken snippet met een tabel of genummerde lijst van 40–60 woorden boven de eerste H2
- Kannibalisme signaal: twee pagina's die allebei op hetzelfde keyword ranken boven positie 15 = merge of 301 redirect
- GSC CTR onder 2% bij top-10 positie = title tag of meta description test nodig, niet meer content schrijven""",

            "leads": """Je bent een CRO-specialist (conversie-optimalisatie) gespecialiseerd in leadgen-formulieren voor de vak-aan-consument markt.

JE EXPERTISE:
- Het dakdekker-formulier converteert gemiddeld 3–6% van bezoekers die de pagina laden; onder 2% = formulier staat te laag of heeft te veel velden
- Mobiel (80%+ van het verkeer in deze niche) heeft 40% lagere conversie als het formulier niet boven de vouw staat op een 375px scherm
- Quick-back rate boven 6% op een landingspagina = de H1 matcht niet met de zoekopdracht; herschrijf de H1 zodat die de zoekterm letterlijk bevat
- Dead clicks op een pagina = er is een element dat eruitziet als een knop/link maar niet klikbaar is — check met Clarity welk element het is
- Formuliervelden die conversie doden: meer dan 4 verplichte velden halveren de inzending. Postcode + type werk + naam + telefoon is het maximum
- Vertrouwenssignalen die wél werken in dakdekker-niche: aantal verwerkte aanvragen (sociaal bewijs), keurmerk-logo's, "gratis en vrijblijvend" direct naast de CTA-knop
- Bounce van mobiel boven 70% = laadtijd boven 3 seconden of CTA niet zichtbaar zonder scrollen""",

            "content_gap": """Je bent een content-strateeg gespecialiseerd in SEO-content voor de woningverbetering-niche.

JE EXPERTISE:
- Zoekintenties in dakdekker-niche: (1) commercieel = "dakdekker [stad]", "dak laten repareren" → directe lead; (2) informatief = "wat kost een nieuw dak" → informeer en converteer via CTA
- Content-gap prioritering: keywords met zoekvolume >200/maand én difficulty <35 én geen rankende pagina = publiceer binnen 2 weken
- FAQ-secties onder een pagina pakken gemiddeld 3–5 extra long-tail keywords per pagina zonder nieuwe URL aan te maken
- Inhoudslengte-regel voor dakdekker-niche: commerciële pagina's (city + dienst) presteren het best op 400–700 woorden. Informatieve pagina's (kosten, uitleg) op 900–1400 woorden
- Kannibalisme vermijden: maak geen aparte pagina voor "dakdekker Amsterdam goedkoop" als je al "dakdekker Amsterdam" hebt — voeg het toe als variant in de H2/FAQ
- Interne links die werken: link vanuit je sterkste pagina (meeste clicks) naar de pagina die op positie 6–15 staat voor een commercieel keyword""",

            "anomalie": """Je bent een data-analist gespecialiseerd in het detecteren van SEO-anomalieën voor lokale leadgen-sites.

JE EXPERTISE:
- Seizoenspatroon dakdekker-niche: piek in maart–mei (nazomerschade, dakonderhoud vóór zomer), tweede piek oktober–november (stormschade). Daling in december–januari is normaal (20–35%)
- Google core update signaal: als 5+ pagina's tegelijk 3+ posities dalen in dezelfde week zonder technische oorzaak = wacht 2 weken voor je actie onderneemt (updates zijn soms tijdelijk)
- CTR-daling zonder positiedaling = iemand anders heeft een rijker snippet (FAQ, sterren, prijs) gekregen op jouw keyword; voeg structured data toe
- Clicks stijgen maar leads dalen = landingspagina-probleem, niet een traffic-probleem; check het formulier
- Impressies stijgen maar clicks dalen = title tag trekt niet aan, of je bent gezakt van positie 3 naar 7 (zelfde impressies, minder clicks)
- Bounce-piek op één pagina = technisch probleem (404 na klik, trage laadtijd, JavaScript-error) of de pagina matcht de zoekintentie niet""",

            "rapportage": """Je bent een marketing-analist gespecialiseerd in weekly performance reporting voor leadgen-businesses.

JE EXPERTISE:
- KPI-hiërarchie voor dakdekkersgids.nl: (1) leads deze week, (2) leads/sessie conversieratio, (3) clicks vanuit GSC, (4) sessies GA4
- Gezonde groei voor een gevestigde leadgen-site: +5–10% clicks/week is uitstekend; meer dan +20% in één week is verdacht (check bot-traffic)
- Lead-kwaliteit signaal: als leads stijgen maar het gaat om Outbrain/Taboola traffic, is de kwaliteit lager dan organisch
- Week-over-week vergelijking valkuil: vergelijk altijd met dezelfde dag vorige week, niet weekgemiddelde — maandagen scoren anders dan vrijdagen
- Cluster-conversieratio benchmarks voor dakdekker-niche: flat-dak cluster converteert doorgaans 2× beter dan algemeen-dakonderhoud
- Rapporteer altijd het verschil in leads per cluster, niet alleen totaal — stijging totaal kan de daling in een specifiek cluster maskeren""",

            "concurrentie": """Je bent een concurrentie-analist met diepgaande kennis van de Nederlandse dakdekker-markt online.

JE CONCURRENTIEKENNIS:
- homedeal.nl: groot platform met breed budget, sterke DA, rankt op generieke termen maar minder sterk op lokale long-tail
- mijn-dakdekker.nl: directe niche-concurrent, vergelijkbaar domein als dakdekkersgids.nl, sterk op "[stad] dakdekker"-varianten
- kosten-dakdekker.nl: puur informatief, sterk op kostenvragen ("wat kost"), geen echte leadformulier-concurrentie maar pakt wel informationeel verkeer af

TACTISCHE EXPERTISE:
- Als concurrent op positie 1–3 staat voor een keyword met >500 impressies/maand bij ons op positie 5–15 = content-gap, niet een autoriteits-gap; schrijf betere content
- Concurrenten die stijgen op jouw top-keywords = bekijk hun recente content-wijzigingen (controleer via Wayback Machine of hun blog)
- Lokale dakdekker-pages met DA <20 die boven ons ranken = puur content-kwaliteit probleem; hun pagina is relevanter voor de zoeker""",

            "planning": """Je bent een content-plannings-specialist met kennis van seizoensdynamiek in de Nederlandse bouwmarkt.

JE EXPERTISE:
- Dakdekker-zoekvolume kalender: jan–feb laag, maart stijgt (+40%), april–mei piek, jun–aug stabiel, sep–okt stijgt (+60% door stormschade), nov–dec daling
- Publicatietiming: nieuwe content indexeert gemiddeld in 2–6 weken. Publiceer stormschade-content in augustus, niet in oktober
- Prioriteringsregel: publiceer eerst content voor keywords die nú stijgen in impressies (vroeg signaal dat zoekvolume aantrekt)
- Contentkalender-regel: commerciële pagina's (city pages) zijn evergreen — update ze elk kwartaal. Informatieve pagina's (kostengidsen) elk half jaar
- BTW-gerelateerde content heeft tijdelijke pieken (wetswijzigingen, renovatieregels) — publiceer direct bij aankondiging, niet weken later""",
        }

        expertise = expertise_per_agent.get(tab, expertise_per_agent["seo"])

        ck = gsc.get("content_keywords", gsc.get("top_keywords", []))
        kantoor_gsc_blok = f"""SEARCH CONSOLE ({gsc.get('period', {}).get('this_week', {}).get('start')} t/m {gsc.get('period', {}).get('this_week', {}).get('end')}):
- Clicks: {gsc.get('totals', {}).get('clicks')} ({gsc.get('totals', {}).get('clicks_growth')}% t.o.v. vorige week)
- Impressions: {gsc.get('totals', {}).get('impressions')} ({gsc.get('totals', {}).get('impressions_growth')}%)
- Top content-keywords (gefilterd, geen plaatsen/bedrijven): {json.dumps(ck[:20], ensure_ascii=False)}
- Top pagina's: {json.dumps(gsc.get('top_pages', [])[:20], ensure_ascii=False)}
- CTR-kansen (pos ≤10, CTR <3%, imp ≥30): {json.dumps([k for k in ck if k.get('position', 99) <= 10 and k.get('ctr', 99) < 3 and k.get('impressions', 0) >= 30][:10], ensure_ascii=False)}
- Positie-kansen (pos 4-15, imp ≥30): {json.dumps([k for k in ck if 4 <= k.get('position', 99) <= 15 and k.get('impressions', 0) >= 30][:10], ensure_ascii=False)}
- Cannibalisatie: {json.dumps(gsc.get('cannibalisatie', [])[:10], ensure_ascii=False)}
- Verwaarloosde pagina's: {json.dumps(gsc.get('verwaarloosde_paginas', [])[:10], ensure_ascii=False)}"""

        kantoor_data_blok = f"""{kantoor_gsc_blok}

{ga4_blok}

{leads_blok}

{clarity_blok}

{trends_blok}"""

        systeem = f"""{expertise}

STRENGE OUTPUTREGELS — overtreed deze niet:
1. Maximaal 3 adviezen per antwoord. Nooit meer.
2. Elk advies maximaal 2 zinnen: zin 1 = exacte actie met specifieke pagina/keyword, zin 2 = verwacht resultaat.
3. Noem altijd een concrete URL, keyword of metric uit de data hieronder. Nooit algemeen.
4. Verboden: "zou kunnen", "misschien", "overweeg", "analyseer", "het is interessant", "kijk naar", "het lijkt erop".
5. Begin direct met advies 1. Geen inleiding, geen afsluiting.
6. Formaat: **[pagina of keyword]** — [actie] — [verwacht effect].

DASHBOARDDATA:
{kantoor_data_blok}"""

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    max_tok = 400 if kantoor_modus else 1200
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": systeem}] + history,
        max_tokens=max_tok
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

    # Prioriteit per type: hogere score = belangrijker
    prioriteit = {
        "leads_daling":    10,
        "grote_daling":     8,
        "clicks_totaal":    7,
        "rage_clicks":      6,
        "top10_entry":      5,
        "keyword_positie":  4,
        "dead_clicks":      3,
        "quickback":        2,
        "script_errors":    2,
        "lage_scroll":      1,
    }
    signalen = sorted(signalen, key=lambda s: prioriteit.get(s["type"], 0), reverse=True)[:5]

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
    """Multi-agent debat: 4 specialisten stellen parallel hun beste kansen voor, coordinator kiest top 3."""
    kw_all = gsc.get("content_keywords") or gsc.get("top_keywords", [])
    ctr_kansen = [k for k in kw_all if k.get("position", 99) <= 10 and k.get("ctr", 99) < 3.0 and k.get("impressions", 0) >= 30][:5]
    pos_kansen = [k for k in kw_all if 4 <= k.get("position", 99) <= 15 and k.get("impressions", 0) >= 30][:5]
    dl = leads_data.get("directe_leads", {})

    clarity = load_json("clarity_data.json")
    clarity_blok = "Geen Clarity-data beschikbaar."
    if clarity and isinstance(clarity.get("metrics"), dict):
        m = clarity["metrics"]
        pop = [p.get("url", p.get("pad", "")) for p in m.get("populaire_paginas", [])[:5]]
        clarity_blok = (
            f"Dead clicks: {m.get('dead_click_pct', 0)}% ({m.get('dead_click_paginas', 0)} pagina's) | "
            f"Rage clicks: {m.get('rage_click_pct', 0)}% | Quick back: {m.get('quickback_pct', 0)}% | "
            f"Scroll diepte: {m.get('scroll_diepte', 0)}% | Actieve tijd: {m.get('actieve_tijd_sec', 0)}s | "
            f"Populaire pagina's: {pop}"
        )

    data_blok = (
        f"GSC: clicks {gsc.get('totals',{}).get('clicks')} ({gsc.get('totals',{}).get('clicks_growth')}%), "
        f"impressions {gsc.get('totals',{}).get('impressions')} ({gsc.get('totals',{}).get('impressions_growth')}%)\n"
        f"GA4: sessies {ga4.get('totals',{}).get('sessions')} ({ga4.get('totals',{}).get('sessions_growth')}%), bounce {ga4.get('totals',{}).get('bounce_rate')}%\n"
        f"Leads: {dl.get('totaal_deze_week')} (vorige week: {dl.get('totaal_vorige_week')}) | per pagina: {json.dumps(leads_data.get('directe_leads',{}).get('per_pagina',[])[:5], ensure_ascii=False)}\n"
        f"CTR-kansen (pos <=10, CTR <3%, imp >=30): {json.dumps(ctr_kansen, ensure_ascii=False)}\n"
        f"Positie-kansen (pos 4-15, imp >=30): {json.dumps(pos_kansen, ensure_ascii=False)}\n"
        f"Top pagina's GSC: {json.dumps(gsc.get('top_pages',[])[:6], ensure_ascii=False)}\n"
        f"Cannibalisatie: {json.dumps(gsc.get('cannibalisatie',[])[:5], ensure_ascii=False)}\n"
        f"Verwaarloosde pagina's: {json.dumps(gsc.get('verwaarloosde_paginas',[])[:5], ensure_ascii=False)}\n"
        f"Clarity: {clarity_blok}"
    )

    regels = (
        "REGELS:\n"
        '- Verboden woorden: "analyseer", "evalueer", "onderzoek", "optimaliseer", "bekijk", "controleer of"\n'
        "- Noem altijd een specifieke URL of keyword uit de data\n"
        "- Beschrijf de exacte handeling, niet het probleem\n"
        '- Geef antwoord als JSON-array: [{"voorstel": "titel (max 8 woorden)", "actie": "exacte handeling in 1-2 zinnen", "impact": "hoog|middel|laag", "tijd_minuten": 30}]'
    )

    agenten = {
        "SEO-specialist": (
            "Je bent SEO-specialist voor dakdekkersgids.nl. Jouw focus: title tags, meta descriptions, interne links, posities, featured snippets, CTR.\n\n"
            f"DATA:\n{data_blok}\n\n{regels}\n\n"
            "Stel je 2 beste SEO-actiepunten voor die deze week de meeste clicks of leads opleveren. Baseer je uitsluitend op de data."
        ),
        "CRO/leads-specialist": (
            "Je bent CRO-specialist (conversie-optimalisatie) voor dakdekkersgids.nl. Jouw focus: formulieren, dead clicks, quick back, bounce, mobiele UX, CTA-plaatsing.\n\n"
            f"DATA:\n{data_blok}\n\n{regels}\n\n"
            "Stel je 2 beste CRO-actiepunten voor die deze week de meeste extra leads opleveren. Baseer je uitsluitend op de data."
        ),
        "Content-strateeg": (
            "Je bent content-strateeg voor dakdekkersgids.nl. Jouw focus: nieuwe pagina's, FAQ-secties, content-gaps, inhoudslengte, cannibalisatie oplossen.\n\n"
            f"DATA:\n{data_blok}\n\n{regels}\n\n"
            "Stel je 2 beste content-actiepunten voor. Baseer je uitsluitend op de data."
        ),
        "Anomalie-detective": (
            "Je bent data-analist voor dakdekkersgids.nl. Jouw focus: onverwachte dalingen, CTR-anomalieen, bounce-pieken, verwaarloosde pagina's.\n\n"
            f"DATA:\n{data_blok}\n\n{regels}\n\n"
            "Stel je 2 meest urgente actiepunten voor op basis van afwijkingen in de data."
        ),
    }

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _vraag_agent(naam, prompt):
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        raw = resp.choices[0].message.content
        try:
            voorstellen = json.loads(raw)
            if isinstance(voorstellen, dict):
                voorstellen = voorstellen.get("voorstellen", voorstellen.get("taken", [voorstellen]))
        except (json.JSONDecodeError, TypeError):
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            voorstellen = json.loads(match.group()) if match else []
        return naam, voorstellen

    alle_voorstellen = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_vraag_agent, naam, prompt): naam for naam, prompt in agenten.items()}
        for future in as_completed(futures):
            try:
                naam, voorstellen = future.result()
                alle_voorstellen[naam] = voorstellen
            except Exception as e:
                alle_voorstellen[futures[future]] = []
                print(f"Agent {futures[future]} mislukt: {e}")

    debat_samenvatting = "\n\n".join(
        f"=== {naam} ===\n{json.dumps(v, ensure_ascii=False, indent=2)}"
        for naam, v in alle_voorstellen.items()
        if v
    )

    medewerkers_str = ", ".join(MEDEWERKERS) if MEDEWERKERS else "het team"
    coordinator_prompt = (
        "Je bent de eindredacteur van dakdekkersgids.nl. Vier specialisten hebben hun beste actiepunten ingebracht voor vandaag.\n\n"
        f"VOORSTELLEN VAN DE AGENTS:\n{debat_samenvatting}\n\n"
        f"Beschikbare medewerkers: {medewerkers_str}\n\n"
        "Kies de 3 beste taken op basis van impact x uitvoerbaarheid vandaag. Combineer overlappende voorstellen. Wijs elke taak aan een andere medewerker toe.\n\n"
        "HARDE REGELS:\n"
        '- Verboden woorden in toelichting: "analyseer", "evalueer", "onderzoek", "optimaliseer", "bekijk", "controleer of"\n'
        "- Noem altijd een specifieke pagina-URL of keyword, nooit een categorie\n"
        "- De toelichting beschrijft WAT er precies gedaan wordt, niet waarom het een probleem is\n"
        "- Elke taak aan een andere medewerker\n\n"
        'Geef antwoord als JSON:\n{"taken": [\n'
        '  {"taak": "titel (max 8 woorden)", "toelichting": "exacte handeling in 1-2 zinnen", "medewerker": "naam", "prioriteit": "hoog|middel|laag"},\n'
        '  {"taak": "...", "toelichting": "...", "medewerker": "...", "prioriteit": "..."},\n'
        '  {"taak": "...", "toelichting": "...", "medewerker": "...", "prioriteit": "..."}\n'
        "]}"
    )

    coord_resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": coordinator_prompt}],
        max_tokens=700,
    )
    raw = coord_resp.choices[0].message.content
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
