"""All library pages."""
import os
import random
import threading
import time

from PySide6.QtCore import QRectF, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..library import streaming
from ..library.db import album_artist
from ..theme import hash_color
from . import icons
from .actions import track_menu, playlist_submenu, _act
from .context import ctx
from .chrome import QueueList
from .grid import CoverGrid
from .tracklist import TrackListPanel, TrackList
from .visuals import AnalyzerCard, LyricsView, Visualizer, VinylHero
from .widgets import (FlowLayout, Badge, Caption, ChipButton, FadeStack, GlassPanel, IconButton, PillButton, PlayButton, Segmented, SearchField,
                      TextField, ask_text, confirm, fmt_long, fmt_time, font, glass_menu, label, paint_glass)


def scroll_page(parent):
    sa = QScrollArea(parent)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setAttribute(Qt.WA_TranslucentBackground)
    sa.setWidget(inner)
    sa.viewport().setAutoFillBackground(False)
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(28, 22, 28, 28)
    lay.setSpacing(18)
    return sa, lay


def album_item(a):
    sub = a["aa"] + (f"  ·  {a['year']}" if a.get("year") else "")
    return {"kind": "album", "title": a["album"], "subtitle": sub, "album": a["album"], "aa": a["aa"],
            "art": {"album": a["album"], "albumartist": a["aa"], "path": a["path"], "source": a.get("source", "local"),
                    "thumb": a.get("thumb")},
            "badge": "HI-RES" if False else ("" if not a.get("lossless") else "")}


def track_item(t):
    return {"kind": "track", "title": t.get("title"), "subtitle": t.get("artist") or "", "art": t, "id": t["id"]}


def artist_item(a):
    return {"kind": "artist", "title": a["name"], "subtitle": f"{a['albums']} albums · {a['n']} tracks", "round": True,
            "name": a["name"], "art": {"album": a.get("album"), "albumartist": a["name"], "path": a["path"],
                                       "source": a.get("source", "local"), "thumb": a.get("thumb")}}


class PageHeader(QWidget):
    """Large editorial header: kicker, title, meta + action row."""

    def __init__(self, kicker="", title="", parent=None, art=None, art_round=False, icon=None):
        super().__init__(parent)
        self.art, self.art_round, self.icon = art, art_round, icon
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(24)
        self.cover = QWidget()
        self.cover.setFixedSize(0, 0)
        self.cover.paintEvent = self._paint_cover
        lay.addWidget(self.cover, 0, Qt.AlignLeft | Qt.AlignBottom)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addStretch()
        self.kicker = Caption(kicker)
        self.title = label(title, 30, QFont.Bold)
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.meta = label("", 9.5, alpha=150)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        col.addWidget(self.kicker)
        col.addWidget(self.title)
        col.addWidget(self.meta)
        col.addSpacing(10)
        col.addLayout(self.actions)
        lay.addLayout(col, 1)
        ctx.art.ready.connect(lambda _k: self.cover.update())

    def set(self, kicker=None, title=None, meta=None, art=None, icon=None, art_round=None, size=176):
        if kicker is not None:
            self.kicker.setText(kicker.upper())
        if title is not None:
            self.title.setText(title)
            self.title.setFont(font(30 if len(title) < 28 else 22, QFont.Bold))
        if meta is not None:
            self.meta.setText(meta)
        self.art, self.icon = art, icon
        if art_round is not None:
            self.art_round = art_round
        s = size if (art or icon) else 0
        self.cover.setFixedSize(s, s)
        self.cover.update()

    def _paint_cover(self, _):
        w = self.cover
        if w.width() == 0:
            return
        p = QPainter(w)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        s = w.width()
        r = QRectF(6, 4, s - 12, s - 12)
        rad = r.width() / 2 if self.art_round else 16
        for i in range(10, 0, -2):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 12))
            p.drawRoundedRect(r.adjusted(-i * .3, i * .4, i * .3, i * .8), rad, rad)
        if self.art:
            p.drawPixmap(r.toRect(), ctx.art.get(self.art, int(r.width()), int(rad)))
        else:
            th = ctx.theme
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, th.acc(90))
            g.setColorAt(1, QColor(14, 14, 18))
            p.setBrush(g)
            p.drawRoundedRect(r, rad, rad)
            icons.draw(p, self.icon or "songs", r.adjusted(r.width() * .3, r.width() * .3, -r.width() * .3, -r.width() * .3),
                       QColor(255, 255, 255, 220), 1.3)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)


class Page(QWidget):
    key = ""

    def load(self, **kw):
        pass

    def refresh(self):
        self.load(**getattr(self, "_args", {}))


# ═══════════════════════════════════════════════════════════════════════ track pages
SMART = {
    "recent_played": ("Recently Played", "clock", "Everything you listened to, newest first", "played"),
    "most_played": ("Most Played", "flame", "Your all-time heavy rotation", "played"),
    "recent_added": ("Recently Added", "new", "Fresh arrivals in your library", "added"),
    "favorites": ("Favorites", "heart", "Tracks you loved", "added"),
    "never_played": ("Never Played", "ghost", "Hidden corners of your library — shuffled", "added"),
    "discovery": ("Random Discovery", "dice", "Weighted towards forgotten & unplayed tracks", "played"),
    "lossless": ("Lossless", "drop", "FLAC, ALAC, WAV and friends", "added"),
    "hires": ("Hi-Res", "sparkle", "Above CD quality — 24-bit or > 48 kHz", "added"),
}


