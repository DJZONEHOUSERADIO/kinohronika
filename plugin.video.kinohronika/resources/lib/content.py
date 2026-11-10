# -*- coding: utf-8 -*-
"""Източници на съдържание: RSS новини, archive.org, YouTube канали."""
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlencode

import xbmc
import xbmcaddon

import util

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")

_SOURCES = None


def sources():
    global _SOURCES
    if _SOURCES is None:
        path = os.path.join(ADDON_PATH, "resources", "data", "sources.json")
        with open(path, "r", encoding="utf-8") as handle:
            _SOURCES = json.load(handle)
    return _SOURCES


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node, names):
    for child in list(node):
        if _local(child.tag) in names:
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def _parse_date(value):
    if not value:
        return 0
    value = value.strip()
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        pass
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt) + 4], fmt).timestamp()
        except Exception:
            continue
    return 0


def _first_image(node):
    for child in node.iter():
        name = _local(child.tag)
        if name in ("thumbnail", "content") and child.get("url"):
            if name == "thumbnail" or (child.get("type", "").startswith("image")):
                return child.get("url")
        if name == "enclosure" and child.get("url"):
            if child.get("type", "").startswith("image"):
                return child.get("url")
    return ""


def parse_feed(xml_text, source):
    """Парсва RSS 2.0 или Atom и връща списък със статии."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        util.log("XML parse error for %s: %s" % (source.get("id"), exc))
        return items

    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = _child_text(node, {"title"})
        link = _child_text(node, {"link"})
        if not link:
            for child in list(node):
                if _local(child.tag) == "link" and child.get("href"):
                    link = child.get("href")
                    break
        if not link:
            link = _child_text(node, {"guid", "id"})
        description = _child_text(node, {"description", "summary", "content", "encoded"})
        published = _child_text(node, {"pubdate", "published", "updated", "date"})
        image = _first_image(node) or util.first_image(description)
        if not title:
            continue
        items.append({
            "title": util.strip_html(title) or title,
            "link": link.strip(),
            "desc": util.strip_html(description),
            "image": image,
            "ts": _parse_date(published),
            "source": source.get("name", ""),
            "source_id": source.get("id", ""),
            "country": source.get("country", ""),
        })
    return items


def _enabled_news_sources():
    configured = util.setting("news_sources", "")
    if not configured.strip():
        return sources()["news"]
    allowed = {part.strip() for part in configured.split(",") if part.strip()}
    return [src for src in sources()["news"] if src["id"] in allowed]


def load_news(force=False):
    """Сваля всички емисии паралелно и връща сортиран списък."""
    ttl = 0 if force else util.setting_int("cache_minutes", 10) * 60
    feeds = _enabled_news_sources()
    per_source = util.setting_int("news_per_source", 12)

    def fetch(source):
        try:
            xml_text = util.http_get(source["url"], ttl=ttl, timeout=12)
            parsed = parse_feed(xml_text, source)[:per_source]
            return parsed
        except Exception as exc:
            util.log("feed %s failed: %s" % (source["id"], exc))
            return []

    results = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for chunk in pool.map(fetch, feeds):
                results.extend(chunk)
    except Exception:
        for source in feeds:
            results.extend(fetch(source))

    # премахваме дубликати по заглавие и по адрес
    seen_titles, seen_links, unique = set(), set(), []
    for item in sorted(results, key=lambda i: i["ts"], reverse=True):
        title_key = re.sub(r"\W+", "", item["title"].lower())[:70]
        link_key = item["link"].split("?")[0]
        if title_key in seen_titles or link_key in seen_links:
            continue
        seen_titles.add(title_key)
        seen_links.add(link_key)
        unique.append(item)

    enabled = set()
    if util.setting_bool("show_bg", True):
        enabled.add("bg")
    if util.setting_bool("show_ru", True):
        enabled.add("ru")
    if not enabled:
        enabled = {"bg", "ru"}
    return [item for item in unique if item["country"] in enabled]


def news_for_country(country):
    items = load_news()
    if country == "all":
        return items
    return [item for item in items if item["country"] == country]


# ------------------------------------------------------------- archive.org

def _archive_params(query, page, rows, sort):
    pairs = [("q", query), ("rows", str(rows)), ("page", str(page)),
             ("output", "json"), ("sort[]", sort)]
    for field in ("identifier", "title", "year", "description", "downloads"):
        pairs.append(("fl[]", field))
    return urlencode(pairs)


def _search(query, page=1, rows=24, sort="downloads desc"):
    url = "https://archive.org/advancedsearch.php?" + _archive_params(
        query, page, rows, sort)
    payload = util.http_json(url, ttl=6 * 3600)
    response = payload.get("response", {})
    docs = response.get("docs", [])
    items = []
    for doc in docs:
        identifier = doc.get("identifier")
        if not identifier:
            continue
        items.append({
            "id": identifier,
            "title": util.strip_html(doc.get("title") or identifier),
            "year": str(doc.get("year") or ""),
            "desc": util.strip_html(doc.get("description") or "")[:700],
            "thumb": "https://archive.org/services/img/" + quote(identifier),
        })
    return {
        "items": items,
        "total": int(response.get("numFound", 0) or 0),
        "page": page,
        "rows": rows,
    }


def archive_search(key, page=1, rows=24):
    cfg = sources()["archive"][key]
    return _search(cfg["query"], page=page, rows=rows,
                   sort=cfg.get("sort", "downloads desc"))


def archive_search_query(query, page=1, rows=24):
    return _search(query, page=page, rows=rows)


def archive_random(key):
    """Връща един случаен елемент от резултатите (за „Сеанс“)."""
    first = archive_search(key, page=1, rows=24)
    total = first["total"]
    if total > 24:
        pages = min(6, max(1, total // 24))
        page = random.randint(1, pages)
        if page != 1:
            try:
                result = archive_search(key, page=page, rows=24)
                if result["items"]:
                    return random.choice(result["items"])
            except Exception:
                pass
    return random.choice(first["items"]) if first["items"] else None


_MEDIA_EXT = (".mp4", ".m4v", ".ogv", ".mkv", ".webm")


def archive_media(identifier):
    """Избира най-подходящия видео файл за даден идентификатор."""
    url = "https://archive.org/metadata/" + quote(identifier)
    payload = util.http_json(url, ttl=7 * 24 * 3600)
    files = payload.get("files", [])
    candidates = []
    for entry in files:
        name = entry.get("name", "")
        lower = name.lower()
        if not lower.endswith(_MEDIA_EXT):
            continue
        if "sample" in lower or "trailer" in lower:
            continue
        try:
            size = int(entry.get("size") or 0)
        except Exception:
            size = 0
        if 0 < size < 3 * 1024 * 1024:
            continue
        if lower.endswith(".ia.mp4"):
            score = 0
        elif lower.endswith(".mp4"):
            score = 1
        elif lower.endswith(".m4v"):
            score = 2
        elif lower.endswith(".webm"):
            score = 3
        elif lower.endswith(".mkv"):
            score = 4
        else:
            score = 5
        candidates.append((score, -size, name, size))
    if not candidates:
        raise RuntimeError("Няма видео файл в този архив")
    candidates.sort()
    _, _, name, size = candidates[0]
    return {
        "url": "https://archive.org/download/%s/%s" % (quote(identifier), quote(name)),
        "name": name,
        "size": size,
        "size_text": util.pretty_size(size),
    }


# ------------------------------------------------------------------ YouTube

_YT_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def youtube_channel(key):
    cfg = None
    for entry in sources()["youtube"]:
        if entry["id"] == key:
            cfg = entry
            break
    if not cfg:
        raise RuntimeError("Непознат канал: %s" % key)
    if cfg.get("user"):
        feed = "https://www.youtube.com/feeds/videos.xml?user=" + cfg["user"]
    else:
        feed = "https://www.youtube.com/feeds/videos.xml?channel_id=" + cfg["channel_id"]
    xml_text = util.http_get(feed, ttl=30 * 60, timeout=15)
    root = ET.fromstring(xml_text)
    items = []
    for entry in root.findall("atom:entry", _YT_NS):
        video_id = entry.findtext("yt:videoId", default="", namespaces=_YT_NS)
        title = entry.findtext("atom:title", default="", namespaces=_YT_NS)
        published = entry.findtext("atom:published", default="", namespaces=_YT_NS)
        description = ""
        thumb = ""
        group = entry.find("media:group", _YT_NS)
        if group is not None:
            description = group.findtext("media:description", default="", namespaces=_YT_NS)
            thumb_node = group.find("media:thumbnail", _YT_NS)
            if thumb_node is not None:
                thumb = thumb_node.get("url", "")
        if not thumb and video_id:
            thumb = "https://i.ytimg.com/vi/%s/hqdefault.jpg" % video_id
        if not video_id:
            continue
        title_lower = title.lower()
        if "#shorts" in title_lower or title_lower.endswith("#short"):
            continue
        items.append({
            "id": video_id,
            "title": title,
            "desc": description[:800],
            "thumb": thumb,
            "ts": _parse_date(published),
            "channel": cfg["name"],
            "channel_id": key,
        })
    return items


def youtube_available():
    try:
        return xbmc.getCondVisibility("System.HasAddon(plugin.video.youtube)")
    except Exception:
        return False
