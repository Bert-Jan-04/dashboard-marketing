# automation — dakdekkersgids.nl

Flask dashboard + data-fetchers voor SEO/GA4 analytics en AI-agents.

## Structuur

```
automation/
├── server.py           # Flask API + mail scheduler (poort 5000)
├── rules.py            # GA4 filterlogica + clusterconfiguratie
├── Procfile            # Railway startcommando
├── requirements.txt
│
├── fetchers/           # Data ophalen van externe bronnen
│   ├── gsc.py          # Google Search Console
│   ├── ga4.py          # Google Analytics 4
│   ├── leads.py        # Leadattributie per cluster
│   ├── trends.py       # Historische trenddata (8 weken)
│   ├── clarity.py      # Microsoft Clarity gedragsdata
│   ├── competitors.py  # Concurrentenanalyse via sitemaps
│   └── sitemap.py      # Sitemap parser
│
├── static/
│   └── dashboard.html  # Frontend (enkelvoudige HTML-app)
│
├── data/               # Gegenereerde JSON-bestanden (niet in git)
│   └── .gitkeep
│
├── scripts/            # Eenmalige hulpscripts
│   └── setup_gmail_token.py  # Gmail OAuth token aanmaken
│
└── credentials/        # Google service account (niet in git)
    └── credentials.json
```

## Starten

```
python server.py
```

Dashboard: http://localhost:5000

## Omgevingsvariabelen

| Variabele | Omschrijving |
|-----------|--------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `GMAIL_ADDRESS` | Afzender e-mailadres |
| `GMAIL_TOKEN_JSON` | Gmail OAuth token (Railway) |
| `GOOGLE_CREDENTIALS_JSON` | Google service account (Railway) |
| `MAIL_ONTVANGERS` | Kommagescheiden e-mailadressen |
| `MEDEWERKERS` | `Naam=email,Naam2=email2` formaat |
| `MANGOOLS_API_KEY` | Mangools keyword API |
| `SECRET_KEY` | Flask sessie-sleutel (willekeurig bij ontbreken) |
| `DASHBOARD_GEBRUIKERS` | `naam:wachtwoord,naam2:ww2` — dashboard logins |

## Dagelijkse mails (7:00)

1. **Takenmail** — altijd, 3 AI-gegenereerde actiepunten per medewerker
2. **Signaleringsmail** — alleen bij detecties (positiedaling, top-10 entry, Clarity-alerts)

Handmatig testen: `POST /api/mail-taken` of `POST /api/mail-signalering`
