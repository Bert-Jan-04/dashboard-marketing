import sys
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
from rules import is_content_page as _is_content_page

CREDENTIALS_FILE = os.path.join(ROOT_DIR, "credentials", "credentials.json")
SITE_URL  = "https://dakdekkersgids.nl/"
DATA_FILE = os.path.join(ROOT_DIR, "data", "gsc_data.json")
SCOPES    = ["https://www.googleapis.com/auth/webmasters.readonly"]

today      = date.today()
week_end   = today - timedelta(days=5)
week_start = week_end - timedelta(days=week_end.weekday())
prev_end   = week_start - timedelta(days=1)
prev_start = prev_end - timedelta(days=6)


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds)


def query(service, start, end, dimensions, row_limit=5000):
    response = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body={
            "startDate": start.isoformat(),
            "endDate":   end.isoformat(),
            "dimensions": dimensions,
            "rowLimit":  row_limit,
        }
    ).execute()
    return response.get("rows", [])


def parse_rows(rows, dimensions):
    result = []
    for row in rows:
        item = {}
        keys = row.get("keys", [])
        for i, dim in enumerate(dimensions):
            item[dim] = keys[i] if i < len(keys) else ""
        item["clicks"]      = row.get("clicks", 0)
        item["impressions"] = row.get("impressions", 0)
        item["ctr"]         = round(row.get("ctr", 0) * 100, 2)
        item["position"]    = round(row.get("position", 0), 1)
        result.append(item)
    return result


def is_company_or_city_page(url):
    path = url.replace("https://dakdekkersgids.nl", "").strip("/")
    return len([s for s in path.split("/") if s]) >= 2  # bedrijfspagina check (cannibalisatie)




def strip_domain(url):
    path = url.replace("https://dakdekkersgids.nl", "") or "/"
    if not path.endswith("/"):
        path += "/"
    return path


