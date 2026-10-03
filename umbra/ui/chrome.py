"""Window chrome: title bar, sidebar, player dock, queue/lyrics side panel."""
import time

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget, QFrame)

from ..config import APP_NAME
from . import icons
from .actions import track_menu
from .context import ctx
from .visuals import Visualizer
from .widgets import (Badge, Caption, ChipButton, GlassPanel, IconButton, Marquee, PlayButton, SearchField, Slider,
                      Tween, ask_text, fmt_long, fmt_time, font, label, anim_ms)


# ═══════════════════════════════════════════════════════════════ logo
def paint_logo(p: QPainter, r: QRectF, accent: QColor):
    """Umbra mark: an eclipse — dark disc with a luminous corona and a sound-wave notch."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    c = r.center()
    R = r.width() / 2
    g = QRadialGradient(c, R)
    a = QColor(accent)
    g.setColorAt(0.55, QColor(a.red(), a.green(), a.blue(), 200))
    g.setColorAt(0.75, QColor(a.red(), a.green(), a.blue(), 60))
    g.setColorAt(1.0, QColor(a.red(), a.green(), a.blue(), 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(c, R, R)
    ring = QLinearGradient(r.topLeft(), r.bottomRight())
    ring.setColorAt(0, QColor(255, 255, 255))
    ring.setColorAt(1, a)
    p.setBrush(ring)
    p.drawEllipse(c, R * 0.66, R * 0.66)
    p.setBrush(QColor(8, 8, 11))
    p.drawEllipse(c + QPointF(R * 0.10, -R * 0.08), R * 0.58, R * 0.58)
    p.setPen(QPen(QColor(255, 255, 255, 220), max(1.0, R * 0.085), Qt.SolidLine, Qt.RoundCap))
    for i, h in enumerate((0.16, 0.30, 0.20)):
        x = c.x() - R * 0.16 + i * R * 0.2 + R * 0.08
        p.drawLine(QPointF(x, c.y() - R * h), QPointF(x, c.y() + R * h))
    p.restore()


# ═══════════════════════════════════════════════════════════════ title bar
class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setFixedHeight(50)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 8, 2)
        lay.setSpacing(6)
        self.logo = QWidget()
        self.logo.setFixedSize(30, 30)
        self.logo.paintEvent = lambda e: self._logo()
        lay.addWidget(self.logo)
        name = QLabel(APP_NAME.upper())
        name.setFont(font(10, QFont.Bold, 4.0))
        name.setStyleSheet("color: rgba(255,255,255,235); background: transparent;")
        lay.addWidget(name)
        lay.addSpacing(18)
        self.back = IconButton("back", 32, 16, "Back  (Alt+←)")
        self.fwd = IconButton("forward", 32, 16, "Forward  (Alt+→)")
        self.back.clicked.connect(win.go_back)
        self.fwd.clicked.connect(win.go_forward)
        lay.addWidget(self.back)
        lay.addWidget(self.fwd)
        lay.addStretch(1)
        self.search = SearchField("Search your library", hint="Ctrl K")
        self.search.setFixedWidth(420)
        self.search.returnPressed.connect(self._search)
        self._st = QTimer(self)
        self._st.setSingleShot(True)
        self._st.setInterval(280)
        self._st.timeout.connect(self._search)
        self.search.textEdited.connect(lambda _: self._st.start())
        lay.addWidget(self.search)
        lay.addStretch(1)
        self.np = IconButton("nowplaying", 34, 18, "Now Playing  (F11 immersive)")
        self.np.clicked.connect(lambda: win.navigate("nowplaying"))
        self.small = IconButton("small", 34, 18, "Small player  (Ctrl+Shift+M)")
        self.small.clicked.connect(lambda: win.toggle_small())
        self.mini = IconButton("mini", 34, 18, "Mini player  (Ctrl+M)")
        self.mini.clicked.connect(win.toggle_mini)
        self.theme_btn = IconButton("palette", 34, 18, "Quick theme")
        self.theme_btn.clicked.connect(win.quick_theme_menu)
        self.settings = IconButton("settings", 34, 18, "Settings  (Ctrl+,)")
        self.settings.clicked.connect(lambda: win.navigate("settings"))
        for b in (self.np, self.small, self.mini, self.theme_btn, self.settings):
            lay.addWidget(b)
        lay.addSpacing(10)
        self.bmin = IconButton("win_min", 34, 16, "Minimize")
        self.bmax = IconButton("win_max", 34, 16, "Maximize")
        self.bclose = IconButton("close", 34, 16, "Close")
        self.bclose.active_color = QColor("#ff5f6d")
        self.bmin.clicked.connect(win.showMinimized)
        self.bmax.clicked.connect(win.toggle_max)
        self.bclose.clicked.connect(win.close)
        self.bclose.enterEvent = lambda e: (setattr(self.bclose, "_red", True), self.bclose._ha.go(1))
        for b in (self.bmin, self.bmax, self.bclose):
            lay.addWidget(b)

    def _logo(self):
        p = QPainter(self.logo)
        paint_logo(p, QRectF(1, 1, 28, 28), ctx.theme.accent)

    def _search(self):
        q = self.search.text().strip()
        if q:
            self.win.navigate("search", query=q, replace=self.win.current_key == "search")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        self.win.toggle_max()


# ═══════════════════════════════════════════════════════════════ sidebar
class NavItem(QWidget):
    clicked = Signal(object)

    def __init__(self, key, text, icon, args=None, parent=None, count=None):
        super().__init__(parent)
        self.key, self.text, self.icon, self.args = key, text, icon, args or {}
        self.count = count
        self.active = False
        self.h = 0.0
        self._ha = Tween(self, "h", 140)
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self.f = font(9.6, QFont.Medium)

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self._ha.go(0)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self)

    def contextMenuEvent(self, e):
        if self.key == "tracks" and self.args.get("kind") == "playlist":
            ctx.win.playlist_menu(self.args["pid"], e.globalPos())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        compact = ctx.settings["sidebar_compact"]
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        if self.h > 0.01 and not self.active:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(12 * self.h)))
            p.drawRoundedRect(r, 10, 10)
        col = QColor(255, 255, 255, 250) if self.active else QColor(255, 255, 255, int(150 + 70 * self.h))
        ic = th.accent if self.active else col
        x = (self.width() - 18) / 2 if compact else 14
        icons.draw(p, self.icon, QRectF(x, (self.height() - 18) / 2, 18, 18), ic)
        if compact:
            return
        p.setFont(self.f)
        p.setPen(col)
        fm = QFontMetrics(self.f)
        p.drawText(QRectF(44, 0, self.width() - 80, self.height()), Qt.AlignVCenter,
                   fm.elidedText(self.text, Qt.ElideRight, self.width() - 84))
        if self.count:
            p.setFont(font(7.6, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255, 90))
            p.drawText(QRectF(0, 0, self.width() - 14, self.height()), Qt.AlignVCenter | Qt.AlignRight, str(self.count))


class Indicator(QWidget):
    """Active nav marker: a flat hairline slab with a short accent bar."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        r = QRectF(self.rect()).adjusted(2, 1, -2, -1)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(QColor(255, 255, 255, 13))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(th.accent)
        p.drawRoundedRect(QRectF(r.left() + 1, r.center().y() - 7, 3, 14), 1.5, 1.5)


