<div align="center">

<img src="docs/cover.png" alt="Umbra — music, in the dark." width="100%">

<br>

<img src="umbra/assets/umbra.png" width="84" alt="Umbra icon">

# Umbra

**music, in the dark.**
A local-first, lossless-friendly music player for Windows — wrapped in liquid glass.

پخش‌کننده‌ی موسیقی تیره، مینیمال و «لیکوئید گلس» برای ویندوز — نوشته‌شده با پایتون

[![Release](https://img.shields.io/github/v/release/sadult/umbra?style=flat-square&color=ffb25c&labelColor=111)](https://github.com/sadult/umbra/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/sadult/umbra/build.yml?style=flat-square&labelColor=111)](https://github.com/sadult/umbra/actions)
![Python](https://img.shields.io/badge/python-3.10%2B-ffb25c?style=flat-square&labelColor=111)
![Qt](https://img.shields.io/badge/Qt-PySide6-ffb25c?style=flat-square&labelColor=111)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-ffb25c?style=flat-square&labelColor=111)
[![License](https://img.shields.io/badge/license-MIT-ffb25c?style=flat-square&labelColor=111)](LICENSE)

[Features](#-features) · [Screenshots](#-screenshots) · [Install](#-install) · [Shortcuts](#-keyboard-shortcuts) · [Build](#-build-an-exe) · [فارسی](#-فارسی)

</div>

---

## ✦ Features

| | |
|---|---|
| 🎧 **Audio engine** | 64-bit float pipeline, gapless, crossfade, fades on pause/seek, 10-band EQ + presets, bass, preamp, stereo width / balance / mono, loudness leveling, soft limiter, WASAPI exclusive, device & buffer selection |
| 📊 **Audio analyzer** | Codec, bit depth, sample rate, bitrate, lossless / lossy / hi-res, true peak, LUFS (BS.1770), dynamic range, live 20 Hz–20 kHz spectrum, L/R meters |
| 🎤 **Lyrics** | Synced `.lrc`, embedded SYLT/USLT or plain; auto-fetch from LRCLIB; **search online & add** with one click (side-car `.lrc` or embedded); click a line to seek |
| 🌒 **Now Playing** | Artwork with a spinning vinyl, lyrics stage (or calm empty space when lyrics are off), analyzer and visualizer toggles; responsive at any size |
| 🪟 **Three players** | Full window · **Small player** (cover, analyzer & visualizer in a compact window) · Mini player — all always-on-top capable |
| 📚 **Library** | Watched folders, songs, albums, artists, genres, folders, playlists (drag & drop, M3U), instant search, smart lists (Recently played, Most played, Recently added, Favorites, Never played, Random discovery) |
| 🏷️ **Tag editor** | Batch editing, artwork (file / paste / drag / online), auto-number, title case, tags ⇄ filename, rename files |
| ☁️ **Streaming** | YouTube Music search & play (yt-dlp); Spotify and YouTube playlist / album links imported — **save as playlist, stream, sync** |
| ⬇️ **Downloads** | Any track or a **whole playlist** — M4A / MP3 / Opus / FLAC, tagged with artwork, queued 3 at a time; playlists switch to the local files automatically |
| 🔤 **Fetch all lyrics** | One button in Settings → Lyrics finds LRCLIB lyrics for your entire library (saved as `.lrc`, embedded, or Umbra-only) |
| 🌙 **Sleep timer** | 15–90 minutes or end of track, with a soft fade-out |
| 🎨 **Design** | Frameless window, liquid-glass panels, Windows acrylic blur, 7 themes, accent from artwork / Windows / wallpaper / custom, glass density, blur, radius, grain, motion, interface scale, compact sidebar — **all live** |

## ✦ Screenshots

<div align="center">

<img src="docs/screenshots/home.png" width="100%" alt="Home">
<sub>Home — a calm bento of what you're playing, your library and what's on repeat.</sub>

<br><br>

<img src="docs/screenshots/now-playing.png" width="100%" alt="Now Playing">
<sub>Now Playing — synced lyrics, analyzer and visualizer.</sub>

<br><br>

<table>
<tr>
<td width="50%"><img src="docs/screenshots/small-player.png" alt="Small player"><br><sub>Small player</sub></td>
<td width="50%"><img src="docs/screenshots/lyrics-search.png" alt="Lyrics search"><br><sub>Search lyrics online & add</sub></td>
</tr>
<tr>
<td><img src="docs/screenshots/albums.png" alt="Albums"><br><sub>Albums</sub></td>
<td><img src="docs/screenshots/queue.png" alt="Queue"><br><sub>Queue panel</sub></td>
</tr>
<tr>
<td><img src="docs/screenshots/settings.png" alt="Settings"><br><sub>Settings · Streaming & downloads</sub></td>
<td><img src="docs/screenshots/about.png" alt="About"><br><sub>About</sub></td>
</tr>
</table>

<img src="docs/screenshots/mini-player.png" width="420" alt="Mini player"><br>
<sub>Mini player</sub>

</div>

## ✦ Install

**Requirements:** Windows 10/11 · Python 3.10+ · [FFmpeg](https://ffmpeg.org) on `PATH` (recommended — AAC/M4A/Opus/WMA decoding, streaming and downloads).

```powershell
git clone https://github.com/sadult/umbra.git
cd umbra
pip install -r requirements.txt
python main.py
```

Or just double-click **`run.bat`** — it creates a virtual environment on first launch.

Install FFmpeg in one line: `winget install Gyan.FFmpeg`

> **Spotify playlists longer than 100 tracks?** Create a free app at [developer.spotify.com](https://developer.spotify.com/dashboard) and paste its Client ID / secret in *Settings → Streaming → Spotify API*.

> **YouTube says “confirm you're not a bot”?** Open *Settings → Streaming → Browser cookies* and pick the browser you're signed in to YouTube with.

Prebuilt Windows builds are on the [Releases](https://github.com/sadult/umbra/releases) page.

## ✦ Keyboard shortcuts

| Keys | Action | Keys | Action |
|---|---|---|---|
| `Space` | Play / pause | `Ctrl` `L` | Lyrics on / off |
| `Ctrl` `→` / `←` | Next / previous | `Ctrl` `Q` | Queue panel |
| `→` / `←` | Seek ±5 s | `Ctrl` `M` | Mini player |
| `Shift` `→` / `←` | Seek ±30 s | `Ctrl` `Shift` `M` | Small player |
| `Ctrl` `↑` / `↓` | Volume | `F11` | Immersive Now Playing |
| `M` | Mute | `Ctrl` `E` | Edit tags |
| `Ctrl` `K` | Search | `Ctrl` `D` | Favorite |
| `Ctrl` `S` / `R` | Shuffle / repeat | `Ctrl` `,` | Settings |

Media keys work globally. Click the cover in the player bar to open Now Playing — click again to close it.

## ✦ Build an exe

```powershell
build.bat          # → dist\Umbra\Umbra.exe
```

Every push to `main` is also built by [GitHub Actions](.github/workflows/build.yml); tagged pushes (`v*`) publish a release zip.

## ✦ Make it yours

The About page reads from [`umbra/about_config.py`](umbra/about_config.py) — name, handle, bio, avatar, links, changelog and credits.
Banner images are generated by [`tools/make_banner.py`](tools/make_banner.py).

## ✦ Project structure

```
umbra/
├── app.py              # bootstrap, single instance, tray
├── player.py           # queue, playback state, favorites
├── audio/              # decoder, float engine, DSP, EQ, analyzer
├── library/            # SQLite library, scanner, tags, lyrics, streaming, downloader
├── ui/                 # window, pages, glass widgets, visuals, mini & small player, settings, about
├── theme.py            # themes & accent extraction
├── winsys.py           # Windows acrylic, media keys, taskbar
└── assets/             # icon
docs/                   # banner & screenshots
tools/make_banner.py    # renders docs/cover.png
```

Data (library database, cache, settings) lives in `%APPDATA%\Umbra`.

## ✦ Credits

[LRCLIB](https://lrclib.net) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Mutagen](https://github.com/quodlibet/mutagen) · [libsndfile](https://libsndfile.github.io/libsndfile/) · [FFmpeg](https://ffmpeg.org) · [Qt for Python](https://doc.qt.io/qtforpython/)

Spotify does not permit third-party audio streaming — Umbra only reads public Spotify metadata and plays the closest YouTube match. Download only what you have the right to.

## ✦ فارسی

**Umbra** یک پخش‌کننده‌ی موسیقی تیره و مینیمال برای ویندوز است: موتور صوتی ۶۴ بیتی، اکولایزر ۱۰ باند، آنالیزور صدا (LUFS، پیک، داینامیک)، متن آهنگ همگام با جست‌وجوی آنلاین و افزودن با یک کلیک، ویرایشگر تگ، پخش، ذخیره، همگام‌سازی و **دانلود** آهنگ و پلی‌لیست از YouTube Music و Spotify، دریافت خودکار لیریک برای کل کتابخانه با یک دکمه، تایمر خواب، پلیر کوچک و مینی‌پلیر، و ۷ تم شیشه‌ای.

**اجرا:**
```
pip install -r requirements.txt
python main.py
```
یا روی `run.bat` دوبار کلیک کنید. برای پشتیبانی کامل از فرمت‌ها و دانلود، FFmpeg را نصب کنید: `winget install Gyan.FFmpeg`

اگر یوتیوب پیام «confirm you're not a bot» داد، از *Settings → Streaming → Browser cookies* مرورگری را که در آن وارد یوتیوب شده‌اید انتخاب کنید.

برای تغییر اطلاعات بخش «درباره»، فایل `umbra/about_config.py` را ویرایش کنید.

## ✦ Author

<table>
<tr>
<td><img src="umbra/assets/umbra.png" width="64"></td>
<td>

**Mersad Shahidi** · [@Bitologist](https://t.me/Bitologist)
🌐 [10ck.ir](https://10ck.ir) · 🐙 [github.com/sadult](https://github.com/sadult) · ✈️ [t.me/Bitologist](https://t.me/Bitologist)

</td>
</tr>
</table>

<div align="center">
<sub>Released under the <a href="LICENSE">MIT License</a> · Made with care in the dark.</sub>
</div>
