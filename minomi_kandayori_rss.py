import os
import sys
import time
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin


LIST_URL = (
    "https://www.city.fukuyama.hiroshima.jp/"
    "soshiki/nanbuchiikishinkou/118628.html"
)

OUTPUT_FILE = "minomi_kandayori.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/156.0.0.0 Safari/537.36"
    )
}


def fetch_page(url):
    last_error = None

    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
            )

            if response.status_code == 200:
                response.encoding = response.apparent_encoding
                return response

            last_error = RuntimeError(
                f"HTTP {response.status_code}: {url}"
            )

            if response.status_code == 403:
                break

            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue

            break

        except requests.RequestException as e:
            last_error = e

            if attempt < 2:
                time.sleep(5 * (attempt + 1))

    raise RuntimeError(f"ページ取得失敗: {last_error}")


def load_existing_items():
    items = {}

    if not os.path.exists(OUTPUT_FILE):
        return items

    tree = ET.parse(OUTPUT_FILE)
    root = tree.getroot()

    for item in root.findall("./channel/item"):
        link = item.findtext("link")

        if link:
            items[link] = {
                "title": item.findtext("title") or "",
                "link": link,
                "description": item.findtext("description") or "",
                "pubDate": item.findtext("pubDate") or "",
            }

    return items


def scrape_articles():
    response = fetch_page(LIST_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    items = {}

    # 「館たより」の見出しを探す
    heading = None

    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = tag.get_text(" ", strip=True)

        if "館たより" in text:
            heading = tag
            break

    if heading is None:
        raise RuntimeError(
            "「館たより」の見出しが見つかりませんでした。"
            "RSSは更新しません。"
        )

    # 「館たより」から次の見出しまでを対象にする
    node = heading.find_next_sibling()

    while node is not None:
        if getattr(node, "name", None) in ["h2", "h3", "h4"]:
            break

        if hasattr(node, "find_all"):
            for a in node.find_all("a", href=True):
                title = a.get_text(" ", strip=True)

                if "交流館だより" not in title:
                    continue

                url = urljoin(LIST_URL, a["href"])

                items[url] = {
                    "title": title,
                    "link": url,
                    "description": title,
                    "pubDate": "",
                }

        node = node.find_next_sibling()

    if not items:
        raise RuntimeError(
            "館たよりを1件も取得できませんでした。"
            "RSSは更新しません。"
        )

    return items


def build_rss(items):
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = (
        "水呑交流館 館たより"
    )

    ET.SubElement(channel, "link").text = LIST_URL

    ET.SubElement(channel, "description").text = (
        "福山市 水呑交流館「館たより」の更新情報"
    )

    ET.SubElement(channel, "language").text = "ja"

    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(JST)
    )

    sorted_items = list(items.values())

    for data in sorted_items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = data["title"]
        ET.SubElement(item, "link").text = data["link"]
        ET.SubElement(item, "guid").text = data["link"]
        ET.SubElement(item, "description").text = data["description"]

        if data.get("pubDate"):
            ET.SubElement(item, "pubDate").text = data["pubDate"]

    tree = ET.ElementTree(rss)

    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    print("水呑交流館の「館たより」を取得します")

    new_items = scrape_articles()

    print(f"Webから取得: {len(new_items)}件")

    existing_items = load_existing_items()

    print(f"既存RSS: {len(existing_items)}件")

    # PDFのURLをキーにして累積保存
    merged = existing_items.copy()
    merged.update(new_items)

    print(f"統合後: {len(merged)}件")

    build_rss(merged)

    print(f"RSSを保存しました: {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)