class Sidebar(GlassPanel):
    def __init__(self, win):
        super().__init__(win, radius=None, level=1.0)
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 12, 10, 10)
        outer.setSpacing(4)
        self.sa = QScrollArea()
        self.sa.setWidgetResizable(True)
        self.sa.setFrameShape(QFrame.NoFrame)
        self.sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.box = QWidget()
        self.box.setAttribute(Qt.WA_TranslucentBackground)
        self.sa.setWidget(self.box)
        outer.addWidget(self.sa, 1)
        self.lay = QVBoxLayout(self.box)
        self.lay.setContentsMargins(0, 0, 4, 0)
        self.lay.setSpacing(1)
        self.ind = Indicator(self.box)
        self.ind.hide()
        self._ia = QPropertyAnimation(self.ind, b"geometry", self)
        self._ia.setEasingCurve(QEasingCurve.OutCubic)
        self.items = []
        self.captions = []
        self.active = None
        self._sec("Library")
        for k, t, i, a in (("home", "Home", "home", {}), ("tracks", "Songs", "songs", {"kind": "songs"}),
                           ("artists", "Artists", "artists", {}), ("albums", "Albums", "albums", {}),
                           ("genres", "Genres", "genres", {}), ("folders", "Folders", "folder", {})):
            self._item(k, t, i, a)
        self._sec("Smart")
        from .views import SMART
        for sk in ("recent_played", "most_played", "recent_added", "favorites", "never_played", "discovery"):
            self._item("tracks", SMART[sk][0], SMART[sk][1], {"kind": "smart", "smart": sk})
        self._sec("Stream")
        for svc, t, i in (("ytmusic", "YouTube Music", "ytmusic"), ("spotify", "Spotify", "spotify")):
            self._item("stream", t, i, {"service": svc})
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.pl_caption = Caption("Playlists")
        row.addWidget(self.pl_caption)
        row.addStretch()
        self.addpl = IconButton("plus", 24, 14, "New playlist")
        self.addpl.clicked.connect(self._new_pl)
        row.addWidget(self.addpl)
        w = QWidget()
        w.setLayout(row)
        w.setContentsMargins(10, 14, 0, 4)
        self.lay.addWidget(w)
        self.captions.append(w)
        self.pl_box = QVBoxLayout()
        self.pl_box.setSpacing(1)
        self.lay.addLayout(self.pl_box)
        self.lay.addStretch()
        # footer
        self.scan_lbl = label("", 7.8, alpha=120)
        self.scan_bar = Slider(height=8, groove=2)
        self.scan_bar.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.scan_bar.hide()
        self.scan_lbl.hide()
        outer.addWidget(self.scan_lbl)
        outer.addWidget(self.scan_bar)
        foot = QHBoxLayout()
        self.about = NavItem("about", "About", "info")
        self.about.clicked.connect(self._click)
        self.items.append(self.about)
        foot.addWidget(self.about, 1)
        self.compact_btn = IconButton("layers", 30, 15, "Compact sidebar")
        self.compact_btn.clicked.connect(self._toggle_compact)
        foot.addWidget(self.compact_btn)
        outer.addLayout(foot)
        self.apply_compact()

    def _sec(self, t):
        c = Caption(t)
        c.setContentsMargins(12, 14, 0, 4)
        self.lay.addWidget(c)
        self.captions.append(c)

    def _item(self, key, text, icon, args, box=None, count=None):
        it = NavItem(key, text, icon, args, count=count)
        it.setToolTip(text)
        it.clicked.connect(self._click)
        (box or self.lay).addWidget(it)
        self.items.append(it)
        return it

    def _click(self, it):
        self.win.navigate(it.key, **it.args)

    def _new_pl(self):
        n = ask_text(self.win, "New playlist", "Name", "New playlist")
        if n:
            pid = ctx.lib.create_playlist(n)
            self.refresh_playlists()
            self.win.navigate("tracks", kind="playlist", pid=pid)

    def refresh_playlists(self):
        for it in [i for i in self.items if i.args.get("kind") == "playlist"]:
            self.items.remove(it)
            it.deleteLater()
        for pl in ctx.lib.playlists():
            self._item("tracks", pl["name"], "playlists", {"kind": "playlist", "pid": pl["id"]}, self.pl_box, pl["n"])
        QTimer.singleShot(0, lambda: self.set_active(self.active_key))

    active_key = ("home", {})

    def set_active(self, key, args=None):
        if isinstance(key, tuple):
            key, args = key
        args = args or {}
        self.active_key = (key, args)
        target = None
        for it in self.items:
            match = it.key == key and all(args.get(k) == v for k, v in it.args.items()) and \
                (not it.args or it.args.get("kind") != "songs" or args.get("kind") == "songs")
            if it.key == "tracks" and key == "tracks":
                match = it.args == {k: args.get(k) for k in it.args} and args.get("kind") == it.args.get("kind")
            it.active = match and target is None
            if it.active:
                target = it
            it.update()
        if target is None or target is self.about:
            self.ind.hide()
            return
        QTimer.singleShot(0, lambda: self._move_ind(target))

    def _move_ind(self, it):
        if not it.isVisible():
            self.ind.hide()
            return
        g = QRect(it.mapTo(self.box, QPoint(0, 0)), it.size())
        if not self.ind.isVisible() or anim_ms(300) == 0:
            self.ind.setGeometry(g)
            self.ind.show()
        else:
            self._ia.stop()
            self._ia.setDuration(anim_ms(300))
            self._ia.setStartValue(self.ind.geometry())
            self._ia.setEndValue(g)
            self._ia.start()
        self.ind.lower()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self.set_active(self.active_key))

    def _toggle_compact(self):
        ctx.settings.set("sidebar_compact", not ctx.settings["sidebar_compact"])

    def apply_compact(self):
        c = ctx.settings["sidebar_compact"]
        self.setFixedWidth(76 if c else 236)
        for w in self.captions:
            w.setVisible(not c)
        self.scan_lbl.setVisible(not c and self.scan_bar.isVisible())
        for it in self.items:
            it.update()
        QTimer.singleShot(30, lambda: self.set_active(self.active_key))

    def scan_progress(self, done, total, path):
        self.scan_bar.show()
        self.scan_lbl.setVisible(not ctx.settings["sidebar_compact"])
        self.scan_bar.setValue(done / max(1, total))
        self.scan_lbl.setText(f"Scanning  {done:,} / {total:,}")

    def scan_done(self):
        self.scan_bar.hide()
        self.scan_lbl.hide()


