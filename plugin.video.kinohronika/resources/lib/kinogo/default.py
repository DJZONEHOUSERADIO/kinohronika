# -*- coding: utf-8 -*-
"""
plugin.video.kinogo — Kodi router for kinogo.org / kinogo.la

Routes:
  root, list, genres, search, sources, seasons, episodes, play
"""

from __future__ import annotations

import sys
from urllib.parse import quote

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from . import utils
from .scraper import FILM_GENRES, SERIAL_GENRES, KinogoScraper, ScraperError

HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1


def main():
    params = utils.parse_query(sys.argv[2] if len(sys.argv) > 2 else "")
    action = (params.get("action") or "").strip()
    if action.startswith("kinogo_"):
        action = action[len("kinogo_"):]
    utils.log(f"Router action={action!r}")

    try:
        if action == "list":
            list_items(params)
        elif action == "genres":
            list_genres(params)
        elif action == "search":
            do_search(params)
        elif action == "open":
            open_item(params)
        elif action == "seasons":
            list_seasons(params)
        elif action == "episodes":
            list_episodes(params)
        elif action == "play":
            play_video(params)
        else:
            root_menu()
    except ScraperError as exc:
        utils.log(f"ScraperError: {exc}", xbmc.LOGERROR)
        utils.notify_error(str(exc))
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except Exception as exc:  # noqa: BLE001
        utils.log(f"Unhandled: {exc}", xbmc.LOGERROR)
        utils.notify_error(str(exc))
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def root_menu():
    items = [
        (utils.get_string(30100) or "New releases", {"action": "list", "path": "/novinki/"}),
        (utils.get_string(30101) or "Premieres", {"action": "list", "path": "/premiery/"}),
        (utils.get_string(30102) or "Films", {"action": "genres", "kind": "film"}),
        (utils.get_string(30103) or "Series", {"action": "genres", "kind": "serial"}),
        (utils.get_string(30104) or "Cartoons", {"action": "list", "path": "/mult/"}),
        (utils.get_string(30105) or "Anime", {"action": "list", "path": "/anime/"}),
        (utils.get_string(30106) or "TV shows", {"action": "list", "path": "/tv/"}),
        (utils.get_string(30107) or "TOP", {"action": "list", "path": "/top.html"}),
        (utils.get_string(30108) or "Collections", {"action": "list", "path": "/podborki/"}),
        (utils.get_string(30109) or "Search", {"action": "search"}),
    ]
    for label, query in items:
        list_item = xbmcgui.ListItem(label=label)
        list_item.setArt({"icon": utils.ADDON_ICON, "thumb": utils.ADDON_ICON, "fanart": utils.ADDON_ICON})
        xbmcplugin.addDirectoryItem(HANDLE, utils.build_url(query), list_item, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE)


def list_genres(params):
    kind = (params.get("kind") or "film").strip()
    if kind == "serial":
        genres = SERIAL_GENRES
        all_path = "/serial/"
        all_label = utils.get_string(30110) or "All series"
    else:
        genres = FILM_GENRES
        all_path = "/film/"
        all_label = utils.get_string(30111) or "All films"

    list_item = xbmcgui.ListItem(label=all_label)
    list_item.setArt({"icon": "DefaultFolder.png"})
    xbmcplugin.addDirectoryItem(
        HANDLE,
        utils.build_url({"action": "list", "path": all_path}),
        list_item,
        isFolder=True,
    )
    for title, path in genres:
        list_item = xbmcgui.ListItem(label=title)
        list_item.setArt({"icon": "DefaultFolder.png"})
        xbmcplugin.addDirectoryItem(
            HANDLE,
            utils.build_url({"action": "list", "path": path}),
            list_item,
            isFolder=True,
        )
    xbmcplugin.endOfDirectory(HANDLE)


def list_items(params):
    path = (params.get("path") or "/").strip()
    page = max(1, int(params.get("page") or 1))
    scraper = KinogoScraper()
    items, max_page = scraper.get_listing(path, page=page)
    xbmcplugin.setContent(HANDLE, "movies")
    if not items:
        utils.notify_error(utils.get_string(30113) or "No items found.")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    for item in items:
        _add_catalog_item(item)
    if page < max_page:
        next_label = (utils.get_string(30112) or "Next page (%s)") % (page + 1)
        list_item = xbmcgui.ListItem(label=next_label)
        list_item.setArt({"icon": "DefaultFolder.png"})
        xbmcplugin.addDirectoryItem(
            HANDLE,
            utils.build_url({"action": "list", "path": path, "page": str(page + 1)}),
            list_item,
            isFolder=True,
        )
    xbmcplugin.endOfDirectory(HANDLE)


