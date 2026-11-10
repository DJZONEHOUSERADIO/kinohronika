# -*- coding: utf-8 -*-
"""Кинохроника — новини, кино и телевизия от български и руски източници."""
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")
ADDON_VERSION = ADDON.getAddonInfo("version")
sys.path.insert(0, os.path.join(ADDON_PATH, "resources", "lib"))

import content  # noqa: E402
import providers  # noqa: E402
import session  # noqa: E402
import ui  # noqa: E402
import util  # noqa: E402

BASE = sys.argv[0]
HANDLE = int(sys.argv[1])
PARAMS = {}
if len(sys.argv) > 2 and sys.argv[2]:
    from urllib.parse import parse_qsl
    PARAMS = dict(parse_qsl(sys.argv[2][1:]))

ui.set_base(BASE)
ui.set_handle(HANDLE)

HEADING = "Кинохроника"


# ------------------------------------------------------------------ помощни

def open_external(link):
    if not link:
        return
    try:
        import webbrowser
        if webbrowser.open(link):
            return
    except Exception:
        pass
    try:
        xbmc.executebuiltin(
            'StartAndroidActivity(,android.intent.action.VIEW,,%s)' % link)
        return
    except Exception:
        pass
    ui.reader("Адрес на статията", link + "\n\nКопирайте адреса в браузъра.")


def news_context(link):
    return [("Отвори в браузър", 'RunPlugin("%s")' % ui.url(action="open", link=link))]


def news_label(item):
    stamp = util.local_date(item.get("ts", 0))[11:]
    meta = item.get("source", "")
    if stamp:
        meta = "%s · %s" % (meta, stamp)
    return "%s\n[COLOR FF7F8C99]%s[/COLOR]" % (item["title"], meta)


def add_news_item(item):
    ui.add(
        news_label(item),
        ui.url(action="article", link=item["link"]),
        art={"thumb": item.get("image") or ""},
        info={
            "title": item["title"],
            "plot": item.get("desc") or "",
            "aired": util.local_date(item.get("ts", 0)),
            "studio": item.get("source", ""),
        },
        folder=False,
        context=news_context(item["link"]),
    )


# -------------------------------------------------------------------- менюта

def root():
    ui.add(
        "[B]Сеанс на деня[/B]\n[COLOR FF7F8C99]новини · карикатура · филм · радио[/COLOR]",
        ui.url(action="session"),
        art={"thumb": ui.ICON},
        folder=True,
    )
    ui.add("[B]Новини[/B]", ui.url(action="news_menu"), folder=True)
    ui.add("[B]Кино[/B]", ui.url(action="cinema"), folder=True)
    ui.add("[B]KinoGo[/B]\n[COLOR FF7F8C99]филми · сериали · аниме[/COLOR]", ui.url(action="kinogo_root"), folder=True)
    ui.add("[B]Телевизия на живо[/B]\n[COLOR FF7F8C99]СМОТРИМ · smotret.tv[/COLOR]",
           ui.url(action="tv_menu"), folder=True)
    ui.add("[B]Сериали[/B]", ui.url(action="tv"), folder=True)
    ui.add("[B]Радио на живо[/B]", ui.url(action="radio"), folder=True)
    ui.add("[B]Търсене в архива[/B]", ui.url(action="search"), folder=True)
    ui.add("[B]За добавката[/B]", ui.url(action="about"), folder=True)
    ui.end("files")


def news_menu():
    ui.add("[B]Всички новини[/B] · България и Русия",
           ui.url(action="news_list", country="all"), folder=True)
    ui.add("България", ui.url(action="news_list", country="bg"), folder=True)
    ui.add("Русия", ui.url(action="news_list", country="ru"), folder=True)
    ui.separator("[COLOR FF7F8C99]— по източник —[/COLOR]")
    for source in content.sources()["news"]:
        ui.add(
            "%s [COLOR FF7F8C99](%s)[/COLOR]" % (
                source["name"], "БГ" if source["country"] == "bg" else "РФ"),
            ui.url(action="feed", id=source["id"]),
            folder=True,
        )
    ui.end("files")


def news_list(country):
    try:
        items = content.news_for_country(country)
    except Exception as exc:
        ui.error("Новините не могат да се заредят: %s" % exc)
        ui.end("files")
        return
    if not items:
        ui.notify("Няма намерени новини")
        ui.end("files")
        return
    for item in items[:120]:
        add_news_item(item)
    ui.end("files")


