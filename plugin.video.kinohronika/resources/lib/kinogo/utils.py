# -*- coding: utf-8 -*-
"""Shared helpers for plugin.video.kinogo."""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_ICON = os.path.join(ADDON.getAddonInfo("path"), "resources", "lib", "kinogo", "icon.png")
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

PRIMARY_URL = "https://kinogo.org"
MIRROR_URL = "https://kinogo.la"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_active_base = None


def log(message, level=xbmc.LOGINFO):
    debug = ADDON.getSettingBool("debug")
    if level >= xbmc.LOGERROR or debug:
        xbmc.log(f"[{ADDON_ID}] {message}", level)


def get_string(string_id):
    return ADDON.getLocalizedString(string_id)


def get_timeout():
    try:
        return max(10, int(ADDON.getSetting("timeout") or 30))
    except (TypeError, ValueError):
        return 30


def get_cache_ttl_seconds():
    try:
        minutes = int(ADDON.getSetting("cache_ttl") or 30)
    except (TypeError, ValueError):
        minutes = 30
    return max(0, minutes) * 60


def get_mirror_setting():
    return (ADDON.getSetting("mirror") or "auto").strip().lower()


def get_base_url(force_refresh=False):
    """Resolve working base URL (org may be behind Cloudflare)."""
    global _active_base
    if _active_base and not force_refresh:
        return _active_base

    choice = get_mirror_setting()
    if choice == "kinogo.org":
        _active_base = PRIMARY_URL
        return _active_base
    if choice == "kinogo.la":
        _active_base = MIRROR_URL
        return _active_base

    # auto: prefer cached working mirror, else probe
    cached = cache_get("working_base")
    if cached in (PRIMARY_URL, MIRROR_URL):
        _active_base = cached
        return _active_base

    import requests

    for candidate in (PRIMARY_URL, MIRROR_URL):
        try:
            response = requests.get(
                candidate + "/",
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"},
                timeout=min(15, get_timeout()),
                allow_redirects=True,
            )
            text = response.text.lower()
            blocked = response.status_code == 403 or "just a moment" in text
            if response.ok and not blocked and len(response.content) > 10000:
                _active_base = candidate.rstrip("/")
                cache_set("working_base", _active_base)
                log(f"Using base URL {_active_base}")
                return _active_base
        except Exception as exc:  # noqa: BLE001
            log(f"Probe failed for {candidate}: {exc}", xbmc.LOGWARNING)

    _active_base = MIRROR_URL
    cache_set("working_base", _active_base)
    return _active_base


def set_base_url(url):
    global _active_base
    _active_base = (url or MIRROR_URL).rstrip("/")
    cache_set("working_base", _active_base)


def ensure_profile():
    if not xbmcvfs.exists(PROFILE_PATH):
        xbmcvfs.mkdirs(PROFILE_PATH)


def cache_path(name):
    ensure_profile()
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name)
    return os.path.join(PROFILE_PATH, f"{safe}.json")


def cache_get(name):
    ttl = get_cache_ttl_seconds()
    if ttl <= 0:
        return None
    path = cache_path(name)
    if not xbmcvfs.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if time.time() - payload.get("ts", 0) > ttl:
            return None
        return payload.get("data")
    except Exception as exc:  # noqa: BLE001
        log(f"cache_get failed: {exc}", xbmc.LOGWARNING)
        return None


def cache_set(name, data):
    ttl = get_cache_ttl_seconds()
    if ttl <= 0 and name != "working_base":
        return
    path = cache_path(name)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time(), "data": data}, fh, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        log(f"cache_set failed: {exc}", xbmc.LOGWARNING)


def notify_error(message, heading=None):
    xbmcgui.Dialog().notification(
        heading or get_string(30120) or "Error",
        message,
        xbmcgui.NOTIFICATION_ERROR,
        5000,
    )


def notify_info(message, heading=None):
    xbmcgui.Dialog().notification(
        heading or ADDON_NAME,
        message,
        xbmcgui.NOTIFICATION_INFO,
        3000,
    )


def parse_query(query):
    if not query:
        return {}
    if query.startswith("?"):
        query = query[1:]
    return dict(parse_qsl(query, keep_blank_values=True))


def build_url(query):
    query = dict(query)
    action = query.get("action")
    if action and not action.startswith("kinogo_"):
        query["action"] = "kinogo_" + action
    return f"plugin://{ADDON_ID}/?{urlencode(query)}"


def absolute_url(url, base=None):
    if not url:
        return ""
    url = html_lib.unescape(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    return urljoin((base or get_base_url()) + "/", url)


def normalize_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:  # noqa: BLE001
            return ""
    text = html_lib.unescape(value).strip()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_title(title):
    title = normalize_text(title)
    title = re.sub(r"\s*смотреть онлайн.*$", "", title, flags=re.I)
    return title.strip()


def is_item_url(url):
    path = urlparse(absolute_url(url)).path
    return bool(re.match(r"^/\d+-[a-z0-9_-]+\.html$", path, re.I))