def main():
    print(f"GSC data ophalen: {week_start} t/m {week_end}")
    service = get_service()

    # ── Basisdata ──────────────────────────────────────────────────────────────
    kw_this    = parse_rows(query(service, week_start, week_end, ["query"]), ["query"])
    kw_prev    = parse_rows(query(service, prev_start, prev_end, ["query"]), ["query"])
    pages_this = parse_rows(query(service, week_start, week_end, ["page"]),  ["page"])
    pages_prev = parse_rows(query(service, prev_start, prev_end, ["page"]),  ["page"])

    # ── Filter: alleen content-pagina's (whitelist op basis van _FALLBACK_PREFIXES) ─
    content_pages      = [p for p in pages_this if _is_content_page(strip_domain(p["page"]))]
    content_pages_prev = [p for p in pages_prev if _is_content_page(strip_domain(p["page"]))]

    # ── Keywords + rankende pagina (voor filtering + cannibalisatie) ───────────
    kw_page_rows = query(service, week_start, week_end, ["query", "page"], row_limit=5000)

    kw_top_page = {}           # keyword → hoogst-rankende pagina (voor content_keywords filter)
    kw_all_pages = defaultdict(list)  # keyword → alle content-pagina's (voor cannibalisatie)

    for row in kw_page_rows:
        keys = row.get("keys", [])
        if len(keys) < 2:
            continue
        q, p = keys[0], keys[1]
        if q not in kw_top_page:
            kw_top_page[q] = p
        # Cannibalisatie: alleen content-pagina's meenemen
        if is_company_or_city_page(p):
            continue
        path = strip_domain(p)
        if not any(x["page"] == path for x in kw_all_pages[q]):
            kw_all_pages[q].append({
                "page":        path,
                "clicks":      int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "position":    round(row.get("position", 0), 1),
            })

    # ── Content-keywords (zonder bedrijfs-/plaatszoekopdrachten) ──────────────
    content_keywords = [
        kw for kw in kw_this
        if _is_content_page(strip_domain(kw_top_page.get(kw["query"], "/")))
    ]

    # ── Cannibalisatie: meerdere pagina's voor hetzelfde keyword ───────────────
    cannibalisatie = sorted(
        [
            {
                "query":       q,
                "count":       len(pages),
                "impressions": sum(p["impressions"] for p in pages),
                "paginas":     sorted(pages, key=lambda x: x["position"]),
            }
            for q, pages in kw_all_pages.items()
            if len(pages) >= 2
        ],
        key=lambda x: -x["impressions"]
    )[:25]

    # ── Featured snippet kansen: goede positie, te lage CTR ───────────────────
    CTR_DREMPEL = {1: 15.0, 2: 10.0, 3: 6.0}
    featured_kansen = []
    for kw in content_keywords:
        pos = round(kw["position"])
        if pos not in CTR_DREMPEL or kw["impressions"] < 30:
            continue
        verwacht = CTR_DREMPEL[pos]
        if kw["ctr"] < verwacht:
            featured_kansen.append({
                **kw,
                "verwacht_ctr":      verwacht,
                "potentieel_clicks": max(0, round((verwacht - kw["ctr"]) / 100 * kw["impressions"])),
            })
    featured_kansen.sort(key=lambda x: -x["potentieel_clicks"])

    # ── Verwaarloosde pagina's: goede positie maar dalende impressies ──────────
    prev_map = {strip_domain(p["page"]): p for p in content_pages_prev}
    verwaarloosde = []
    for p in content_pages:
        path = strip_domain(p["page"])
        prev = prev_map.get(path)
        if not prev or prev["impressions"] < 30:
            continue
        if p["position"] > 20:
            continue
        daling = (prev["impressions"] - p["impressions"]) / prev["impressions"] * 100
        if daling >= 15:
            verwaarloosde.append({
                "page":             path,
                "impressions":      p["impressions"],
                "impressions_prev": prev["impressions"],
                "daling_pct":       round(daling, 1),
                "position":         p["position"],
                "clicks":           p["clicks"],
            })
    verwaarloosde.sort(key=lambda x: -x["daling_pct"])

    # ── 30-dagen keyword lookup (voor keyword research — vangt ook keywords met 0 clicks) ──
    month_start = week_end - timedelta(days=29)
    kw_month = parse_rows(query(service, month_start, week_end, ["query"]), ["query"])

    # ── Positie-historiek: top 20 keywords, laatste 8 weken ───────────────────
    top_kw_set = {kw["query"] for kw in content_keywords[:20]}
    keyword_historiek = {q: [] for q in top_kw_set}
    for i in range(7, -1, -1):  # week 7 (oudst) → week 0 (huidig)
        if i == 0:
            ws, we = week_start, week_end
        else:
            we = week_start - timedelta(days=1) - timedelta(days=7 * (i - 1))
            ws = we - timedelta(days=6)
        week_rows = parse_rows(query(service, ws, we, ["query"]), ["query"])
        week_map = {r["query"]: r["position"] for r in week_rows}
        for q in top_kw_set:
            keyword_historiek[q].append({
                "week": ws.isoformat(),
                "positie": week_map.get(q),
            })

    # ── Totalen & groei ────────────────────────────────────────────────────────
    totals_this = {"clicks": sum(r["clicks"] for r in kw_this),
                   "impressions": sum(r["impressions"] for r in kw_this)}
    totals_prev = {"clicks": sum(r["clicks"] for r in kw_prev),
                   "impressions": sum(r["impressions"] for r in kw_prev)}

    def growth(now, prev):
        return 0 if prev == 0 else round((now - prev) / prev * 100, 1)

    data = {
        "period": {
            "this_week": {"start": week_start.isoformat(), "end": week_end.isoformat()},
            "prev_week": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        },
        "totals": {
            "clicks":             totals_this["clicks"],
            "clicks_growth":      growth(totals_this["clicks"], totals_prev["clicks"]),
            "impressions":        totals_this["impressions"],
            "impressions_growth": growth(totals_this["impressions"], totals_prev["impressions"]),
        },
        "top_keywords":           kw_this,
        "content_keywords":       content_keywords,
        "kw_month":               kw_month,
        "top_pages":              content_pages[:20],
        "prev_keywords":          kw_prev[:20],
        "cannibalisatie":         cannibalisatie,
        "featured_snippet_kansen": featured_kansen[:15],
        "verwaarloosde_paginas":  verwaarloosde[:15],
        "keyword_historiek":      keyword_historiek,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    gefilterd_kw = len(kw_this) - len(content_keywords)
    gefilterd_pg = len(pages_this) - len(content_pages)
    print(f"Klaar! {totals_this['clicks']} clicks | {len(content_keywords)} content-keywords "
          f"({gefilterd_kw} kw gefilterd) | {len(content_pages)} content-pagina's "
          f"({gefilterd_pg} stads/bedrijf gefilterd) | {len(cannibalisatie)} cannibalisaties | "
          f"{len(featured_kansen)} snippet-kansen | {len(verwaarloosde)} verwaarloosde pagina's")
    print(f"Data opgeslagen in {DATA_FILE}")


if __name__ == "__main__":
    main()
