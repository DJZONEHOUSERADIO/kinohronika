# -*- coding: utf-8 -*-
"""Изграждане на списъци и диалози в Kodi."""
import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

import util

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")
ICON = os.path.join(ADDON_PATH, "icon.png")
FANART = os.path.join(ADDON_PATH, "fanart.jpg")

_BASE = ""
_HANDLE = 0


def set_base(base):
    global _BASE
    _BASE = base


def set_handle(handle):
    global _HANDLE
    _HANDLE = handle


def url(**params):
    return util.build_url(_BASE, **params)


def _listitem(label, art=None, info=None, playable=False):
    try:
        item = xbmcgui.ListItem(label=label, offscreen=True)
    except TypeError:
        item = xbmcgui.ListItem(label=label)
    art = art or {}
    item.setArt({
        "icon": art.get("icon") or ICON,
        "thumb": art.get("thumb") or art.get("poster") or ICON,
        "poster": art.get("poster") or art.get("thumb") or ICON,
        "fanart": art.get("fanart") or FANART,
    })
    if info:
        item.setInfo("video", info)
    if playable:
        item.setProperty("IsPlayable", "true")
    return item


def add(label, target, art=None, info=None, folder=True, playable=False, context=None):
    item = _listitem(label, art, info, playable)
    if context:
        item.addContextMenuItems(context)
    xbmcplugin.addDirectoryItem(_HANDLE, target, item, folder)


def separator(label):
    item = _listitem(label)
    xbmcplugin.addDirectoryItem(_HANDLE, "", item, False)


def end(content_type=None):
    try:
        xbmcplugin.addSortMethod(_HANDLE, xbmcplugin.SORT_METHOD_NONE)
    except Exception:
        pass
    if content_type:
        try:
            xbmcplugin.setContent(_HANDLE, content_type)
        except Exception:
            pass
    xbmcplugin.endOfDirectory(_HANDLE, cacheToDisc=False)


def notify(message, heading="Кинохроника", icon=None):
    try:
        xbmcgui.Dialog().notification(heading, message, icon or ICON, 4000, False)
    except Exception:
        xbmc.log("[kinohronika] %s" % message, xbmc.LOGINFO)


def error(message):
    util.log("ERROR: %s" % message, xbmc.LOGERROR)
    try:
        xbmcgui.Dialog().ok("Кинохроника", message)
    except Exception:
        pass


def reader(heading, text):
    if not text or not text.strip():
        notify("Няма текст за показване")
        return
    try:
        xbmcgui.Dialog().textviewer(heading[:80], text)
    except Exception as exc:
        util.log("textviewer failed: %s" % exc)
        notify("Неуспешно отваряне на текста")


def ask(heading, options):
    try:
        return xbmcgui.Dialog().select(heading, options)
    except Exception:
        return -1


def yesno(heading, message):
    try:
        return xbmcgui.Dialog().yesno(heading, message)
    except Exception:
        return False


def keyboard(heading, default=""):
    try:
        return xbmcgui.Dialog().input(heading, defaultt=default, type=xbmcgui.INPUT_ALPHANUM)
    except Exception:
        return ""
