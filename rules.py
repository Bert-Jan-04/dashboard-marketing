"""
Centrale filterregels voor dakdekkersgids.nl analytics.

Importeer vanuit elk script:
    from rules import PROPERTY_ID, CLUSTERS, lead_filter, meta_lead_filter
    from rules import get_content_pages_from_gsc
"""

import json
import os
from urllib.parse import urlparse, quote
from google.analytics.data_v1beta.types import (
    FilterExpression, FilterExpressionList, Filter
)

# ── Configuratie ──────────────────────────────────────────────────────────────

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials", "credentials.json")
PROPERTY_ID      = "355158317"
SITE_URL         = "https://dakdekkersgids.nl/"
SITE_URL_ENCODED = "sc-domain:dakdekkersgids.nl"

CLUSTERS = ["/daklekkage/", "/dakreparatie/", "/keuzehulp/", "/dakpannen/"]

# ── Leadregels ────────────────────────────────────────────────────────────────
#
# Geldige directe lead (dakdekker_lead event):
#   - landingPage bevat NIET /bedankt          → geen directe bedankt-bezoeken
#   - landingPage is NIET (not set)            → geen ongetraceerd verkeer
#   - landingPage bevat NIET /form-test        → geen testformulieren
#   - landingPage bevat NIET /offerte-aanvragen → bezoeker moet eerst content zien
#   - kanaal is Organic Search of Direct
#   - landingPage staat in GSC content-whitelist (geen plaatsen/bedrijven)

LEAD_EVENT       = "dakdekker_lead"
META_LEAD_EVENT  = "dakdekker_leads_meta"

EXCLUDED_LANDING_CONTAINS = ["/bedankt", "/form-test", "/offerte-aanvragen"]
EXCLUDED_LANDING_EXACT    = ["(not set)"]
VALID_CHANNELS            = ["Organic Search", "Direct"]

# Uitgesloten paden ook als content page (ook al zouden ze uit GSC komen)
EXCLUDED_CONTENT_PAGES = {
    "/bedrijf-aanmelden/", "/claim-bedrijf/", "/contact/",
    "/redactie/", "/offerte-aanvragen/", "/bedankt-dakdekkers/",
    "/gratis-bedrijfsvermelding/",
}

# Fallback-prefixes als GSC niet beschikbaar is
_FALLBACK_PREFIXES = [
    "/dak", "/keuzehulp", "/draagkracht", "/btw-dakdekker",
    "/stormschade", "/groendak", "/verduurzaming", "/nokverhoging",
    "/loodslabben", "/zinkwerken", "/hemelwaterafvoer", "/schoorsteen",
    "/hoe-de-dakhelling", "/welke-dakbedekking", "/waarom-grind",
    "/stijgende-prijzen", "/veel-dakproblemen", "/prefab-dak",
    "/regenpijp-", "/asbest-", "/boeidelen-", "/onderdak",
    "/offertevergelijker", "/offertes", "/aanvragen-", "/prijsadvies",
    "/gratis-dakinspectie", "/gratis-offertes", "/kennisbank", "/gids", "/nieuws",
]


# ── Sitemap-gebaseerde stad/bedrijf filtering ─────────────────────────────────

def get_city_pages_from_sitemap():
    """Kept for backwards compatibility."""
    return set()


def is_content_page(path, city_pages=None):
    """
    True als het pad een content-pagina is.
    Gebruikt een whitelist van bekende content-prefixen (_FALLBACK_PREFIXES).
    Stads-, provincie- en bedrijfspagina's vallen hier automatisch buiten.
    """
    if not path.endswith("/"):
        path += "/"
    if path in EXCLUDED_CONTENT_PAGES:
        return False
    for prefix in _FALLBACK_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ── GSC content-pagina's ophalen ──────────────────────────────────────────────

