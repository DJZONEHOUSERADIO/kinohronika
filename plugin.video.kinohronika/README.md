# Kinohronika — Kodi Add-on

[![License: GPL v2](https://img.shields.io/badge/License-GPLv2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)
[![Kodi](https://img.shields.io/badge/Kodi-19%20%7C%2020%20%7C%2021-2082ea)](https://kodi.tv)
[![Release](https://img.shields.io/github/v/release/DJZONEHOUSERADIO/kinohronika?include_prereleases)](https://github.com/DJZONEHOUSERADIO/kinohronika/releases)

Unofficial community Kodi add-on for **news, cinema, television and radio** from Bulgarian and Russian sources — with a daily programme shaped like an old cinema bill.

**Add-on ID:** `plugin.video.kinohronika`  
**Version:** 1.0.4  
**Requires:** Kodi 19 (Matrix) or newer

---

## Idea

**Session of the Day** builds an evening programme the way cinemas used to: newsreel → cartoon → film of the day → radio to close. The cartoon and film are chosen deterministically from the date, so each day gets a different session.

---

## Features

- **News** — Bulgarian and Russian RSS feeds in one timeline, or filtered by country and source. Read articles inside Kodi or open them in a browser.
- **Cinema & animation** — public collections on [archive.org](https://archive.org), plus official YouTube channels from Mosfilm, Soyuzmultfilm, Gosteleradiofond, BNT and Belarusfilm.
- **Live TV & series** — channels and catalogue from SMOTRIM and smotret.tv.
- **Live radio** — Bulgarian National Radio (BNR) programmes.
- **KinoGo catalogue** — new titles, premieres, films and series by genre, anime, animation, TV shows, collections and search, with seasons/episodes where available. The add-on picks a working mirror (`kinogo.org` / `kinogo.la`), discovers sources via a smotret-style pipeline (direct streams, embedded players, mirror pages), shows a Kodi chooser when several sources are available, and resolves the selection with the right headers (including VK Video and OK.ru).
- **Languages** — Bulgarian, English and Russian UI strings.

---

## Install

### From GitHub Release (recommended)

1. Download **`plugin.video.kinohronika-1.0.4.zip`** from the [Releases](https://github.com/DJZONEHOUSERADIO/kinohronika/releases) page.
2. In Kodi: **Add-ons → Install from zip file** → select the zip.
3. Optional: install **YouTube** (`plugin.video.youtube`) for studio-channel playback, and **InputStream Adaptive** for HLS.

### From source

```bash
git clone https://github.com/DJZONEHOUSERADIO/kinohronika.git
cd kinohronika
# zip the plugin.video.kinohronika folder and install that zip in Kodi
```

---

## Dependencies

Managed by Kodi where possible:

| Dependency | Required |
|---|---|
| `xbmc.python` 3.0.0+ | yes |
| `script.module.requests` | yes |
| `script.module.beautifulsoup4` | yes |
| `inputstream.adaptive` | optional (HLS) |
| `plugin.video.youtube` | optional (official studio channels) |

---

## Notes

- The add-on does **not** host or redistribute media files. It links to public RSS feeds, archive.org items, official studio channels, live streams and third-party catalogues.
- Availability of live TV, VOD and catalogue items depends on the source site, your network and regional restrictions (for example SMOTRIM may geo-block outside Russia).
- The KinoGo section loads metadata and video sources from an external site; playback depends on that site and the supported resolvers.

---

## License

GPL-2.0-only — see [LICENSE](LICENSE).

Content rights belong to their respective owners.
