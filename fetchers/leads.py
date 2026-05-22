"""
Leads analyse deze week — dakdekkersgids.nl

Strikte regels:
  1. Directe leads: dakdekker_lead event
       - Geen directe /bedankt-landingen
       - Geen (not set) landingPage
       - Geen /form-test pagina's
       - Alleen Organic Search of Direct kanaal
  2. Meta leads: dakdekker_leads_meta event (apart geteld)
  3. Cluster attributie (Funnel API, cross-sessie):
       - Stap 1: clusterpage bezocht (page_view)
       - Stap 2: dakdekker_lead event (niet een pageview)
       - Open funnel, isDirectlyFollowedBy: false
"""

import sys
import json
import os
from datetime import date, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest,
    FilterExpression, FilterExpressionList, Filter, OrderBy
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
from rules import (
    CREDENTIALS_FILE, PROPERTY_ID, CLUSTERS,
    lead_filter, meta_lead_filter as _meta_lead_filter,
    get_content_pages_from_gsc,
)

FUNNEL_URL = f"https://analyticsdata.googleapis.com/v1alpha/properties/{PROPERTY_ID}:runFunnelReport"

today      = date.today()
week_end   = today - timedelta(days=5)
week_start = week_end - timedelta(days=week_end.weekday())
prev_end   = week_start - timedelta(days=1)
prev_start = prev_end - timedelta(days=6)


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_creds():
    return service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=[
            "https://www.googleapis.com/auth/analytics.readonly",
            "https://www.googleapis.com/auth/webmasters.readonly",
        ]
    )


# ── Funnel API ────────────────────────────────────────────────────────────────

def funnel_leads(session, cluster_path, start, end):
    """
    GA4 Funnel API:
      Stap 1 — page_view op clusterpad
      Stap 2 — dakdekker_lead event (streng: echt formulier ingevuld)
    Cross-sessie, open funnel.
    """
    body = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "funnel": {
            "isOpenFunnel": True,
            "steps": [
                {
                    "name": "Cluster bezocht",
                    "filterExpression": {
                        "funnelEventFilter": {
                            "eventName": "page_view",
                            "funnelParameterFilterExpression": {
                                "funnelParameterFilter": {
                                    "eventParameterName": "page_location",
                                    "stringFilter": {
                                        "matchType": "CONTAINS",
                                        "value": cluster_path
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "name": "Lead",
                    "isDirectlyFollowedBy": False,
                    "filterExpression": {
                        "funnelEventFilter": {
                            "eventName": "dakdekker_lead"
                        }
                    }
                }
            ]
        }
    }

    resp = session.post(FUNNEL_URL, json=body)
    resp.raise_for_status()
    data = resp.json()

    visitors = 0
    leads    = 0

    if "funnelTable" in data and data["funnelTable"].get("rows"):
        visitors = int(data["funnelTable"]["rows"][0]["metricValues"][0]["value"])

    if "funnelVisualization" in data and data["funnelVisualization"].get("rows"):
        for row in data["funnelVisualization"]["rows"]:
            dims = row.get("dimensionValues", [])
            if len(dims) >= 2 and "2." in dims[0]["value"] and dims[1]["value"] == "continuing":
                leads = int(row["metricValues"][0]["value"])
                break

    return visitors, leads


# ── Standaard GA4 queries ─────────────────────────────────────────────────────

def get_leads(client, start, end, valid_pages=None):
    """Strikte directe leads: dakdekker_lead event, organic/direct, geen rommel."""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPage")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=lead_filter(valid_pages),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=25
    )
    response = client.run_report(request)
    return [
        {"pagina": row.dimension_values[0].value, "leads": int(row.metric_values[0].value)}  # landingPage
        for row in response.rows
    ]


def get_meta_leads(client, start, end):
    """Meta/betaalde leads: dakdekker_leads_meta event."""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPage")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=_meta_lead_filter(),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=10
    )
    response = client.run_report(request)
    return [
        {"landingspagina": row.dimension_values[0].value, "leads": int(row.metric_values[0].value)}
        for row in response.rows
    ]


def get_leads_per_kanaal(client, start, end, valid_pages=None):
    """Kanaalverdeling van strikte leads."""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="sessionDefaultChannelGrouping")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=lead_filter(valid_pages),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=10
    )
    response = client.run_report(request)
    return [
        {"kanaal": row.dimension_values[0].value, "leads": int(row.metric_values[0].value)}
        for row in response.rows
    ]