class TrackPage(Page):
    syncDone = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 8)
        lay.setSpacing(14)
        self.header = PageHeader()
        lay.addWidget(self.header)
        tb = QHBoxLayout()
        tb.setSpacing(8)
        self.play = PillButton("Play", "play", primary=True)
        self.shuf = PillButton("Shuffle", "shuffle")
        self.more = IconButton("more", 36, 18, "More")
        self.play.clicked.connect(lambda: ctx.player.play_tracks(self.panel.list.ids(), 0, shuffle=False))
        self.shuf.clicked.connect(lambda: ctx.player.play_tracks(self.panel.list.ids(), 0, shuffle=True))
        self.more.clicked.connect(self._more)
        self.reroll = PillButton("Reroll", "dice")
        self.reroll.clicked.connect(self.refresh)
        self.filter = SearchField("Filter", hint="")
        self.filter.setFixedWidth(220)
        self.filter.textChanged.connect(self._apply_filter)
        self.sort = QComboBox()
        for k, l in (("artist", "Artist"), ("album", "Album"), ("title", "Title"), ("added", "Date added"),
                     ("plays", "Most played"), ("duration", "Duration"), ("year", "Year")):
            self.sort.addItem(l, k)
        self.sort.currentIndexChanged.connect(lambda _: self.refresh())
        self.dl = PillButton("Download", "download")
        self.dl.clicked.connect(self._download)
        self.sync = PillButton("Sync", "refresh")
        self.sync.setToolTip("Re-read the original Spotify / YouTube playlist and update this one")
        self.sync.clicked.connect(self._sync_remote)
        self.syncDone.connect(self._sync_done)
        ctx.downloads.batch.connect(lambda *_: self.isVisible() and self._dl_state())
        for w in (self.play, self.shuf, self.reroll, self.dl, self.sync, self.more):
            tb.addWidget(w)
        tb.addStretch()
        tb.addWidget(self.filter)
        tb.addWidget(self.sort)
        lay.addLayout(tb)
        self.panel = TrackListPanel(self)
        lay.addWidget(self.panel, 1)
        self.all_rows = []
        self.empty = label("", 11, alpha=110)
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.empty.hide()

    def load(self, kind="songs", **kw):
        self._args = dict(kind=kind, **kw)
        lib = ctx.lib
        order = self.sort.currentData()
        self.reroll.setVisible(kind == "smart" and kw.get("smart") in ("discovery", "never_played"))
        self.sort.setVisible(kind in ("songs", "genre", "folder", "smart") and kw.get("smart") not in ("recent_played", "most_played", "discovery"))
        lst = self.panel.list
        lst.playlist_id = None
        lst.date_mode = "added"
        art, icon, rnd = None, None, False
        if kind == "songs":
            rows = lib.tracks("source='local'", order=order)
            title, kick, icon = "Songs", "Library", "songs"
        elif kind == "smart":
            sk = kw["smart"]
            rows = lib.smart(sk, limit=500)
            if order and sk in ("favorites", "lossless", "hires", "recent_added", "never_played") and self.sort.currentIndex() > 0:
                rows = lib.tracks("id IN (%s)" % ",".join(str(r["id"]) for r in rows) if rows else "0", order=order)
            title, icon, desc, dm = SMART[sk]
            kick = "Smart playlist"
            lst.date_mode = dm
        elif kind == "genre":
            g = kw["genre"]
            rows = lib.tracks("COALESCE(NULLIF(genre,''),'Unknown')=? COLLATE NOCASE AND source='local'", (g,), order=order)
            title, kick, icon = g, "Genre", "genres"
        elif kind == "folder":
            f = kw["folder"]
            rows = lib.tracks("path LIKE ?", (f.rstrip("\\/") + "%",), order=order)
            title, kick, icon = os.path.basename(f.rstrip("\\/")) or f, "Folder", "folder"
        elif kind == "playlist":
            pid = kw["pid"]
            pl = next((p for p in lib.playlists() if p["id"] == pid), None)
            rows = lib.playlist_tracks(pid)
            title, kick = (pl["name"] if pl else "Playlist"), "Playlist"
            lst.playlist_id = pid
            art = rows[0] if rows else None
            icon = "playlists"
            if pl and pl.get("origin"):
                o = pl["origin"].split(":")
                kick = ("Spotify " + (o[1] if len(o) > 2 else "playlist")) if o[0] == "spotify" else "YouTube playlist"
        else:
            rows, title, kick = [], "", ""
        self.all_rows = rows
        self._pl = pl if kind == "playlist" else None
        self._dl_state()
        dur = sum(r.get("duration") or 0 for r in rows)
        meta = f"{len(rows)} tracks  ·  {fmt_long(dur)}"
        if kind == "smart":
            meta = SMART[kw['smart']][2] + "   ·   " + meta
        self.header.set(kick, title, meta, art=art, icon=icon, size=150)
        self._apply_filter(self.filter.text())
        self.empty.setVisible(not rows)
        self.empty.setText("Nothing here yet." if kind != "smart" else "Nothing here yet — play some music.")

    def _dl_state(self):
        rows = self.all_rows
        streams = [t for t in rows if t.get("source", "local") != "local"]
        pend = ctx.downloads.pending(streams)
        busy = [t for t in pend if ctx.downloads.state(t) is not None]
        self.dl.setVisible(bool(streams) and bool(pend))
        self.dl.setEnabled(not busy)
        self.dl.setText(f"Downloading · {len(pend) - len(busy)} left" if busy else f"Download {len(pend)}")
        self.sync.setVisible(bool(self._pl and self._pl.get("link")))

    def _download(self):
        n = ctx.downloads.download_many(self.all_rows)
        if n:
            ctx.toast(f"Downloading {n} tracks — the playlist switches to the local files as they finish", "download")
        self._dl_state()

    def _sync_remote(self):
        pl = self._pl
        if not pl or not pl.get("link"):
            return
        self.sync.setEnabled(False)
        self.sync.setText("Syncing…")

        def run():
            try:
                self.syncDone.emit(pl["id"], streaming.fetch_link(pl["link"]))
            except Exception as e:
                self.syncDone.emit(pl["id"], str(e))
        threading.Thread(target=run, daemon=True).start()

    def _sync_done(self, pid, info):
        self.sync.setEnabled(True)
        self.sync.setText("Sync")
        if isinstance(info, str):
            ctx.toast("Sync failed — " + info, "info")
            return
        before = len(ctx.lib.playlist_tracks(pid))
        ids = ctx.downloads.prefer_local([ctx.lib.add_stream(it) for it in info["tracks"]])
        info = dict(info, origin=self._pl["origin"])
        ctx.lib.save_remote_playlist(info, ids)
        ctx.win.refresh_playlists()
        d = len(ids) - before
        ctx.toast(f"Synced “{info['name']}” · {len(ids)} tracks" + (f" · {d:+d}" if d else " · up to date"), "refresh")
        if ctx.settings["playlist_autodownload"]:
            ctx.downloads.download_many(ctx.lib.playlist_tracks(pid))
        self.refresh()

    def _apply_filter(self, text):
        text = text.strip().lower()
        if not text:
            self.panel.list.set_tracks(self.all_rows)
            return
        terms = text.split()
        rows = [r for r in self.all_rows if all(any(t in (r.get(k) or "").lower() for k in ("title", "artist", "album", "genre")) for t in terms)]
        self.panel.list.set_tracks(rows)

    def _more(self):
        m = glass_menu(self)
        ids = self.panel.list.ids()
        _act(m, "Add all to queue", "queue", lambda: ctx.player.add_to_queue(ids))
        m.addMenu(playlist_submenu(m, ids))
        local = [t for t in self.panel.list.tracks() if t.get("source", "local") == "local"]
        _act(m, "Edit tags of all…", "tag", lambda: ctx.win.open_tag_editor(local), bool(local))
        a = self._args
        if a.get("kind") == "playlist":
            m.addSeparator()
            pid = a["pid"]

            def rename():
                n = ask_text(ctx.win, "Rename playlist", "Name", self.header.title.text())
                if n:
                    ctx.lib.rename_playlist(pid, n)
                    ctx.win.refresh_playlists()
                    self.refresh()

            def export():
                fn, _ = QFileDialog.getSaveFileName(self, "Export playlist", self.header.title.text() + ".m3u8", "M3U8 (*.m3u8)")
                if fn:
                    with open(fn, "w", encoding="utf-8") as f:
                        f.write("#EXTM3U\n")
                        for t in self.panel.list.tracks():
                            if t.get("source", "local") == "local":
                                f.write(f"#EXTINF:{int(t.get('duration') or 0)},{t.get('artist')} - {t.get('title')}\n{t['path']}\n")
                    ctx.toast("Playlist exported", "download")

            def delete():
                if confirm(ctx.win, "Delete playlist", f"Delete “{self.header.title.text()}”? Tracks stay in your library.", "Delete"):
                    ctx.lib.delete_playlist(pid)
                    ctx.win.refresh_playlists()
                    ctx.win.navigate("home")
            _act(m, "Rename…", "edit", rename)
            _act(m, "Export as M3U8…", "download", export)
            _act(m, "Delete playlist", "trash", delete)
        m.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))