def do_search(params):
    query = (params.get("query") or "").strip()
    page = max(1, int(params.get("page") or 1))
    if not query:
        keyboard = xbmc.Keyboard("", utils.get_string(30109) or "Search")
        keyboard.doModal()
        if not keyboard.isConfirmed():
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
        query = keyboard.getText().strip()
    if not query:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    scraper = KinogoScraper()
    items, max_page = scraper.search(query, page=page)
    xbmcplugin.setContent(HANDLE, "movies")
    if not items:
        utils.notify_error(utils.get_string(30113) or "No results found.")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    for item in items:
        _add_catalog_item(item)
    if page < max_page:
        list_item = xbmcgui.ListItem(
            label=(utils.get_string(30112) or "Next page (%s)") % (page + 1)
        )
        xbmcplugin.addDirectoryItem(
            HANDLE,
            utils.build_url({"action": "search", "query": query, "page": str(page + 1)}),
            list_item,
            isFolder=True,
        )
    xbmcplugin.endOfDirectory(HANDLE)


def open_item(params):
    """Open movie/series: seasons folder if serial player, else source picker / play."""
    url = (params.get("url") or "").strip()
    if not url:
        raise ScraperError("Missing URL")

    scraper = KinogoScraper()
    detail = scraper.get_item_detail(url)
    sources = [s for s in detail.get("sources") or [] if "trailer" not in s["embed"].lower()]
    if not sources:
        raise ScraperError(utils.get_string(30121) or "No playable sources")

    # Probe first source for seasons
    try:
        seasons = scraper.resolvers.get_seasons_from_embed(sources[0]["embed"], referer=url)
    except Exception:  # noqa: BLE001
        seasons = []

    if seasons and sum(len(s.get("episodes") or []) for s in seasons) > 1:
        xbmcplugin.setContent(HANDLE, "tvshows")
        for season in seasons:
            season_num = season.get("season")
            eps = len(season.get("episodes") or [])
            label = (utils.get_string(30114) or "Season %s (%s eps)") % (season_num, eps)
            list_item = xbmcgui.ListItem(label=label)
            art = detail.get("thumb") or utils.ADDON_ICON
            list_item.setArt({"thumb": art, "poster": art, "fanart": art, "icon": art})
            xbmcplugin.addDirectoryItem(
                HANDLE,
                utils.build_url(
                    {
                        "action": "episodes",
                        "url": url,
                        "embed": sources[0]["embed"],
                        "season": str(season_num),
                    }
                ),
                list_item,
                isFolder=True,
            )
        # Also offer alternate players if any
        if len(sources) > 1:
            for source in sources[1:]:
                list_item = xbmcgui.ListItem(label=source["label"])
                list_item.setProperty("IsPlayable", "true")
                xbmcplugin.addDirectoryItem(
                    HANDLE,
                    utils.build_url(
                        {"action": "play", "url": url, "embed": source["embed"]}
                    ),
                    list_item,
                    isFolder=False,
                )
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # Movie / single: list playable sources
    xbmcplugin.setContent(HANDLE, "movies")
    art = detail.get("thumb") or utils.ADDON_ICON
    for source in sources:
        label = source.get("label") or "Play"
        if len(sources) == 1:
            label = (utils.get_string(30115) or "Watch: %s") % (detail.get("title") or label)
        list_item = xbmcgui.ListItem(label=label)
        list_item.setArt({"thumb": art, "poster": art, "fanart": art, "icon": art})
        list_item.setInfo(
            "video",
            {
                "title": detail.get("title") or label,
                "plot": detail.get("plot") or "",
                "mediatype": "movie",
            },
        )
        list_item.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(
            HANDLE,
            utils.build_url(
                {
                    "action": "play",
                    "url": url,
                    "embed": source["embed"],
                    "title": detail.get("title") or "",
                }
            ),
            list_item,
            isFolder=False,
        )
    xbmcplugin.endOfDirectory(HANDLE)


def list_seasons(params):
    open_item(params)


