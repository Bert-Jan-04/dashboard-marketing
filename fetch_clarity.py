import json
import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN      = os.getenv("CLARITY_API_TOKEN")
PROJECT_ID = os.getenv("CLARITY_PROJECT_ID")
DATA_FILE  = os.path.join(os.path.dirname(__file__), "data", "clarity_data.json")
BASE_URL   = "https://www.clarity.ms/export-data/api/v1"


def fetch(endpoint, params):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_metrics(raw):
    out = {}
    for item in raw:
        name = item["metricName"]
        info = item["information"]
        if name == "Traffic":
            out["sessies"]           = int(info[0].get("totalSessionCount", 0))
            out["bot_sessies"]       = int(info[0].get("totalBotSessionCount", 0))
            out["gebruikers"]        = int(info[0].get("distinctUserCount", 0))
            out["paginas_per_sessie"] = round(info[0].get("pagesPerSessionPercentage", 0), 2)
        elif name == "ScrollDepth":
            out["scroll_diepte"] = round(info[0].get("averageScrollDepth", 0), 1)
        elif name == "EngagementTime":
            out["actieve_tijd_sec"] = int(info[0].get("activeTime", 0))
            out["totale_tijd_sec"]  = int(info[0].get("totalTime", 0))
        elif name == "DeadClickCount":
            out["dead_click_pct"]      = info[0].get("sessionsWithMetricPercentage", 0)
            out["dead_click_paginas"]  = int(info[0].get("pagesViews", 0))
        elif name == "RageClickCount":
            out["rage_click_pct"]     = info[0].get("sessionsWithMetricPercentage", 0)
        elif name == "QuickbackClick":
            out["quickback_pct"]      = info[0].get("sessionsWithMetricPercentage", 0)
            out["quickback_paginas"]  = int(info[0].get("pagesViews", 0))
        elif name == "ScriptErrorCount":
            out["script_error_pct"]   = info[0].get("sessionsWithMetricPercentage", 0)
        elif name == "Device":
            out["apparaten"] = [{"naam": d["name"], "sessies": int(d["sessionsCount"])} for d in info]
        elif name == "PopularPages":
            out["populaire_paginas"] = [
                {"url": p["url"].replace("https://dakdekkersgids.nl", "") or "/",
                 "bezoeken": int(p["visitsCount"])}
                for p in info
            ]
        elif name == "ReferrerUrl":
            out["verwijzers"] = [
                {"url": r["name"] or "Direct", "sessies": int(r["sessionsCount"])}
                for r in info
            ]
    return out


def main():
    if not TOKEN or not PROJECT_ID:
        print("CLARITY_API_TOKEN of CLARITY_PROJECT_ID ontbreekt in .env")
        return

    end   = date.today()
    start = end - timedelta(days=7)
    params = {
        "projectId": PROJECT_ID,
        "startDate": start.strftime("%Y-%m-%d"),
        "endDate":   end.strftime("%Y-%m-%d"),
    }

    print(f"Clarity data ophalen: {params['startDate']} t/m {params['endDate']}")
    raw     = fetch("project-live-insights", params)
    metrics = parse_metrics(raw)

    data = {
        "periode": {"start": params["startDate"], "eind": params["endDate"]},
        "metrics": metrics,
        "gegenereerd": date.today().isoformat(),
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Klaar! {metrics.get('sessies', 0)} sessies | "
          f"scroll {metrics.get('scroll_diepte', 0)}% | "
          f"dead clicks {metrics.get('dead_click_pct', 0)}% | "
          f"quickback {metrics.get('quickback_pct', 0)}%")
    print(f"Data opgeslagen in {DATA_FILE}")


if __name__ == "__main__":
    main()
