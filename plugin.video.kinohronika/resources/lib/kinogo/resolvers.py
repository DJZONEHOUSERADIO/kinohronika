# -*- coding: utf-8 -*-
"""Host resolvers for KinoGo embeds (ortified / collaps-style players)."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests
import xbmc

from . import utils

_HLS_RE = re.compile(r'hls\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"', re.I)
_M3U8_RE = re.compile(r"(https?://[^\s\"'\\]+\.m3u8[^\s\"'\\]*)", re.I)
_SEASONS_RE = re.compile(r"seasons\s*:\s*(\[)", re.I)


class ResolveError(Exception):
    pass


def _extract_json_array(text, start_bracket_index):
    """Extract a balanced JSON array starting at '[' index."""
    depth = 0
    in_str = False
    escape = False
    for i in range(start_bracket_index, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start_bracket_index : i + 1]
    return ""


class HostResolvers:
    def __init__(self, session=None, timeout=None):
        self.session = session or requests.Session()
        self.timeout = timeout or utils.get_timeout()
        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": utils.get_base_url() + "/",
        }

    def resolve(self, embed_url, referer=None, season=None, episode=None):
        embed_url = utils.absolute_url(embed_url)
        host = (urlparse(embed_url).netloc or "").lower()
        utils.log(f"Resolve host={host} url={embed_url}")

        if "ortified" in host or "collaps" in host or "apicollaps" in host:
            return self.resolve_ortified(
                embed_url, referer=referer, season=season, episode=episode
            )
        if "stravers" in host:
            return self.resolve_generic_hls(embed_url, referer=referer)

        # Generic: fetch page and hunt for m3u8
        return self.resolve_generic_hls(embed_url, referer=referer)

    def resolve_ortified(self, embed_url, referer=None, season=None, episode=None):
        embed_url = utils.absolute_url(embed_url)
        referer = referer or utils.get_base_url() + "/"
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        html = page.text

        seasons = self.parse_seasons(html)
        if seasons:
            stream = self._pick_episode_stream(seasons, season=season, episode=episode)
            if stream:
                self.last_headers = {
                    "User-Agent": utils.USER_AGENT,
                    "Referer": embed_url,
                    "Origin": f"https://{urlparse(embed_url).netloc}",
                }
                utils.log(f"Ortified episode stream: {stream}")
                return stream

        match = _HLS_RE.search(html)
        if match:
            stream = match.group(1).replace("\\/", "/")
            self.last_headers = {
                "User-Agent": utils.USER_AGENT,
                "Referer": embed_url,
                "Origin": f"https://{urlparse(embed_url).netloc}",
            }
            utils.log(f"Ortified movie stream: {stream}")
            return stream

        found = _M3U8_RE.findall(html.replace("\\/", "/"))
        # Prefer direct CDN over proxy wrappers
        for url in found:
            if "showvid" in url or "x-px" in url:
                continue
            self.last_headers = {
                "User-Agent": utils.USER_AGENT,
                "Referer": embed_url,
            }
            return url
        if found:
            self.last_headers = {
                "User-Agent": utils.USER_AGENT,
                "Referer": embed_url,
            }
            return found[0]

        raise ResolveError("Ortified stream not found")

    def parse_seasons(self, html):
        match = _SEASONS_RE.search(html or "")
        if not match:
            return []
        raw = _extract_json_array(html, match.start(1))
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            utils.log(f"seasons JSON parse failed: {exc}", xbmc.LOGWARNING)
            return []
        if not isinstance(data, list):
            return []
        return data

    def get_seasons_from_embed(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.get_base_url() + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        seasons = self.parse_seasons(page.text)
        result = []
        for season in seasons:
            season_num = season.get("season")
            episodes = []
            for ep in season.get("episodes") or []:
                if season.get("blocked"):
                    continue
                episodes.append(
                    {
                        "episode": str(ep.get("episode") or ""),
                        "title": ep.get("title")
                        or f"S{season_num}E{ep.get('episode')}",
                        "url": (ep.get("hls") or "").replace("\\/", "/"),
                        "id": ep.get("id"),
                    }
                )
            if episodes:
                result.append(
                    {
                        "season": season_num,
                        "episodes": episodes,
                        "blocked": bool(season.get("blocked")),
                    }
                )
        return result

    @staticmethod
    def _pick_episode_stream(seasons, season=None, episode=None):
        if not seasons:
            return ""
        target_season = None
        if season not in (None, ""):
            try:
                season_i = int(season)
            except (TypeError, ValueError):
                season_i = season
            for item in seasons:
                if item.get("season") == season_i or str(item.get("season")) == str(season):
                    target_season = item
                    break
        if target_season is None:
            target_season = seasons[0]

        episodes = target_season.get("episodes") or []
        if not episodes:
            return ""
        if episode not in (None, ""):
            for ep in episodes:
                if str(ep.get("episode")) == str(episode):
                    return (ep.get("hls") or "").replace("\\/", "/")
        return (episodes[0].get("hls") or "").replace("\\/", "/")

    def resolve_generic_hls(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.get_base_url() + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        html = page.text.replace("\\/", "/")
        match = _HLS_RE.search(html)
        if match:
            stream = match.group(1)
        else:
            found = _M3U8_RE.findall(html)
            stream = found[0] if found else ""
        if not stream:
            raise ResolveError(f"No HLS stream in {urlparse(embed_url).netloc}")
        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": embed_url,
        }
        return stream