def feed(feed_id):
    source = next((s for s in content.sources()["news"] if s["id"] == feed_id), None)
    if not source:
        ui.error("Непознат източник")
        ui.end("files")
        return
    try:
        xml_text = util.http_get(source["url"], ttl=util.setting_int("cache_minutes", 10) * 60)
        items = content.parse_feed(xml_text, source)
    except Exception as exc:
        ui.error("Емисията не може да се зареди: %s" % exc)
        ui.end("files")
        return
    for item in items[:60]:
        add_news_item(item)
    ui.end("files")


def article(link):
    item = None
    try:
        item = next((n for n in content.load_news() if n["link"] == link), None)
    except Exception:
        item = None
    title = item["title"] if item else "Статия"
    summary = item.get("desc", "") if item else ""
    text = ""
    try:
        page = util.http_get(link, ttl=24 * 3600, timeout=12)
        text = util.extract_article(page)
    except Exception as exc:
        util.log("article fetch failed: %s" % exc)
    if len(text) < 300:
        text = summary
    body = text.strip()
    if not body:
        body = "Текстът не може да бъде извлечен. Отворете статията в браузър."
    tail = "\n\n— — —"
    if item and item.get("source"):
        tail += "\nИзточник: %s" % item["source"]
    tail += "\n%s" % link
    ui.reader(title, body + tail)


def cinema():
    archive = content.sources()["archive"]
    for key in ("features", "cartoons", "silent"):
        cfg = archive.get(key)
        if not cfg:
            continue
        ui.add("%s\n[COLOR FF7F8C99]archive.org · %s[/COLOR]" % (cfg["name"], cfg.get("note", "")),
               ui.url(action="ia_list", key=key, page=1), folder=True)
    ui.separator("[COLOR FF7F8C99]— YouTube канали на притежателите на правата —[/COLOR]")
    for channel in content.sources()["youtube"]:
        ui.add("%s\n[COLOR FF7F8C99]%s[/COLOR]" % (channel["name"], channel.get("note", "")),
               ui.url(action="yt", key=channel["id"]), folder=True)
    ui.end("videos")


def tv():
    wanted = {"bnt", "gtrf_tv", "gtrf_radio", "belarusfilm"}
    for channel in content.sources()["youtube"]:
        if channel["id"] not in wanted:
            continue
        ui.add("%s\n[COLOR FF7F8C99]%s[/COLOR]" % (channel["name"], channel.get("note", "")),
               ui.url(action="yt", key=channel["id"]), folder=True)
    newsreel = content.sources()["archive"].get("newsreel")
    if newsreel:
        ui.separator("[COLOR FF7F8C99]— архивни телевизионни емисии —[/COLOR]")
        ui.add("%s\n[COLOR FF7F8C99]%s[/COLOR]" % (newsreel["name"], newsreel.get("note", "")),
               ui.url(action="ia_list", key="newsreel", page=1), folder=True)
    ui.add("Радио БНР на живо", ui.url(action="radio"), folder=True)
    ui.end("videos")



# --------------------------------------------------------------- телевизия

def _play_url(url, probe_first=False, message=None):
    if probe_first and not providers.probe(url):
        ui.notify(message or "Потокът е недостъпен от тази мрежа")
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(path=url)
    item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def tv_menu():
    smotrim = content.sources()["tv"]["smotrim"]
    smotret = content.sources()["tv"]["smotret"]
    ui.add("[B]%s[/B] · на живо\n[COLOR FF7F8C99]%d канала · официална платформа на ВГТРК[/COLOR]"
           % (smotrim["name"], len(smotrim["channels"])),
           ui.url(action="tv_sm_live"), folder=True)
    ui.add("[B]%s[/B] · филми и сериали\n[COLOR FF7F8C99]каталог на СМОТРИМ[/COLOR]"
           % smotrim["name"], ui.url(action="tv_sm_catalog"), folder=True)
    try:
        count = len(providers.smotret_channels())
        extra = "%d канала · %s" % (count, smotret.get("note", ""))
    except Exception:
        extra = smotret.get("note", "")
    ui.add("[B]%s[/B] · телевизии\n[COLOR FF7F8C99]%s[/COLOR]"
           % (smotret["name"], extra), ui.url(action="tv_st"), folder=True)
    ui.end("files")


def tv_sm_live():
    for channel in providers.smotrim_channels():
        ui.add(channel["name"],
               ui.url(action="tv_sm_play_live", id=channel["id"]),
               art={"thumb": ui.ICON},
               info={"title": channel["name"], "plot": "Пряко предаване · СМОТРИМ"},
               folder=False, playable=True)
    ui.end("videos")


