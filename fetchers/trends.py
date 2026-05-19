import json
import os
from datetime import date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest,
    FilterExpression, Filter
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDENTIALS_FILE = os.path.join(ROOT_DIR, "credentials", "credentials.json")
SITE_URL = "https://dakdekkersgids.nl/"
PROPERTY_ID = "355158317"
DATA_FILE = os.path.join(ROOT_DIR, "data", "trends_data.json")
SCOPES_GSC = ["https://www.googleapis.com/auth/webmasters.readonly"]
SCOPES_GA4 = ["https://www.googleapis.com/auth/analytics.readonly"]
WEKEN = 8


def week_ranges():
    today = date.today()
    # Meest recente volledige week eindigt 3 dagen geleden (GSC vertraging)
    einde = today - timedelta(days=3)
    # Zorg dat we op een zondag eindigen (of de meest recente dag)
    ranges = []
    for i in range(WEKEN):
        week_end = einde - timedelta(weeks=i)
        week_start = week_end - timedelta(days=6)
        ranges.append((week_start, week_end))
    return list(reversed(ranges))


def get_gsc_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES_GSC)
    return build("searchconsole", "v1", credentials=creds)


def get_ga4_client():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES_GA4)
    return BetaAnalyticsDataClient(credentials=creds)


def gsc_top_paginas(service, start, end, limit=10):
    """Top pagina's per week met positie (voor positie-historiek chart)."""
    resp = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body={
            "startDate": start.isoformat(),
            "endDate":   end.isoformat(),
            "dimensions": ["page"],
            "rowLimit": limit,
        }
    ).execute()
    result = []
    for r in resp.get("rows", []):
        path = r["keys"][0].replace("https://dakdekkersgids.nl", "") or "/"
        if not path.endswith("/"): path += "/"
        result.append({
            "page":        path,
            "clicks":      int(r.get("clicks", 0)),
            "impressions": int(r.get("impressions", 0)),
            "position":    round(r.get("position", 0), 1),
        })
    return result


def gsc_week(service, start, end):
    resp = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": [],
            "rowLimit": 1
        }
    ).execute()
    rows = resp.get("rows", [])
    if rows:
        r = rows[0]
        return {
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": round(r.get("ctr", 0) * 100, 2),
            "position": round(r.get("position", 0), 1)
        }
    return {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}


def ga4_week(client, start, end):
    # Totalen
    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers"),
                 Metric(name="conversions"), Metric(name="bounceRate")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=1
    )
    resp = client.run_report(req)
    totals = {"sessions": 0, "active_users": 0, "conversions": 0, "bounce_rate": 0}
    if resp.rows:
        row = resp.rows[0]
        totals = {
            "sessions": int(row.metric_values[0].value),
            "active_users": int(row.metric_values[1].value),
            "conversions": int(row.metric_values[2].value),
            "bounce_rate": round(float(row.metric_values[3].value) * 100, 1)
        }

    # Offerteaanvragen via /bedankt/
    req2 = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPage")],
        metrics=[Metric(name="sessions")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value="/bedankt/"
                )
            )
        ),
        limit=50
    )
    resp2 = client.run_report(req2)
    aanvragen = sum(int(r.metric_values[0].value) for r in resp2.rows)

    return {**totals, "offerteaanvragen": aanvragen}


def main():
    print(f"Trends ophalen — laatste {WEKEN} weken...")
    gsc_service = get_gsc_service()
    ga4_client = get_ga4_client()
    weken = week_ranges()
    resultaten = []

    for start, end in weken:
        label = f"W{start.isocalendar()[1]}"
        print(f"  {label}: {start} t/m {end}")
        gsc        = gsc_week(gsc_service, start, end)
        ga4        = ga4_week(ga4_client, start, end)
        top_pages  = gsc_top_paginas(gsc_service, start, end)
        resultaten.append({
            "week":      label,
            "start":     start.isoformat(),
            "end":       end.isoformat(),
            "gsc":       gsc,
            "ga4":       ga4,
            "top_pages": top_pages,
        })

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(resultaten, f, indent=2, ensure_ascii=False)

    print(f"Klaar! Data opgeslagen in {DATA_FILE}")


if __name__ == "__main__":
    main()
