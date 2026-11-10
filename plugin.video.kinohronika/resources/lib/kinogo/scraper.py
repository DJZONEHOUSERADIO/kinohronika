# -*- coding: utf-8 -*-
"""Scraper for KinoGo (kinogo.org / kinogo.la mirrors)."""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import quote, urlparse

import requests
import xbmc
from bs4 import BeautifulSoup

from . import utils
from .resolvers import HostResolvers, ResolveError

_ITEM_HREF_RE = re.compile(r"/\d+-[a-z0-9_-]+\.html", re.I)
_PAGE_RE = re.compile(r"/page/(\d+)/?")


class ScraperError(Exception):
    pass


FILM_GENRES = [
    ("Боевики", "/film/boeviki/"),
    ("Комедии", "/film/komedii/"),
    ("Драмы", "/film/dramy/"),
    ("Ужасы", "/film/uzhasy/"),
    ("Триллеры", "/film/trillery/"),
    ("Фантастика", "/film/fantastika/"),
    ("Фэнтези", "/film/fjentjezi/"),
    ("Мелодрамы", "/film/melodramy/"),
    ("Детективы", "/film/detektivy/"),
    ("Приключения", "/film/priklyuchniya/"),
    ("Криминал", "/film/kriminal/"),
    ("Военные", "/film/voennye/"),
    ("Исторические", "/film/istoricheskie/"),
    ("Документальные", "/film/dokumentalnye/"),
    ("Семейные", "/film/semejnye/"),
    ("Русские", "/film/russkie-filmy/"),
    ("Зарубежные", "/film/zarubezhnye-filmy/"),
]

SERIAL_GENRES = [
    ("Русские", "/serial/russkye_serialy/"),
    ("Зарубежные", "/serial/zarubezhnye_serialy/"),
    ("Турецкие", "/serial/tureckie-serialy/"),
    ("Драмы", "/serial/drama/"),
    ("Комедии", "/serial/komediya/"),
    ("Боевики", "/serial/boevik/"),
    ("Триллеры", "/serial/triller/"),
    ("Фантастика", "/serial/fantastik/"),
    ("Детективы", "/serial/detektiv/"),
    ("Криминал", "/serial/kriminall/"),
]


