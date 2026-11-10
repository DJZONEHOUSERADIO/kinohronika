# -*- coding: utf-8 -*-
"""Телевизия: СМОТРИМ (smotrim.ru) и smotret.tv.

СМОТРИМ е официалната платформа на ВГТРК: канали, филми и сериали.
smotret.tv е агрегатор, който вгражда официалните плейъри на телевизиите
(Rutube, OK.ru, 1tv и др.), затова тук се разрешава самият плейър.
"""
import html as htmllib
import re

from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse

import content
import util


def _cfg():
    return content.sources()["tv"]


# ------------------------------------------------------------------ СМОТРИМ

def smotrim_channels():
    return _cfg()["smotrim"]["channels"]


def smotrim_live(channel_id):
    """Връща (hls_url, заглавие) за канал или хвърля разбираема грешка."""
    api = _cfg()["smotrim"]["api"]
    payload = util.http_json("%s/channel/%s" % (api, channel_id), ttl=120)
    data = payload.get("data") or {}
    streams = data.get("streams") or {}
    url = streams.get("m3u8") or streams.get("hls")
    title = data.get("title") or ""
    if not url:
        raise RuntimeError(
            "„%s“ не излъчва извън Русия (геоблокиран достъп)." % (title or "Каналът"))
    return url, title


def _og(html_text, prop):
    match = re.search(
        r'<meta property="og:%s" content="([^"]*)"' % prop, html_text, re.I)
    return htmllib.unescape(match.group(1)) if match else ""


def smotrim_catalog():
    """Филми и сериали от каталога на СМОТРИМ."""
    url = _cfg()["smotrim"]["catalog"]
    page = util.http_get(url, ttl=3600)
    items = []
    for block in page.split('class="card-brand ')[1:]:
        if "card-brand__title" not in block:
            continue
        title_match = re.search(
            r'class="card-brand__title"><a href="/brand/(\d+)" class="card-brand__link">([^<]+)</a>',
            block)
        if not title_match:
            continue
        brand_id, title = title_match.group(1), htmllib.unescape(title_match.group(2)).strip()
        meta_match = re.search(
            r'class="card-brand__meta"><a href="/brand/\d+" class="card-brand__link"><span>(.*?)</span>',
            block, re.S)
        meta = re.sub(r"<[^>]+>", "", meta_match.group(1)) if meta_match else ""
        meta = htmllib.unescape(meta).replace("\xa0", " ").strip()
        image_match = re.search(r'<img[^>]+src="(https://cdn\.smotrim\.ru[^"]+)"', block)
        label_match = re.search(
            r'class="card-brand__label"><a href="/brand/\d+"[^>]*>([^<]+)</a>', block)
        items.append({
            "id": brand_id,
            "title": title,
            "meta": re.sub(r"\s+", " ", meta),
            "label": htmllib.unescape(label_match.group(1)) if label_match else "",
            "thumb": image_match.group(1) if image_match else "",
        })
    # премахваме повторените карти
    unique, seen = [], set()
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
    return unique


def smotrim_brand(brand_id):
    """Връща данни за филм/сериал и списък с епизоди."""
    site = _cfg()["smotrim"]["site"]
    page = util.http_get("%s/brand/%s" % (site, brand_id), ttl=1800)
    raw_title = _og(page, "title")
    title = re.sub(r"^(Сериал|Фильм|Мультфильм|Документальный фильм|Спектакль)\s+", "", raw_title)
    title = re.sub(r"\s*[-–—]\s*смотреть.*$", "", title, flags=re.I).strip()
    description = re.sub(r"^[^\wА-Яа-я]+", "", _og(page, "description")).strip()
    poster = _og(page, "image")

    episodes = []
    seen = set()
    for match in re.finditer(r'href="/video/(\d+)"', page):
        video_id = match.group(1)
        if video_id in seen:
            continue
        window = page[match.start():match.start() + 700]
        label_match = re.search(r"<span[^>]*>([^<]*\d+[^<]*)</span>", window)
        label = htmllib.unescape(label_match.group(1)).strip() if label_match else ""
        duration = re.search(r"(\d+\s*мин)", window)
        seen.add(video_id)
        episodes.append({
            "id": video_id,
            "label": label or ("Епизод %d" % (len(episodes) + 1)),
            "duration": duration.group(1) if duration else "",
        })
    return {
        "title": title or "СМОТРИМ",
        "description": description,
        "poster": poster,
        "episodes": episodes,
    }


def smotrim_video(video_id):
    api = _cfg()["smotrim"]["api"]
    payload = util.http_json("%s/video/%s" % (api, video_id), ttl=120)
    data = payload.get("data") or {}
    streams = data.get("streams") or {}
    url = streams.get("m3u8")
    if not url:
        raise RuntimeError("Видеото не е достъпно (геоблокирано или платено).")
    return url


# ---------------------------------------------------------------- smotret.tv

def smotret_channels():
    site = _cfg()["smotret"]["site"]
    page = util.http_get(site + "/", ttl=6 * 3600)
    channels, seen = [], set()
    for block in page.split('<li data-channel-id="')[1:]:
        slug = block.split('"', 1)[0]
        if not slug or slug in seen:
            continue
        name_match = re.search(r'class="tv_channel_name"[^>]*>([^<]+)<', block[:2500])
        name = htmllib.unescape(name_match.group(1)).strip() if name_match else slug.replace("-", " ")
        seen.add(slug)
        channels.append({
            "slug": slug,
            "name": name,
            "thumb": "%s/images/%s.webp" % (site, slug),
        })
    return channels


def smotret_streams(slug):
    """Return source candidates exactly as the standalone Smotret add-on does."""
    from kinogo.smotret.scraper import SmotretScraper

    site = _cfg()["smotret"]["site"]
    channel_url = "%s/%s" % (site.rstrip("/"), slug)
    return SmotretScraper().get_channel_sources(channel_url)


def smotret_stream(slug, source=None):
    """Resolve the selected smotret.tv source using the bundled resolver."""
    from kinogo.smotret.scraper import SmotretScraper

    site = _cfg()["smotret"]["site"]
    channel_url = "%s/%s" % (site.rstrip("/"), slug)
    return SmotretScraper().get_video_stream(channel_url, source=source)


# ------------------------------------------------------------------- проверка

def probe(url, timeout=8):
    """Проверява дали адресът е достъпен от текущата мрежа."""
    request = Request(url, headers=dict(util.HEADERS, Range="bytes=0-2047"))
    try:
        response = urlopen(request, timeout=timeout)
        code = getattr(response, "status", None) or response.getcode()
        return code in (200, 206)
    except HTTPError as exc:
        return exc.code not in (401, 403, 404)
    except Exception:
        return False
