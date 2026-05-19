import requests
import json
import os
import re
import time
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONCURRENTEN = [
    {"naam": "HomeDeal", "domein": "homedeal.nl", "basis": "https://www.homedeal.nl", "start": "https://www.homedeal.nl/dakbedekking/"},
    {"naam": "Mijn Dakdekker", "domein": "mijn-dakdekker.nl", "basis": "https://www.mijn-dakdekker.nl", "start": "https://www.mijn-dakdekker.nl/"},
    {"naam": "Kosten Dakdekker", "domein": "kosten-dakdekker.nl", "basis": "https://www.kosten-dakdekker.nl", "start": "https://www.kosten-dakdekker.nl/"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DAK_WOORDEN = ["dak", "plat", "schild", "pannen", "goot", "isolat", "bitumen", "lood", "zink", "riet", "asbest"]


def slug_naar_keyword(slug):
    slug = re.sub(r"\.(html|php|aspx|htm)$", "", slug)
    return re.sub(r"[-_]+", " ", slug).strip().lower()


def fetch_sitemap_urls(basis_url):
    kandidaten = [
        basis_url + "/sitemap.xml",
        basis_url + "/sitemap_index.xml",
        basis_url + "/sitemap-index.xml",
        basis_url + "/sitemap_pages.xml",
    ]
    for sitemap_url in kandidaten:
        try:
            r = requests.get(sitemap_url, headers=HEADERS, timeout=12)
            if r.status_code != 200 or "<" not in r.text:
                continue
            root = ET.fromstring(r.text.encode("utf-8"))
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Sitemap index → loop sub-sitemaps
            sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
            if sub_sitemaps:
                urls = []
                for sm in sub_sitemaps[:8]:
                    try:
                        r2 = requests.get(sm.text.strip(), headers=HEADERS, timeout=12)
                        if r2.status_code == 200:
                            root2 = ET.fromstring(r2.text.encode("utf-8"))
                            urls += [loc.text.strip() for loc in root2.findall(".//sm:url/sm:loc", ns)]
                        time.sleep(0.5)
                    except Exception:
                        pass
                if urls:
                    return urls

            # Gewone sitemap
            urls = [loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", ns)]
            if urls:
                return urls
        except Exception:
            pass
    return []


def mangools_keyword_data(keyword):
    key = os.getenv("MANGOOLS_API_KEY", "")
    if not key:
        return {}
    try:
        r = requests.get(
            "https://api.mangools.com/v2/kwfinder/related-keywords",
            params={"kw": keyword, "location_id": 2528, "lang_id": 1043},
            headers={"X-Access-Token": key},
            timeout=15,
        )
        if r.status_code == 200:
            for kw in r.json().get("keywords", []):
                if kw.get("kw", "").lower() == keyword.lower():
                    return {"sv": kw.get("sv", 0), "seo": kw.get("seo"), "cpc": kw.get("cpc")}
    except Exception:
        pass
    return {}


def main():
    gsc_path = os.path.join(BASE_DIR, "data", "gsc_data.json")
    gsc = json.load(open(gsc_path, encoding="utf-8")) if os.path.exists(gsc_path) else {}
    onze_keywords = {k["query"].lower(): k for k in gsc.get("top_keywords", [])}

    concurrenten_resultaat = []
    keyword_naar_domeinen = {}

    for c in CONCURRENTEN:
        print(f"  Sitemap ophalen: {c['domein']} ...", flush=True)
        alle_urls = fetch_sitemap_urls(c["basis"])

        # Filter op dak-gerelateerde URLs
        dak_urls = [u for u in alle_urls if any(w in u.lower() for w in DAK_WOORDEN)]

        # Keywords uit URL-slugs extraheren
        gevonden_keywords = []
        for url in dak_urls[:200]:
            path = urlparse(url).path
            delen = [d for d in path.strip("/").split("/") if len(d) > 3]
            for deel in delen:
                kw = slug_naar_keyword(deel)
                if kw and kw not in gevonden_keywords and not re.match(r"^\d+$", kw):
                    gevonden_keywords.append(kw)
                    keyword_naar_domeinen.setdefault(kw, [])
                    if c["domein"] not in keyword_naar_domeinen[kw]:
                        keyword_naar_domeinen[kw].append(c["domein"])

        concurrenten_resultaat.append({
            "naam": c["naam"],
            "domein": c["domein"],
            "paginas_totaal": len(alle_urls),
            "dak_paginas": len(dak_urls),
            "keywords": gevonden_keywords[:60],
        })
        print(f"    > {len(alle_urls)} pagina's, {len(dak_urls)} dak-gerelateerd, {len(gevonden_keywords)} keywords")
        time.sleep(1)

    # Dreigingsanalyse: concurrent heeft content + wij ranken zwak of niet
    dreigingen = []
    for kw, domeinen in keyword_naar_domeinen.items():
        onze = onze_keywords.get(kw, {})
        positie = onze.get("position", 999)
        impressies = onze.get("impressions", 0)
        clicks = onze.get("clicks", 0)

        dreiging_score = (
            len(domeinen) * 30
            + (20 if 4 <= positie <= 15 else 10 if positie <= 20 else 0)
            + min(impressies, 500) / 10
        )

        dreigingen.append({
            "keyword": kw,
            "onze_positie": round(positie, 1) if positie < 999 else None,
            "onze_impressies": impressies,
            "onze_clicks": clicks,
            "concurrenten": domeinen,
            "dreiging_score": round(dreiging_score, 1),
        })

    dreigingen.sort(key=lambda x: -x["dreiging_score"])

    # Verrijken met Mangools (top 12, rate-limit-bewust)
    print("  Mangools verrijking top-dreigingen...", flush=True)
    for d in dreigingen[:12]:
        kw_data = mangools_keyword_data(d["keyword"])
        if kw_data:
            d.update(kw_data)
        time.sleep(1.2)

    output = {
        "gegenereerd": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "concurrenten": concurrenten_resultaat,
        "dreigingen": dreigingen[:40],
        "samenvatting": {
            "totaal_concurrent_keywords": len(keyword_naar_domeinen),
            "overlap_met_ons": sum(1 for kw in keyword_naar_domeinen if kw in onze_keywords),
            "meerdere_concurrenten": sum(1 for v in keyword_naar_domeinen.values() if len(v) > 1),
        },
    }

    out_path = os.path.join(BASE_DIR, "data", "competitor_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nKlaar — {len(dreigingen)} dreigingen gevonden, opgeslagen in data/competitor_data.json")
    return output


if __name__ == "__main__":
    print("Concurrentenanalyse starten...")
    main()