def tv_sm_play_live(channel_id):
    try:
        url, title = providers.smotrim_live(channel_id)
    except Exception as exc:
        ui.notify(str(exc))
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    _play_url(url, probe_first=True,
              message="„%s“ е геоблокиран извън Русия." % title)


def tv_sm_catalog():
    try:
        items = providers.smotrim_catalog()
    except Exception as exc:
        ui.error("Каталогът на СМОТРИМ не се зарежда: %s" % exc)
        ui.end("videos")
        return
    for item in items:
        label = item["title"]
        if item["meta"]:
            label = "%s\n[COLOR FF7F8C99]%s[/COLOR]" % (label, item["meta"][:70])
        ui.add(label, ui.url(action="tv_sm_brand", id=item["id"]),
               art={"thumb": item["thumb"]},
               info={"title": item["title"], "plot": item["meta"]},
               folder=True)
    ui.end("videos")


def tv_sm_brand(brand_id):
    try:
        data = providers.smotrim_brand(brand_id)
    except Exception as exc:
        ui.error("Страницата не се зарежда: %s" % exc)
        ui.end("videos")
        return
    episodes = data["episodes"]
    if not episodes:
        ui.notify("Няма налични епизоди")
        ui.end("videos")
        return
    for index, episode in enumerate(episodes):
        label = episode["label"]
        if episode["duration"]:
            label += " [COLOR FF7F8C99]· %s[/COLOR]" % episode["duration"]
        ui.add(label, ui.url(action="tv_sm_play", id=episode["id"]),
               art={"thumb": data["poster"]},
               info={"title": "%s · %s" % (data["title"], episode["label"]),
                     "plot": data["description"], "tvshowtitle": data["title"]},
               folder=False, playable=True)
    ui.end("episodes")


def tv_sm_play(video_id):
    try:
        url = providers.smotrim_video(video_id)
    except Exception as exc:
        ui.notify(str(exc))
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    _play_url(url, probe_first=True,
              message="СМОТРИМ ограничава видеото извън Русия.")


def tv_st():
    try:
        channels = providers.smotret_channels()
    except Exception as exc:
        ui.error("Списъкът с канали не се зарежда: %s" % exc)
        ui.end("videos")
        return
    for channel in channels:
        ui.add(channel["name"],
               ui.url(action="tv_st_play", slug=channel["slug"]),
               art={"thumb": channel["thumb"]},
               info={"title": channel["name"], "plot": "Пряко предаване · smotret.tv"},
               folder=False, playable=True)
    ui.end("videos")


def tv_st_play(slug):
    try:
        url = providers.smotret_stream(slug)
    except Exception as exc:
        ui.notify(str(exc))
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    _play_url(url)


def ia_list(key, page):
    try:
        result = content.archive_search(key, page=page)
    except Exception as exc:
        ui.error("Архивът не отговаря: %s" % exc)
        ui.end("videos")
        return
    for item in result["items"]:
        title = item["title"]
        if item["year"]:
            title = "%s (%s)" % (title, item["year"])
        ui.add(
            title,
            ui.url(action="ia_play", id=item["id"]),
            art={"thumb": item["thumb"]},
            info={"title": item["title"], "year": item["year"], "plot": item["desc"]},
            folder=False,
            playable=True,
        )
    total, rows = result["total"], result["rows"]
    if page * rows < total:
        ui.add("[B]Следваща страница →[/B]",
               ui.url(action="ia_list", key=key, page=page + 1), folder=True)
    if page > 1:
        ui.add("[COLOR FF7F8C99]← Предишна страница[/COLOR]",
               ui.url(action="ia_list", key=key, page=page - 1), folder=True)
    ui.end("videos")


def ia_play(identifier):
    try:
        media = content.archive_media(identifier)
    except Exception as exc:
        ui.error("Файлът не е наличен: %s" % exc)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(path=media["url"])
    item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def yt(key):
    try:
        items = content.youtube_channel(key)
    except Exception as exc:
        ui.error("Каналът не може да се зареди: %s" % exc)
        ui.end("videos")
        return
    for entry in items:
        ui.add(
            entry["title"],
            ui.url(action="yt_play", id=entry["id"]),
            art={"thumb": entry["thumb"]},
            info={
                "title": entry["title"],
                "plot": entry["desc"],
                "aired": util.local_date(entry["ts"]),
                "studio": entry["channel"],
            },
            folder=False,
            playable=True,
        )
    ui.end("videos")


