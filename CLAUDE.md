# automation — dakdekkersgids.nl

Flask dashboard + data-fetchers voor SEO/GA4 analytics.

## Structuur
- `server.py` — Flask API + mail scheduler (poort 5000)
- `dashboard.html` — frontend
- `rules.py` — GA4 filterlogica + clusterconfiguratie
- `fetch_gsc.py`, `fetch_ga4.py`, `fetch_sitemap.py`, `fetch_trends.py` — data ophalen
- `leads_week.py` — leadattributie per cluster
- `data/` — JSON output van alle fetchers

## Starten
```
python server.py
```
Dashboard: http://localhost:5000
