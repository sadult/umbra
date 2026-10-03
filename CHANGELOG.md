# Changelog

## 1.2.0
- **Fetch all lyrics**: Settings → Lyrics walks the whole library and attaches LRCLIB lyrics (as `.lrc`, embedded, or Umbra-only); also available per selection from the right-click menu.
- **Spotify & YouTube playlists**: import a playlist / album link, save it as an Umbra playlist, stream it, **Download all**, and **Sync** it later. Optional Spotify API keys import playlists beyond 100 tracks.
- Downloads run in a queue (3 at a time); finished downloads replace the stream in every playlist and keep plays & favorites. Downloaded streams always play from disk.
- Optional auto-download of new tracks when a playlist is synced.
- Sleep timer (15–90 min or end of track) with a 20 s fade — Now Playing and tray.

## 1.1.0
- Every appearance setting now applies live (radius, glass, blur, grain, backdrop, accent, visualizer, compact sidebar, interface scale).
- Now Playing: queue and lyrics fully separated; lyrics on/off leaves a calm empty stage; responsive layout.
- Online lyrics search with one-click **Add lyrics** (side-car `.lrc` or embedded).
- Download YouTube Music & Spotify tracks (M4A / MP3 / Opus / FLAC) with tags and artwork; optional browser cookies for yt-dlp.
- New **Small player** with analyzer and visualizer.
- App icon on Home; new About page.
- Clicking the player-bar cover toggles Now Playing.
- Removed the small crescent marks; fixed Artists page flicker and resize glitches.

## 1.0.0
- First release — glass UI, 10-band EQ, analyzer, synced lyrics, tag editor, streaming.
