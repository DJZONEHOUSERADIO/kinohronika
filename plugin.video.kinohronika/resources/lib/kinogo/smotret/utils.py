# -*- coding: utf-8 -*-
"""Shared helpers for plugin.video.smotret."""

from __future__ import annotations

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
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))

BASE_URL = "https://smotret.tv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CATEGORY_PATHS = {
    "/music/",
    "/sport/",
    "/news/",
    "/detskie/",
    "/christian/",
    "/razvlekatelnye/",
    "/poznavatelnye/",
    "/region/",
    "/relax/",
}


def log(message, level=xbmc.LOGINFO):
    debug = ADDON.getSettingBool("debug")
    if level >= xbmc.LOGERROR or debug:
        xbmc.log(f"[{ADDON_ID}] {message}", level)


def get_string(string_id):
    return ADDON.getLocalizedString(string_id)


def get_timeout():
    try:
        return max(5, int(ADDON.getSetting("timeout") or 25))
    except (TypeError, ValueError):
        return 25


def get_cache_ttl_seconds():
    try:
        minutes = int(ADDON.getSetting("cache_ttl") or 30)
    except (TypeError, ValueError):
        minutes = 30
    return max(0, minutes) * 60


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
        log(f"cache_get failed for {name}: {exc}", xbmc.LOGWARNING)
        return None


def cache_set(name, data):
    ttl = get_cache_ttl_seconds()
    if ttl <= 0:
        return
    path = cache_path(name)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time(), "data": data}, fh, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        log(f"cache_set failed for {name}: {exc}", xbmc.LOGWARNING)


def notify_error(message, heading=None):
    xbmcgui.Dialog().notification(
        heading or get_string(30102) or "Error",
        message,
        xbmcgui.NOTIFICATION_ERROR,
        5000,
    )


def parse_query(query):
    if not query:
        return {}
    if query.startswith("?"):
        query = query[1:]
    return dict(parse_qsl(query, keep_blank_values=True))


def build_url(query):
    return f"plugin://{ADDON_ID}/?{urlencode(query)}"


def absolute_url(url, base=None):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    return urljoin((base or BASE_URL) + "/", url)


def clean_channel_title(title):
    title = (title or "").strip()
    title = re.sub(r"^Логотип\s+", "", title, flags=re.I)
    title = re.sub(r"\s*—\s*смотреть.*$", "", title, flags=re.I)
    title = re.sub(r"\s*смотреть онлайн.*$", "", title, flags=re.I)
    title = re.sub(r"\s*слушать.*$", "", title, flags=re.I)
    return re.sub(r"\s+", " ", title).strip()


def is_category_path(path):
    return path in _CATEGORY_PATHS


def is_channel_path(path):
    if not path or path == "/":
        return False
    if is_category_path(path if path.endswith("/") else path + "/"):
        return False
    skip = {"/info.html", "/info/", "/"}
    if path in skip:
        return False
    return bool(re.match(r"^/(?:[a-z0-9-]+/)*[a-z0-9_-]+$", path, re.I))


def host_label(url):
    host = (urlparse(url).netloc or "").lower()
    if "ok.ru" in host or "odnoklassniki" in host:
        return "OK.ru"
    if "mediavitrina" in host:
        return "MediaVitrina"
    if "smotrim" in host or "vgtrk" in host:
        return "Smotrim"
    if "rutube" in host:
        return "Rutube"
    if "vk" in host:
        return "VK"
    if "1tv.ru" in host:
        return "1TV"
    if ".m3u8" in url.lower():
        return "HLS"
    return host or "Stream"
