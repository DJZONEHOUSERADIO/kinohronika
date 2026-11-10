# -*- coding: utf-8 -*-
"""Host resolvers for smotret.tv embeds."""

from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import parse_qs, urlparse

import requests
import xbmc

from . import utils

_M3U8_RE = re.compile(r"(https?://[^\s\"'\\]+\.m3u8[^\s\"'\\]*)", re.I)
_STREAMS_RE = re.compile(r"var\s+streams\s*=\s*\[([^\]]+)\]", re.I)
_MEDIAVITRINA_BALANCER_RE = re.compile(
    r"default_2026/([a-z0-9_+-]+)/streams", re.I
)


class ResolveError(Exception):
    pass


class HostResolvers:
    def __init__(self, session=None, timeout=None):
        self.session = session or requests.Session()
        self.timeout = timeout or utils.get_timeout()
        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": utils.BASE_URL + "/",
        }

    def resolve(self, source_url, referer=None, source_type="embed"):
        source_url = utils.absolute_url(source_url)
        referer = referer or utils.BASE_URL + "/"
        utils.log(f"Resolve type={source_type} url={source_url}")

        if source_type == "direct":
            return self.resolve_direct(source_url, referer=referer)

        host = (urlparse(source_url).netloc or "").lower()
        if "ok.ru" in host or "odnoklassniki.ru" in host:
            return self.resolve_okru(source_url, referer=referer)
        if "mediavitrina.ru" in host:
            return self.resolve_mediavitrina(source_url, referer=referer)
        if "smotrim.ru" in host or "embed.smotrim" in host:
            return self.resolve_smotrim_channel(source_url, referer=referer)
        if "vk.com" in host or "vkvideo.ru" in host or "vk.ru" in host:
            return self.resolve_vk(source_url, referer=referer)
        if "rutube.ru" in host:
            return self.resolve_rutube(source_url, referer=referer)
        if "1tv.ru" in host:
            return self.resolve_1tv(source_url, referer=referer)
        if ".m3u8" in source_url.lower() or ".mp4" in source_url.lower():
            return self.resolve_direct(source_url, referer=referer)

        raise ResolveError(f"Unsupported source: {host or source_url}")

    def resolve_direct(self, stream_url, referer=None):
        stream_url = utils.absolute_url(stream_url)
        if stream_url.startswith("/"):
            raise ResolveError("Invalid relative stream URL")
        if "/error.m3u8" in stream_url:
            raise ResolveError("Stream unavailable")
        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
        }
        utils.log(f"Direct stream: {stream_url}")
        return stream_url

    def resolve_okru(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        mid = None
        match = re.search(r"/videoembed/(\d+)", embed_url)
        if match:
            mid = match.group(1)
        else:
            qs = parse_qs(urlparse(embed_url).query)
            mid = (qs.get("mid") or [None])[0]
        if not mid:
            raise ResolveError("OK.ru video id not found")

        page_url = f"https://ok.ru/videoembed/{mid}"
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        page = self.session.get(page_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        opts_m = re.search(r'data-options=["\']([^"\']+)["\']', page.text)
        if not opts_m:
            raise ResolveError("OK.ru player options missing")
        options = json.loads(html_lib.unescape(opts_m.group(1)))
        flashvars = options.get("flashvars") or {}
        if isinstance(flashvars, str):
            flashvars = json.loads(flashvars)
        metadata = flashvars.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(metadata, dict):
            raise ResolveError("OK.ru metadata missing")

        stream = (
            metadata.get("hlsMasterPlaylistUrl")
            or metadata.get("hlsPlaybackMasterPlaylistUrl")
            or metadata.get("hlsManifestUrl")
            or metadata.get("ondemandHls")
            or ""
        )
        if not stream:
            for quality in ("full", "hd", "sd", "low", "lowest", "mobile"):
                for item in metadata.get("videos") or []:
                    if item.get("name") == quality and item.get("url"):
                        stream = item["url"]
                        break
                if stream:
                    break
        if not stream:
            raise ResolveError("OK.ru stream URL missing")

        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": "https://ok.ru/",
            "Origin": "https://ok.ru",
        }
        utils.log(f"OK.ru resolved: {stream}")
        return stream

    def resolve_mediavitrina(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
            "Origin": "https://player.mediavitrina.ru",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        html = page.text

        balancer_slug = ""
        match = _MEDIAVITRINA_BALANCER_RE.search(html)
        if match:
            balancer_slug = match.group(1)
        if not balancer_slug:
            path_parts = urlparse(embed_url).path.strip("/").split("/")
            if "smotret_tv_web" in path_parts:
                idx = path_parts.index("smotret_tv_web")
                candidates = [path_parts[idx - 1]] if idx > 0 else []
                candidates.extend(path_parts)
                for candidate in candidates:
                    if not candidate or candidate == "smotret_tv_web":
                        continue
                    slug = re.sub(r"_v\d+$", "", candidate)
                    api = self._mediavitrina_api(slug)
                    if self._mediavitrina_api_ok(api, embed_url):
                        balancer_slug = slug
                        break
        if not balancer_slug:
            raise ResolveError("MediaVitrina balancer slug not found")

        api = self._mediavitrina_api(balancer_slug)
        response = self.session.get(
            api,
            headers={
                "User-Agent": utils.USER_AGENT,
                "Referer": embed_url,
                "Origin": "https://player.mediavitrina.ru",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        stream = ""
        for key in ("hls", "hlsp", "mpdp"):
            values = payload.get(key) or []
            if values:
                stream = values[0]
                break
        if not stream:
            raise ResolveError("MediaVitrina stream missing")

        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": embed_url,
            "Origin": "https://player.mediavitrina.ru",
        }
        utils.log(f"MediaVitrina resolved: {stream}")
        return stream

    def _mediavitrina_api(self, slug):
        return (
            "https://media.mediavitrina.ru/balancer/v3/default_2026/"
            f"{slug}/streams.json?application_id=smotret_tv_web"
            "&player_referer_hostname=smotret.tv&egress_version_id=14862273"
        )

    def _mediavitrina_api_ok(self, api, referer):
        try:
            response = self.session.get(
                api,
                headers={
                    "User-Agent": utils.USER_AGENT,
                    "Referer": referer,
                    "Origin": "https://player.mediavitrina.ru",
                },
                timeout=self.timeout,
            )
            if not response.ok:
                return False
            payload = response.json()
            return bool((payload.get("hls") or payload.get("hlsp") or payload.get("mpdp")))
        except Exception:  # noqa: BLE001
            return False

    def resolve_smotrim_channel(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        channel_id = ""
        match = re.search(r"/channel/id/(\d+)", embed_url)
        if match:
            channel_id = match.group(1)
        if not channel_id:
            raise ResolveError("Smotrim channel id not found")

        api = f"https://player-api.smotrim.ru/api/v1/channel/{channel_id}"
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": "https://embed.smotrim.ru/",
            "Origin": "https://embed.smotrim.ru",
            "Accept": "application/json",
        }
        response = self.session.get(api, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        streams = data.get("streams") or {}
        stream = streams.get("m3u8") or streams.get("http") or ""
        if not stream:
            raise ResolveError("Smotrim stream missing")

        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": "https://embed.smotrim.ru/",
            "Origin": "https://embed.smotrim.ru",
        }
        utils.log(f"Smotrim resolved: {stream}")
        return stream

    def resolve_vk(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        if "vk.com/video_ext.php" in embed_url:
            embed_url = embed_url.replace(
                "vk.com/video_ext.php", "vkvideo.ru/video_ext.php"
            )
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        page = self.session.get(embed_url, headers=headers, timeout=self.timeout)
        page.raise_for_status()
        html = page.text

        stream = ""
        for key in ("url1080", "url720", "url480", "url360", "url240"):
            match = re.search(rf'"{key}"\s*:\s*"(https?:[^"]+)"', html)
            if match:
                stream = match.group(1).replace("\\/", "/")
                break
        if not stream:
            match = re.search(r'"hls"\s*:\s*"(https?:[^"]+)"', html)
            if match:
                stream = match.group(1).replace("\\/", "/")
        if not stream:
            found = _M3U8_RE.findall(html.replace("\\/", "/"))
            if found:
                stream = found[0]
        if not stream:
            raise ResolveError("VK stream not found")

        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": "https://vk.com/",
            "Origin": "https://vk.com",
        }
        utils.log(f"VK resolved: {stream}")
        return stream

    def resolve_rutube(self, embed_url, referer=None):
        embed_url = utils.absolute_url(embed_url)
        match = re.search(r"(?:embed|video)/([0-9a-f]{32})", embed_url, re.I)
        if not match:
            match = re.search(r"/video/([0-9a-f]{32})", embed_url, re.I)
        if not match:
            raise ResolveError("Rutube id not found")
        video_id = match.group(1)

        api = f"https://rutube.ru/api/play/options/{video_id}/"
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
            "Accept": "application/json",
        }
        response = self.session.get(
            api,
            headers=headers,
            params={"no_404": "true", "referer": referer or utils.BASE_URL},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            page = self.session.get(
                f"https://rutube.ru/play/embed/{video_id}",
                headers={
                    "User-Agent": utils.USER_AGENT,
                    "Referer": referer or utils.BASE_URL + "/",
                },
                timeout=self.timeout,
            )
            page.raise_for_status()
            found = _M3U8_RE.findall(page.text.replace("\\/", "/"))
            if not found:
                raise ResolveError(f"Rutube unavailable ({response.status_code})")
            stream = found[0]
        else:
            data = response.json()
            balancer = data.get("video_balancer") or {}
            stream = balancer.get("m3u8") or balancer.get("default") or ""
            if not stream:
                raise ResolveError("Rutube m3u8 missing")

        self.last_headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": "https://rutube.ru/",
            "Origin": "https://rutube.ru",
        }
        utils.log(f"Rutube resolved: {stream}")
        return stream

    def resolve_1tv(self, embed_url, referer=None):
        """1TV live embeds are JS-heavy; try the public live chooser page."""
        embed_url = utils.absolute_url(embed_url)
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": referer or utils.BASE_URL + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        candidates = [embed_url]
        if "interactive.html" in embed_url:
            candidates.append("https://static.1tv.ru/eump/embeds/1tv_live.html")
        candidates.append("https://static.1tv.ru/eump/embeds/public_live_chooser.html")

        last_error = None
        for url in candidates:
            try:
                page = self.session.get(url, headers=headers, timeout=self.timeout)
                page.raise_for_status()
                found = _M3U8_RE.findall(page.text.replace("\\/", "/"))
                if found:
                    stream = found[0]
                    self.last_headers = {
                        "User-Agent": utils.USER_AGENT,
                        "Referer": "https://www.1tv.ru/",
                        "Origin": "https://www.1tv.ru",
                    }
                    utils.log(f"1TV resolved: {stream}")
                    return stream
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        raise ResolveError(
            str(last_error) if last_error else "1TV stream not found — try another mirror"
        )

    @staticmethod
    def extract_direct_streams(html):
        match = _STREAMS_RE.search(html or "")
        if not match:
            return []
        streams = []
        for item in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            url = utils.absolute_url(item)
            if not url or url.startswith("/error"):
                continue
            if ".m3u8" in url.lower() or ".mp4" in url.lower():
                streams.append(url)
        return streams
