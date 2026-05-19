import json
import os
import requests
import xml.etree.ElementTree as ET

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT_DIR, "data", "sitemap_urls.json")
SITEMAP_INDEX = "https://dakdekkersgids.nl/sitemap_index.xml"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def fetch_xml(url):
    res = requests.get(url, timeout=15)
    res.raise_for_status()
    return ET.fromstring(res.content)


def main():
    print("Sitemap ophalen...")
    index = fetch_xml(SITEMAP_INDEX)
    sitemap_urls = [el.text for el in index.findall(f".//{NS}loc")]
    print(f"{len(sitemap_urls)} sitemaps gevonden")

    alle_urls = []
    for sitemap_url in sitemap_urls:
        print(f"  Ophalen: {sitemap_url}")
        try:
            tree = fetch_xml(sitemap_url)
            urls = [el.text for el in tree.findall(f".//{NS}loc")]
            alle_urls.extend(urls)
            print(f"    {len(urls)} URLs")
        except Exception as e:
            print(f"    Fout: {e}")

    # Sla op als gesorteerde lijst van paden (zonder domein)
    paden = sorted(set(
        url.replace("https://dakdekkersgids.nl", "").rstrip("/") or "/"
        for url in alle_urls
    ))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"urls": paden, "totaal": len(paden)}, f, indent=2, ensure_ascii=False)

    print(f"\nKlaar! {len(paden)} unieke pagina's opgeslagen in {DATA_FILE}")


if __name__ == "__main__":
    main()
