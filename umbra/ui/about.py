"""About page — developer card (edit umbra/about_config.py)."""
import os
import platform
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont, QImage, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget, QGridLayout
import PySide6

from ..about_config import CHANGELOG, CREDITS, DEVELOPER, PROJECT
from ..config import APP_NAME, APP_TAGLINE, APP_VERSION, data_dir
from . import icons
from .art import rounded
from .chrome import paint_logo
from .context import ctx
from .widgets import Badge, Caption, PillButton, font, label, paint_glass, rr_path

LINK_ICONS = {"github": "github", "website": "globe", "telegram": "telegram", "twitter": "external", "x": "external",
              "instagram": "image", "email": "link", "youtube": "ytmusic"}


class Avatar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(132, 132)
        self.img = QImage(DEVELOPER.get("avatar")) if DEVELOPER.get("avatar") and os.path.exists(DEVELOPER["avatar"]) else None
        self.t = 0.0
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(33)

    def _tick(self):
        self.t += 0.02
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        c = QPointF(66, 66)
        import math
        for i in range(3):
            a = th.acc(int(60 - i * 18))
            p.setPen(QPen(a, 1.2))
            p.setBrush(Qt.NoBrush)
            r = 58 + i * 4 + math.sin(self.t * 2 + i) * 1.5
            p.drawEllipse(c, r, r)
        r = QRectF(16, 16, 100, 100)
        if self.img is not None and not self.img.isNull():
            p.drawPixmap(r.toRect(), rounded(self.img, 100, 50))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, th.acc(200))
            g.setColorAt(1, QColor(20, 20, 26))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(r)
            initials = "".join(w[0] for w in DEVELOPER.get("name", "?").split()[:2]).upper()
            p.setFont(font(30, QFont.Bold))
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(r, Qt.AlignCenter, initials)


class Card(QWidget):
    def __init__(self, parent=None, level=1.0, accent=0.0):
        super().__init__(parent)
        self.level, self.accent = level, accent
        self._hover = None
        self.setMouseTracking(True)

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_glass(p, self, QRectF(self.rect()).adjusted(1, 1, -1, -1), None, self.level, self._hover, accent_edge=self.accent)


class Hero(Card):
    """Animated hero: the app icon floating in an orbit of slow particles, wordmark and project actions."""

    def __init__(self, parent=None):
        super().__init__(parent, 1.0, 0.8)
        self.t = 0.0
        import random
        rnd = random.Random(7)
        self.stars = [(rnd.random(), rnd.random(), rnd.uniform(0.4, 1.6), rnd.uniform(0, 6.28)) for _ in range(70)]
        self._icon = None
        tm = QTimer(self)
        tm.timeout.connect(self._tick)
        tm.start(33)

    def _tick(self):
        if self.isVisible():
            self.t += 0.033
            self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        import math
        from .window import app_icon
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setClipPath(rr_path(r, th.radius))
        for x, y, sz, ph in self.stars:
            a = int(40 + 50 * (0.5 + 0.5 * math.sin(self.t * 1.3 + ph)))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(r.left() + x * r.width(), r.top() + y * r.height()), sz, sz)
        c = QPointF(r.right() - 190, r.center().y())
        g = QRadialGradient(c, 230)
        g.setColorAt(0, th.acc(70))
        g.setColorAt(1, th.acc(0))
        p.setBrush(g)
        p.drawEllipse(c, 230, 230)
        for i, (rx, ry, sp) in enumerate(((150, 52, 0.35), (178, 66, -0.22))):
            p.save()
            p.translate(c)
            p.rotate(-18 + i * 30)
            p.setPen(QPen(th.acc(70 - i * 25), 1.1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), rx, ry)
            ang = self.t * sp * 2
            p.setPen(Qt.NoPen)
            p.setBrush(th.accent)
            p.drawEllipse(QPointF(rx * math.cos(ang), ry * math.sin(ang)), 3.2 - i, 3.2 - i)
            p.restore()
        if self._icon is None or getattr(self, "_acc", None) != th.accent.name():
            self._icon = app_icon(400)
            self._acc = th.accent.name()
        bob = math.sin(self.t * 1.2) * 5
        p.drawPixmap(QRectF(c.x() - 100, c.y() - 100 + bob, 200, 200).toRect(), self._icon)


