"""Mini player — a compact 'eclipse card': artwork-tinted glass, big cover, quiet controls,
and the progress drawn as a lit hairline along the bottom edge."""
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..theme import blur_image
from .context import ctx
from .visuals import Visualizer
from .widgets import IconButton, Marquee, PlayButton, Tween, fmt_time, font, paint_crescent, rr_path

W, H, RAD, COVER = 420, 124, 22, 96


class MiniPlayer(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.setMouseTracking(True)
        self.bg = None
        self.h = 0.0
        self._ha = Tween(self, "h", 180)
        self._seek_hover = False
        self._cover_hover = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14 + COVER + 14, 12, 14, 16)
        lay.setSpacing(6)
        col = QVBoxLayout()
        col.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(0)
        self.title = Marquee("", 11, QFont.DemiBold)
        top.addWidget(self.title, 1)
        self.back = IconButton("expand", 24, 12, "Back to full window")
        self.pin = IconButton("pin", 24, 12, "Always on top", checkable=True)
        self.close_b = IconButton("close", 24, 12, "Close mini player")
        self.pin.setChecked(True)
        self.tools = (self.back, self.pin, self.close_b)
        for b in self.tools:
            top.addWidget(b)
        col.addLayout(top)
        self.artist = Marquee("", 9, QFont.Normal, 150)
        col.addWidget(self.artist)
        col.addStretch()
        ctl = QHBoxLayout()
        ctl.setSpacing(4)
        self.fav = IconButton("heart", 30, 15, "Favorite")
        self.prev = IconButton("prev", 32, 17, "Previous")
        self.play = PlayButton(38)
        self.next = IconButton("next", 32, 17, "Next")
        self.viz = Visualizer(self, compact=True, style="bars", bands=10)
        self.viz.setFixedSize(46, 20)
        ctl.addWidget(self.prev)
        ctl.addWidget(self.play)
        ctl.addWidget(self.next)
        ctl.addStretch()
        ctl.addWidget(self.viz)
        ctl.addWidget(self.fav)
        col.addLayout(ctl)
        lay.addLayout(col, 1)
        p = ctx.player
        self.prev.clicked.connect(p.prev)
        self.next.clicked.connect(p.next)
        self.play.clicked.connect(p.toggle)
        self.fav.clicked.connect(lambda: p.toggle_favorite())
        self.back.clicked.connect(lambda: ctx.win.toggle_mini())
        self.close_b.clicked.connect(self._close)
        self.pin.toggled.connect(self._pin)
        p.trackChanged.connect(self._track)
        p.stateChanged.connect(lambda st: self.play.set_playing(st == "playing"))
        p.favoriteChanged.connect(lambda *_: self._fav())
        ctx.theme.changed.connect(self.update)
        ctx.art.ready.connect(lambda _k: self._make_bg())
        t = QTimer(self)
        t.timeout.connect(self.update)
        t.start(250)
        self._track(p.current)
        self._tools(0)

    # ── behaviour
    def _close(self):
        self.hide()
        ctx.win.showNormal()
        ctx.win.raise_()

    def _pin(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _tools(self, v):
        for b in self.tools:
            b.setVisible(v > 0.5)

    def enterEvent(self, e):
        self._ha.go(1)
        self._tools(1)

    def leaveEvent(self, e):
        self._ha.go(0)
        self._tools(0)
        self._seek_hover = self._cover_hover = False

    def _track(self, t):
        self.title.setText((t or {}).get("title") or "Not playing")
        self.artist.setText((t or {}).get("artist") or "")
        self.play.set_playing(ctx.player.engine.state == "playing")
        self._fav()
        self._make_bg()

    def _fav(self):
        f = ctx.player.is_favorite()
        self.fav.set_icon("heart_fill" if f else "heart")
        self.fav.setCheckable(True)
        self.fav.setChecked(f)

    def _make_bg(self):
        t = ctx.player.current
        if not t:
            self.bg = None
        else:
            img = ctx.art.get(t, 64, 0).toImage()
            self.bg = QPixmap.fromImage(blur_image(img, 4, 14)) if not img.isNull() else None
        self.update()

    def _seek_rect(self):
        return QRectF(14 + COVER + 14, H - 12, W - COVER - 42, 10)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        sr = self._seek_rect().adjusted(0, -4, 0, 4)
        d = ctx.player.engine.duration() or 0
        if sr.contains(e.position()) and d:
            ctx.player.seek(max(0.0, min(1.0, (e.position().x() - sr.left()) / sr.width())) * d)
            return
        if QRectF(14, 14, COVER, COVER).contains(e.position()):
            return
        self.windowHandle().startSystemMove()

    def mouseReleaseEvent(self, e):
        if QRectF(14, 14, COVER, COVER).contains(e.position()):
            ctx.win.toggle_mini()

    def mouseMoveEvent(self, e):
        hv = self._seek_rect().adjusted(0, -4, 0, 4).contains(e.position())
        ch = QRectF(14, 14, COVER, COVER).contains(e.position())
        if hv != self._seek_hover or ch != self._cover_hover:
            self._seek_hover, self._cover_hover = hv, ch
            self.setCursor(Qt.PointingHandCursor if (hv or ch) else Qt.ArrowCursor)
            self.update()

    def mouseDoubleClickEvent(self, e):
        ctx.win.toggle_mini()

    def wheelEvent(self, e):
        v = ctx.player.engine.volume + (0.05 if e.angleDelta().y() > 0 else -0.05)
        ctx.player.set_volume(max(0.0, min(1.0, v)))

    # ── painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rr_path(r, RAD)
        p.save()
        p.setClipPath(path)
        p.fillRect(r, th.bg)
        if self.bg is not None:
            p.setOpacity(0.55)
            p.drawPixmap(r, self.bg, QRectF(self.bg.rect()))
            p.setOpacity(1)
        p.fillRect(r, QColor(6, 6, 9, 150))
        side = QLinearGradient(r.topLeft(), r.topRight())
        side.setColorAt(0, QColor(0, 0, 0, 0))
        side.setColorAt(1, QColor(0, 0, 0, 90))
        p.fillRect(r, side)
        p.restore()
        # hairline rim
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 70))
        rim.setColorAt(0.5, QColor(255, 255, 255, 14))
        rim.setColorAt(1, th.acc(90))
        p.setPen(QPen(rim, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), RAD, RAD)
        # cover
        t = ctx.player.current or {"title": "Umbra"}
        cr = QRectF(14, 14, COVER, COVER)
        p.drawPixmap(cr.toRect(), ctx.art.get(t, COVER, 14))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRoundedRect(cr.adjusted(.5, .5, -.5, -.5), 14, 14)
        if self._cover_hover or self._seek_hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(cr, 14, 14)
            from . import icons
            icons.draw(p, "expand", QRectF(cr.center().x() - 11, cr.center().y() - 11, 22, 22), QColor(255, 255, 255, 0 if self._seek_hover else 230))
        # progress hairline + times
        e = ctx.player.engine
        d = e.duration() or 0
        pos = e.position()
        k = (pos / d) if d else 0
        sr = self._seek_rect()
        y = sr.center().y()
        p.setPen(QPen(QColor(255, 255, 255, 30), 2 if self._seek_hover else 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(sr.left(), y), QPointF(sr.right(), y))
        p.setPen(QPen(th.accent, 2.4 if self._seek_hover else 1.6, Qt.SolidLine, Qt.RoundCap))
        x = sr.left() + sr.width() * k
        if k > 0:
            p.drawLine(QPointF(sr.left(), y), QPointF(x, y))
        p.setPen(Qt.NoPen)
        p.setBrush(th.accent)
        p.drawEllipse(QPointF(x, y), 4.0 if self._seek_hover else 2.8, 4.0 if self._seek_hover else 2.8)
        if self._seek_hover:
            p.setFont(font(7.4, QFont.Medium, mono=True))
            p.setPen(QColor(255, 255, 255, 170))
            p.drawText(QRectF(cr.left(), cr.bottom() - 20, COVER, 16), Qt.AlignCenter, f"{fmt_time(pos)} / {fmt_time(d)}")


# ═══════════════════════════════════════════════════════════════ small player
class SmallPlayer(QWidget):
    """A desk-sized companion between Mini and full: artwork, transport, live analyzer and visualizer."""

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        from PySide6.QtWidgets import QSizePolicy
        from .visuals import AnalyzerCard
        from .widgets import Badge, GlassPanel, IconButton, Slider, label
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(900, 600)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(10)
        # top bar
        top = QHBoxLayout()
        top.setSpacing(4)
        brand = QWidget()
        brand.setFixedSize(110, 26)
        brand.paintEvent = lambda e, w=brand: self._brand(w)
        top.addWidget(brand)
        top.addStretch()
        self.pin = IconButton("pin", 28, 14, "Always on top", checkable=True)
        self.pin.setChecked(True)
        self.pin.toggled.connect(self._pin)
        self.mini_b = IconButton("mini", 28, 14, "Mini player")
        self.mini_b.clicked.connect(lambda: ctx.win.toggle_mini())
        self.back = IconButton("expand", 28, 14, "Back to full window")
        self.back.clicked.connect(lambda: ctx.win.toggle_small())
        self.close_b = IconButton("close", 28, 14, "Close")
        self.close_b.clicked.connect(lambda: ctx.win.toggle_small())
        for b in (self.pin, self.mini_b, self.back, self.close_b):
            top.addWidget(b)
        root.addLayout(top)
        # body
        body = QHBoxLayout()
        body.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(4)
        self.cover = QWidget()
        self.cover.setFixedSize(220, 220)
        self.cover.paintEvent = lambda e: self._cover()
        left.addWidget(self.cover)
        left.addSpacing(8)
        self.title = Marquee("", 15, QFont.Bold)
        self.title.setFixedWidth(260)
        self.artist = Marquee("", 10, QFont.Normal, 165)
        self.artist.setFixedWidth(260)
        left.addWidget(self.title)
        left.addWidget(self.artist)
        chips = QHBoxLayout()
        chips.setSpacing(5)
        self.b_fmt = Badge("", True)
        self.b_q = Badge("")
        chips.addWidget(self.b_fmt)
        chips.addWidget(self.b_q)
        chips.addStretch()
        left.addLayout(chips)
        left.addStretch()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(262)
        body.addWidget(lw)
        card = GlassPanel(radius=None, level=0.9)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        self.analyzer = AnalyzerCard()
        cl.addWidget(self.analyzer)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        body.addWidget(card, 1)
        root.addLayout(body, 1)
        self.viz = Visualizer(self)
        self.viz.setFixedHeight(56)
        root.addWidget(self.viz)
        # seek
        sk = QHBoxLayout()
        sk.setSpacing(8)
        self.t_pos = label("0:00", 8, QFont.Medium, alpha=150)
        self.t_pos.setFont(font(8, QFont.Medium, mono=True))
        self.t_dur = label("0:00", 8, QFont.Medium, alpha=150)
        self.t_dur.setFont(font(8, QFont.Medium, mono=True))
        self.seek = Slider(height=20, groove=4, formatter=lambda v: fmt_time(v * (ctx.player.engine.duration() or 0)))
        self.seek.released.connect(lambda v: ctx.player.seek(v * (ctx.player.engine.duration() or 0)))
        sk.addWidget(self.t_pos)
        sk.addWidget(self.seek, 1)
        sk.addWidget(self.t_dur)
        root.addLayout(sk)
        # transport
        tr = QHBoxLayout()
        tr.setSpacing(10)
        p = ctx.player
        self.fav = IconButton("heart", 34, 17, "Favorite")
        self.fav.clicked.connect(lambda: p.toggle_favorite())
        tr.addWidget(self.fav)
        tr.addStretch()
        self.shuf = IconButton("shuffle", 34, 17, "Shuffle", checkable=True)
        self.prev = IconButton("prev", 38, 20, "Previous")
        self.play = PlayButton(46)
        self.next = IconButton("next", 38, 20, "Next")
        self.rep = IconButton("repeat", 34, 17, "Repeat", checkable=True)
        for w in (self.shuf, self.prev, self.play, self.next, self.rep):
            tr.addWidget(w)
        tr.addStretch()
        self.vol = Slider(height=20, groove=4, accent=False, formatter=lambda v: f"{int(v * 100)}%")
        self.vol.setFixedWidth(110)
        self.vol.moved.connect(p.set_volume)
        tr.addWidget(IconButton("volume", 30, 15, ""))
        tr.addWidget(self.vol)
        root.addLayout(tr)
        self.play.clicked.connect(p.toggle)
        self.prev.clicked.connect(p.prev)
        self.next.clicked.connect(p.next)
        self.shuf.clicked.connect(lambda: p.toggle_shuffle())
        self.rep.clicked.connect(lambda: p.cycle_repeat())
        p.trackChanged.connect(self._track)
        p.stateChanged.connect(lambda st: self.play.set_playing(st == "playing"))
        p.shuffleChanged.connect(self._modes)
        p.repeatChanged.connect(lambda _r: self._modes())
        p.favoriteChanged.connect(lambda *_: self._fav())
        p.volumeChanged.connect(lambda v: not self.vol.drag and self.vol.setValue(v))
        ctx.theme.changed.connect(self.update)
        ctx.art.ready.connect(lambda _k: self.cover.update())
        self.vol.setValue(p.engine.volume)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(120)
        self._track(p.current)
        self._modes()

    def _brand(self, w):
        from .chrome import paint_logo
        p = QPainter(w)
        p.setRenderHint(QPainter.Antialiasing)
        paint_logo(p, QRectF(0, 2, 22, 22), ctx.theme.accent)
        p.setFont(font(9, QFont.Bold, 3))
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(30, 0, 80, 26), Qt.AlignVCenter, "UMBRA")

    def _pin(self, on):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _modes(self, *_):
        p = ctx.player
        self.shuf.setChecked(p.shuffle)
        self.rep.setChecked(p.repeat != "off")
        self.rep.set_icon("repeat_one" if p.repeat == "one" else "repeat")

    def _fav(self):
        f = ctx.player.is_favorite()
        self.fav.set_icon("heart_fill" if f else "heart")
        self.fav.setCheckable(True)
        self.fav.setChecked(f)

    def _track(self, t):
        t = t or {}
        self.title.setText(t.get("title") or "Not playing")
        self.artist.setText(" · ".join(x for x in (t.get("artist"), t.get("album")) if x))
        if t.get("source", "local") != "local":
            self.b_fmt.setText((t.get("source") or "").upper(), True)
            self.b_q.setText("STREAM")
        else:
            self.b_fmt.setText((t.get("codec") or "").upper(), bool(t.get("lossless")))
            self.b_q.setText(f"{t.get('bitdepth') or 16}-BIT · {(t.get('samplerate') or 44100) / 1000:g} KHZ" if t.get("lossless")
                             else (f"{t['bitrate']} KBPS" if t.get("bitrate") else ""))
        self.play.set_playing(ctx.player.engine.state == "playing")
        self._fav()
        self.cover.update()

    def _tick(self):
        if not self.isVisible():
            return
        e = ctx.player.engine
        d = e.duration() or 0
        pos = e.position()
        if not self.seek.drag:
            self.seek.setValue(pos / d if d else 0)
        self.t_pos.setText(fmt_time(pos))
        self.t_dur.setText(fmt_time(d))

    def _cover(self):
        p = QPainter(self.cover)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        t = ctx.player.current or {"title": "Umbra"}
        r = QRectF(0, 0, 220, 220)
        p.drawPixmap(r.toRect(), ctx.art.get(t, 220, 18))
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 18, 18)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 48:
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.position().y() < 48:
            ctx.win.toggle_small()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        rad = th.radius + 8
        p.save()
        p.setClipPath(rr_path(r, rad))
        th.paint_backdrop(p, r, time.time() if ctx.settings["ambient_motion"] else 0)
        p.restore()
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 70))
        rim.setColorAt(0.5, QColor(255, 255, 255, 14))
        rim.setColorAt(1, th.acc(80))
        p.setPen(QPen(rim, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)
