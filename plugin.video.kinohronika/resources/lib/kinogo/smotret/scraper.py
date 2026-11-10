# -*- coding: utf-8 -*-
"""Scraper for https://smotret.tv/ — categories, channels and live streams."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
import xbmc
from bs4 import BeautifulSoup

from . import utils
from .resolvers import HostResolvers, ResolveError


class ScraperError(Exception):
    pass


class SmotretScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": utils.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        self.timeout = utils.get_timeout()
        self.resolvers = HostResolvers(session=self.session, timeout=self.timeout)

    def _get(self, url, referer=None, **kwargs):
        url = utils.absolute_url(url)
        utils.log(f"GET {url}")
        headers = kwargs.pop("headers", {})
        merged = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
        }
        merged.update(headers)
        response = self.session.get(url, headers=merged, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response

    def get_categories(self):
        cached = utils.cache_get("categories")
        if cached:
            return cached

        soup = BeautifulSoup(self._get(utils.BASE_URL + "/").content, "html.parser")
        categories = []
        seen = set()
        for anchor in soup.select("#categoriesList a[href], .category_list a[href]"):
            path = anchor.get("href") or ""
            if not path.startswith("/") or not path.endswith("/"):
                continue
            if not utils.is_category_path(path):
                continue
            if path in seen:
                continue
            title = utils.clean_channel_title(anchor.get_text(" ", strip=True))
            title = re.sub(r"^∷\s*", "", title).strip()
            if not title:
                continue
            seen.add(path)
            categories.append(
                {
                    "title": title,
                    "path": path,
                    "url": utils.absolute_url(path),
                }
            )

        if categories:
            utils.cache_set("categories", categories)
        return categories

    def get_logo_map(self):
        cached = utils.cache_get("logo_map")
        if cached:
            return cached

        soup = BeautifulSoup(self._get(utils.BASE_URL + "/").content, "html.parser")
        logos = {}
        for anchor in soup.select("a[href]"):
            href = anchor.get("href") or ""
            if not re.match(r"^/[a-z0-9-]+$", href):
                continue
            img = anchor.select_one("img")
            if img and img.get("src"):
                slug = href.strip("/")
                logos[slug] = utils.absolute_url(img.get("src"))

        if logos:
            utils.cache_set("logo_map", logos)
        return logos

    def get_main_channels(self):
        cached = utils.cache_get("main_channels")
        if cached:
            return cached

        soup = BeautifulSoup(self._get(utils.BASE_URL + "/").content, "html.parser")
        logos = self.get_logo_map()
        channels = []
        seen = set()

        for anchor in soup.select(".channels a.vest[href]"):
            href = anchor.get("href") or ""
            if not re.match(r"^/[a-z0-9-]+$", href):
                continue
            slug = href.strip("/")
            if slug in seen:
                continue
            title = utils.clean_channel_title(anchor.get("title") or "")
            if not title:
                continue
            seen.add(slug)
            channels.append(
                {
                    "title": title,
                    "slug": slug,
                    "url": utils.absolute_url(href),
                    "thumb": logos.get(slug, ""),
                }
            )

        if channels:
            utils.cache_set("main_channels", channels)
        return channels

    def get_category_channels(self, category_path):
        category_path = category_path or "/"
        if not category_path.startswith("/"):
            category_path = "/" + category_path
        if not category_path.endswith("/"):
            category_path += "/"

        cache_key = "category_" + category_path.strip("/").replace("/", "_")
        cached = utils.cache_get(cache_key)
        if cached:
            return cached

        soup = BeautifulSoup(self._get(utils.absolute_url(category_path)).content, "html.parser")
        logos = self.get_logo_map()
        channels = []
        seen = set()
        prefix = category_path.rstrip("/") + "/"

        for anchor in soup.select("a[href]"):
            href = anchor.get("href") or ""
            if not href.startswith(prefix):
                continue
            rel = href[len(prefix) :].strip("/")
            if not rel or "/" in rel:
                continue

            title = utils.clean_channel_title(anchor.get("title") or "")
            if not title:
                img = anchor.select_one("img")
                if img:
                    title = utils.clean_channel_title(img.get("alt") or "")
            if not title:
                title = utils.clean_channel_title(anchor.get_text(" ", strip=True))
            if not title:
                continue

            url = utils.absolute_url(href)
            if url in seen:
                continue
            seen.add(url)

            slug = rel
            thumb = logos.get(slug, "")
            if not thumb:
                img = anchor.select_one("img")
                if img and img.get("src"):
                    thumb = utils.absolute_url(img.get("src"))

            channels.append(
                {
                    "title": title,
                    "slug": slug,
                    "url": url,
                    "thumb": thumb,
                    "category": category_path.strip("/"),
                }
            )

        channels.sort(key=lambda item: item["title"].lower())
        if channels:
            utils.cache_set(cache_key, channels)
        return channels

    def search_channels(self, query):
        query = (query or "").strip().lower()
        if not query:
            return []

        all_channels = []
        seen_urls = set()

        for channel in self.get_main_channels():
            if channel["url"] not in seen_urls:
                seen_urls.add(channel["url"])
                all_channels.append(channel)

        for category in self.get_categories():
            for channel in self.get_category_channels(category["path"]):
                if channel["url"] not in seen_urls:
                    seen_urls.add(channel["url"])
                    all_channels.append(channel)

        return [
            channel
            for channel in all_channels
            if query in channel["title"].lower() or query in channel.get("slug", "").lower()
        ]

    def get_channel_sources(self, channel_url):
        channel_url = utils.absolute_url(channel_url)
        if not channel_url:
            raise ScraperError("Missing channel URL")

        response = self._get(channel_url)
        soup = BeautifulSoup(response.content, "html.parser")
        player_iframe = None
        for iframe in soup.select("iframe"):
            src = iframe.get("src") or ""
            if src:
                player_iframe = utils.absolute_url(src, base=channel_url)
                break
        if not player_iframe:
            raise ScraperError("Player iframe not found on channel page")

        return self._extract_sources_from_player(player_iframe, referer=channel_url)

    def _extract_sources_from_player(self, player_url, referer):
        response = self._get(player_url, referer=referer)
        html = response.text
        sources = []
        seen = set()

        def add_source(label, url, source_type):
            url = utils.absolute_url(url)
            if not url or url in seen:
                return
            seen.add(url)
            sources.append({"label": label, "url": url, "type": source_type})

        for stream in self.resolvers.extract_direct_streams(html):
            add_source(utils.host_label(stream), stream, "direct")

        soup = BeautifulSoup(html, "html.parser")
        for iframe in soup.select("iframe"):
            src = iframe.get("src") or ""
            if not src:
                continue
            embed = utils.absolute_url(src, base=player_url)
            add_source(utils.host_label(embed), embed, "embed")

        mirror_pages = [player_url]
        for anchor in soup.select(".menu a[href]"):
            href = anchor.get("href") or ""
            if not href.endswith(".html"):
                continue
            mirror_pages.append(utils.absolute_url(href, base=player_url))

        for mirror_url in mirror_pages[1:]:
            try:
                mirror_response = self._get(mirror_url, referer=referer)
                mirror_html = mirror_response.text
                for stream in self.resolvers.extract_direct_streams(mirror_html):
                    add_source(f"{utils.host_label(stream)} mirror", stream, "direct")
                mirror_soup = BeautifulSoup(mirror_html, "html.parser")
                for iframe in mirror_soup.select("iframe"):
                    src = iframe.get("src") or ""
                    if not src:
                        continue
                    embed = utils.absolute_url(src, base=mirror_url)
                    label = f"{utils.host_label(embed)} mirror"
                    add_source(label, embed, "embed")
            except requests.RequestException as exc:
                utils.log(f"Mirror fetch failed ({mirror_url}): {exc}", xbmc.LOGWARNING)

        if not sources:
            raise ScraperError("No playable sources found for this channel")
        return sources

    def get_video_stream(self, channel_url, source=None):
        channel_url = utils.absolute_url(channel_url)
        sources = self.get_channel_sources(channel_url)
        if source:
            picked = next((item for item in sources if item["url"] == source), None)
            if not picked:
                raise ScraperError("Selected source not found")
            sources = [picked]

        last_error = None
        for item in sources:
            try:
                stream = self.resolvers.resolve(
                    item["url"],
                    referer=channel_url,
                    source_type=item["type"],
                )
                if stream:
                    return {
                        "url": stream,
                        "headers": dict(self.resolvers.last_headers or {}),
                        "label": item["label"],
                    }
            except (ResolveError, requests.RequestException) as exc:
                last_error = exc
                utils.log(
                    f"Source resolve failed ({item['label']}): {exc}",
                    xbmc.LOGWARNING,
                )

        raise ScraperError(
            str(last_error) if last_error else "Unable to resolve video stream"
        )