# ═══════════════════════════════════════════════════════════════════════ grids
class GridPage(Page):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 8)
        lay.setSpacing(14)
        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        self.kicker = Caption("Library")
        self.title = label({"albums": "Albums", "artists": "Artists", "genres": "Genres", "playlists": "Playlists"}[kind], 30, QFont.Bold)
        self.meta = label("", 9.5, alpha=150)
        col.addWidget(self.kicker)
        col.addWidget(self.title)
        col.addWidget(self.meta)
        top.addLayout(col)
        top.addStretch()
        self.filter = SearchField("Filter", hint="")
        self.filter.setFixedWidth(220)
        self.filter.textChanged.connect(self._filter)
        top.addWidget(self.filter, 0, Qt.AlignBottom)
        if kind == "albums":
            self.sort = Segmented([("artist", "Artist"), ("album", "Title"), ("year", "Year"), ("added", "Added"), ("plays", "Plays")])
            self.sort.changed.connect(lambda _: self.refresh())
            top.addWidget(self.sort, 0, Qt.AlignBottom)
        if kind == "playlists":
            b = PillButton("New playlist", "plus", primary=True)
            b.clicked.connect(self._new_pl)
            imp = PillButton("Import M3U", "download")
            imp.clicked.connect(self._import)
            top.addWidget(imp, 0, Qt.AlignBottom)
            top.addWidget(b, 0, Qt.AlignBottom)
        lay.addLayout(top)
        self.grid = CoverGrid(self)
        self.grid.opened.connect(self._open)
        self.grid.playRequested.connect(self._play)
        self.grid.menuRequested.connect(self._menu)
        lay.addWidget(self.grid, 1)
        self.items = []

    def load(self, **kw):
        self._args = kw
        lib = ctx.lib
        if self.kind == "albums":
            al = lib.albums(order=self.sort.cur)
            self.items = [album_item(a) for a in al]
            self.meta.setText(f"{len(al)} albums")
        elif self.kind == "artists":
            ar = lib.artists()
            self.items = [artist_item(a) for a in ar]
            self.meta.setText(f"{len(ar)} artists")
        elif self.kind == "genres":
            gs = lib.genres()
            gi = {"rock": "flame", "electronic": "wave", "jazz": "sparkle", "classical": "albums", "pop": "heart",
                  "hip-hop": "headphones", "ambient": "drop", "metal": "flame"}
            self.items = [{"kind": "genre", "title": g["name"], "subtitle": f"{g['n']} tracks · {fmt_long(g['dur'])}",
                           "tile": True, "color": hash_color(g["name"], 0.22, 0.2), "icon": gi.get(g["name"].lower(), "genres"),
                           "genre": g["name"]} for g in gs]
            self.meta.setText(f"{len(gs)} genres")
        elif self.kind == "playlists":
            pls = lib.playlists()
            smart = [{"kind": "smart", "smart": k, "title": v[0], "subtitle": "Smart playlist", "tile": True,
                      "icon": v[1], "color": QColor(30, 30, 38)} for k, v in SMART.items()]
            mine = []
            for pl in pls:
                tr = lib.playlist_tracks(pl["id"])[:1]
                mine.append({"kind": "playlist", "pid": pl["id"], "title": pl["name"], "subtitle": f"{pl['n']} tracks",
                             "art": tr[0] if tr else {"title": pl["name"]}})
            self.items = mine + smart
            self.meta.setText(f"{len(pls)} playlists · {len(smart)} smart")
        self._filter(self.filter.text())

    def _filter(self, text):
        t = text.strip().lower()
        self.grid.set_items([i for i in self.items if not t or t in (i["title"] or "").lower() or t in (i.get("subtitle") or "").lower()])

    def _open(self, it):
        ctx.win.open_item(it)

    def _play(self, it):
        ctx.win.play_item(it)

    def _menu(self, it, gpos):
        ids = ctx.win.item_ids(it)
        m = glass_menu(self)
        _act(m, "Play", "play", lambda: ctx.player.play_tracks(ids))
        _act(m, "Shuffle", "shuffle", lambda: ctx.player.play_tracks(ids, shuffle=True))
        _act(m, "Play next", "queue", lambda: ctx.player.play_next(ids))
        _act(m, "Add to queue", "plus", lambda: ctx.player.add_to_queue(ids))
        m.addMenu(playlist_submenu(m, ids))
        if it["kind"] in ("album", "artist", "genre"):
            m.addSeparator()
            _act(m, "Edit tags…", "tag", lambda: ctx.win.open_tag_editor(ctx.lib.get_many(ids)))
        if it["kind"] == "playlist":
            m.addSeparator()
            _act(m, "Delete playlist", "trash", lambda: (ctx.lib.delete_playlist(it["pid"]), ctx.win.refresh_playlists(), self.refresh()))
        m.exec(gpos)

    def _new_pl(self):
        n = ask_text(ctx.win, "New playlist", "Name", "New playlist")
        if n:
            pid = ctx.lib.create_playlist(n)
            ctx.win.refresh_playlists()
            ctx.win.navigate("tracks", kind="playlist", pid=pid)

    def _import(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Import playlist", "", "Playlists (*.m3u *.m3u8)")
        if not fn:
            return
        base = os.path.dirname(fn)
        ids = []
        with open(fn, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line if os.path.isabs(line) else os.path.normpath(os.path.join(base, line))
                r = ctx.lib.q("SELECT id FROM tracks WHERE path=?", (p,))
                if r:
                    ids.append(r[0]["id"])
        pid = ctx.lib.create_playlist(os.path.splitext(os.path.basename(fn))[0], ids)
        ctx.win.refresh_playlists()
        ctx.toast(f"Imported {len(ids)} tracks", "playlists")
        ctx.win.navigate("tracks", kind="playlist", pid=pid)


# ═══════════════════════════════════════════════════════════════════════ album / artist
class AlbumPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 8)
        lay.setSpacing(16)
        self.header = PageHeader()
        lay.addWidget(self.header)
        self.play = PillButton("Play", "play", primary=True)
        self.shuf = PillButton("Shuffle", "shuffle")
        self.edit = PillButton("Edit album", "tag")
        self.q = IconButton("queue", 36, 18, "Add to queue")
        self.artist_btn = ChipButton("Artist", "artists")
        for w in (self.play, self.shuf, self.edit, self.q):
            self.header.actions.addWidget(w)
        self.header.actions.addStretch()
        self.panel = TrackListPanel(self, show_album=False, show_cover=False, number_mode="track")
        lay.addWidget(self.panel, 1)
        self.play.clicked.connect(lambda: ctx.player.play_tracks(self.panel.list.ids(), 0, shuffle=False))
        self.shuf.clicked.connect(lambda: ctx.player.play_tracks(self.panel.list.ids(), 0, shuffle=True))
        self.edit.clicked.connect(lambda: ctx.win.open_tag_editor(self.panel.list.tracks()))
        self.q.clicked.connect(lambda: ctx.player.add_to_queue(self.panel.list.ids()))

    def load(self, album="", aa="", **kw):
        self._args = dict(album=album, aa=aa)
        rows = ctx.lib.album_tracks(album, aa)
        self.panel.list.set_tracks(rows)
        t = rows[0] if rows else {"album": album, "albumartist": aa}
        dur = sum(r.get("duration") or 0 for r in rows)
        yr = max((r.get("year") or 0) for r in rows) if rows else 0
        genre = next((r["genre"] for r in rows if r.get("genre")), "")
        q = ""
        if rows:
            t0 = rows[0]
            if t0.get("lossless"):
                q = f"  ·  {(t0.get('codec') or '').upper()} {t0.get('bitdepth') or 16}/{(t0.get('samplerate') or 44100) / 1000:g}"
            else:
                q = f"  ·  {(t0.get('codec') or '').upper()} {t0.get('bitrate') or ''} kbps"
        parts = [aa] + ([str(yr)] if yr else []) + ([genre] if genre else []) + [f"{len(rows)} tracks", fmt_long(dur)]
        self.header.set("Album", album, "  ·  ".join(parts) + q, art=t, size=200)


class ArtistPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page(self)
        outer.addWidget(sa)
        self.header = PageHeader()
        lay.addWidget(self.header)
        self.play = PillButton("Play", "play", primary=True)
        self.shuf = PillButton("Shuffle", "shuffle")
        self.radio = PillButton("Artist radio", "wave")
        for w in (self.play, self.shuf, self.radio):
            self.header.actions.addWidget(w)
        self.header.actions.addStretch()
        lay.addWidget(Caption("Popular"))
        self.top = TrackList(self, show_album=True)
        self.top.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.top)
        lay.addWidget(Caption("Discography"))
        self.albums = CoverGrid(self, shelf=True)
        self.albums.opened.connect(lambda it: ctx.win.open_item(it))
        self.albums.playRequested.connect(lambda it: ctx.win.play_item(it))
        lay.addWidget(self.albums)
        lay.addStretch()
        self.play.clicked.connect(lambda: ctx.player.play_tracks([r["id"] for r in self.all], 0, shuffle=False))
        self.shuf.clicked.connect(lambda: ctx.player.play_tracks([r["id"] for r in self.all], 0, shuffle=True))
        self.radio.clicked.connect(self._radio)
        self.all = []

    def load(self, name="", **kw):
        self._args = dict(name=name)
        self.all = ctx.lib.artist_tracks(name, "album")
        top = sorted(self.all, key=lambda r: -(r.get("play_count") or 0))[:8]
        self.top.set_tracks(top)
        self.top.setFixedHeight(56 * len(top) + 6)
        als = ctx.lib.albums("source='local' AND (lower(albumartist)=lower(?) OR lower(artist)=lower(?))", (name, name), order="year")
        self.albums.set_items([album_item(a) for a in als])
        dur = sum(r.get("duration") or 0 for r in self.all)
        plays = sum(r.get("play_count") or 0 for r in self.all)
        self.header.set("Artist", name, f"{len(als)} albums  ·  {len(self.all)} tracks  ·  {fmt_long(dur)}  ·  {plays} plays",
                        art=self.all[0] if self.all else None, art_round=True, size=190)

    def _radio(self):
        ids = [r["id"] for r in self.all]
        genres = {r.get("genre") for r in self.all if r.get("genre")}
        extra = []
        for g in genres:
            extra += [r["id"] for r in ctx.lib.tracks("genre=? COLLATE NOCASE AND source='local'", (g,), order="RANDOM()", limit=25)]
        pool = list(dict.fromkeys(ids[:30] + extra))
        random.shuffle(pool)
        ctx.player.play_tracks(pool[:80])


