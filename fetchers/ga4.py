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
    CREDENTIALS_FILE, PROPERTY_ID,
    get_content_pages_from_gsc,
    is_content_page,
)

DATA_FILE = os.path.join(ROOT_DIR, "data", "ga4_data.json")

today      = date.today()
week_end   = today - timedelta(days=5)
week_start = week_end - timedelta(days=week_end.weekday())
prev_end   = week_start - timedelta(days=1)
prev_start = prev_end - timedelta(days=6)


def get_client_and_session():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=[
            "https://www.googleapis.com/auth/analytics.readonly",
            "https://www.googleapis.com/auth/webmasters.readonly",
        ]
    )
    return BetaAnalyticsDataClient(credentials=creds), AuthorizedSession(creds)


def run_report(client, dimensions, metrics, start, end, limit=20):
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=limit
    )
    return client.run_report(request)


def parse_report(response, dimensions, metrics):
    result = []
    for row in response.rows:
        item = {}
        for i, dim in enumerate(dimensions):
            item[dim] = row.dimension_values[i].value
        for i, met in enumerate(metrics):
            val = row.metric_values[i].value
            item[met] = float(val) if "." in val else int(val)
        result.append(item)
    return result


def get_offerteaanvragen(client, start, end, valid_pages=None):
    """
    dakdekker_lead events per landingPage, gefilterd op content-pagina's.
    """
    from rules import lead_filter
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="landingPage")],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimension_filter=lead_filter(valid_pages=valid_pages),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)],
        limit=20
    )
    response = client.run_report(request)
    return [
        {
            "landing_page": row.dimension_values[0].value,
            "aanvragen": int(row.metric_values[0].value)
        }
        for row in response.rows
    ]


def get_totals(client, start, end):
    response = run_report(
        client,
        dimensions=[],
        metrics=["sessions", "activeUsers", "conversions", "bounceRate"],
        start=start,
        end=end,
        limit=1
    )
    if response.rows:
        row = response.rows[0]
        return {
            "sessions":    int(row.metric_values[0].value),
            "active_users": int(row.metric_values[1].value),
            "conversions": int(row.metric_values[2].value),
            "bounce_rate": round(float(row.metric_values[3].value) * 100, 1)
        }
    return {}


def growth(now, prev):
    if prev == 0:
        return 0
    return round((now - prev) / prev * 100, 1)


def main():
    print(f"GA4 data ophalen: {week_start} t/m {week_end}")
    client, session = get_client_and_session()

    # GSC content-pagina's ophalen voor de filter
    print("GSC content-pagina's ophalen...", end=" ", flush=True)
    try:
        valid_pages = get_content_pages_from_gsc(session)
        print(f"{len(valid_pages)} pagina's gevonden.")
    except Exception as e:
        print(f"mislukt ({e}), valt terug op prefix-whitelist.")
        valid_pages = None

    # Totalen deze week en vorige week
    totals_this = get_totals(client, week_start, week_end)
    totals_prev = get_totals(client, prev_start, prev_end)

    # Offerteaanvragen per landing page (gefilterd met GSC-whitelist)
    offerteaanvragen      = get_offerteaanvragen(client, week_start, week_end, valid_pages)
    offerteaanvragen_prev = get_offerteaanvragen(client, prev_start, prev_end, valid_pages)

    # Top pagina's (test-pagina's uitgesloten)
    pages_request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers"), Metric(name="bounceRate")],
        date_ranges=[DateRange(start_date=week_start.isoformat(), end_date=week_end.isoformat())],
        dimension_filter=FilterExpression(
            not_expression=FilterExpression(filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value="/form-test"
                )
            ))
        ),
        limit=20
    )
    pages_response = client.run_report(pages_request)
    all_pages = parse_report(pages_response, ["pagePath"], ["sessions", "activeUsers", "bounceRate"])
    top_pages = [p for p in all_pages if is_content_page(p["pagePath"])]

    # Kanalen (organic, direct, etc.)
    channels_response = run_report(
        client,
        dimensions=["sessionDefaultChannelGrouping"],
        metrics=["sessions", "conversions"],
        start=week_start,
        end=week_end
    )
    channels = parse_report(channels_response, ["sessionDefaultChannelGrouping"], ["sessions", "conversions"])

    data = {
        "period": {
            "this_week": {"start": week_start.isoformat(), "end": week_end.isoformat()},
            "prev_week": {"start": prev_start.isoformat(), "end": prev_end.isoformat()}
        },
        "totals": {
            "sessions":         totals_this.get("sessions", 0),
            "sessions_growth":  growth(totals_this.get("sessions", 0), totals_prev.get("sessions", 0)),
            "active_users":     totals_this.get("active_users", 0),
            "active_users_growth": growth(totals_this.get("active_users", 0), totals_prev.get("active_users", 0)),
            "conversions":      totals_this.get("conversions", 0),
            "conversions_growth": growth(totals_this.get("conversions", 0), totals_prev.get("conversions", 0)),
            "bounce_rate":      totals_this.get("bounce_rate", 0)
        },
        "top_pages": top_pages[:15],
        "channels":  channels,
        "offerteaanvragen": {
            "deze_week":          offerteaanvragen,
            "totaal_deze_week":   sum(r["aanvragen"] for r in offerteaanvragen),
            "totaal_vorige_week": sum(r["aanvragen"] for r in offerteaanvragen_prev),
            "groei": growth(
                sum(r["aanvragen"] for r in offerteaanvragen),
                sum(r["aanvragen"] for r in offerteaanvragen_prev)
            )
        },
        "content_pages_count": len(valid_pages) if valid_pages is not None else None,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Klaar! {totals_this.get('sessions', 0)} sessies ({growth(totals_this.get('sessions', 0), totals_prev.get('sessions', 0))}%)")
    print(f"Data opgeslagen in {DATA_FILE}")


if __name__ == "__main__":
    main()
