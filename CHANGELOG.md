# Changelog

All notable changes to the **Kinohronika** Kodi add-on (`plugin.video.kinohronika`) are documented here.

## [1.0.4] — 2026-11-10

### Added
- Source discovery method ported from `plugin.video.smotret`: direct streams, embedded players and mirror pages
- Native Kodi dialog when more than one playable source is found, so the user can choose which stream to start
- Selected sources are resolved with the matching HTTP headers and resolver

### Changed
- KinoGo playback pipeline uses the new smotret-style discovery while keeping VK Video and OK.ru support from the previous release

## [1.0.1] — 2026-11-10

### Added
- KinoGo catalogue: new titles, premieres, films/series by genre, anime, animation, TV shows, collections and search
- Season and episode browsing for series
- Automatic mirror selection between `kinogo.org` and `kinogo.la`
- Built-in resolvers for supported KinoGo video players
- Optional InputStream Adaptive dependency for HLS playback
- `requests` and `beautifulsoup4` module dependencies

### Changed
- Packaging and metadata for the 1.0.1 zip release

## [1.0.0] — 2026-11-10

### Added
- Initial release for Kodi 19 / 20 / 21
- Session of the Day (newsreel → cartoon → film → radio)
- Bulgarian and Russian RSS news with in-Kodi reader
- archive.org cinema and animation collections
- Official YouTube channels: Mosfilm, Soyuzmultfilm, Gosteleradiofond, BNT, Belarusfilm
- Live TV via SMOTRIM and smotret.tv
- Live BNR radio programmes
- Bulgarian, English and Russian interface strings