# ═══════════════════════════════════════════════════════════════════════ home
class StatTile(QWidget):
    def __init__(self, value, label_, icon, parent=None):
        super().__init__(parent)
        self.v, self.l, self.i = value, label_, icon
        self.setFixedHeight(84)
        self.setMinimumWidth(130)
        self._hover = None
        self.setMouseTracking(True)

    def set(self, v):
        self.v = v
        self.update()

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, None, 0.8, self._hover)
        icons.draw(p, self.i, QRectF(r.right() - 34, 14, 18, 18), ctx.theme.acc(200))
        p.setFont(font(19, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 245))
        p.drawText(QRectF(16, 12, r.width() - 50, 34), Qt.AlignLeft | Qt.AlignVCenter, str(self.v))
        p.setFont(font(8, QFont.Medium))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(16, 48, r.width() - 20, 20), Qt.AlignLeft | Qt.AlignVCenter, self.l)


class HeroCard(QWidget):
    """'Now playing / pick up where you left off' glass hero with live visualizer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = None
        self.setMouseTracking(True)
        self.setMinimumHeight(292)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(10)
        lay = QHBoxLayout()
        lay.setSpacing(20)
        self.cover = QWidget()
        self.cover.setFixedSize(166, 166)
        self.cover.paintEvent = self._cover
        self.cover.setCursor(Qt.PointingHandCursor)
        self.cover.mouseReleaseEvent = lambda e: ctx.win.navigate("nowplaying")
        lay.addWidget(self.cover, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.kick = Caption("Now playing")
        self.title = label("", 20, QFont.Bold)
        self.title.setWordWrap(True)
        self.sub = label("", 10, alpha=165)
        self.sub.setWordWrap(True)
        self.meta = label("", 8.2, alpha=110)
        self.meta.setFont(font(8.2, mono=True))
        col.addWidget(self.kick)
        col.addSpacing(4)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        col.addStretch()
        col.addWidget(self.meta)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.play = PillButton("Play", "play", primary=True)
        self.open = PillButton("Open", "nowplaying")
        self.play.clicked.connect(ctx.player.toggle)
        self.open.clicked.connect(lambda: ctx.win.navigate("nowplaying"))
        row.addWidget(self.play)
        row.addWidget(self.open)
        row.addStretch()
        col.addSpacing(6)
        col.addLayout(row)
        lay.addLayout(col, 1)
        outer.addLayout(lay, 1)
        self.viz = Visualizer(self, compact=True)
        self.viz.setFixedHeight(40)
        outer.addWidget(self.viz)
        ctx.player.trackChanged.connect(self.update_track)
        ctx.player.stateChanged.connect(self._state)
        ctx.art.ready.connect(lambda _k: self.cover.update())
        self.update_track(ctx.player.current)

    def _state(self, st):
        self.play.setText("Pause" if st == "playing" else "Play")
        self.play.icon_name = "pause" if st == "playing" else "play"
        self.kick.setText("NOW PLAYING" if st == "playing" else "PICK UP WHERE YOU LEFT OFF")
        self.play.update()

    def update_track(self, t):
        if not t:
            self.title.setText("Nothing playing")
            self.sub.setText("Pick something from your library, or let Discovery surprise you.")
            self.meta.setText("")
            self.cover.update()
            return
        self.title.setText(t.get("title") or "")
        self.sub.setText(" · ".join(x for x in (t.get("artist"), t.get("album")) if x))
        bits = []
        if t.get("codec"):
            bits.append(t["codec"].upper())
        if t.get("lossless") and t.get("bitdepth"):
            bits.append(f"{t['bitdepth']}-bit / {(t.get('samplerate') or 0) / 1000:g} kHz")
        elif t.get("bitrate"):
            bits.append(f"{t['bitrate']} kbps")
        bits.append(fmt_time(t.get("duration")))
        if t.get("play_count"):
            bits.append(f"played {t['play_count']}×")
        self.meta.setText("   ·   ".join(bits))
        self.cover.update()
        self._state(ctx.player.engine.state)

    def _cover(self, _):
        p = QPainter(self.cover)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        t = ctx.player.current or {"title": "Umbra"}
        r = QRectF(0, 0, 166, 166)
        p.drawPixmap(r.toRect(), ctx.art.get(t, 166, 16))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 16, 16)

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, None, 1.0, self._hover, accent_edge=0.6)


class Onboarding(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 30)
        lay.setSpacing(8)
        lay.addWidget(Caption("Welcome to Umbra"))
        lay.addWidget(label("Bring your music into the dark.", 24, QFont.Bold))
        lay.addWidget(label("Add one or more folders — Umbra keeps them as live references, watches for changes and "
                            "reads every tag, cover and lyric it can find.", 10, alpha=160, wrap=True))
        lay.addStretch()
        row = QHBoxLayout()
        b = PillButton("Add music folder", "folder", primary=True)
        b.clicked.connect(lambda: ctx.win.add_folder())
        s = PillButton("Stream from YouTube Music", "ytmusic")
        s.clicked.connect(lambda: ctx.win.navigate("stream", service="ytmusic"))
        row.addWidget(b)
        row.addWidget(s)
        row.addStretch()
        lay.addLayout(row)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, None, 1.0, accent_edge=1.0)
        g = QRadialGradient(QPointF(r.right() - 120, r.top() + 40), 380)
        g.setColorAt(0, ctx.theme.acc(60))
        g.setColorAt(1, ctx.theme.acc(0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 22, 22)
        icons.draw(p, "albums", QRectF(r.right() - 190, r.top() + 30, 160, 160), QColor(255, 255, 255, 22), 0.8)


class Tile(QWidget):
    """Bento cell: quiet glass slab with a mono caption and hover light."""
    clicked = Signal()

    def __init__(self, caption="", parent=None, clickable=True):
        super().__init__(parent)
        self.caption = caption
        self._hover = None
        self.setMouseTracking(True)
        self.setMinimumHeight(132)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paint_base(self, p):
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, None, 0.85, self._hover)
        if self.caption:
            p.setFont(font(7.2, QFont.DemiBold, 1.8, mono=True))
            p.setPen(QColor(255, 255, 255, 115))
            p.drawText(QRectF(18, 14, r.width() - 36, 16), Qt.AlignLeft | Qt.AlignVCenter, self.caption.upper())
        return r

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_base(p)


class FigureTile(Tile):
    """A single big number — the bento's typographic anchor."""

    def __init__(self, caption, icon, parent=None):
        super().__init__(caption, parent)
        self.icon, self.value, self.unit, self.foot = icon, "0", "", ""

    def set(self, value, unit="", foot=""):
        self.value, self.unit, self.foot = value, unit, foot
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.paint_base(p)
        icons.draw(p, self.icon, QRectF(r.right() - 34, 14, 16, 16), ctx.theme.acc(220))
        f = font(30, QFont.Bold)
        f.setLetterSpacing(QFont.PercentageSpacing, 96)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 245))
        fm = QFontMetrics(f)
        y = r.bottom() - 46
        p.drawText(QRectF(18, y - 40, r.width() - 36, 44), Qt.AlignLeft | Qt.AlignBottom, self.value)
        if self.unit:
            p.setFont(font(10, QFont.DemiBold))
            p.setPen(ctx.theme.acc(230))
            p.drawText(QRectF(26 + fm.horizontalAdvance(self.value), y - 44, 120, 40), Qt.AlignLeft | Qt.AlignBottom, self.unit)
        p.setFont(font(8.4))
        p.setPen(QColor(255, 255, 255, 125))
        p.drawText(QRectF(18, y + 8, r.width() - 36, 18), Qt.AlignLeft | Qt.AlignVCenter, self.foot)