def list_episodes(params):
    url = (params.get("url") or "").strip()
    embed = (params.get("embed") or "").strip()
    season = (params.get("season") or "").strip()
    if not url or not season:
        raise ScraperError("Missing season params")

    scraper = KinogoScraper()
    seasons = scraper.get_seasons(url, embed_url=embed or None)
    target = None
    for item in seasons:
        if str(item.get("season")) == str(season):
            target = item
            break
    if not target:
        raise ScraperError("Season not found")

    xbmcplugin.setContent(HANDLE, "episodes")
    detail = scraper.get_item_detail(url)
    thumb = detail.get("thumb") or utils.ADDON_ICON
    for ep in target.get("episodes") or []:
        ep_num = ep.get("episode") or ""
        label = ep.get("title") or f"S{season}E{ep_num}"
        list_item = xbmcgui.ListItem(label=label)
        list_item.setArt({"thumb": thumb, "poster": thumb, "fanart": thumb, "icon": thumb})
        list_item.setInfo(
            "video",
            {
                "title": label,
                "tvshowtitle": detail.get("title") or "",
                "season": int(season) if str(season).isdigit() else 0,
                "episode": int(ep_num) if str(ep_num).isdigit() else 0,
                "mediatype": "episode",
            },
        )
        list_item.setProperty("IsPlayable", "true")
        # Prefer direct HLS from seasons payload when present
        if ep.get("url"):
            play_url = utils.build_url(
                {
                    "action": "play",
                    "url": url,
                    "embed": embed,
                    "season": str(season),
                    "episode": str(ep_num),
                    "stream": ep["url"],
                    "title": label,
                }
            )
        else:
            play_url = utils.build_url(
                {
                    "action": "play",
                    "url": url,
                    "embed": embed,
                    "season": str(season),
                    "episode": str(ep_num),
                    "title": label,
                }
            )
        xbmcplugin.addDirectoryItem(HANDLE, play_url, list_item, isFolder=False)
    xbmcplugin.endOfDirectory(HANDLE)


def play_video(params):
    item_url = (params.get("url") or "").strip()
    embed = (params.get("embed") or "").strip()
    season = (params.get("season") or "").strip() or None
    episode = (params.get("episode") or "").strip() or None
    stream = (params.get("stream") or "").strip()
    title = (params.get("title") or "").strip()

    scraper = KinogoScraper()
    header_map = {
        "User-Agent": utils.USER_AGENT,
        "Referer": utils.get_base_url() + "/",
    }

    try:
        if stream and ".m3u8" in stream.lower():
            resolved_url = stream
            header_map["Referer"] = embed or item_url or header_map["Referer"]
        else:
            resolved = scraper.get_stream(
                item_url, embed=embed or None, season=season, episode=episode
            )
            resolved_url = resolved.get("url") or ""
            header_map = resolved.get("headers") or header_map
            title = title or resolved.get("title") or ""
    except ScraperError as exc:
        utils.notify_error(utils.get_string(30121) or str(exc))
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    if not resolved_url:
        utils.notify_error(utils.get_string(30121) or "Failed to resolve stream")
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    utils.log(f"Playing {resolved_url}")
    list_item = xbmcgui.ListItem(label=title or "KinoGo", path=resolved_url)
    list_item.setProperty("IsPlayable", "true")
    if title:
        list_item.setInfo("video", {"title": title, "mediatype": "video"})

    headers = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in header_map.items())
    is_hls = ".m3u8" in resolved_url.lower()

    if is_hls:
        list_item.setMimeType("application/vnd.apple.mpegurl")
        list_item.setContentLookup(False)
        try:
            xbmcaddon.Addon("inputstream.adaptive")
            list_item.setProperty("inputstream", "inputstream.adaptive")
            list_item.setProperty("inputstream.adaptive.manifest_type", "hls")
            list_item.setProperty("inputstream.adaptive.stream_headers", headers)
            list_item.setProperty("inputstream.adaptive.manifest_headers", headers)
        except Exception:  # noqa: BLE001
            list_item.setPath(f"{resolved_url}|{headers}")
            utils.log("Native HLS fallback", xbmc.LOGINFO)
    else:
        list_item.setPath(f"{resolved_url}|{headers}")

    xbmcplugin.setResolvedUrl(HANDLE, True, list_item)


def _add_catalog_item(item):
    title = item.get("title") or "Item"
    list_item = xbmcgui.ListItem(label=title)
    thumb = item.get("thumb") or utils.ADDON_ICON
    list_item.setArt({"thumb": thumb, "poster": thumb, "fanart": thumb, "icon": thumb})
    info = {"title": title, "mediatype": "movie"}
    if item.get("plot"):
        info["plot"] = item["plot"]
    list_item.setInfo("video", info)
    xbmcplugin.addDirectoryItem(
        HANDLE,
        utils.build_url({"action": "open", "url": item.get("url", "")}),
        list_item,
        isFolder=True,
    )


if __name__ == "__main__":
    main()
