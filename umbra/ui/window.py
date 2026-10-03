"""Umbra main window — frameless glass shell."""
import os
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QCursor, QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QPen, QLinearGradient
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import winsys
from ..config import APP_NAME, AUDIO_EXTS
from ..library.db import album_artist
from ..library.tags import read_tags
from ..theme import PRESETS
from . import icons
from .about import AboutPage
from .actions import _act
from .chrome import PlayerBar, SidePanel, Sidebar, TitleBar, paint_logo
from .context import ctx
from .mini import MiniPlayer, SmallPlayer
from .settings_page import SettingsPage
from .tageditor import TagEditor
from .views import (AlbumPage, ArtistPage, FoldersPage, GridPage, HomePage, NowPlayingPage, SearchPage, StreamPage,
                    TrackPage)
from .widgets import FadeStack, GlassPanel, Toast, confirm, glass_menu, rr_path, stylesheet

EDGE = 7


def app_icon(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(34, 34, 42))
    g.setColorAt(1, QColor(6, 6, 9))
    p.setPen(QPen(QColor(255, 255, 255, 60), size / 128))
    p.setBrush(g)
    p.drawRoundedRect(r, size * 0.24, size * 0.24)
    paint_logo(p, r.adjusted(size * 0.14, size * 0.14, -size * 0.14, -size * 0.14), ctx.theme.accent if ctx.theme else QColor("#E9E9EE"))
    p.end()
    return pm


