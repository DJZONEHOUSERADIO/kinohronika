# -*- coding: utf-8 -*-
"""Мрежа, кеш и текстови помощни функции."""
import gzip
import hashlib
import html as htmllib
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bg-BG,bg;q=0.9,ru;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip",
}


def log(msg, level=xbmc.LOGDEBUG):
    try:
        xbmc.log("[%s] %s" % (ADDON_ID, msg), level)
    except Exception:
        pass


def setting(key, default=""):
    try:
        value = ADDON.getSetting(key)
    except Exception:
        return default
    return value if value not in (None, "") else default


def setting_int(key, default):
    try:
        return int(float(setting(key, str(default))))
    except Exception:
        return default


def setting_bool(key, default=False):
    value = str(setting(key, "true" if default else "false")).lower()
    return value in ("true", "1", "yes", "on")


# ---------------------------------------------------------------- кеш

_CACHE_DIR = None


def cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR:
        return _CACHE_DIR
    try:
        path = xbmcvfs.translatePath(
            "special://profile/addon_data/%s/cache" % ADDON_ID)
    except Exception:
        path = os.path.join(os.path.expanduser("~"), ".kinohronika", "cache")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    _CACHE_DIR = path
    return path


def _cache_path(key):
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir(), digest + ".json")


def cache_get(key, ttl):
    if ttl <= 0:
        return None
    try:
        with open(_cache_path(key), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if time.time() - payload.get("ts", 0) <= ttl:
            return payload.get("data")
    except Exception:
        pass
    return None


def cache_put(key, data):
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as handle:
            json.dump({"ts": time.time(), "data": data}, handle)
    except Exception as exc:
        log("cache write failed: %s" % exc)


def cache_clear():
    try:
        for name in os.listdir(cache_dir()):
            if name.endswith(".json"):
                os.remove(os.path.join(cache_dir(), name))
    except Exception:
        pass


# ---------------------------------------------------------------- мрежа

def _decode(raw, content_type=""):
    head = raw[:600].decode("ascii", "ignore")
    charset = ""
    match = re.search(r"charset=[\"']?([\w\-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1).lower()
    else:
        match = re.search(r"<\?xml[^>]*encoding=[\"']([\w\-]+)", head, re.I)
        if match:
            charset = match.group(1).lower()
        else:
            match = re.search(r"charset=[\"']?([\w\-]+)", head, re.I)
            if match:
                charset = match.group(1).lower()
    candidates = []
    if charset:
        candidates.append("cp1251" if charset in ("windows-1251", "cp-1251") else charset)
    candidates += ["utf-8", "cp1251"]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def http_get(url, ttl=600, timeout=15, cache_key=None, headers=None):
    """Връща текста на URL с дисков кеш. Хвърля изключение при грешка."""
    key = cache_key or url
    cached = cache_get(key, ttl)
    if cached is not None:
        return cached
    request = Request(url, headers=dict(HEADERS, **(headers or {})))
    last_error = None
    for attempt in (0, 1):
        try:
            response = urlopen(request, timeout=timeout)
            break
        except HTTPError:
            raise
        except URLError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.7)
                continue
            raise RuntimeError("Мрежова грешка: %s" % exc.reason)
    try:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        if response.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        text = _decode(raw, content_type)
    except Exception as exc:
        raise RuntimeError("Грешка при зареждане: %s" % exc)
    cache_put(key, text)
    log("GET %s (%d bytes)" % (url, len(text)))
    return text


def http_json(url, ttl=600, timeout=20, headers=None):
    return json.loads(http_get(url, ttl=ttl, timeout=timeout, headers=headers))


def build_url(base, **params):
    clean = {k: v for k, v in params.items() if v is not None}
    return base + "?" + urlencode(clean)


# ---------------------------------------------------------------- HTML

_RE_SCRIPT = re.compile(r"<(script|style|noscript|iframe|svg|form|nav|footer)[^>]*>.*?</\1>",
                        re.I | re.S)
_RE_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|section|article|blockquote|figure)[^>]*>",
                       re.I)
_RE_TAG = re.compile(r"<[^>]+>")


def strip_html(value):
    if not value:
        return ""
    text = _RE_SCRIPT.sub(" ", value)
    text = _RE_BLOCK.sub("\n", text)
    text = _RE_TAG.sub(" ", text)
    text = htmllib.unescape(text).replace("\xa0", " ")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


def first_image(markup):
    if not markup:
        return ""
    match = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", markup, re.I)
    return htmllib.unescape(match.group(1)) if match else ""


def extract_article(page, limit=14000):
    """Извлича основния текст: най-дългият блок от параграфи в статия/контейнер."""
    patterns = (
        r"<article[^>]*>(.*?)</article>",
        r"<div[^>]+(?:class|id)=[\"'][^\"']*(?:article|content|entry|post|story|text|body)[^\"']*[\"'][^>]*>(.*?)</div>",
        r"<main[^>]*>(.*?)</main>",
    )
    best = ""
    for pattern in patterns:
        for match in re.finditer(pattern, page, re.I | re.S):
            chunk = match.group(1)
            paragraphs = [
                strip_html(part)
                for part in re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.I | re.S)
            ]
            text = "\n\n".join(p for p in paragraphs if len(p) >= 40)
            if len(text) > len(best):
                best = text
    if len(best) > 700:
        return best[:limit]

    paragraphs = [
        strip_html(part)
        for part in re.findall(r"<p[^>]*>(.*?)</p>", page, re.I | re.S)
    ]
    text = "\n\n".join(p for p in paragraphs if len(p) >= 60)
    if len(text) > 700:
        return text[:limit]

    match = re.search(r"<body[^>]*>(.*?)</body>", page, re.I | re.S)
    return strip_html(match.group(1) if match else page)[:limit]


def pretty_size(num):
    try:
        num = float(num)
    except Exception:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return "%.1f %s" % (num, unit) if unit != "B" else "%d B" % num
        num /= 1024.0
    return ""


def local_date(timestamp):
    try:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))
    except Exception:
        return ""