# ═══════════════════════════════════════════════════════════════ player dock
class CoverThumb(QWidget):
    def __init__(self, parent=None, size=58):
        super().__init__(parent)
        self.setFixedSize(size + 8, size + 8)
        self.s = size
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Open / close Now Playing")
        ctx.art.ready.connect(lambda _k: self.update())

    def mouseReleaseEvent(self, e):
        ctx.win.toggle_nowplaying()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        t = ctx.player.current or {"title": "Umbra"}
        r = QRectF(4, 4, self.s, self.s)
        g = QRadialGradient(r.center(), self.s * 0.75)
        g.setColorAt(0.5, ctx.theme.acc(60))
        g.setColorAt(1, ctx.theme.acc(0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(r.center(), self.s * 0.75, self.s * 0.75)
        p.drawPixmap(r.toRect(), ctx.art.get(t, self.s, 10))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 10, 10)


class PlayerBar(GlassPanel):
    def __init__(self, win):
        super().__init__(win, radius=None, level=1.15)
        self.win = win
        self.setFixedHeight(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 18, 8)
        lay.setSpacing(12)
        # left: now playing
        left = QHBoxLayout()
        left.setSpacing(12)
        self.cover = CoverThumb()
        left.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(1)
        info.addStretch()
        self.title = Marquee("Not playing", 10.5, QFont.DemiBold)
        self.artist = Marquee("", 9, QFont.Normal, 150)
        self.artist.setCursor(Qt.PointingHandCursor)
        self.artist.mouseReleaseEvent = lambda e: self._go_artist()
        info.addWidget(self.title)
        info.addWidget(self.artist)
        brow = QHBoxLayout()
        brow.setSpacing(5)
        self.b_fmt = Badge("", True)
        self.b_q = Badge("")
        brow.addWidget(self.b_fmt)
        brow.addWidget(self.b_q)
        brow.addStretch()
        info.addLayout(brow)
        info.addStretch()
        left.addLayout(info, 1)
        self.fav = IconButton("heart", 32, 17, "Favorite  (Ctrl+D)")
        self.fav.clicked.connect(lambda: ctx.player.toggle_favorite())
        left.addWidget(self.fav)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        lay.addWidget(lw)
        # center: transport + seek
        center = QVBoxLayout()
        center.setSpacing(0)
        tr = QHBoxLayout()
        tr.setSpacing(10)
        tr.addStretch()
        self.shuf = IconButton("shuffle", 34, 17, "Shuffle  (Ctrl+S)", checkable=True)
        self.prev = IconButton("prev", 38, 20, "Previous  (Ctrl+←)", round_bg=True)
        self.play = PlayButton(42)
        self.next = IconButton("next", 38, 20, "Next  (Ctrl+→)", round_bg=True)
        self.rep = IconButton("repeat", 34, 17, "Repeat  (Ctrl+R)", checkable=True)
        for w in (self.shuf, self.prev, self.play, self.next, self.rep):
            tr.addWidget(w)
        tr.addStretch()
        center.addLayout(tr)
        sk = QHBoxLayout()
        sk.setSpacing(8)
        self.t_pos = label("0:00", 8, QFont.Medium, alpha=150)
        self.t_pos.setFont(font(8, QFont.Medium, mono=True))
        self.t_dur = label("0:00", 8, QFont.Medium, alpha=150)
        self.t_dur.setFont(font(8, QFont.Medium, mono=True))
        self.t_pos.setFixedWidth(46)
        self.t_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.t_dur.setFixedWidth(46)
        self.seek = Slider(height=22, groove=4, formatter=lambda v: fmt_time(v * (ctx.player.engine.duration() or 0)))
        self.seek.released.connect(lambda v: ctx.player.seek(v * (ctx.player.engine.duration() or 0)))
        self.t_dur.mousePressEvent = lambda e: self._toggle_remaining()
        sk.addWidget(self.t_pos)
        sk.addWidget(self.seek, 1)
        sk.addWidget(self.t_dur)
        center.addLayout(sk)
        lay.addLayout(center, 1)
        # right: tools
        right = QHBoxLayout()
        right.setSpacing(4)
        self.viz = Visualizer(self, compact=True, style="bars", bands=14)
        self.viz.setFixedSize(54, 26)
        right.addWidget(self.viz)
        right.addSpacing(6)
        self.lyr = IconButton("lyrics", 34, 17, "Lyrics  (Ctrl+L)", checkable=True)
        self.lyr.setChecked(bool(ctx.settings["np_lyrics"]))
        ctx.settings.changed.connect(lambda k, v: k == "np_lyrics" and self.lyr.setChecked(bool(v)))
        self.que = IconButton("queue", 34, 17, "Queue  (Ctrl+Q)", checkable=True)
        self.eq = IconButton("eq", 34, 17, "Equalizer")
        self.vol_btn = IconButton("volume", 34, 17, "Mute  (M)")
        self.vol = Slider(height=22, groove=4, accent=False, formatter=lambda v: f"{int(v * 100)}%")
        self.vol.setFixedWidth(104)
        for w in (self.lyr, self.que, self.eq, self.vol_btn, self.vol):
            right.addWidget(w)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(360)
        lay.addWidget(rw)
        # wiring
        p = ctx.player
        self.play.clicked.connect(p.toggle)
        self.prev.clicked.connect(p.prev)
        self.next.clicked.connect(p.next)
        self.shuf.clicked.connect(lambda: p.toggle_shuffle())
        self.rep.clicked.connect(lambda: p.cycle_repeat())
        self.vol.moved.connect(p.set_volume)
        self.vol_btn.clicked.connect(p.toggle_mute)
        self.vol_btn.wheelEvent = self.vol.wheelEvent
        self.lyr.clicked.connect(lambda: win.toggle_lyrics())
        self.que.clicked.connect(lambda: win.toggle_side("queue"))
        self.eq.clicked.connect(lambda: win.navigate("settings", section="eq"))
        p.trackChanged.connect(self._track)
        p.stateChanged.connect(lambda st: self.play.set_playing(st == "playing"))
        p.shuffleChanged.connect(self._sync_modes)
        p.repeatChanged.connect(lambda _r: self._sync_modes())
        p.favoriteChanged.connect(lambda *_: self._fav())
        p.volumeChanged.connect(self._vol)
        self.remaining = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)
        self._sync_modes()
        self._vol(p.engine.volume)
        self.vol.setValue(p.engine.volume)

    def _go_artist(self):
        t = ctx.player.current
        if t and t.get("artist"):
            ctx.win.open_artist(t.get("albumartist") or t["artist"])

    def _toggle_remaining(self):
        self.remaining = not self.remaining

    def _sync_modes(self, *_):
        p = ctx.player
        self.shuf.setChecked(p.shuffle)
        self.rep.setChecked(p.repeat != "off")
        self.rep.set_icon("repeat_one" if p.repeat == "one" else "repeat")

    def _vol(self, v):
        m = ctx.player.engine.muted
        self.vol_btn.set_icon("mute" if m or v == 0 else ("volume_low" if v < 0.45 else "volume"))
        if not self.vol.drag:
            self.vol.setValue(v)

    def _fav(self):
        f = ctx.player.is_favorite()
        self.fav.set_icon("heart_fill" if f else "heart")
        self.fav.setCheckable(True)
        self.fav.setChecked(f)

    def _track(self, t):
        self.cover.update()
        if not t:
            self.title.setText("Not playing")
            self.artist.setText("")
            self.b_fmt.setText("")
            self.b_q.setText("")
            return
        self.title.setText(t.get("title") or "")
        self.artist.setText(t.get("artist") or "")
        if t.get("source", "local") != "local":
            self.b_fmt.setText(t["source"].upper(), True)
            self.b_q.setText("STREAM")
        else:
            self.b_fmt.setText((t.get("codec") or "").upper(), bool(t.get("lossless")))
            if t.get("lossless"):
                self.b_q.setText(f"{t.get('bitdepth') or 16}/{(t.get('samplerate') or 44100) / 1000:g}")
            else:
                self.b_q.setText(f"{t.get('bitrate') or ''}K" if t.get("bitrate") else "")
        self._fav()

    def _tick(self):
        e = ctx.player.engine
        d = e.duration() or 0
        pos = e.position()
        if not self.seek.drag:
            self.seek.setValue(pos / d if d else 0)
        self.t_pos.setText(fmt_time(pos))
        self.t_dur.setText(("-" + fmt_time(d - pos)) if self.remaining and d else fmt_time(d))