class MixTile(Tile):
    """Smart-list shortcut: crescent glyph, title, count; click opens, ▶ plays."""

    def __init__(self, smart, parent=None):
        super().__init__("", parent)
        self.smart = smart
        self.n = 0

    def set_count(self, n):
        self.n = n
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if QRectF(self.width() - 52, self.height() - 52, 40, 40).contains(e.position()):
            ids = [t["id"] for t in ctx.lib.smart(self.smart, 200)]
            ctx.player.play_tracks(ids, shuffle=self.smart in ("discovery", "never_played"))
        else:
            ctx.win.navigate("tracks", kind="smart", smart=self.smart)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.paint_base(p)
        title, icon, desc, _o = SMART[self.smart]
        th = ctx.theme
        icons.draw(p, icon, QRectF(18, 18, 22, 22), th.acc(235))
        p.setFont(font(13, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 240))
        tw = r.width() - 70
        fs = 13
        while fs > 9.5 and QFontMetrics(font(fs, QFont.Bold)).horizontalAdvance(title) > tw:
            fs -= 0.5
        p.setFont(font(fs, QFont.Bold))
        p.drawText(QRectF(18, r.bottom() - 58, tw, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.ElideRight, int(tw)))
        p.setFont(font(8.2, mono=True))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(18, r.bottom() - 34, r.width() - 80, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{self.n} TRACKS" if self.n else "EMPTY")
        c = QPointF(self.width() - 32, self.height() - 32)
        hov = self._hover is not None
        p.setPen(Qt.NoPen)
        p.setBrush(th.accent if hov else QColor(255, 255, 255, 22))
        p.drawEllipse(c, 16, 16)
        icons.draw(p, "play", QRectF(c.x() - 7, c.y() - 7, 14, 14), QColor(10, 10, 12) if hov else QColor(255, 255, 255, 210))


class ListTile(Tile):
    """Compact ranked track list (On repeat)."""

    def __init__(self, caption, parent=None):
        super().__init__(caption, parent)
        self.tracks = []

    def set_tracks(self, tracks):
        self.tracks = tracks[:4]
        self.update()

    def _row(self, pos):
        i = int((pos.y() - 40) // 36)
        return i if 0 <= i < len(self.tracks) and pos.y() >= 40 else -1

    def mouseReleaseEvent(self, e):
        i = self._row(e.position())
        if e.button() == Qt.LeftButton and i >= 0:
            ctx.player.play_tracks([t["id"] for t in self.tracks], i)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.paint_base(p)
        hi = self._row(self._hover) if self._hover is not None else -1
        for i, t in enumerate(self.tracks):
            y = 40 + i * 36
            row = QRectF(10, y, r.width() - 20, 34)
            if i == hi:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 14))
                p.drawRoundedRect(row, 8, 8)
            p.setFont(font(9, QFont.DemiBold, mono=True))
            p.setPen(ctx.theme.acc(220) if i == 0 else QColor(255, 255, 255, 90))
            p.drawText(QRectF(18, y, 22, 34), Qt.AlignLeft | Qt.AlignVCenter, f"{i + 1:02d}")
            p.drawPixmap(QRectF(46, y + 4, 26, 26).toRect(), ctx.art.get(t, 26, 5))
            fm = QFontMetrics(font(9.4, QFont.DemiBold))
            p.setFont(font(9.4, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255, 235))
            w = r.width() - 170
            p.drawText(QRectF(82, y, w, 34), Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(t.get("title") or "", Qt.ElideRight, int(w)))
            p.setFont(font(8.2))
            p.setPen(QColor(255, 255, 255, 110))
            p.drawText(QRectF(r.width() - 140, y, 120, 34), Qt.AlignRight | Qt.AlignVCenter,
                       QFontMetrics(font(8.2)).elidedText(t.get("artist") or "", Qt.ElideRight, 80) + f"  ·  {t.get('play_count') or 0}×")
        if not self.tracks:
            p.setFont(font(9))
            p.setPen(QColor(255, 255, 255, 100))
            p.drawText(r, Qt.AlignCenter, "Play something — your heavy rotation shows up here.")