def yt_play(video_id):
    link = "https://www.youtube.com/watch?v=" + video_id
    if content.youtube_available():
        item = xbmcgui.ListItem(path="plugin://plugin.video.youtube/play/?video_id=" + video_id)
        xbmcplugin.setResolvedUrl(HANDLE, True, item)
        return
    if util.setting("youtube_mode", "0") == "1":
        open_external(link)
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    choice = ui.ask("Нужна е добавката YouTube", [
        "Инсталирай YouTube добавката",
        "Отвори в браузър",
        "Отказ",
    ])
    if choice == 0:
        xbmc.executebuiltin("InstallAddon(plugin.video.youtube)")
        ui.notify("След инсталацията опитайте отново")
    elif choice == 1:
        open_external(link)
    xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())


def radio():
    for station in content.sources()["radio"]:
        ui.add(
            station["name"],
            ui.url(action="play_radio", id=station["id"]),
            art={"thumb": ui.ICON},
            info={"title": station["name"], "plot": "Пряко предаване на БНР"},
            folder=False,
            playable=True,
        )
    ui.end("files")


def play_radio(station_id):
    station = next((s for s in content.sources()["radio"] if s["id"] == station_id), None)
    if not station:
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(path=station["url"])
    item.setProperty("IsPlayable", "true")
    item.setInfo("music", {"title": station["name"]})
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def session_view():
    program = session.build()
    header = "[B]СЕАНС НА ДЕНЯ[/B]\n[COLOR FF7F8C99]%s[/COLOR]" % time.strftime("%d.%m.%Y")
    ui.separator(header)

    count = len(program.get("news") or [])
    ui.add("1 · Кинохроника\n[COLOR FF7F8C99]%d заглавия от деня[/COLOR]" % count,
           ui.url(action="session_news"), folder=True)

    cartoon = program.get("cartoon")
    if cartoon:
        ui.add("2 · Карикатура\n[COLOR FF7F8C99]%s[/COLOR]" % cartoon["title"][:70],
               ui.url(action="ia_play", id=cartoon["id"]),
               art={"thumb": cartoon["thumb"]},
               info={"title": cartoon["title"], "plot": cartoon["desc"]},
               folder=False, playable=True)
    film = program.get("film")
    if film:
        title = film["title"]
        if film["year"]:
            title += " (%s)" % film["year"]
        ui.add("3 · Филм на деня\n[COLOR FF7F8C99]%s[/COLOR]" % title,
               ui.url(action="ia_play", id=film["id"]),
               art={"thumb": film["thumb"]},
               info={"title": film["title"], "year": film["year"], "plot": film["desc"]},
               folder=False, playable=True)
    station = program.get("radio")
    if station:
        ui.add("4 · Радио на финала\n[COLOR FF7F8C99]%s[/COLOR]" % station["name"],
               ui.url(action="play_radio", id=station["id"]),
               info={"title": station["name"]}, folder=False, playable=True)
    ui.end("files")


def session_news():
    program = session.build()
    for item in program.get("news") or []:
        add_news_item(item)
    ui.end("files")


def search():
    query = ui.keyboard("Търсене в archive.org (филми)")
    if not query:
        ui.end("videos")
        return
    search_results(query, 1)


def search_results(query, page):
    try:
        result = content.archive_search_query(query, page=page)
    except Exception as exc:
        ui.error("Търсенето не успя: %s" % exc)
        ui.end("videos")
        return
    if not result["items"]:
        ui.notify("Няма резултати за „%s“" % query)
    for item in result["items"]:
        title = item["title"]
        if item["year"]:
            title = "%s (%s)" % (title, item["year"])
        ui.add(title, ui.url(action="ia_play", id=item["id"]),
               art={"thumb": item["thumb"]},
               info={"title": item["title"], "year": item["year"], "plot": item["desc"]},
               folder=False, playable=True)
    if page * result["rows"] < result["total"]:
        ui.add("[B]Следваща страница →[/B]",
               ui.url(action="search_more", q=query, page=page + 1), folder=True)
    ui.end("videos")