class LinkTile(Card):
    """Big clickable link card: icon, label, address, ↗."""

    def __init__(self, name, url, parent=None):
        super().__init__(parent, 0.85, 0.3)
        self.name, self.url = name, url
        self.setFixedHeight(76)
        self.setMinimumWidth(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(url)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl(self.url))

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        hov = self._hover is not None
        ic = QRectF(16, 18, 40, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(th.acc(230) if hov else QColor(255, 255, 255, 18))
        p.drawRoundedRect(ic, 12, 12)
        icons.draw(p, LINK_ICONS.get(self.name.lower(), "link"), ic.adjusted(10, 10, -10, -10),
                   QColor(10, 10, 12) if hov else QColor(255, 255, 255, 220))
        p.setFont(font(10.5, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(70, 16, self.width() - 110, 22), Qt.AlignLeft | Qt.AlignVCenter, self.name)
        p.setFont(font(8.4, mono=True))
        p.setPen(th.acc(210) if hov else QColor(255, 255, 255, 130))
        addr = self.url.split("://", 1)[-1].rstrip("/")
        p.drawText(QRectF(70, 38, self.width() - 110, 20), Qt.AlignLeft | Qt.AlignVCenter, addr)
        icons.draw(p, "external", QRectF(self.width() - 34, 30, 16, 16), QColor(255, 255, 255, 200 if hov else 90))


class FeatureTile(Card):
    def __init__(self, icon, title, text, parent=None):
        super().__init__(parent, 0.75)
        self.icon, self.title, self.text = icon, title, text
        self.setFixedHeight(112)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        icons.draw(p, self.icon, QRectF(18, 18, 22, 22), ctx.theme.acc(230))
        p.setFont(font(10.5, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(18, 48, self.width() - 36, 20), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(font(8.4))
        p.setPen(QColor(255, 255, 255, 130))
        p.drawText(QRectF(18, 70, self.width() - 36, 36), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.text)


class StatPill(Card):
    def __init__(self, value, name, parent=None):
        super().__init__(parent, 0.7)
        self.value, self.name = value, name
        self.setFixedHeight(78)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(font(20, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 245))
        p.drawText(QRectF(18, 10, self.width() - 30, 34), Qt.AlignLeft | Qt.AlignVCenter, self.value)
        p.setFont(font(7.4, QFont.DemiBold, 1.6, mono=True))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(18, 46, self.width() - 30, 18), Qt.AlignLeft | Qt.AlignVCenter, self.name.upper())


FEATURES = [
    ("eq", "Pro audio engine", "64-bit DSP, gapless, crossfade, 10-band EQ, WASAPI exclusive."),
    ("analyzer", "Audio analyzer", "Bit depth, sample rate, true peak, LUFS, DR and a live spectrum."),
    ("lyrics", "Synced lyrics", "LRC, embedded or LRCLIB — search online and add with one click."),
    ("tag", "Tag editor", "Batch edit every field, artwork from file, web or clipboard."),
    ("sparkle", "Smart lists", "Recently played, on repeat, never played, random discovery."),
    ("download", "Stream & download", "YouTube Music search, Spotify imports, offline downloads."),
    ("palette", "Themes that adapt", "Seven presets, accents from artwork, Windows or wallpaper."),
    ("small", "Three sizes", "Full window, a Small player with analyzer, and a Mini capsule."),
]

SHORTCUTS = [("Space", "Play / pause"), ("Ctrl ← / →", "Previous / next"), ("Ctrl K", "Search"),
             ("Ctrl L", "Lyrics on / off"), ("Ctrl Q", "Queue"), ("Ctrl M", "Mini player"),
             ("Ctrl Shift M", "Small player"), ("F11", "Immersive"), ("Ctrl D", "Favorite"), ("Ctrl ,", "Settings")]


class AboutPage(QWidget):
    key = "about"

    def __init__(self, parent=None):
        super().__init__(parent)
        from .views import scroll_page
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa, lay = scroll_page(self)
        outer.addWidget(sa)
        lay.setSpacing(14)
        # ── hero
        hero = Hero()
        hero.setFixedHeight(330)
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(36, 32, 36, 30)
        hl.setSpacing(6)
        hl.addWidget(Caption(f"Version {APP_VERSION}  ·  {PROJECT.get('license', 'MIT')} licence"))
        name = label(APP_NAME.upper(), 52, QFont.Black)
        name.setFont(font(52, QFont.Black, 14))
        hl.addWidget(name)
        hl.addWidget(label(APP_TAGLINE, 14, QFont.Medium, alpha=180))
        hl.addSpacing(8)
        hl.addWidget(label("A local-first, lossless-friendly music player with a clean glass interface.\n"
                           "Built for people who still curate their own library.", 9.8, alpha=135))
        hl.addStretch()
        br = QHBoxLayout()
        br.setSpacing(8)
        for i, (t, ic, u) in enumerate((("Star on GitHub", "github", PROJECT["repo"]), ("Releases", "download", PROJECT["releases"]),
                                         ("Report an issue", "info", PROJECT["issues"]))):
            b = PillButton(t, ic, primary=(i == 0))
            b.clicked.connect(lambda _=False, url=u: QDesktopServices.openUrl(QUrl(url)))
            br.addWidget(b)
        br.addStretch()
        hl.addLayout(br)
        lay.addWidget(hero)
        # ── developer
        lay.addWidget(Caption("Made by"))
        dev = Card(level=0.9, accent=0.4)
        dl = QHBoxLayout(dev)
        dl.setContentsMargins(28, 26, 28, 26)
        dl.setSpacing(26)
        dl.addWidget(Avatar(), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        nr = QHBoxLayout()
        nr.setSpacing(10)
        nr.addWidget(label(DEVELOPER.get("name", ""), 24, QFont.Bold))
        handle = Badge(DEVELOPER.get("handle", ""), True)
        handle.setCursor(Qt.PointingHandCursor)
        handle.setToolTip("Copy")
        handle.mousePressEvent = lambda e: (QApplication.clipboard().setText(DEVELOPER.get("handle", "")),
                                            ctx.toast("Handle copied", "check"))
        nr.addWidget(handle)
        nr.addStretch()
        col.addLayout(nr)
        col.addWidget(label(f"{DEVELOPER.get('role', '')}   ·   {DEVELOPER.get('location', '')}", 9.5, alpha=150))
        col.addSpacing(8)
        col.addWidget(label(DEVELOPER.get("bio", ""), 10, alpha=200, wrap=True))
        col.addSpacing(12)
        st = QHBoxLayout()
        st.setSpacing(6)
        for s_ in DEVELOPER.get("stack", []):
            st.addWidget(Badge(s_.upper()))
        st.addStretch()
        col.addLayout(st)
        dl.addLayout(col, 1)
        lay.addWidget(dev)
        links = QHBoxLayout()
        links.setSpacing(12)
        for k, url in DEVELOPER.get("links", {}).items():
            links.addWidget(LinkTile(k, url), 1)
        lay.addLayout(links)
        # ── your library, in numbers
        lay.addWidget(Caption("Your library, in numbers"))
        s = ctx.lib.stats()
        self.stats = QHBoxLayout()
        self.stats.setSpacing(12)
        self.pills = {}
        for k, n in (("tracks", "Tracks"), ("albums", "Albums"), ("artists", "Artists"), ("hours", "Hours of music"),
                     ("plays", "Plays"), ("lossless", "Lossless")):
            w = StatPill("0", n)
            self.pills[k] = w
            self.stats.addWidget(w, 1)
        lay.addLayout(self.stats)
        # ── features
        lay.addWidget(Caption("What's inside"))
        fg = QGridLayout()
        fg.setSpacing(12)
        for i, (ic, t, d) in enumerate(FEATURES):
            fg.addWidget(FeatureTile(ic, t, d), i // 4, i % 4)
        lay.addLayout(fg)
        # ── changelog + shortcuts
        row2 = QHBoxLayout()
        row2.setSpacing(14)
        ch = Card(level=0.8)
        chl = QVBoxLayout(ch)
        chl.setContentsMargins(24, 20, 24, 20)
        chl.setSpacing(6)
        chl.addWidget(Caption("What's new"))
        for ver, items in CHANGELOG:
            vr = QHBoxLayout()
            vr.addWidget(Badge("v" + ver, ver == APP_VERSION))
            vr.addStretch()
            chl.addLayout(vr)
            for it in items:
                chl.addWidget(label("—  " + it, 9, alpha=175, wrap=True))
            chl.addSpacing(6)
        chl.addStretch()
        kc = Card(level=0.8)
        kl = QVBoxLayout(kc)
        kl.setContentsMargins(24, 20, 24, 20)
        kl.setSpacing(6)
        kl.addWidget(Caption("Keyboard"))
        kg = QGridLayout()
        kg.setVerticalSpacing(7)
        for i, (k, d) in enumerate(SHORTCUTS):
            kk = label(k, 8.6, QFont.DemiBold)
            kk.setFont(font(8.6, QFont.DemiBold, mono=True))
            kk.setStyleSheet(f"color: {ctx.theme.accent.name()}; background: transparent;")
            kg.addWidget(kk, i, 0)
            kg.addWidget(label(d, 9, alpha=170), i, 1)
        kl.addLayout(kg)
        kl.addStretch()
        row2.addWidget(ch, 3)
        row2.addWidget(kc, 2)
        lay.addLayout(row2)
        # ── system + credits
        row = QHBoxLayout()
        row.setSpacing(14)
        sysc = Card(level=0.8)
        sl = QVBoxLayout(sysc)
        sl.setContentsMargins(24, 20, 24, 20)
        sl.addWidget(Caption("System"))
        from ..audio import decoder
        info = [("Python", platform.python_version()), ("Qt / PySide6", PySide6.__version__),
                ("Platform", f"{platform.system()} {platform.release()}"),
                ("Audio", "PortAudio · float32" if ctx.player.engine.available() else "unavailable"),
                ("FFmpeg", "found" if decoder.FFMPEG else "not found"),
                ("Data", str(data_dir()))]
        g = QGridLayout()
        for i, (k, v) in enumerate(info):
            g.addWidget(label(k, 9, alpha=120), i, 0)
            vv = label(v, 9, QFont.DemiBold)
            vv.setFont(font(8.6, QFont.DemiBold, mono=True))
            g.addWidget(vv, i, 1, Qt.AlignRight)
        sl.addLayout(g)
        sl.addStretch()
        cred = Card(level=0.8)
        cl = QVBoxLayout(cred)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.addWidget(Caption("Standing on the shoulders of"))
        for k, d in CREDITS:
            r = QHBoxLayout()
            r.addWidget(label(k, 9.5, QFont.DemiBold))
            r.addStretch()
            r.addWidget(label(d, 8.6, alpha=120))
            cl.addLayout(r)
        cl.addStretch()
        row.addWidget(sysc, 1)
        row.addWidget(cred, 1)
        lay.addLayout(row)
        foot = label(f"{APP_NAME} {APP_VERSION}  ·  crafted by {DEVELOPER.get('name', '')} — in the dark.", 8.6, alpha=100)
        foot.setAlignment(Qt.AlignCenter)
        lay.addWidget(foot)
        lay.addStretch()

    def load(self, **kw):
        s = ctx.lib.stats()
        n = s["tracks"] or 0
        vals = {"tracks": f"{n:,}", "albums": f"{s['albums']:,}", "artists": f"{s['artists']:,}",
                "hours": f"{s['dur'] / 3600:.1f}", "plays": f"{s['plays']:,}",
                "lossless": f"{(100 * s['lossless'] / n) if n else 0:.0f}%"}
        for k, w in self.pills.items():
            w.value = vals[k]
            w.update()

    def refresh(self):
        self.load()