# ═══════════════════════════════════════════════════════════════ queue / side panel
class QueueDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.v = view

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), 50)

    def paint(self, p, opt, idx):
        data = idx.data(Qt.UserRole)
        if not data:
            return
        qpos, tid, num = data
        t = ctx.lib.get(tid)
        if not t:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(opt.rect).adjusted(2, 1, -6, -1)
        hov = bool(opt.state & QStyle.State_MouseOver)
        sel = bool(opt.state & QStyle.State_Selected)
        if hov or sel:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24 if sel else 14))
            p.drawRoundedRect(r, 10, 10)
        p.setFont(font(8, QFont.DemiBold, mono=True))
        p.setPen(QColor(255, 255, 255, 90))
        p.drawText(QRectF(r.left() + 4, r.top(), 24, r.height()), Qt.AlignVCenter | Qt.AlignHCenter, f"{num:02d}")
        p.drawPixmap(QRectF(r.left() + 32, r.center().y() - 17, 34, 34).toRect(), ctx.art.get(t, 34, 7))
        tx = r.left() + 76
        tw = r.width() - 76 - 48
        f1 = font(9.2, QFont.DemiBold)
        f2 = font(8.2)
        p.setFont(f1)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(tx, r.top() + 6, tw, 18), Qt.AlignVCenter, QFontMetrics(f1).elidedText(t.get("title") or "", Qt.ElideRight, int(tw)))
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(tx, r.top() + 25, tw, 16), Qt.AlignVCenter, QFontMetrics(f2).elidedText(t.get("artist") or "", Qt.ElideRight, int(tw)))
        if hov:
            icons.draw(p, "close", QRectF(r.right() - 30, r.center().y() - 8, 16, 16), QColor(255, 255, 255, 170))
        else:
            p.setFont(font(8, QFont.Medium, mono=True))
            p.setPen(QColor(255, 255, 255, 100))
            p.drawText(QRectF(r.right() - 48, r.top(), 42, r.height()), Qt.AlignVCenter | Qt.AlignRight, fmt_time(t.get("duration")))
        p.restore()