def get_content_pages_from_gsc(session, days=90, min_impressions=5):
    """
    Haal alle pagina's op uit Google Search Console en filter automatisch
    stads- en bedrijfspagina's eruit.

    Detectie-logica:
      - Bedrijfspagina's: pad heeft 2+ segmenten  (/stad/bedrijf/)
      - Stadspagina's   : pad is ouder van een bedrijfspagina (/stad/)
      - Contentpagina's : alles wat overblijft (1 segment, geen ouder)

    Geeft een gesorteerde lijst van paden terug (hoogste impressies eerst).
    """
    from datetime import date, timedelta

    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    # Probeer eerst sc-domain, dan https-variant (beide URL-geëncodeerd in het pad)
    for site_id in [SITE_URL_ENCODED, SITE_URL]:
        encoded = quote(site_id, safe="")
        url  = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query"
        body = {
            "startDate":  start.isoformat(),
            "endDate":    end.isoformat(),
            "dimensions": ["page"],
            "rowLimit":   25000,
        }
        resp = session.post(url, json=body)
        if resp.status_code == 200:
            break
        if resp.status_code not in (403, 404):
            resp.raise_for_status()
    else:
        resp.raise_for_status()

    rows = resp.json().get("rows", [])

    # Verzamel paden + impressies
    path_impressions: dict[str, int] = {}
    for row in rows:
        raw_url     = row["keys"][0]
        path        = urlparse(raw_url).path
        impressions = int(row.get("impressions", 0))
        if impressions < min_impressions:
            continue
        # Normaliseer: altijd eindigend op /
        if not path.endswith("/"):
            path += "/"
        path_impressions[path] = path_impressions.get(path, 0) + impressions

    # Detecteer stadspagina's: ouders van 2-segment paden
    city_pages: set[str]    = set()
    company_pages: set[str] = set()
    for path in path_impressions:
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 2:
            company_pages.add(path)
            city_pages.add("/" + segments[0] + "/")

    # Contentpagina's = geen bedrijf, geen stad, niet uitgesloten
    content_pages = [
        path for path in path_impressions
        if path not in company_pages
        and path not in city_pages
        and path not in EXCLUDED_CONTENT_PAGES
    ]

    # Sorteer op impressies (meest bezochte eerst)
    content_pages.sort(key=lambda p: -path_impressions.get(p, 0))
    return content_pages


# ── Filter-bouwers ────────────────────────────────────────────────────────────

def _build_landing_whitelist(valid_pages=None):
    """
    Bouw de OR-groep voor geldige landingspagina's.
    - valid_pages opgegeven: gebruik exacte paden (uit GSC)
    - valid_pages is None  : val terug op statische prefixes
    """
    whitelist = [
        # Homepage telt altijd mee
        FilterExpression(filter=Filter(
            field_name="landingPage",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="/"
            )
        ))
    ]

    if valid_pages is not None:
        for page in valid_pages:
            whitelist.append(FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=page
                )
            )))
    else:
        for prefix in _FALLBACK_PREFIXES:
            whitelist.append(FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                    value=prefix
                )
            )))

    return FilterExpression(or_group=FilterExpressionList(expressions=whitelist))


def lead_filter(valid_pages=None):
    """
    GA4 FilterExpression voor strikte directe leads.

    valid_pages: lijst van geldige landingspaginapaden (uit get_content_pages_from_gsc).
                 Geeft None mee → valt terug op statische prefix-whitelist.
    """
    expressions = [
        # Alleen dakdekker_lead events
        FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=LEAD_EVENT
            )
        )),
    ]

    # Uitgesloten landingspagina's (CONTAINS)
    for path in EXCLUDED_LANDING_CONTAINS:
        expressions.append(FilterExpression(
            not_expression=FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value=path
                )
            ))
        ))

    # Uitgesloten landingspagina's (EXACT)
    for value in EXCLUDED_LANDING_EXACT:
        expressions.append(FilterExpression(
            not_expression=FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=value
                )
            ))
        ))

    # Alleen geldige kanalen
    expressions.append(FilterExpression(
        or_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="sessionDefaultChannelGrouping",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=channel
                )
            ))
            for channel in VALID_CHANNELS
        ])
    ))

    # Whitelist: alleen content-landingspagina's
    expressions.append(_build_landing_whitelist(valid_pages))

    return FilterExpression(and_group=FilterExpressionList(expressions=expressions))


def meta_lead_filter():
    """GA4 FilterExpression voor Meta/betaalde leads."""
    return FilterExpression(filter=Filter(
        field_name="eventName",
        string_filter=Filter.StringFilter(
            match_type=Filter.StringFilter.MatchType.EXACT,
            value=META_LEAD_EVENT
        )
    ))


def conversie_filter(valid_pages=None, extra_expressions=None):
    """
    GA4 FilterExpression voor conversiepaden (landingPage -> /bedankt/).

    valid_pages     : paden uit get_content_pages_from_gsc (of None voor fallback).
    extra_expressions: optionele lijst van FilterExpression om toe te voegen.
    """
    expressions = []

    # Uitgesloten landingspagina's (CONTAINS)
    for path in EXCLUDED_LANDING_CONTAINS:
        expressions.append(FilterExpression(
            not_expression=FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value=path
                )
            ))
        ))

    # Uitgesloten landingspagina's (EXACT)
    for value in EXCLUDED_LANDING_EXACT:
        expressions.append(FilterExpression(
            not_expression=FilterExpression(filter=Filter(
                field_name="landingPage",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=value
                )
            ))
        ))

    # Alleen geldige kanalen
    expressions.append(FilterExpression(
        or_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="sessionDefaultChannelGrouping",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=channel
                )
            ))
            for channel in VALID_CHANNELS
        ])
    ))

    # Whitelist landingspagina's (optioneel, dezelfde logica als lead_filter)
    if valid_pages is not None:
        expressions.append(_build_landing_whitelist(valid_pages))

    if extra_expressions:
        expressions.extend(extra_expressions)

    return FilterExpression(and_group=FilterExpressionList(expressions=expressions))