def get_totals(client, start, end):
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=1
    )
    response = client.run_report(request)
    if response.rows:
        r = response.rows[0]
        return {"sessions": int(r.metric_values[0].value), "active_users": int(r.metric_values[1].value)}
    return {"sessions": 0, "active_users": 0}


def growth(now, prev):
    if prev == 0:
        return "nieuw" if now > 0 else "0"
    pct = round((now - prev) / prev * 100, 1)
    return f"{pct:+.1f}%"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*62}")
    print(f"  LEADS ANALYSE - dakdekkersgids.nl")
    print(f"  Deze week  : {week_start} t/m {week_end}")
    print(f"  Vorige week: {prev_start} t/m {prev_end}")
    print(f"  Regels     : dakdekker_lead event | organic+direct | geen nep")
    print(f"{'='*62}\n")

    creds   = get_creds()
    client  = BetaAnalyticsDataClient(credentials=creds)
    session = AuthorizedSession(creds)

    # ── GSC content-pagina's ophalen (eenmalig, voor alle filters) ────────────
    print("  GSC content-pagina's ophalen...", end=" ", flush=True)
    try:
        valid_pages = get_content_pages_from_gsc(session)
        print(f"{len(valid_pages)} contentpagina's gevonden.")
    except Exception as e:
        print(f"mislukt ({e}), valt terug op prefix-whitelist.")
        valid_pages = None

    # ── Directe leads ────────────────────────────────────────────────────────
    leads_nu    = get_leads(client, week_start, week_end, valid_pages)
    leads_prev  = get_leads(client, prev_start, prev_end, valid_pages)
    totaal_nu   = sum(r["leads"] for r in leads_nu)
    totaal_prev = sum(r["leads"] for r in leads_prev)
    kanalen     = get_leads_per_kanaal(client, week_start, week_end, valid_pages)
    meta_nu     = get_meta_leads(client, week_start, week_end)
    meta_prev   = get_meta_leads(client, prev_start, prev_end)
    totaal_meta_nu   = sum(r["leads"] for r in meta_nu)
    totaal_meta_prev = sum(r["leads"] for r in meta_prev)
    totals_nu   = get_totals(client, week_start, week_end)
    totals_prev = get_totals(client, prev_start, prev_end)
    conv        = round(totaal_nu / totals_nu["sessions"] * 100, 2) if totals_nu["sessions"] else 0

    print(f"  ORGANISCHE LEADS (streng gefilterd)")
    print(f"  {'-'*50}")
    print(f"  Totaal      : {totaal_nu:>4}  (vorige week: {totaal_prev}, {growth(totaal_nu, totaal_prev)})")
    print(f"  Sessies     : {totals_nu['sessions']:>4}  (vorige week: {totals_prev['sessions']}, {growth(totals_nu['sessions'], totals_prev['sessions'])})")
    print(f"  Conversie   : {conv}%")

    if leads_nu:
        print(f"\n  Per pagina:")
        for r in leads_nu:
            print(f"    {r['leads']:>3}x  {r['pagina']}")

    if kanalen:
        print(f"\n  Per kanaal:")
        for k in kanalen:
            pct = round(k["leads"] / totaal_nu * 100, 1) if totaal_nu else 0
            print(f"    {k['leads']:>3}x  {k['kanaal']:<30} ({pct}%)")

    print(f"\n  META LEADS (dakdekker_leads_meta event)")
    print(f"  {'-'*50}")
    print(f"  Totaal: {totaal_meta_nu}  (vorige week: {totaal_meta_prev}, {growth(totaal_meta_nu, totaal_meta_prev)})")
    for r in meta_nu:
        print(f"    {r['leads']:>3}x  {r['landingspagina']}")

    # ── Cluster attributie ────────────────────────────────────────────────────
    cum_start = date(2026, 3, 20)

    print(f"\n  CLUSTER ATTRIBUTIE (cross-sessie | dakdekker_lead event)")
    print(f"\n  Deze week ({week_start} t/m {week_end}):")
    print(f"  {'-'*52}")
    print(f"  {'Cluster':<22} {'Bez':>5} {'Leads':>6} {'Conv%':>7} {'vw leads':>9}")
    print(f"  {'-'*52}")

    cluster_nu   = {}
    cluster_prev = {}
    cluster_cum  = {}

    for c in CLUSTERS:
        v_nu,   l_nu   = funnel_leads(session, c, week_start, week_end)
        v_prev, l_prev = funnel_leads(session, c, prev_start, prev_end)
        conv_c = f"{l_nu/v_nu*100:.1f}%" if v_nu > 0 else "-"
        trend  = growth(l_nu, l_prev) if l_prev > 0 or l_nu > 0 else "-"
        print(f"  {c:<22} {v_nu:>5} {l_nu:>6} {conv_c:>7}   {l_prev:>4} ({trend})")
        cluster_nu[c]   = {"bezoekers": v_nu,   "leads": l_nu}
        cluster_prev[c] = {"bezoekers": v_prev, "leads": l_prev}

    print(f"\n  Cumulatief (20 mrt t/m {week_end}):")
    print(f"  {'-'*52}")
    print(f"  {'Cluster':<22} {'Bez':>5} {'Leads':>6} {'Conv%':>7}")
    print(f"  {'-'*52}")

    for c in CLUSTERS:
        v_cum, l_cum = funnel_leads(session, c, cum_start, week_end)
        conv_c = f"{l_cum/v_cum*100:.1f}%" if v_cum > 0 else "-"
        print(f"  {c:<22} {v_cum:>5} {l_cum:>6} {conv_c:>7}")
        cluster_cum[c] = {"bezoekers": v_cum, "leads": l_cum}

    # ── Opslaan ───────────────────────────────────────────────────────────────
    output = {
        "gegenereerd_op": today.isoformat(),
        "methode": "dakdekker_lead event | organic+direct | geen nep-leads",
        "periode": {
            "deze_week":   {"start": week_start.isoformat(), "end": week_end.isoformat()},
            "vorige_week": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        },
        "directe_leads": {
            "totaal_deze_week":   totaal_nu,
            "totaal_vorige_week": totaal_prev,
            "groei":              growth(totaal_nu, totaal_prev),
            "per_pagina":         leads_nu,
            "per_kanaal":         kanalen,
        },
        "meta_leads": {
            "totaal_deze_week":   totaal_meta_nu,
            "totaal_vorige_week": totaal_meta_prev,
            "groei":              growth(totaal_meta_nu, totaal_meta_prev),
            "per_landingspagina": meta_nu,
        },
        "sessies": {
            "deze_week":   totals_nu,
            "vorige_week": totals_prev,
        },
        "conversieratio_pct": conv,
        "cluster_attributie": {
            "deze_week":   cluster_nu,
            "vorige_week": cluster_prev,
            "cumulatief":  cluster_cum,
        },
        "content_pages_count": len(valid_pages) if valid_pages is not None else None,
    }

    output_file = os.path.join(ROOT_DIR, "data", "leads_week.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Historiek opslaan (voor cluster trend chart) ──────────────────────────
    history_file = os.path.join(ROOT_DIR, "data", "leads_history.json")
    history = []
    if os.path.exists(history_file):
        with open(history_file, encoding="utf-8") as f:
            history = json.load(f)

    week_key = week_start.isoformat()
    history  = [h for h in history if h.get("week_start") != week_key]
    history.append({
        "week":          f"W{week_start.isocalendar()[1]}",
        "week_start":    week_key,
        "week_end":      week_end.isoformat(),
        "clusters":      cluster_nu,
        "directe_leads": totaal_nu,
        "meta_leads":    totaal_meta_nu,
    })
    history = sorted(history, key=lambda h: h["week_start"])[-12:]
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"\n  Data opgeslagen in: data/leads_week.json")
    print(f"  Historiek: {len(history)} weken opgeslagen in data/leads_history.json")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