class QueueList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(QueueDelegate(self))
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemDoubleClicked.connect(lambda it: ctx.player.play_index(it.data(Qt.UserRole)[0]))
        self.model().rowsMoved.connect(self._moved)
        ctx.art.ready.connect(lambda _k: self.viewport().update())
        self._sync = False

    def rebuild(self):
        self._sync = True
        self.clear()
        p = ctx.player
        for n, qpos in enumerate(range(p.index + 1, len(p.queue)), start=1):
            it = QListWidgetItem()
            it.setData(Qt.UserRole, (qpos, p.queue[qpos], n))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.addItem(it)
        self._sync = False

    def _moved(self, *a):
        if self._sync:
            return
        ids = [self.item(i).data(Qt.UserRole)[1] for i in range(self.count())]
        QTimer.singleShot(0, lambda: ctx.player.set_upcoming(ids))

    def mouseReleaseEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        if it and e.button() == Qt.LeftButton and e.position().x() > self.viewport().width() - 40:
            ctx.player.remove_at([it.data(Qt.UserRole)[0]])
            return
        super().mouseReleaseEvent(e)

    def _menu(self, pos):
        items = self.selectedItems() or ([self.itemAt(pos)] if self.itemAt(pos) else [])
        if not items:
            return
        tracks = [ctx.lib.get(i.data(Qt.UserRole)[1]) for i in items]
        m = track_menu(self, tracks, queue_positions=[i.data(Qt.UserRole)[0] for i in items])
        if m:
            m.exec(self.viewport().mapToGlobal(pos))


class NowCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(76)
        ctx.player.trackChanged.connect(lambda _t: self.update())
        ctx.art.ready.connect(lambda _k: self.update())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        t = ctx.player.current
        r = QRectF(self.rect()).adjusted(0, 2, -4, -2)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, th.acc(40))
        g.setColorAt(1, QColor(255, 255, 255, 8))
        p.setPen(QPen(th.acc(70), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 14, 14)
        if not t:
            p.setPen(QColor(255, 255, 255, 120))
            p.setFont(font(9))
            p.drawText(r, Qt.AlignCenter, "Queue is empty")
            return
        p.drawPixmap(QRectF(r.left() + 10, r.top() + 10, r.height() - 20, r.height() - 20).toRect(), ctx.art.get(t, int(r.height() - 20), 9))
        tx = r.left() + r.height() + 2
        tw = r.width() - tx - 12
        f1, f2 = font(10, QFont.DemiBold), font(8.6)
        p.setFont(f1)
        p.setPen(QColor(255, 255, 255, 245))
        p.drawText(QRectF(tx, r.top() + 14, tw, 20), Qt.AlignVCenter, QFontMetrics(f1).elidedText(t.get("title") or "", Qt.ElideRight, int(tw)))
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(QRectF(tx, r.top() + 36, tw, 18), Qt.AlignVCenter, QFontMetrics(f2).elidedText(t.get("artist") or "", Qt.ElideRight, int(tw)))


class SidePanel(GlassPanel):
    """Right panel: the play queue (lyrics live on their own in Now Playing)."""

    def __init__(self, win):
        super().__init__(win, radius=None, level=1.0)
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 10, 12)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(label("Queue", 15, QFont.Bold))
        top.addStretch()
        x = IconButton("close", 30, 15, "Close panel")
        x.clicked.connect(lambda: win.toggle_side(None))
        top.addWidget(x)
        lay.addLayout(top)
        # queue page
        self.qw = QWidget()
        ql = QVBoxLayout(self.qw)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(8)
        ql.addWidget(Caption("Now playing"))
        ql.addWidget(NowCard())
        row = QHBoxLayout()
        self.up_caption = Caption("Up next")
        row.addWidget(self.up_caption)
        row.addStretch()
        for ic, tip, fn in (("shuffle", "Shuffle upcoming", lambda: ctx.player.shuffle_upcoming()),
                            ("playlists", "Save queue as playlist", self._save),
                            ("trash", "Clear upcoming", lambda: ctx.player.clear_upcoming())):
            b = IconButton(ic, 28, 15, tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        ql.addLayout(row)
        self.list = QueueList()
        ql.addWidget(self.list, 1)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for t, ic, fn in (("Similar", "sparkle", lambda: ctx.player.add_similar()),
                          ("Artist", "artists", lambda: ctx.player.add_current_artist()),
                          ("Album", "albums", lambda: ctx.player.add_current_album())):
            c = ChipButton(t, ic)
            c.setToolTip(f"Add {t.lower()} {'songs' if t == 'Similar' else ''}".strip())
            c.clicked.connect(fn)
            chips.addWidget(c)
        chips.addStretch()
        ql.addLayout(chips)
        self.foot = label("", 8, alpha=110)
        ql.addWidget(self.foot)
        lay.addWidget(self.qw, 1)
        ctx.player.queueChanged.connect(self.refresh)
        self.refresh()


    def refresh(self):
        self.list.rebuild()
        p = ctx.player
        up = p.queue[p.index + 1:]
        dur = sum((ctx.lib.get(i) or {}).get("duration") or 0 for i in up)
        self.up_caption.setText(f"UP NEXT · {len(up)}")
        self.foot.setText(f"{len(p.queue)} in queue  ·  {fmt_long(dur)} remaining  ·  drag to reorder")

    def _save(self):
        if not ctx.player.queue:
            return
        n = ask_text(self.win, "Save queue", "Playlist name", "Queue " + time.strftime("%d %b %H:%M"))
        if n:
            ctx.lib.create_playlist(n, ctx.player.queue)
            self.win.refresh_playlists()
            ctx.toast(f"Saved “{n}”", "playlists")