def about():
    archive = content.sources()["archive"]
    channels = ", ".join(c["name"] for c in content.sources()["youtube"])
    feeds = ", ".join(n["name"] for n in content.sources()["news"])
    text = (
        "Кинохроника %s\n\n"
        "Добавката събира на едно място новини, филми и телевизия от български "
        "и руски източници — без каталози и без пиратство.\n\n"
        "НОВИНИ\n%s\n\n"
        "КИНО И ТЕЛЕВИЗИЯ\n"
        "archive.org (обществено достояние): %s\n"
        "YouTube канали на притежателите на правата: %s\n\n"
        "ТЕЛЕВИЗИЯ НА ЖИВО\n"
        "СМОТРИМ (smotrim.ru, ВГТРК): 20 канала + каталог с филми и сериали.\n"
        "smotret.tv: 70 канала чрез официалните плейъри (Rutube, OK.ru, 1tv).\n"
        "СМОТРИМ геоблокира част от каналите и видеата извън Русия — "
        "добавката го проверява и показва съобщение вместо черен екран.\n\n"
        "РАДИО\nПряко предаване на БНР (HLS).\n\n"
        "КАК РАБОТИ\n"
        "• Всичко се зарежда от публичните емисии и API-та на самите източници.\n"
        "• Няма собствен сървър, няма регистрация, няма тракери.\n"
        "• Видеото от YouTube се възпроизвежда през добавката YouTube.\n"
        "• Статиите се четат в текстов прозорец; пълният текст е на линка.\n\n"
        "ПРАВА\n"
        "Авторските права върху съдържанието принадлежат на източниците. "
        "Добавката само препраща към официално публикувани материали и не "
        "съхранява копия. Ако даден източник премахне материал, той изчезва "
        "и оттук.\n\n"
        "Версия: %s" % (ADDON_VERSION, feeds, ", ".join(
            cfg["name"] for cfg in archive.values()), channels, ADDON_VERSION)
    )
    ui.reader("За добавката", text)
    ui.end("files")


def refresh():
    ui.notify("Обновено")
    xbmc.executebuiltin("Container.Refresh")


def dispatch():
    action = PARAMS.get("action", "root")
    if action.startswith("kinogo_") and action != "kinogo_root":
        from kinogo import default as kinogo_router
        kinogo_router.main()
        return
    if action == "kinogo_root":
        from kinogo import default as kinogo_router
        kinogo_router.root_menu()
        return
    try:
        if action == "root":
            root()
        elif action == "news_menu":
            news_menu()
        elif action == "news_list":
            news_list(PARAMS.get("country", "all"))
        elif action == "feed":
            feed(PARAMS.get("id", ""))
        elif action == "article":
            article(PARAMS.get("link", ""))
        elif action == "open":
            open_external(PARAMS.get("link", ""))
        elif action == "cinema":
            cinema()
        elif action == "tv":
            tv()
        elif action == "tv_menu":
            tv_menu()
        elif action == "tv_sm_live":
            tv_sm_live()
        elif action == "tv_sm_play_live":
            tv_sm_play_live(PARAMS.get("id", ""))
        elif action == "tv_sm_catalog":
            tv_sm_catalog()
        elif action == "tv_sm_brand":
            tv_sm_brand(PARAMS.get("id", ""))
        elif action == "tv_sm_play":
            tv_sm_play(PARAMS.get("id", ""))
        elif action == "tv_st":
            tv_st()
        elif action == "tv_st_play":
            tv_st_play(PARAMS.get("slug", ""))
        elif action == "ia_list":
            ia_list(PARAMS.get("key", "features"), int(PARAMS.get("page", 1)))
        elif action == "ia_play":
            ia_play(PARAMS.get("id", ""))
        elif action == "yt":
            yt(PARAMS.get("key", ""))
        elif action == "yt_play":
            yt_play(PARAMS.get("id", ""))
        elif action == "radio":
            radio()
        elif action == "play_radio":
            play_radio(PARAMS.get("id", ""))
        elif action == "session":
            session_view()
        elif action == "session_news":
            session_news()
        elif action == "search":
            search()
        elif action == "search_more":
            search_results(PARAMS.get("q", ""), int(PARAMS.get("page", 1)))
        elif action == "about":
            about()
        elif action == "refresh":
            refresh()
        elif action == "clear_cache":
            util.cache_clear()
            ui.notify("Кешът е изчистен")
            xbmc.executebuiltin("Container.Refresh")
        else:
            root()
    except Exception as exc:
        util.log("dispatch error (%s): %s" % (action, exc), xbmc.LOGERROR)
        ui.error("Възникна грешка: %s" % exc)


if __name__ == "__main__":
    dispatch()
