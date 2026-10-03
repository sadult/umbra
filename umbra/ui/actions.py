"""Context menus & common actions shared by every view."""
import os
import subprocess
import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from . import icons
from .context import ctx
from .widgets import ask_text, glass_menu


def _act(menu, text, icon, fn, enabled=True):
    a = QAction(icons.qicon(icon, "#e8e8ee", 16), text, menu)
    a.triggered.connect(fn)
    a.setEnabled(enabled)
    menu.addAction(a)
    return a


def reveal(path):
    if not path or not os.path.exists(path):
        return
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def playlist_submenu(parent, ids):
    m = glass_menu(parent)
    m.setTitle("Add to playlist")
    m.setIcon(icons.qicon("playlists", "#e8e8ee", 16))

    def new():
        name = ask_text(ctx.win, "New playlist", "Name", "New playlist")
        if name:
            ctx.lib.create_playlist(name, ids)
            ctx.win.refresh_playlists()
            ctx.toast(f"Created “{name}”", "playlists")
    _act(m, "New playlist…", "plus", new)
    pls = ctx.lib.playlists()
    if pls:
        m.addSeparator()
    for pl in pls:
        def add(_=False, pid=pl["id"], name=pl["name"]):
            ctx.lib.add_to_playlist(pid, ids)
            ctx.win.refresh_playlists()
            ctx.toast(f"Added to “{name}”", "playlists")
        _act(m, pl["name"], "playlists", add)
    return m


def track_menu(parent, tracks, playlist_id=None, on_removed=None, queue_positions=None):
    if not tracks:
        return None
    ids = [t["id"] for t in tracks]
    t0 = tracks[0]
    p = ctx.player
    m = glass_menu(parent)
    _act(m, "Play", "play", lambda: p.play_tracks(ids))
    _act(m, "Play next", "queue", lambda: p.play_next(ids))
    _act(m, "Add to queue", "plus", lambda: p.add_to_queue(ids))
    m.addMenu(playlist_submenu(m, ids))
    m.addSeparator()
    fav = all(t.get("favorite") for t in tracks)
    _act(m, "Remove from favorites" if fav else "Add to favorites", "heart",
         lambda: [p.toggle_favorite(i) for i in ids if bool(ctx.lib.get(i).get("favorite")) == fav])
    local = [t for t in tracks if t.get("source", "local") == "local"]
    _act(m, f"Edit tags{'' if len(local) < 2 else f' ({len(local)} tracks)'}…", "tag",
         lambda: ctx.win.open_tag_editor(local), bool(local))
    m.addSeparator()
    if t0.get("album"):
        _act(m, "Go to album", "albums", lambda: ctx.win.open_album(t0["album"], t0.get("albumartist") or t0.get("artist") or "Unknown Artist"))
    if t0.get("artist"):
        _act(m, "Go to artist", "artists", lambda: ctx.win.open_artist(t0.get("albumartist") or t0["artist"]))
    if t0.get("source", "local") == "local":
        _act(m, "Show in Explorer", "folder", lambda: reveal(t0["path"]))
    elif t0.get("url"):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        _act(m, "Open on web", "external", lambda: QDesktopServices.openUrl(QUrl(t0["url"])))
    streams = [t for t in tracks if t.get("source", "local") != "local" and ctx.downloads.state(t) is None]
    if streams:
        _act(m, f"Download{'' if len(streams) < 2 else f' ({len(streams)} tracks)'}", "download",
             lambda: ctx.downloads.download_many(streams))
    if local:
        def fetch():
            if ctx.lyrics_batch.start(local, None, False):
                ctx.toast(f"Fetching lyrics for {len(local)} track(s)…", "lyrics")
            else:
                ctx.toast("A lyrics fetch is already running", "info")
        _act(m, f"Fetch lyrics from LRCLIB{'' if len(local) < 2 else f' ({len(local)} tracks)'}", "lyrics", fetch)
    if playlist_id is not None and on_removed:
        m.addSeparator()
        _act(m, "Remove from playlist", "trash", on_removed)
    if queue_positions is not None:
        m.addSeparator()
        _act(m, "Remove from queue", "trash", lambda: p.remove_at(queue_positions))
    return m


def sleep_menu(parent):
    """Sleep timer choices — shared by Now Playing and the tray."""
    p = ctx.player
    m = glass_menu(parent)
    m.setTitle("Sleep timer")
    left = p.sleep_remaining()
    if left is not None:
        txt = "after this track" if left == "end" else f"{left // 60}:{left % 60:02d} left"
        _act(m, f"Turn off  ({txt})", "close", lambda: (p.set_sleep(None), ctx.toast("Sleep timer off", "clock")))
        m.addSeparator()
    for mins in (15, 30, 45, 60, 90):
        _act(m, f"{mins} minutes", "clock", lambda mins=mins: (p.set_sleep(mins), ctx.toast(f"Pausing in {mins} minutes", "clock")))
    _act(m, "End of this track", "clock", lambda: (p.set_sleep("end"), ctx.toast("Pausing after this track", "clock")))
    return m
