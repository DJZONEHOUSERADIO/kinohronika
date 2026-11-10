# -*- coding: utf-8 -*-
"""Host resolvers for KinoGo embeds (ortified / collaps-style players)."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

import requests
import xbmc
from bs4 import BeautifulSoup

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

    @staticmethod
    def supports_stream_choice(embed_url):
        host = (urlparse(embed_url or "").netloc or "").lower().split(":", 1)[0]
        return (host == "vkvideo.ru" or host.endswith(".vkvideo.ru") or
                host == "vk.com" or host.endswith(".vk.com") or
                host == "ok.ru" or host.endswith(".ok.ru") or
                host == "odnoklassniki.ru" or host.endswith(".odnoklassniki.ru"))

    @staticmethod
    def _media_url(value):
        if not isinstance(value, str):
            return False
        value = html.unescape(value.strip()).replace("\\/", "/")
        if value.startswith("//"):
            value = "https:" + value
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https", "rtmp", "rtmps") and bool(parsed.netloc)

    @staticmethod
    def _stream_label(name, url, height=None):
        name = str(name or "").strip()
        if height:
            return "%sp · %s" % (height, name or "Видео")
        if re.search(r"\d{3,4}p", name, re.I):
            return name
        path = urlparse(url).path.lower()
        if path.endswith(".m3u8"):
            return name or "HLS · адаптивен поток"
        if path.endswith(".mpd"):
            return name or "MPEG-DASH · адаптивен поток"
        if path.endswith((".mp4", ".m4v", ".webm")):
            return name or "MP4 видео"
        return name or "Видео поток"

    @staticmethod
    def _json_objects(text):
        decoder = json.JSONDecoder()
        found = []
        seen = set()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except (ValueError, TypeError):
                continue
            if isinstance(value, (dict, list)):
                marker = (index, type(value))
                if marker not in seen:
                    found.append(value)
                    seen.add(marker)
            if len(found) >= 300:
                break
        return found

    @staticmethod
    def _add_stream(streams, url, label="", height=None, headers=None,
                    media_type=None, allow_unknown=False):
        if not HostResolvers._media_url(url):
            return
        url = html.unescape(url.strip()).replace("\\/", "/").replace("\\u0026", "&")
        if url.startswith("//"):
            url = "https:" + url
        parsed = urlparse(url)
        path = parsed.path.lower()
        if path.endswith(".m3u8"):
            media_type = "hls"
        elif path.endswith(".mpd"):
            media_type = "mpd"
        elif parsed.scheme in ("rtmp", "rtmps"):
            media_type = "rtmp"
        elif path.endswith((".mp4", ".m4v", ".webm")):
            media_type = "mp4"
        elif not (allow_unknown and media_type in ("hls", "mpd", "mp4", "rtmp")):
            return
        label = HostResolvers._stream_label(label, url, height)
        if not any(item["url"] == url for item in streams):
            streams.append({"url": url, "label": label, "headers": dict(headers or {}),
                            "type": media_type or "mp4"})

    @classmethod
    def _collect_streams(cls, value, streams, context=""):
        if isinstance(value, dict):
            context_l = str(context).lower()
            if context_l in ("playerurls", "videos", "streams", "formats"):
                candidate = value.get("url") or value.get("src")
                if candidate:
                    label = (value.get("name") or value.get("type") or
                             value.get("quality") or value.get("format_id") or "")
                    fmt_type = str(value.get("type") or value.get("format_id") or "").lower()
                    height = value.get("height")
                    if not height:
                        resolution = re.search(r"(?:url|cache)(\d+)", fmt_type)
                        height = resolution.group(1) if resolution else None
                    media_type = "hls" if "hls" in fmt_type else ("mpd" if "dash" in fmt_type or "mpd" in fmt_type else "mp4")
                    cls._add_stream(streams, candidate, label, height, media_type=media_type, allow_unknown=True)
            for key, child in value.items():
                key_l = str(key).lower()
                if isinstance(child, str):
                    if re.match(r"^(?:url|cache)\d+$", key_l):
                        height = re.search(r"\d+", key_l)
                        cls._add_stream(streams, child, key_l, height.group(0) if height else None,
                                        media_type="mp4", allow_unknown=True)
                    elif key_l in {
                        "hls", "dash", "hlsurl", "dashurl", "hlsmanifesturl",
                        "ondemandhls", "ondemanddash", "hlsmasterplaylisturl",
                        "url", "src", "stream", "streamurl", "videourl",
                    }:
                        media_type = "hls" if "hls" in key_l else ("mpd" if "dash" in key_l else None)
                        cls._add_stream(streams, child, key_l, media_type=media_type,
                                        allow_unknown=media_type is not None)
                    elif key_l in ("metadata", "metadataembedded") and child.lstrip().startswith(("{", "[")):
                        try:
                            cls._collect_streams(json.loads(child), streams, key_l)
                        except ValueError:
                            pass
                elif isinstance(child, (dict, list)):
                    cls._collect_streams(child, streams, key_l)
        elif isinstance(value, list):
            for child in value:
                cls._collect_streams(child, streams, context)

    @staticmethod
    def _hls_variants(manifest_url, body):
        variants = []
        pending = None
        for line in (body or "").splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                attrs = {}
                for match in re.finditer(r'([A-Z0-9-]+)=((?:"[^"]*")|[^,]*)', line.split(":", 1)[1]):
                    attrs[match.group(1)] = match.group(2).strip().strip('"')
                pending = attrs
                continue
            if not line or line.startswith("#") or pending is None:
                continue
            resolved = urljoin(manifest_url, line)
            base = urlparse(manifest_url)
            child = urlparse(resolved)
            if not child.query and base.query and not line.startswith(("http://", "https://", "//")):
                child = child._replace(query=base.query)
                resolved = urlunparse(child)
            resolution = pending.get("RESOLUTION", "")
            height = None
            res_match = re.search(r"\d+[xX](\d+)", resolution)
            if res_match:
                height = res_match.group(1)
            bandwidth = pending.get("AVERAGE-BANDWIDTH") or pending.get("BANDWIDTH")
            name = pending.get("NAME") or ("HLS" + (" %sp" % height if height else ""))
            if bandwidth:
                try:
                    name += " · %.1f Mbps" % (int(bandwidth) / 1000000.0)
                except (TypeError, ValueError):
                    pass
            variants.append({"url": resolved, "label": name, "height": height})
            pending = None
        return variants

    def get_streams(self, embed_url, referer=None):
        """Return public direct/HLS/DASH variants advertised by a VK or OK page."""
        embed_url = utils.absolute_url(embed_url)
        if not self.supports_stream_choice(embed_url):
            raise ResolveError("Неподдържан VK/OK адрес")
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or embed_url,
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8,bg;q=0.6",
        }
        try:
            page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
            page.raise_for_status()
        except requests.RequestException as exc:
            raise ResolveError("Неуспешно зареждане на VK/OK плейъра: %s" % exc) from exc

        page_url = getattr(page, "url", None) or embed_url
        body = html.unescape(page.text or "").replace("\\/", "/").replace("\\u0026", "&")
        objects = self._json_objects(body)
        streams = []
        for obj in objects:
            self._collect_streams(obj, streams)

        # OK embeds keep metadata in a data-options JSON object. Some variants
        # provide metadataUrl instead of inline metadata; fetch it with the
        # player location parameter as the site expects.
        if "ok.ru" in urlparse(page_url).netloc or "odnoklassniki.ru" in urlparse(page_url).netloc:
            soup = BeautifulSoup(body, "html.parser")
            player = None
            for node in soup.find_all(attrs={"data-options": True}):
                raw = html.unescape(node.get("data-options") or "")
                if "flashvars" in raw or "metadataUrl" in raw:
                    try:
                        player = json.loads(raw)
                        break
                    except ValueError:
                        continue
            flashvars = (player or {}).get("flashvars") or {}
            metadata_url = flashvars.get("metadataUrl")
            if metadata_url and not flashvars.get("metadata"):
                try:
                    metadata_response = self.session.post(
                        urljoin(page_url, unquote(metadata_url)),
                        data={"st.location": flashvars.get("location", "")},
                        headers={**headers, "Referer": page_url},
                        timeout=self.timeout,
                    )
                    metadata_response.raise_for_status()
                    objects.append(metadata_response.json())
                    self._collect_streams(objects[-1], streams)
                except (requests.RequestException, ValueError) as exc:
                    utils.log("OK metadata request failed: %s" % exc, xbmc.LOGWARNING)

        # Catch escaped public stream URLs that are present in older player payloads.
        for raw_url in re.findall(r"https?://[^\s\"'<>\\]+", body):
            candidate = raw_url.rstrip(",);]")
            if re.search(r"\.(?:m3u8|mpd|mp4|m4v|webm)(?:[?#]|$)", candidate, re.I):
                self._add_stream(streams, candidate, "")

        # Provider URLs can require their player page as the HTTP referer.
        for stream in streams:
            stream["headers"].setdefault("User-Agent", utils.USER_AGENT)
            stream["headers"].setdefault("Referer", page_url)

        # Expand HLS master playlists into explicit quality choices. Keep the
        # master as an adaptive fallback when its variants cannot be read.
        expanded = []
        for stream in streams:
            path = urlparse(stream["url"]).path.lower()
            if stream.get("type") != "hls" and not path.endswith(".m3u8"):
                expanded.append(stream)
                continue
            try:
                manifest = self.session.get(
                    stream["url"], headers={**headers, **stream["headers"], "Referer": page_url},
                    timeout=self.timeout,
                )
                manifest.raise_for_status()
                variants = self._hls_variants(stream["url"], manifest.text)
            except requests.RequestException as exc:
                utils.log("HLS variant lookup failed: %s" % exc, xbmc.LOGWARNING)
                variants = []
            if variants:
                for variant in variants:
                    self._add_stream(expanded, variant["url"], variant["label"],
                                     variant.get("height"), {"User-Agent": utils.USER_AGENT, "Referer": page_url},
                                     media_type="hls")
            else:
                expanded.append(stream)

        if not expanded:
            raise ResolveError("VK/OK не предостави достъпен видео поток. Възможни са ограничен достъп или неподдържан плейър.")
        expanded.sort(key=lambda item: (int(re.search(r"(\d{3,4})p", item["label"]).group(1))
                                        if re.search(r"(\d{3,4})p", item["label"]) else 0,
                                        ".m3u8" in item["url"].lower()), reverse=True)
        return expanded

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
