"""Umbra — persistent settings & paths."""
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

APP_NAME = "Umbra"
APP_VERSION = "1.2.0"
APP_TAGLINE = "music, in the dark."

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".mp4", ".aac",
              ".wma", ".aif", ".aiff", ".ape", ".wv", ".alac", ".dsf", ".mka", ".webm"}


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(sub: str) -> Path:
    d = data_dir() / "cache" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULTS = {
    # appearance
    "theme": "Eclipse",
    "accent_source": "theme",      # theme | artwork | windows | wallpaper | custom
    "custom_accent": "#9db4ff",
    "backdrop": "void",           # void | artwork | wallpaper | acrylic
    "glass_opacity": 0.50,
    "backdrop_dim": 0.70,
    "backdrop_blur": 3,              # 1..5 blur passes
    "radius": 12,
    "grain": True,
    "ambient_motion": True,
    "animations": True,
    "anim_speed": 1.0,
    "specular": True,                # cursor-following liquid highlight
    "visualizer_style": "bars",      # bars | mirror | liquid | radial | scope
    "visualizer_bands": 56,
    "np_lyrics": True,               # Now Playing: show lyrics
    "np_analyzer": True,             # Now Playing: show analyzer card
    "np_visualizer": True,           # Now Playing: show bottom visualizer
    "sidebar_compact": False,
    "font_scale": 1.0,
    # playback
    "volume": 0.8,
    "muted": False,
    "shuffle": False,
    "repeat": "off",                 # off | all | one
    "output_device": None,
    "exclusive": False,
    "buffer_ms": 120,
    "crossfade": 0.0,
    "gapless": True,
    "fade_pause_ms": 180,
    "leveling": "off",               # off | rg_track | rg_album | smart
    "leveling_target": -14.0,
    "leveling_preamp": 0.0,
    "limiter": True,
    "mono": False,
    "swap_channels": False,
    "balance": 0.0,
    "stereo_width": 1.0,
    "eq_enabled": False,
    "eq_gains": [0.0] * 10,
    "eq_preamp": 0.0,
    "eq_preset": "Flat",
    "eq_custom": {},
    "bass_boost": 0.0,
    "play_count_threshold": 0.5,
    "resume_session": True,
    # library
    "scan_on_start": True,
    "watch_folders": True,
    "folder_art_names": "cover,folder,front,album,artwork",
    # lyrics
    "online_lyrics": True,
    "lyrics_size": 26,
    "lyrics_align": "left",
    "lyrics_offset": 0.0,
    "lyrics_blur_far": True,
    "lyrics_batch_mode": "lrc",      # lrc | embed | cache  — where "Fetch all lyrics" saves results
    # streaming
    "streaming_enabled": True,
    "stream_quality": "best",
    "download_dir": "",              # empty → ~/Music/Umbra Downloads
    "download_format": "m4a",        # m4a | mp3 | opus | flac (needs FFmpeg) ; native otherwise
    "download_add_library": True,
    "playlist_autodownload": False,  # download new tracks when a Spotify / YouTube playlist is synced
    "spotify_client_id": "",         # optional Spotify app — imports playlists longer than 100 tracks
    "spotify_client_secret": "",
    "ytdlp_cookies": "none",         # none | chrome | edge | firefox | brave — fixes "confirm you're not a bot"
    "downloaded": {},                # stream path → local file
    # internal
    "geometry": None,
    "session": None,
    "first_run": True,
}


class Settings(QObject):
    changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.path = data_dir() / "settings.json"
        self._d = dict(DEFAULTS)
        try:
            if self.path.exists():
                self._d.update(json.loads(self.path.read_text("utf-8")))
        except Exception:
            pass
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self.save)

    def get(self, key, default=None):
        v = self._d.get(key, DEFAULTS.get(key, default))
        return default if v is None and default is not None else v

    def __getitem__(self, key):
        return self.get(key)

    def set(self, key, value, emit=True):
        if self._d.get(key) == value:
            return
        self._d[key] = value
        self._timer.start()
        if emit:
            self.changed.emit(key, value)

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._d, indent=2, ensure_ascii=False), "utf-8")
            tmp.replace(self.path)
        except Exception as e:
            print("settings save failed:", e)


_settings = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