class KinogoScraper:
    def __init__(self):
        self.base = utils.get_base_url()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": utils.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,bg;q=0.6",
                "Referer": self.base + "/",
            }
        )
        self.timeout = utils.get_timeout()
        self.resolvers = HostResolvers(session=self.session, timeout=self.timeout)

    def _get(self, url, **kwargs):
        url = utils.absolute_url(url, base=self.base)
        utils.log(f"GET {url}")
        headers = kwargs.pop("headers", {})
        merged = {
            "User-Agent": utils.USER_AGENT,
            "Referer": self.base + "/",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        merged.update(headers)
        try:
            response = self.session.get(url, headers=merged, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ScraperError(str(exc)) from exc

        if self._is_cf_challenge(response):
            # Switch mirror once and retry
            if self.base == utils.PRIMARY_URL:
                utils.log("Cloudflare on primary — switching to mirror", xbmc.LOGWARNING)
                utils.set_base_url(utils.MIRROR_URL)
                self.base = utils.MIRROR_URL
                self.session.headers["Referer"] = self.base + "/"
                retry_url = utils.absolute_url(
                    urlparse(url).path + (("?" + urlparse(url).query) if urlparse(url).query else ""),
                    base=self.base,
                )
                response = self.session.get(
                    retry_url, headers={**merged, "Referer": self.base + "/"}, timeout=self.timeout
                )
            if self._is_cf_challenge(response):
                raise ScraperError(
                    "Сайтът е зад Cloudflare. Изберете mirror=kinogo.la в настройките."
                )

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScraperError(str(exc)) from exc

        response.encoding = "utf-8"
        return response

    def _post(self, url, data=None, **kwargs):
        url = utils.absolute_url(url, base=self.base)
        utils.log(f"POST {url}")
        headers = kwargs.pop("headers", {})
        merged = {
            "User-Agent": utils.USER_AGENT,
            "Referer": self.base + "/",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        merged.update(headers)
        try:
            response = self.session.post(
                url, data=data, headers=merged, timeout=self.timeout, **kwargs
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScraperError(str(exc)) from exc
        response.encoding = "utf-8"
        return response

    @staticmethod
    def _is_cf_challenge(response):
        if response is None:
            return True
        if response.status_code == 403:
            return True
        text = (response.text or "")[:2000].lower()
        return "just a moment" in text or "cf-browser-verification" in text

    @staticmethod
    def _soup(response):
        text = response.text if hasattr(response, "text") else response.content.decode("utf-8", "replace")
        return BeautifulSoup(text, "html.parser")

    # ------------------------------------------------------------------ list
    def get_listing(self, path, page=1):
        path = path or "/"
        page = max(1, int(page or 1))
        if page > 1:
            if not path.endswith("/"):
                path += "/"
            list_url = f"{path}page/{page}/"
        else:
            list_url = path

        response = self._get(list_url)
        soup = self._soup(response)
        items = self._parse_movie_cards(soup)
        max_page = self._detect_max_page(soup, path)
        return items, max_page

    def search(self, query, page=1):
        query = (query or "").strip()
        if not query:
            return [], 1
        page = max(1, int(page or 1))
        if page > 1:
            # DLE search pagination
            response = self._get(f"/search/{quote(query)}/page/{page}/")
        else:
            response = self._post(
                self.base + "/",
                data={"do": "search", "subaction": "search", "story": query},
            )
        soup = self._soup(response)
        items = self._parse_movie_cards(soup)
        max_page = self._detect_max_page(soup, f"/search/{query}/")
        return items, max_page

    def _parse_movie_cards(self, soup):
        items = []
        seen = set()
        cards = soup.select(".movie")
        if not cards:
            # fallback: any item-like anchors
            for anchor in soup.select("a[href]"):
                href = utils.absolute_url(anchor.get("href") or "", base=self.base)
                if not utils.is_item_url(href) or href in seen:
                    continue
                title = utils.clean_title(anchor.get_text(" ", strip=True))
                if not title or len(title) < 2:
                    continue
                seen.add(href)
                items.append({"title": title, "url": href, "thumb": "", "plot": ""})
            return items

        for card in cards:
            anchor = card.select_one("h2.zagolovki a, .zagolovki a, h2 a, a[href*='.html']")
            if not anchor:
                continue
            href = utils.absolute_url(anchor.get("href") or "", base=self.base)
            if not href or href in seen:
                continue
            if not utils.is_item_url(href) and not _ITEM_HREF_RE.search(href):
                continue
            title = utils.clean_title(anchor.get_text(" ", strip=True) or anchor.get("title") or "")
            if not title:
                continue

            thumb = ""
            img = card.select_one(".movie__info-img img[data-src], .movie__card img[data-src], img[data-src]")
            if not img:
                img = card.select_one(".movie__info-img img, .movie__card img")
            if img:
                candidates = [
                    img.get("data-src") or "",
                    img.get("data-original") or "",
                    img.get("src") or "",
                ]
                for cand in candidates:
                    cand = (cand or "").strip()
                    if not cand:
                        continue
                    low = cand.lower()
                    if any(x in low for x in ("lazy-poster", "noavatar", "plus_fav", "spacer", "blank.")):
                        continue
                    thumb = utils.absolute_url(cand, base=self.base)
                    break

            plot = ""
            desc = card.select_one(".movie__desc, .shorttext, .description")
            if desc:
                plot = desc.get_text(" ", strip=True)

            seen.add(href)
            items.append(
                {
                    "title": title,
                    "url": href,
                    "thumb": thumb,
                    "plot": plot,
                }
            )
        return items

    def _detect_max_page(self, soup, path=""):
        max_page = 1
        for anchor in soup.select("a[href*='/page/']"):
            href = anchor.get("href") or ""
            match = _PAGE_RE.search(href)
            if match:
                max_page = max(max_page, int(match.group(1)))
            text = (anchor.get_text(strip=True) or "").replace("\xa0", " ")
            if text.isdigit():
                max_page = max(max_page, int(text))
        return max_page

    # ------------------------------------------------------------- detail/play
    def get_item_detail(self, item_url):
        item_url = utils.absolute_url(item_url, base=self.base)
        response = self._get(item_url)
        soup = self._soup(response)

        title = ""
        h1 = soup.select_one("h1, .fullstorytitle h1, .zagolovki")
        if h1:
            title = utils.clean_title(h1.get_text(" ", strip=True))
        if not title and soup.title:
            title = utils.clean_title(soup.title.get_text(" ", strip=True))

        thumb = ""
        img = soup.select_one(".poster img, .full-poster img, .movie__info-img img, meta[property='og:image']")
        if img:
            thumb = img.get("content") or img.get("data-src") or img.get("src") or ""
            thumb = utils.absolute_url(thumb, base=self.base)

        plot = ""
        for sel in (".full-text", ".fullstory", ".description", "[itemprop='description']"):
            node = soup.select_one(sel)
            if node:
                plot = node.get_text(" ", strip=True)
                if len(plot) > 40:
                    break

        sources = self._extract_sources(soup, response.text)
        return {
            "title": title,
            "url": item_url,
            "thumb": thumb,
            "plot": plot,
            "sources": sources,
        }

    def _extract_sources(self, soup, html):
        sources = []
        seen = set()

        # Pair tab labels with boxes when possible
        labels = []
        for li in soup.select("#preroll ~ ul li, .tabs li, ul.tabs li"):
            text = li.get_text(" ", strip=True)
            if text:
                labels.append(text)

        boxes = soup.select("#preroll .box, .box iframe, iframe[data-src], iframe[src]")
        # Prefer dedicated boxes
        box_nodes = soup.select("#preroll .box")
        if box_nodes:
            for idx, box in enumerate(box_nodes):
                iframe = box.select_one("iframe")
                if not iframe:
                    continue
                src = iframe.get("data-src") or iframe.get("src") or ""
                src = utils.absolute_url(html_lib.unescape(src), base=self.base)
                if not src or src in seen:
                    continue
                if "trailer" in src.lower():
                    label = labels[idx] if idx < len(labels) else "Trailer"
                else:
                    label = labels[idx] if idx < len(labels) else f"Player {idx + 1}"
                if "ortified" not in src and "stravers" not in src and "collaps" not in src:
                    # keep unknown embeds too
                    pass
                seen.add(src)
                sources.append({"label": label, "embed": src})
        else:
            for idx, iframe in enumerate(soup.select("iframe")):
                src = iframe.get("data-src") or iframe.get("src") or ""
                src = utils.absolute_url(html_lib.unescape(src), base=self.base)
                if not src or src in seen:
                    continue
                if "trailer" in src.lower():
                    label = "Trailer"
                else:
                    label = f"Player {idx + 1}"
                seen.add(src)
                sources.append({"label": label, "embed": src})

        # Regex fallback for encoded embeds
        for match in re.finditer(
            r"""(?:src|data-src)\s*=\s*["']((?:https?:)?//(?:api\.)?(?:ortified|stravers|collaps)[^"']+)["']""",
            html,
            re.I,
        ):
            src = utils.absolute_url(html_lib.unescape(match.group(1)), base=self.base)
            if src and src not in seen:
                seen.add(src)
                label = "Trailer" if "trailer" in src.lower() else f"Player {len(sources) + 1}"
                sources.append({"label": label, "embed": src})

        # Prefer non-trailer first
        sources.sort(key=lambda item: 1 if "trailer" in (item.get("embed") or "").lower() else 0)
        return sources

    def get_seasons(self, item_url, embed_url=None):
        item_url = utils.absolute_url(item_url, base=self.base)
        if not embed_url:
            detail = self.get_item_detail(item_url)
            sources = [s for s in detail.get("sources") or [] if "trailer" not in s["embed"].lower()]
            if not sources:
                raise ScraperError("Няма плейър за този сериал")
            embed_url = sources[0]["embed"]
        return self.resolvers.get_seasons_from_embed(embed_url, referer=item_url)

    def get_stream(self, item_url, embed=None, season=None, episode=None):
        item_url = utils.absolute_url(item_url, base=self.base)
        detail = self.get_item_detail(item_url)
        sources = detail.get("sources") or []
        if embed:
            sources = [s for s in sources if s["embed"] == embed] or [
                {"label": "Selected", "embed": embed}
            ]
        if not sources:
            raise ScraperError("Няма намерени видео източници")

        last_error = None
        for source in sources:
            if "trailer" in (source.get("embed") or "").lower() and not embed:
                continue
            try:
                stream = self.resolvers.resolve(
                    source["embed"],
                    referer=item_url,
                    season=season,
                    episode=episode,
                )
                if stream:
                    return {
                        "url": stream,
                        "headers": dict(self.resolvers.last_headers or {}),
                        "label": source.get("label") or "",
                        "title": detail.get("title") or "",
                    }
            except (ResolveError, requests.RequestException) as exc:
                last_error = exc
                utils.log(f"Source failed ({source.get('label')}): {exc}", xbmc.LOGWARNING)

        raise ScraperError(str(last_error) if last_error else "Unable to resolve stream")