class MainWindow(QWidget):
    sideToggled = Signal(bool)

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        ctx.win = self
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(app_icon()))
        self.setMinimumSize(1100, 700)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.t0 = time.time()
        self.history, self.future = [], []
        self.current_key = None
        self.pages = {}
        self.mini = None
        self.immersive = False
        self._last_accent = None

        root = QVBoxLayout(self)
        root.setContentsMargins(EDGE + 3, EDGE - 2, EDGE + 3, EDGE + 3)
        root.setSpacing(8)
        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)
        mid = QHBoxLayout()
        mid.setSpacing(8)
        self.sidebar = Sidebar(self)
        mid.addWidget(self.sidebar)
        self.content = GlassPanel(self, level=0.75)
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(0, 0, 0, 0)
        self.stack = FadeStack(self.content)
        cl.addWidget(self.stack)
        mid.addWidget(self.content, 1)
        self.side = SidePanel(self)
        self.side.setFixedWidth(0)
        self.side.hide()
        mid.addWidget(self.side)
        root.addLayout(mid, 1)
        self.playerbar = PlayerBar(self)
        root.addWidget(self.playerbar)
        self.toast = Toast(self)
        self._side_anim = QVariantAnimation(self)
        self._side_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._side_anim.valueChanged.connect(lambda v: self.side.setFixedWidth(int(v)))

        self.ambient = QTimer(self)
        self.ambient.timeout.connect(self._ambient_tick)
        self._apply_ambient()

        th = ctx.theme
        th.changed.connect(self._theme_changed)
        th.backdropChanged.connect(self.update)
        ctx.settings.changed.connect(self._setting)
        ctx.player.trackChanged.connect(self._track_changed)
        ctx.player.message.connect(lambda m: self.toast.show_msg(m, "info"))
        self._libtimer = QTimer(self)
        self._libtimer.setSingleShot(True)
        self._libtimer.setInterval(900)
        self._libtimer.timeout.connect(self.library_changed)
        ctx.downloads.progress.connect(self._dl_progress)
        ctx.downloads.finished.connect(self._dl_finished)
        ctx.downloads.failed.connect(lambda k, e: self.toast.show_msg("Download failed — " + e, "info"))
        ctx.downloads.batch.connect(self._dl_batch)
        ctx.lyrics_batch.finished.connect(self._lyrics_batch_done)
        ctx.scanner.progress.connect(self.sidebar.scan_progress)
        ctx.scanner.finished.connect(self._scan_done)
        self._shortcuts()
        self._tray()
        self.refresh_playlists()
        self._theme_changed()
        geo = ctx.settings["geometry"]
        if geo:
            self.setGeometry(*geo[:4])
            if len(geo) > 4 and geo[4]:
                QTimer.singleShot(0, self.showMaximized)
        else:
            self.resize(1480, 920)
        self.navigate("home")

    # ───────────────────────────────────────────── painting / frame
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if not self.isMaximized() and not self.isFullScreen():
            r = r.adjusted(1, 1, -1, -1)
        rad = 0 if (self.isMaximized() or self.isFullScreen()) else ctx.theme.radius + 4
        path = rr_path(r, rad)
        p.setClipPath(path)
        acrylic = ctx.settings["backdrop"] == "acrylic" and winsys.IS_WIN
        if acrylic:
            c = QColor(ctx.theme.bg)
            c.setAlpha(110)
            p.fillRect(r, c)
        else:
            ctx.theme.paint_backdrop(p, r, time.time() - self.t0 if ctx.settings["ambient_motion"] else 0)
        p.setClipping(False)
        if rad:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(255, 255, 255, 60))
            g.setColorAt(0.5, QColor(255, 255, 255, 14))
            g.setColorAt(1, QColor(255, 255, 255, 30))
            p.setPen(QPen(g, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)

    def _apply_ambient(self):
        if ctx.settings["ambient_motion"] and ctx.settings["backdrop"] != "acrylic":
            self.ambient.start(66)
        else:
            self.ambient.stop()

    def _ambient_tick(self):
        if self.isVisible() and not self.isMinimized():
            self.update()

    def _edges(self, pos):
        if self.isMaximized() or self.isFullScreen():
            return Qt.Edges()
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        e = Qt.Edges()
        if x <= EDGE:
            e |= Qt.LeftEdge
        if x >= w - EDGE:
            e |= Qt.RightEdge
        if y <= EDGE - 3:
            e |= Qt.TopEdge
        if y >= h - EDGE:
            e |= Qt.BottomEdge
        return e

    def mouseMoveEvent(self, e):
        ed = self._edges(e.position().toPoint())
        cur = Qt.ArrowCursor
        if ed in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            cur = Qt.SizeFDiagCursor
        elif ed in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            cur = Qt.SizeBDiagCursor
        elif ed & (Qt.LeftEdge | Qt.RightEdge):
            cur = Qt.SizeHorCursor
        elif ed & (Qt.TopEdge | Qt.BottomEdge):
            cur = Qt.SizeVerCursor
        self.setCursor(cur)

    def mousePressEvent(self, e):
        ed = self._edges(e.position().toPoint())
        if e.button() == Qt.LeftButton and ed:
            self.windowHandle().startSystemResize(ed)

    def toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):
        super().changeEvent(e)
        if hasattr(self, "titlebar"):
            self.titlebar.bmax.set_icon("win_restore" if self.isMaximized() else "win_max")
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        hwnd = int(self.winId())
        winsys.set_dark_frame(hwnd)
        if ctx.settings["backdrop"] == "acrylic":
            winsys.set_acrylic(hwnd, True)

    # ───────────────────────────────────────────── theme
    def _theme_changed(self):
        acc = ctx.theme.accent.name()
        if acc != self._last_accent:
            self._last_accent = acc
            QApplication.instance().setStyleSheet(stylesheet())
            self.setWindowIcon(QIcon(app_icon()))
            if hasattr(self, "tray"):
                self.tray.setIcon(QIcon(app_icon(64)))
        self.update()

    def _setting(self, key, v):
        if key in ("ambient_motion", "backdrop"):
            self._apply_ambient()
        if key == "backdrop" and winsys.IS_WIN:
            winsys.set_acrylic(int(self.winId()), v == "acrylic")
        if key == "sidebar_compact":
            self.sidebar.apply_compact()
        if key == "streaming_enabled":
            for it in self.sidebar.items:
                if it.key == "stream":
                    it.setVisible(bool(v))
        self.update()

    def _track_changed(self, t):
        img = ctx.art.image(t, sync=True) if t else None
        ctx.theme.set_artwork(img)
        if t:
            self.setWindowTitle(f"{t.get('title')} — {t.get('artist') or ''}  ·  {APP_NAME}")
            if hasattr(self, "tray"):
                self.tray.setToolTip(f"{t.get('title')} — {t.get('artist') or ''}")

    # ───────────────────────────────────────────── navigation
    def _page(self, key):
        if key not in self.pages:
            cls = {"home": HomePage, "tracks": TrackPage, "album": AlbumPage, "artist": ArtistPage, "folders": FoldersPage,
                   "search": SearchPage, "stream": StreamPage, "nowplaying": NowPlayingPage, "settings": SettingsPage,
                   "about": AboutPage}.get(key)
            w = GridPage(key) if key in ("albums", "artists", "genres", "playlists") else cls()
            self.pages[key] = w
            self.stack.addWidget(w)
        return self.pages[key]

    def navigate(self, key, replace=False, _hist=True, **args):
        page = self._page(key)
        if _hist and self.current_key is not None and not replace:
            self.history.append(self._cur_state)
            self.future.clear()
            self.history = self.history[-60:]
        self._cur_state = (key, dict(args))
        self.current_key = key
        page.load(**args)
        self.stack.show_widget(page)
        self.sidebar.set_active(key, args)
        self.titlebar.back.setEnabled(bool(self.history))
        self.titlebar.fwd.setEnabled(bool(self.future))

    def restart_app(self):
        import sys
        from PySide6.QtCore import QProcess
        ctx.settings.save()
        try:
            ctx.player.save_session()
        except Exception:
            pass
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, args)
        QApplication.quit()

    def toggle_nowplaying(self):
        """Cover in the player bar: first click opens Now Playing, the second click closes it again."""
        if self.current_key == "nowplaying":
            if self.history:
                self.go_back()
            else:
                self.navigate("home")
        else:
            self.navigate("nowplaying")

    def go_back(self):
        if self.history:
            self.future.append(self._cur_state)
            k, a = self.history.pop()
            self.navigate(k, _hist=False, **a)

    def go_forward(self):
        if self.future:
            self.history.append(self._cur_state)
            k, a = self.future.pop()
            self.navigate(k, _hist=False, **a)

    def reload_current(self):
        if self.current_key:
            k, a = self._cur_state
            self.pages[k].load(**a)

    def library_changed(self):
        ctx.lib.invalidate()
        for k, pg in self.pages.items():
            if k != self.current_key and hasattr(pg, "_args"):
                pg._stale = True
        self.reload_current()
        self.refresh_playlists()

    def refresh_playlists(self):
        self.sidebar.refresh_playlists()

    def _lyrics_batch_done(self, found, total, skipped, cancelled):
        self.toast.show_msg(f"Lyrics {'stopped' if cancelled else 'done'} · added to {found} of {total} songs", "lyrics")
        cur = ctx.player.current
        if cur and found:
            ctx.lyrics.request(cur)

    # ── downloads
    def _dl_progress(self, key, v):
        if v == 0 and ctx.downloads._b[1] <= 1:
            self.toast.show_msg("Downloading…", "download")

    def _dl_finished(self, key, f):
        if ctx.downloads._b[1] <= 1:
            self.toast.show_msg(f"Downloaded  ·  {os.path.basename(f)}", "download")
        self._libtimer.start()

    def _dl_batch(self, done, total, failed):
        if done + failed >= total:
            self.toast.show_msg(f"Downloaded {done} of {total} tracks" + (f" · {failed} failed" if failed else ""), "download")
        else:
            self.toast.show_msg(f"Downloading  ·  {done + failed} / {total}", "download")

    def open_album(self, album, aa):
        self.navigate("album", album=album, aa=aa)

    def open_artist(self, name):
        self.navigate("artist", name=name)

    def item_ids(self, it):
        lib = ctx.lib
        k = it["kind"]
        if k == "album":
            return [r["id"] for r in lib.album_tracks(it["album"], it["aa"])]
        if k == "artist":
            return [r["id"] for r in lib.artist_tracks(it["name"], "album")]
        if k == "genre":
            return lib.ids("COALESCE(NULLIF(genre,''),'Unknown')=? COLLATE NOCASE AND source='local'", (it["genre"],), "album")
        if k == "playlist":
            return [t["id"] for t in lib.playlist_tracks(it["pid"])]
        if k == "smart":
            return [t["id"] for t in lib.smart(it["smart"], 300)]
        if k == "track":
            return [it["id"]]
        return []

    def open_item(self, it):
        k = it["kind"]
        if k == "album":
            self.open_album(it["album"], it["aa"])
        elif k == "artist":
            self.open_artist(it["name"])
        elif k == "genre":
            self.navigate("tracks", kind="genre", genre=it["genre"])
        elif k == "playlist":
            self.navigate("tracks", kind="playlist", pid=it["pid"])
        elif k == "smart":
            self.navigate("tracks", kind="smart", smart=it["smart"])
        elif k == "track":
            self.play_item(it)

    def play_item(self, it):
        ids = self.item_ids(it)
        if ids:
            ctx.player.play_tracks(ids, 0, shuffle=True if it["kind"] in ("smart", "genre", "artist") else None)
            if it["kind"] == "track":
                QTimer.singleShot(300, lambda: ctx.player.add_similar(20))

    def playlist_menu(self, pid, gpos):
        m = glass_menu(self)
        ids = [t["id"] for t in ctx.lib.playlist_tracks(pid)]
        _act(m, "Play", "play", lambda: ctx.player.play_tracks(ids))
        _act(m, "Shuffle", "shuffle", lambda: ctx.player.play_tracks(ids, shuffle=True))
        _act(m, "Add to queue", "queue", lambda: ctx.player.add_to_queue(ids))
        m.addSeparator()

        def delete():
            if confirm(self, "Delete playlist", "Delete this playlist? Tracks stay in your library.", "Delete"):
                ctx.lib.delete_playlist(pid)
                self.refresh_playlists()
                if self._cur_state[1].get("pid") == pid:
                    self.navigate("home")
        _act(m, "Delete", "trash", delete)
        m.exec(gpos)

    # ───────────────────────────────────────────── actions
    def open_tag_editor(self, tracks):
        tracks = [t for t in tracks if t and t.get("source", "local") == "local"]
        if not tracks:
            self.toast.show_msg("Tags can be edited for local files only", "info")
            return
        TagEditor(self, tracks).exec()

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add music folder")
        if d:
            d = os.path.normpath(d)
            ctx.lib.add_folder(d)
            ctx.scanner.scan([d])
            self.toast.show_msg(f"Scanning “{os.path.basename(d)}”…", "folder")
            if self.current_key == "folders":
                self.reload_current()

    def _scan_done(self, changed, removed):
        self.sidebar.scan_done()
        ctx.scanner.refresh_watch()
        if changed or removed:
            self.toast.show_msg(f"Library updated · {changed} new/changed" + (f" · {removed} removed" if removed else ""), "check")
            self.library_changed()

    def toggle_lyrics(self):
        """Lyrics live in Now Playing: open it with lyrics on, or switch them off if already showing."""
        on = bool(ctx.settings["np_lyrics"])
        if self.current_key == "nowplaying" and on:
            ctx.settings.set("np_lyrics", False)
        else:
            ctx.settings.set("np_lyrics", True)
            if self.current_key != "nowplaying":
                self.navigate("nowplaying")

    def side_open(self):
        return self.side.isVisible() and self.side.width() > 10 and not getattr(self, "_side_hide_after", False)

    def toggle_side(self, tab="queue"):
        if tab == "lyrics":
            return self.toggle_lyrics()
        target = 0 if (tab is None or self.side_open()) else 350
        if target:
            self.side.show()
        self.playerbar.que.setChecked(target > 0)
        self.sideToggled.emit(target > 0)
        self._side_anim.stop()
        from .widgets import anim_ms
        self._side_anim.setDuration(max(1, anim_ms(320)))
        self._side_anim.setStartValue(self.side.width())
        self._side_anim.setEndValue(target)
        self._side_hide_after = target == 0
        if not getattr(self, "_side_anim_hooked", False):
            self._side_anim.finished.connect(lambda: self._side_hide_after and self.side.hide())
            self._side_anim_hooked = True
        self._side_anim.start()

    def toggle_small(self):
        if getattr(self, "small", None) is None:
            self.small = SmallPlayer()
        if self.mini is not None and self.mini.isVisible():
            self.mini.hide()
        if self.small.isVisible():
            self.small.hide()
            self.showNormal()
            self.raise_()
        else:
            g = self.geometry()
            self.small.move(g.center().x() - self.small.width() // 2, g.center().y() - self.small.height() // 2)
            self.small.show()
            self.hide()

    def toggle_mini(self):
        if self.mini is None:
            self.mini = MiniPlayer()
        if getattr(self, "small", None) is not None and self.small.isVisible():
            self.small.hide()
            g = self.small.geometry()
            self.mini.move(g.right() - self.mini.width(), g.bottom() - self.mini.height())
            self.mini.show()
            return
        if self.mini.isVisible():
            self.mini.hide()
            self.showNormal()
            self.raise_()
        else:
            g = self.geometry()
            self.mini.move(g.right() - self.mini.width() - 30, g.bottom() - self.mini.height() - 30)
            self.mini.show()
            self.hide()

    def toggle_immersive(self):
        self.immersive = not self.immersive
        self.sidebar.setVisible(not self.immersive)
        if self.immersive:
            self._side_was = self.side.isVisible()
            self.side.hide()
            self.navigate("nowplaying")
            self.showFullScreen()
        else:
            if getattr(self, "_side_was", False):
                self.side.show()
            self.showNormal()

    def quick_theme_menu(self):
        m = glass_menu(self)
        s = ctx.settings
        for n in PRESETS:
            a = _act(m, ("●  " if s["theme"] == n else "    ") + n, "palette", lambda _=False, n=n: s.set("theme", n))
        m.addSeparator()
        for key, label_ in (("artwork", "Accent from artwork"), ("windows", "Accent from Windows"), ("wallpaper", "Accent from wallpaper"), ("theme", "Theme accent")):
            _act(m, ("✓  " if s["accent_source"] == key else "    ") + label_, "drop", lambda _=False, k=key: s.set("accent_source", k))
        m.addSeparator()
        for key, label_ in (("artwork", "Backdrop: artwork"), ("wallpaper", "Backdrop: wallpaper"), ("void", "Backdrop: void"), ("acrylic", "Backdrop: Windows acrylic")):
            _act(m, ("✓  " if s["backdrop"] == key else "    ") + label_, "layers", lambda _=False, k=key: s.set("backdrop", k))
        b = self.titlebar.theme_btn
        m.exec(b.mapToGlobal(b.rect().bottomLeft()))

    def _shortcuts(self):
        p = ctx.player
        tb = self.titlebar

        def sc(seq, fn, ctx_=Qt.WindowShortcut):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(ctx_)
            s.activated.connect(fn)

        def guard(fn):
            def w():
                fw = QApplication.focusWidget()
                from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
                if isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit)):
                    return
                fn()
            return w
        sc("Space", guard(p.toggle))
        sc("Ctrl+Right", p.next)
        sc("Ctrl+Left", p.prev)
        sc("Right", guard(lambda: p.seek_rel(5)))
        sc("Left", guard(lambda: p.seek_rel(-5)))
        sc("Shift+Right", guard(lambda: p.seek_rel(30)))
        sc("Shift+Left", guard(lambda: p.seek_rel(-30)))
        sc("Ctrl+Up", lambda: p.set_volume(p.engine.volume + 0.05))
        sc("Ctrl+Down", lambda: p.set_volume(p.engine.volume - 0.05))
        sc("M", guard(p.toggle_mute))
        sc("Ctrl+K", lambda: (tb.search.setFocus(), tb.search.selectAll()))
        sc("Ctrl+F", lambda: (tb.search.setFocus(), tb.search.selectAll()))
        sc("Ctrl+S", p.toggle_shuffle)
        sc("Ctrl+R", p.cycle_repeat)
        sc("Ctrl+D", lambda: p.toggle_favorite())
        sc("Ctrl+L", self.toggle_lyrics)
        sc("Ctrl+Shift+M", self.toggle_small)
        sc("Ctrl+Q", lambda: self.toggle_side("queue"))
        sc("Ctrl+E", lambda: p.current and self.open_tag_editor([p.current]))
        sc("Ctrl+M", self.toggle_mini)
        sc("F11", self.toggle_immersive)
        sc("Ctrl+,", lambda: self.navigate("settings"))
        sc("Alt+Left", self.go_back)
        sc("Alt+Right", self.go_forward)
        sc("Escape", lambda: self.immersive and self.toggle_immersive())

    def _tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(app_icon(64)), self)
        m = glass_menu(self)
        p = ctx.player
        _act(m, "Play / Pause", "play", p.toggle)
        _act(m, "Next", "next", p.next)
        _act(m, "Previous", "prev", p.prev)
        m.addSeparator()
        from .actions import sleep_menu
        sm = [None]

        def sl():
            sm[0] = sleep_menu(m)
            sm[0].exec(QCursor.pos())
        _act(m, "Sleep timer…", "clock", sl)
        _act(m, "Show Umbra", "expand", lambda: (self.showNormal(), self.raise_(), self.activateWindow()))
        _act(m, "Quit", "close", self.close)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and (self.showNormal(), self.raise_(), self.activateWindow()))
        self.tray.show()

    def media_key(self, name):
        p = ctx.player
        {"playpause": p.toggle, "next": p.next, "prev": p.prev, "stop": lambda: p.engine.pause()}.get(name, lambda: None)()

    # ───────────────────────────────────────────── drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files, dirs = [], []
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isdir(p):
                dirs.append(os.path.normpath(p))
            elif os.path.splitext(p)[1].lower() in AUDIO_EXTS:
                files.append(p)
        for d in dirs:
            ctx.lib.add_folder(d)
        if dirs:
            ctx.scanner.scan(dirs)
            self.toast.show_msg(f"Added {len(dirs)} folder(s) to library", "folder")
        if files:
            self.open_files(files)

    def open_files(self, files):
        ids = []
        for f in files:
            r = ctx.lib.q("SELECT id FROM tracks WHERE path=?", (f,))
            if r:
                ids.append(r[0]["id"])
            else:
                d = read_tags(f)
                d.pop("lyrics", None)
                st = os.stat(f)
                d.update(path=f, source="local", filesize=st.st_size, mtime=st.st_mtime, folder=os.path.dirname(f))
                ids.append(ctx.lib.upsert(d))
        if ids:
            ctx.player.play_tracks(ids)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move((self.width() - self.toast.width()) // 2, self.height() - 160)

    def closeEvent(self, e):
        g = self.normalGeometry() if self.isMaximized() else self.geometry()
        ctx.settings.set("geometry", [g.x(), g.y(), g.width(), g.height(), self.isMaximized()], emit=False)
        ctx.player.shutdown()
        ctx.settings.save()
        if self.mini:
            self.mini.close()
        if hasattr(self, "tray"):
            self.tray.hide()
        e.accept()
        QApplication.instance().quit()