class CoversTile(Tile):
    """Recently added: a row of covers."""

    def __init__(self, caption, parent=None):
        super().__init__(caption, parent)
        self.items = []

    def set_items(self, items):
        self.items = items[:5]
        self.update()

    def _cells(self):
        n = max(1, len(self.items))
        w = self.width() - 36
        s = min(self.height() - 64, (w - (n - 1) * 10) / n)
        return [QRectF(18 + i * (s + 10), 40, s, s) for i in range(len(self.items))]

    def mouseReleaseEvent(self, e):
        for it, c in zip(self.items, self._cells()):
            if c.adjusted(0, 0, 0, 22).contains(e.position()):
                ctx.win.open_item(it)
                return
        ctx.win.navigate("tracks", kind="smart", smart="recent_added")

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_base(p)
        for it, c in zip(self.items, self._cells()):
            p.drawPixmap(c.toRect(), ctx.art.get(it["art"], int(c.width()), 8))
            if self._hover is not None and c.contains(self._hover):
                p.setPen(QPen(ctx.theme.acc(200), 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(c.adjusted(.7, .7, -.7, -.7), 8, 8)
            p.setFont(font(8.2, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255, 200))
            p.drawText(QRectF(c.left(), c.bottom() + 4, c.width(), 16), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(font(8.2, QFont.DemiBold)).elidedText(it.get("title") or "", Qt.ElideRight, int(c.width())))


class HomePage(Page):
    """Bento home: one hero, a handful of figures and shortcuts, one shelf. Calm by design."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page(self)
        outer.addWidget(sa)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.date = Caption("")
        self.greet = QLabel()
        self.greet.setFont(font(30, QFont.Bold))
        self.greet.setStyleSheet("background: transparent; color: white;")
        col.addWidget(self.date)
        col.addWidget(self.greet)
        top = QHBoxLayout()
        top.addLayout(col)
        top.addStretch()
        self.brand = QWidget()
        self.brand.setFixedSize(230, 76)
        self.brand.paintEvent = lambda e: self._brand()
        self.brand.setCursor(Qt.PointingHandCursor)
        self.brand.mouseReleaseEvent = lambda e: ctx.win.navigate("about")
        top.addWidget(self.brand, 0, Qt.AlignBottom)
        lay.addLayout(top)
        lay.addSpacing(4)
        self.onb = Onboarding()
        lay.addWidget(self.onb)
        self.bento = QWidget()
        g = QGridLayout(self.bento)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(12)
        self.hero = HeroCard()
        self.f_lib = FigureTile("Library", "songs")
        self.f_time = FigureTile("Listening time", "clock")
        self.m_fav = MixTile("favorites")
        self.m_disc = MixTile("discovery")
        self.t_rep = ListTile("On repeat")
        self.t_new = CoversTile("Recently added")
        self.f_lib.clicked.connect(lambda: ctx.win.navigate("tracks", kind="all"))
        self.f_time.clicked.connect(lambda: ctx.win.navigate("tracks", kind="smart", smart="most_played"))
        g.addWidget(self.hero, 0, 0, 2, 2)
        g.addWidget(self.f_lib, 0, 2)
        g.addWidget(self.f_time, 0, 3)
        g.addWidget(self.m_fav, 1, 2)
        g.addWidget(self.m_disc, 1, 3)
        g.addWidget(self.t_rep, 2, 0, 1, 2)
        g.addWidget(self.t_new, 2, 2, 1, 2)
        for c in range(4):
            g.setColumnStretch(c, 1)
        for rr, h in ((0, 140), (1, 140), (2, 192)):
            g.setRowMinimumHeight(rr, h)
        lay.addWidget(self.bento)
        # one shelf only
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 10, 0, 0)
        bl.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(Caption("Jump back in"))
        row.addStretch()
        more = ChipButton("Show all")
        more.clicked.connect(lambda: ctx.win.navigate("tracks", kind="smart", smart="recent_played"))
        row.addWidget(more)
        bl.addLayout(row)
        self.recent = CoverGrid(self, cell=150, shelf=True)
        self.recent.opened.connect(lambda it: ctx.win.open_item(it))
        self.recent.playRequested.connect(lambda it: ctx.win.play_item(it))
        bl.addWidget(self.recent)
        self.recent_box = box
        lay.addWidget(box)
        lay.addStretch()

    def _brand(self):
        from .window import app_icon
        from ..config import APP_VERSION
        p = QPainter(self.brand)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        W = self.brand.width()
        ic = getattr(self, "_icon", None)
        if ic is None or getattr(self, "_icon_acc", None) != ctx.theme.accent.name():
            self._icon = ic = app_icon(152)
            self._icon_acc = ctx.theme.accent.name()
        p.drawPixmap(QRectF(W - 76, 0, 76, 76).toRect(), ic)
        p.setFont(font(12, QFont.Bold, 5))
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(0, 14, W - 88, 26), Qt.AlignRight | Qt.AlignVCenter, "UMBRA")
        p.setFont(font(8.4))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(0, 38, W - 88, 18), Qt.AlignRight | Qt.AlignVCenter, "music, in the dark.")
        p.setFont(font(7, QFont.DemiBold, 1.4, mono=True))
        p.setPen(ctx.theme.acc(200))
        p.drawText(QRectF(0, 56, W - 88, 14), Qt.AlignRight | Qt.AlignVCenter, f"v{APP_VERSION}")

    def load(self, **kw):
        h = time.localtime().tm_hour
        part = "Good night" if h < 5 else "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"
        self.greet.setText(f"{part}<span style='color:{ctx.theme.accent.name()}'>.</span>")
        self.date.setText(time.strftime("%A · %d %B"))
        lib = ctx.lib
        s = lib.stats()
        empty = s["tracks"] == 0
        self.onb.setVisible(empty)
        self.bento.setVisible(not empty)
        self.f_lib.set(f"{s['tracks']:,}", "tracks", f"{s['albums']} albums  ·  {s['artists']} artists")
        lossless = (100 * s["lossless"] / s["tracks"]) if s["tracks"] else 0
        hrs = s["dur"] / 3600
        self.f_time.set(f"{hrs:.1f}" if hrs < 10 else f"{hrs:.0f}", "h", f"{lossless:.0f}% lossless  ·  {s['plays']:,} plays")
        self.m_fav.set_count(len(lib.smart("favorites", 9999)))
        self.m_disc.set_count(min(s["tracks"], 80))
        self.t_rep.set_tracks([t for t in lib.smart("most_played", 4) if t.get("play_count")])
        self.t_new.set_items([album_item(a) for a in lib.albums(order="added")[:5]])
        recent_albums, seen = [], set()
        for t in lib.smart("recent_played", 80):
            k = (album_artist(t).lower(), (t.get("album") or "").lower())
            if k in seen:
                continue
            seen.add(k)
            recent_albums.append(album_item({"album": t["album"], "aa": album_artist(t), "year": t.get("year"),
                                             "path": t["path"], "source": t.get("source"), "thumb": t.get("thumb")})
                                 if t.get("album") else track_item(t))
            if len(recent_albums) >= 14:
                break
        self.recent.set_items(recent_albums)
        self.recent_box.setVisible(bool(recent_albums))


# ═══════════════════════════════════════════════════════════════════════ folders
class FolderRow(QWidget):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setFixedHeight(74)
        self._hover = None
        self.setMouseTracking(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 14, 0)
        lay.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("folder", ctx.theme.accent.name(), 22))
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addStretch()
        st = ctx.lib.folder_stats(path)
        exists = os.path.isdir(path)
        col.addWidget(label(os.path.basename(path.rstrip("\\/")) or path, 11, QFont.DemiBold))
        col.addWidget(label(f"{path}   ·   {st['n']} tracks · {fmt_long(st['d'])} · {st['s'] / 1e9:.1f} GB" +
                            ("" if exists else "   ·   ⚠ offline"), 8.5, alpha=120))
        col.addStretch()
        lay.addLayout(col, 1)
        o = ChipButton("Open", "forward")
        o.clicked.connect(lambda: ctx.win.navigate("tracks", kind="folder", folder=path))
        r = IconButton("refresh", 32, 16, "Rescan this folder")
        r.clicked.connect(lambda: ctx.scanner.scan([path]))
        d = IconButton("trash", 32, 16, "Remove reference")
        d.clicked.connect(self._remove)
        for w in (o, r, d):
            lay.addWidget(w)

    def _remove(self):
        if confirm(ctx.win, "Remove folder", f"Stop tracking “{self.path}”? Files on disk are not touched.", "Remove"):
            ctx.lib.remove_folder(self.path)
            ctx.scanner.refresh_watch()
            ctx.win.reload_current()
            ctx.win.library_changed()

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_glass(p, self, QRectF(self.rect()).adjusted(1, 1, -1, -1), None, 0.8, self._hover)


class FoldersPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, self.lay = scroll_page(self)
        outer.addWidget(sa)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(Caption("Library"))
        col.addWidget(label("Folders", 30, QFont.Bold))
        col.addWidget(label("Folders are references — Umbra never moves or copies your files.", 9.5, alpha=140))
        head.addLayout(col)
        head.addStretch()
        b = PillButton("Add folder", "plus", primary=True)
        b.clicked.connect(lambda: ctx.win.add_folder())
        r = PillButton("Rescan all", "refresh")
        r.clicked.connect(lambda: ctx.scanner.scan())
        f = PillButton("Full re-read", "tag")
        f.setToolTip("Re-read every tag even if files did not change")
        f.clicked.connect(lambda: ctx.scanner.scan(full=True))
        for w in (f, r, b):
            head.addWidget(w, 0, Qt.AlignBottom)
        self.lay.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(10)
        self.lay.addLayout(self.rows)
        self.lay.addStretch()

    def load(self, **kw):
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        fs = ctx.lib.folders()
        for f in fs:
            self.rows.addWidget(FolderRow(f))
        if not fs:
            self.rows.addWidget(label("No folders yet. Add one to start building your library.", 11, alpha=120))


# ═══════════════════════════════════════════════════════════════════════ search
class SearchPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page(self)
        outer.addWidget(sa)
        self.kick = Caption("Search")
        self.title = label("", 26, QFont.Bold)
        lay.addWidget(self.kick)
        lay.addWidget(self.title)
        row = QHBoxLayout()
        self.yt = ChipButton("Search YouTube Music", "ytmusic")
        self.yt.clicked.connect(lambda: ctx.win.navigate("stream", service="ytmusic", query=self.q))
        row.addWidget(self.yt)
        row.addStretch()
        lay.addLayout(row)
        self.c_tracks = Caption("Songs")
        lay.addWidget(self.c_tracks)
        self.tracks = TrackList(self)
        self.tracks.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.tracks)
        self.c_alb = Caption("Albums")
        lay.addWidget(self.c_alb)
        self.albums = CoverGrid(self, shelf=True)
        lay.addWidget(self.albums)
        self.c_art = Caption("Artists")
        lay.addWidget(self.c_art)
        self.artists = CoverGrid(self, shelf=True)
        lay.addWidget(self.artists)
        for g in (self.albums, self.artists):
            g.opened.connect(lambda it: ctx.win.open_item(it))
            g.playRequested.connect(lambda it: ctx.win.play_item(it))
        lay.addStretch()
        self.q = ""

    def load(self, query="", **kw):
        self._args = dict(query=query)
        self.q = query
        self.title.setText(f"“{query}”")
        rows = ctx.lib.search(query, 60)
        self.tracks.set_tracks(rows[:12])
        self.tracks.setFixedHeight(56 * min(12, len(rows)) + 6)
        ql = query.lower()
        albums = [a for a in ctx.lib.albums() if ql in a["album"].lower() or ql in a["aa"].lower()][:20]
        self.albums.set_items([album_item(a) for a in albums])
        arts = [a for a in ctx.lib.artists() if ql in a["name"].lower()][:20]
        self.artists.set_items([artist_item(a) for a in arts])
        for c, w, n in ((self.c_tracks, self.tracks, len(rows)), (self.c_alb, self.albums, len(albums)), (self.c_art, self.artists, len(arts))):
            c.setVisible(n > 0)
            w.setVisible(n > 0)
        self.kick.setText(f"SEARCH · {len(rows)} SONGS · {len(albums)} ALBUMS · {len(arts)} ARTISTS")


# ═══════════════════════════════════════════════════════════════════════ streaming
SERVICES = {
    "ytmusic": ("YouTube Music", "ytmusic", "Search the YouTube Music catalogue and stream instantly — or paste a YouTube / "
                                          "YouTube Music playlist link to import it."),
    "spotify": ("Spotify", "spotify", "Paste a public Spotify track, album or playlist link. Save it as a playlist, stream it "
                                      "(matched from YouTube — Spotify doesn't allow third-party streaming) or download it."),
}


class StreamPage(Page):
    results = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 8)
        lay.setSpacing(12)
        self.header = PageHeader()
        lay.addWidget(self.header)
        row = QHBoxLayout()
        self.field = SearchField("Search songs, artists…", hint="Enter")
        self.field.returnPressed.connect(self._go)
        self.go = PillButton("Search", "search", primary=True)
        self.go.clicked.connect(self._go)
        row.addWidget(self.field, 1)
        row.addWidget(self.go)
        lay.addLayout(row)
        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.play = PillButton("Play all", "play")
        self.play.clicked.connect(lambda: ctx.player.play_tracks(ctx.downloads.prefer_local(self.panel.list.ids()), 0))
        self.shuf = PillButton("Shuffle", "shuffle")
        self.shuf.clicked.connect(lambda: ctx.player.play_tracks(ctx.downloads.prefer_local(self.panel.list.ids()), 0, shuffle=True))
        self.save = PillButton("Save as playlist", "playlists")
        self.save.clicked.connect(self._save)
        self.dl = PillButton("Download all", "download")
        self.dl.clicked.connect(self._download)
        self.open_pl = PillButton("Open playlist", "external")
        self.open_pl.clicked.connect(lambda: self._pid and ctx.win.navigate("tracks", kind="playlist", pid=self._pid))
        for w in (self.play, self.shuf, self.save, self.dl, self.open_pl):
            acts.addWidget(w)
        acts.addStretch()
        self.status = label("", 9.5, alpha=130)
        acts.addWidget(self.status)
        lay.addLayout(acts)
        self.panel = TrackListPanel(self, show_album=True)
        lay.addWidget(self.panel, 1)
        self.results.connect(self._show)
        self.service = "ytmusic"
        self._tok = 0
        self._info = None     # last imported link (dict from streaming.fetch_link)
        self._pid = None
        ctx.downloads.batch.connect(lambda *_: self._sync_buttons())
        ctx.downloads.registered.connect(lambda *_: self._sync_buttons())
        self._sync_buttons()

    def load(self, service="ytmusic", query="", **kw):
        if service not in SERVICES:
            service = "ytmusic"
        changed = service != self.service
        self._args = dict(service=service)
        self.service = service
        name, icon, desc = SERVICES[service]
        self.header.set("Stream", name, desc, icon=icon, size=130)
        self.field.setPlaceholderText("Paste a Spotify link — playlist, album or track (open.spotify.com/…)" if service == "spotify"
                                      else "Search songs, artists…  or paste a YouTube playlist link")
        self.go.setText("Import" if service == "spotify" else "Search")
        if not streaming.available():
            self.status.setText("⚠  yt-dlp is not installed — run:  pip install yt-dlp   (and install FFmpeg for playback)")
        elif changed:
            self.status.setText("")
        if query:
            self.field.setText(query)
            self._go()
        elif changed or not self.panel.list.tracks():
            self._info, self._pid = None, None
            prev = ctx.lib.tracks("source=?", ("spotify" if service == "spotify" else "youtube",),
                                  order="last_played DESC, added DESC", limit=60)
            self.panel.list.set_tracks(prev)
            if prev:
                self.status.setText("Recently streamed")
        self._sync_buttons()

    def _go(self):
        q = self.field.text().strip()
        if not q:
            return
        self._tok += 1
        tok = self._tok
        svc = self.service
        link = streaming.is_link(q)
        if svc == "spotify" and not link:
            self.status.setText("⚠  Paste a Spotify link (open.spotify.com/playlist/…)")
            return
        self.status.setText("Reading link…" if link else f"Searching {SERVICES[svc][0]}…")

        def run():
            try:
                if link:
                    self.results.emit(tok, ("import", streaming.fetch_link(q)))
                else:
                    self.results.emit(tok, ("search", (q, streaming.search(q, svc, 25))))
            except Exception as e:
                self.results.emit(tok, ("error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _show(self, tok, res):
        if tok != self._tok:
            return
        kind, data = res
        if kind == "error":
            self.status.setText(f"⚠  {data}")
            return
        if kind == "import":
            info = data
            ids = [ctx.lib.add_stream(it) for it in info["tracks"]]
            if info.get("kind") == "album":
                for i in ids:
                    ctx.lib.update(i, album=info["name"])
            self._info = info
            ex = ctx.lib.playlist_by_origin(info["origin"])
            self._pid = ex["id"] if ex else None
            self.panel.list.set_tracks(ctx.lib.get_many(ids))
            what = {"playlist": "playlist", "album": "album", "track": "track"}.get(info.get("kind"), "")
            msg = f"“{info['name']}” · {len(ids)} tracks" + (f" · {what}" if what else "")
            if not info.get("complete", True):
                msg += "  ·  first 100 only — add Spotify API keys in Settings → Streaming for the rest"
            if ex:
                ctx.lib.save_remote_playlist(info, ctx.downloads.prefer_local(ids))
                ctx.win.refresh_playlists()
                msg += "  ·  saved playlist updated"
            self.status.setText(msg)
        else:
            q, items = data
            self._info, self._pid = None, None
            ids = [ctx.lib.add_stream(it) for it in items]
            self.panel.list.set_tracks(ctx.lib.get_many(ids))
            self.status.setText(f"{len(ids)} results for “{q}” · double-click to stream")
        self._sync_buttons()

    def _sync_buttons(self):
        tr = self.panel.list.tracks()
        has = bool(tr)
        for w in (self.play, self.shuf, self.save, self.dl):
            w.setVisible(has)
        pend = ctx.downloads.pending(tr) if has else []
        busy = [t for t in pend if ctx.downloads.state(t) is not None]
        self.dl.setText(f"Downloading {len(tr) - len(pend)} / {len(tr)}" if busy else
                        ("Downloaded" if has and not pend else f"Download all ({len(pend)})"))
        self.dl.setEnabled(bool(pend) and not busy)
        self.save.setText("Saved ✓" if self._pid else ("Save as playlist" if self._info else "Save all as playlist"))
        self.save.setEnabled(not self._pid)
        self.open_pl.setVisible(bool(self._pid))

    def _save(self, quiet=False):
        ids = self.panel.list.ids()
        if not ids:
            return None
        if self._info:
            pid, _ = ctx.lib.save_remote_playlist(self._info, ctx.downloads.prefer_local(ids))
            self._pid = pid
            name = self._info["name"]
        else:
            name = ask_text(ctx.win, "Save as playlist", "Name", self.field.text() or "Stream mix")
            if not name:
                return None
            pid = ctx.lib.create_playlist(name, ctx.downloads.prefer_local(ids))
        ctx.win.refresh_playlists()
        if not quiet:
            ctx.toast(f"Saved “{name}” · {len(ids)} tracks", "playlists")
        self._sync_buttons()
        return pid

    def _download(self):
        tr = self.panel.list.tracks()
        if self._info and not self._pid:
            self._save(quiet=True)   # downloading an import also keeps it as a playlist
        n = ctx.downloads.download_many(tr)
        ctx.toast(f"Downloading {n} tracks → {os.path.basename(ctx.settings['download_dir'] or 'Umbra Downloads')}" if n
                  else "Everything here is already downloaded", "download")
        self._sync_buttons()


# ═══════════════════════════════════════════════════════════════════════ now playing
class NowPlayingPage(Page):
    """Full-screen player: artwork + transport on the left, a switchable stage (lyrics / up next / visual)
    in the centre, and the analyzer on the right. Small toggles in the top-right control what is shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 16, 22, 14)
        lay.setSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(22)
        # ── left: artwork, meta, transport
        left = QVBoxLayout()
        left.setSpacing(6)
        self.hero = VinylHero()
        left.addWidget(self.hero, 1)
        self.title = label("", 22, QFont.Bold)
        self.title.setWordWrap(True)
        self.artist = label("", 11.5, QFont.Medium, alpha=190)
        self.artist.setCursor(Qt.PointingHandCursor)
        self.artist.mousePressEvent = lambda e: self._goartist()
        self.album = label("", 9.5, alpha=120)
        left.addWidget(self.title)
        left.addWidget(self.artist)
        left.addWidget(self.album)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.b_fmt = Badge("", True)
        self.b_q = Badge("")
        self.b_plays = Badge("")
        for b in (self.b_fmt, self.b_q, self.b_plays):
            chips.addWidget(b)
        chips.addStretch()
        left.addLayout(chips)
        acts = FlowLayout(spacing=2)
        self.fav = IconButton("heart", 36, 18, "Favorite")
        self.fav.clicked.connect(lambda: ctx.player.toggle_favorite())
        self.addpl = IconButton("playlists", 32, 16, "Add to playlist")
        self.addpl.clicked.connect(self._addpl)
        self.tag = IconButton("tag", 32, 16, "Edit tags")
        self.tag.clicked.connect(lambda: ctx.player.current and ctx.win.open_tag_editor([ctx.player.current]))
        self.goalb = IconButton("albums", 32, 16, "Go to album")
        self.goalb.clicked.connect(self._goalb)
        self.refetch = IconButton("search", 32, 16, "Search lyrics online")
        self.refetch.clicked.connect(lambda: self.lyrics._search())
        self.dl = IconButton("download", 32, 16, "Download this track")
        self.dl.clicked.connect(lambda: ctx.downloads.download(ctx.player.current))
        self.small = IconButton("small", 32, 16, "Small player")
        self.small.clicked.connect(lambda: ctx.win.toggle_small())
        self.mini = IconButton("mini", 32, 16, "Mini player")
        self.mini.clicked.connect(lambda: ctx.win.toggle_mini())
        self.sleep = IconButton("clock", 32, 16, "Sleep timer", checkable=True)
        self.sleep.clicked.connect(self._sleep_menu)
        ctx.player.sleepChanged.connect(self._sleep_state)
        for w in (self.fav, self.addpl, self.tag, self.dl, self.goalb, self.refetch, self.sleep, self.small, self.mini):
            acts.addWidget(w)
        left.addLayout(acts)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(380)
        self.lw = lw
        body.addWidget(lw)
        # ── centre stage
        mid = QVBoxLayout()
        mid.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(2)
        self.stage_cap = Caption("Lyrics")
        bar.addWidget(self.stage_cap)
        bar.addStretch()
        self.t_lyr = IconButton("lyrics", 30, 15, "Lyrics on / off", checkable=True)
        self.t_que = IconButton("queue", 30, 15, "Queue (opens the queue panel)", checkable=True)
        self.t_an = IconButton("analyzer", 30, 15, "Audio analyzer", checkable=True)
        self.t_viz = IconButton("wave", 30, 15, "Visualizer", checkable=True)
        for w in (self.t_lyr, self.t_que, self.t_an, self.t_viz):
            bar.addWidget(w)
        mid.addLayout(bar)
        self.stage = FadeStack()
        self.lyrics = LyricsView()
        self.lyrics.show_source = False
        self.stage.addWidget(self.lyrics)
        self.empty = QWidget()
        self.stage.addWidget(self.empty)
        mid.addWidget(self.stage, 1)
        body.addLayout(mid, 1)
        # ── analyzer
        self.card = GlassPanel(radius=None, level=0.9)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(0, 0, 0, 0)
        self.analyzer = AnalyzerCard()
        cl.addWidget(self.analyzer)
        self.card.setFixedWidth(300)
        body.addWidget(self.card)
        lay.addLayout(body, 1)
        self.viz = Visualizer(self)
        self.viz.setFixedHeight(110)
        lay.addWidget(self.viz)
        # toggles
        s = ctx.settings
        self.t_lyr.setChecked(bool(s["np_lyrics"]))
        self.t_an.setChecked(bool(s["np_analyzer"]))
        self.t_viz.setChecked(bool(s["np_visualizer"]))
        self.t_lyr.clicked.connect(lambda on: (s.set("np_lyrics", on), self._stage()))
        self.t_que.clicked.connect(lambda on: ctx.win.toggle_side("queue"))
        QTimer.singleShot(0, lambda: ctx.win.sideToggled.connect(self.t_que.setChecked))
        self.t_an.clicked.connect(lambda on: (s.set("np_analyzer", on), self._stage()))
        self.t_viz.clicked.connect(lambda on: (s.set("np_visualizer", on), self._stage()))
        ctx.settings.changed.connect(self._setting)
        ctx.player.trackChanged.connect(self._track)
        ctx.player.favoriteChanged.connect(lambda *_: self._fav())
        ctx.lyrics.loaded.connect(self._lyrics)
        self._stage()
        self._track(ctx.player.current)

    def resizeEvent(self, e):
        w = self.width()
        self.lw.setFixedWidth(380 if w > 1180 else (330 if w > 960 else 270))
        self.card.setFixedWidth(300 if w > 1180 else 272)
        self.title.setFont(font(22 if w > 960 else 18, QFont.Bold))
        super().resizeEvent(e)

    def _setting(self, k, v):
        btn = {"np_lyrics": self.t_lyr, "np_analyzer": self.t_an, "np_visualizer": self.t_viz}.get(k)
        if btn is not None:
            btn.setChecked(bool(v))
            self._stage()

    def toggle_lyrics(self):
        self.t_lyr.click()

    def _sleep_menu(self):
        from .actions import sleep_menu
        self.sleep.setChecked(ctx.player.sleep_remaining() is not None)
        sleep_menu(self).exec(self.sleep.mapToGlobal(self.sleep.rect().bottomLeft()))

    def _sleep_state(self, left):
        self.sleep.setChecked(left is not None)
        self.sleep.setToolTip("Sleep timer" if left is None else
                              ("Sleep timer · after this track" if left == "end" else f"Sleep timer · {left // 60}:{left % 60:02d} left"))

    def _stage(self):
        s = ctx.settings
        if self.t_lyr.isChecked():
            l = self.lyrics.lyr
            w = self.lyrics
            cap = "Lyrics" + (f" · {'synced' if l.kind == 'synced' else 'plain'} · {l.source}" if l and l.kind in ("synced", "plain") else "")
        else:
            w, cap = self.empty, ""
        self.stage.show_widget(w)
        self.stage_cap.setText(cap)
        self.card.setVisible(bool(s["np_analyzer"]))
        self.viz.setVisible(bool(s["np_visualizer"]))

    def _goartist(self):
        t = ctx.player.current
        if t and t.get("artist"):
            ctx.win.open_artist(album_artist(t))

    def _track(self, t):
        if not t:
            self.title.setText("Nothing playing")
            self.artist.setText("")
            self.album.setText("")
            self.lyrics.set_lyrics(None)
            self.dl.setVisible(False)
            return
        self.title.setText(t.get("title") or "")
        self.artist.setText(t.get("artist") or "")
        self.album.setText(" · ".join(str(x) for x in (t.get("album"), t.get("year") or None, t.get("genre")) if x))
        codec = (t.get("codec") or "").upper()
        self.b_fmt.setText(codec if t.get("source", "local") == "local" else t["source"].upper(), bool(t.get("lossless")))
        if t.get("lossless"):
            self.b_q.setText(f"{t.get('bitdepth') or 16}-BIT · {(t.get('samplerate') or 44100) / 1000:g} KHZ")
        elif t.get("bitrate"):
            self.b_q.setText(f"{t['bitrate']} KBPS")
        else:
            self.b_q.setText("")
        self.b_plays.setText(f"{t.get('play_count') or 0} PLAYS")
        stream = t.get("source", "local") != "local"
        self.dl.setVisible(stream)
        self.tag.setVisible(not stream)
        self._fav()
        self.lyrics.set_loading()
        ctx.lyrics.request(t)

    def _lyrics(self, tid, lyr):
        cur = ctx.player.current
        if cur and cur.get("id") == tid:
            self.lyrics.set_lyrics(lyr)
            if self.stage.currentWidget() is self.lyrics:
                self._stage()

    def _refetch(self):
        t = ctx.player.current
        if t:
            ctx.lyrics.forget(t)
            self.lyrics.set_loading()
            ctx.lyrics.request(t)

    def _fav(self):
        f = ctx.player.is_favorite()
        self.fav.set_icon("heart_fill" if f else "heart")
        self.fav.active_color = ctx.theme.accent
        self.fav.setCheckable(True)
        self.fav.setChecked(f)

    def _addpl(self):
        t = ctx.player.current
        if t:
            playlist_submenu(self, [t["id"]]).exec(self.addpl.mapToGlobal(self.addpl.rect().bottomLeft()))

    def _goalb(self):
        t = ctx.player.current
        if t and t.get("album"):
            ctx.win.open_album(t["album"], album_artist(t))
