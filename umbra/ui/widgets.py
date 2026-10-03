"""Umbra glass toolkit — liquid-glass panels and hand-painted controls."""
import math

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt,
                            QTimer, QVariantAnimation, Signal, Property, QParallelAnimationGroup)
from PySide6.QtGui import (QPixmap, QBrush, QColor, QCursor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient, QAction, QKeySequence)
from PySide6.QtWidgets import (QAbstractButton, QLayout, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, QGraphicsDropShadowEffect)

from ..config import settings
from ..theme import theme
from . import icons

FONT_FAMILIES = ["Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Display",
                 "Noto Sans", "Helvetica Neue", "Arial"]


def font(size=10, weight=QFont.Normal, spacing=0.0, mono=False):
    f = QFont()
    f.setFamilies(["Cascadia Mono", "JetBrains Mono", "Consolas", "Noto Sans Mono", "monospace"] if mono else FONT_FAMILIES)
    f.setPointSizeF(size * float(settings()["font_scale"]))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def fmt_time(sec):
    sec = int(max(0, sec or 0))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_long(sec):
    sec = int(sec or 0)
    h, r = divmod(sec, 3600)
    m = r // 60
    if h >= 24:
        return f"{h // 24} d {h % 24} h"
    return f"{h} h {m} min" if h else f"{m} min"


def anim_ms(ms):
    s = settings()
    if not s["animations"]:
        return 0
    return int(ms / max(0.2, float(s["anim_speed"])))


class Tween(QVariantAnimation):
    """Animate a float attribute on a widget and repaint."""

    def __init__(self, target, attr, ms=220, curve=QEasingCurve.OutCubic):
        super().__init__(target)
        self.t, self.attr = target, attr
        self.setDuration(ms)
        self.setEasingCurve(curve)
        self.valueChanged.connect(self._set)

    def _set(self, v):
        setattr(self.t, self.attr, float(v))
        self.t.update()

    def go(self, end, ms=None):
        self.stop()
        d = anim_ms(ms if ms is not None else 220)
        if d == 0:
            self._set(end)
            return
        self.setDuration(d)
        self.setStartValue(float(getattr(self.t, self.attr)))
        self.setEndValue(float(end))
        self.start()


# ════════════════════════════════════════════════════════════════════ glass painting
def rr_path(r: QRectF, radius):
    p = QPainterPath()
    p.addRoundedRect(r, radius, radius)
    return p


def crescent_path(c: QPointF, r: float, phase=0.42):
    """Umbra's signature mark: a disc eclipsed by an offset disc."""
    a = QPainterPath()
    a.addEllipse(c, r, r)
    b = QPainterPath()
    b.addEllipse(QPointF(c.x() + r * phase * 1.25, c.y() - r * phase * 0.9), r * 0.92, r * 0.92)
    return a.subtracted(b)


def paint_crescent(p: QPainter, c: QPointF, r: float, color: QColor, phase=0.42):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(crescent_path(c, r, phase))
    p.restore()


def paint_shadow(p: QPainter, r: QRectF, radius, strength=1.0, spread=14):
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(spread, 0, -2):
        a = int(5 * strength * (1 - i / spread) ** 1.6 + 1)
        p.setBrush(QColor(0, 0, 0, a))
        rr = r.adjusted(-i * 0.5, -i * 0.25, i * 0.5, i)
        p.drawRoundedRect(rr, radius + i * 0.5, radius + i * 0.5)
    p.restore()


def paint_glass(p: QPainter, widget: QWidget, r: QRectF, radius=None, level=1.0, hover: QPointF | None = None,
                rim=True, tint_alpha=None, shadow=False, accent_edge=0.0):
    """Liquid glass: frosted backdrop sample + tint + sheen + specular rim + cursor caustic."""
    th = theme()
    radius = th.radius if radius is None else radius
    path = rr_path(r, radius)
    if shadow:
        paint_shadow(p, r, radius, 1.0)
    p.save()
    p.setClipPath(path)
    # 1 ─ frosted backdrop sample (fake backdrop-filter)
    if th.frost is not None and widget is not None:
        win = widget.window()
        off = widget.mapTo(win, QPoint(0, 0))
        W, H = max(1, win.width()), max(1, win.height())
        fr = th.frost
        sx, sy = fr.width() / W, fr.height() / H
        src = QRectF((off.x() + r.x()) * sx, (off.y() + r.y()) * sy, r.width() * sx, r.height() * sy)
        p.setOpacity(0.9)
        p.drawPixmap(r, fr, src)
        p.setOpacity(1.0)
    # 2 ─ tint
    tint = QColor(th.tint)
    base = th.glass if tint_alpha is None else tint_alpha
    tint.setAlphaF(max(0.0, min(1.0, base * level)))
    p.fillRect(r, tint)
    # 3 ─ vertical sheen (liquid volume)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, QColor(255, 255, 255, int(16 * level)))
    g.setColorAt(0.35, QColor(255, 255, 255, int(4 * level)))
    g.setColorAt(1.0, QColor(255, 255, 255, int(2 * level)))
    p.fillRect(r, g)
    # 4 ─ cursor caustic
    if hover is not None and settings()["specular"]:
        rg = QRadialGradient(hover, max(140.0, r.width() * 0.35))
        rg.setColorAt(0, QColor(255, 255, 255, 16))
        rg.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, rg)
    p.restore()
    if rim:
        # 5 ─ specular rim: bright top-left, fading, faint accent at bottom-right
        p.save()
        p.setBrush(Qt.NoBrush)
        rim_g = QLinearGradient(r.topLeft(), r.bottomRight())
        rim_g.setColorAt(0.0, QColor(255, 255, 255, 64))
        rim_g.setColorAt(0.25, QColor(255, 255, 255, 18))
        rim_g.setColorAt(0.7, QColor(255, 255, 255, 8))
        ae = th.acc(int(10 + 50 * accent_edge))
        rim_g.setColorAt(1.0, ae)
        p.setPen(QPen(QBrush(rim_g), 1.0))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        # inner dark line for depth
        p.setPen(QPen(QColor(0, 0, 0, 60), 1.0))
        p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), radius - 1, radius - 1)
        p.restore()


class GlassPanel(QFrame):
    """A floating liquid-glass island."""

    def __init__(self, parent=None, radius=None, level=1.0, specular=True, shadow=False):
        super().__init__(parent)
        self.radius, self.level, self.shadow = radius, level, shadow
        self._hover = None
        self.setAttribute(Qt.WA_StyledBackground, False)
        if specular:
            self.setMouseTracking(True)
        th = theme()
        th.changed.connect(self.update)
        th.backdropChanged.connect(self.update)

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_glass(p, self, QRectF(self.rect()), self.radius, self.level, self._hover, shadow=self.shadow)


# ════════════════════════════════════════════════════════════════════ buttons
class IconButton(QAbstractButton):
    def __init__(self, icon, size=34, icon_size=18, tip="", parent=None, checkable=False, round_bg=True, stroke=1.6):
        super().__init__(parent)
        self.icon_name = icon
        self.icon_size = icon_size
        self.round_bg = round_bg
        self.stroke = stroke
        self.badge = False
        self.setFixedSize(size, size)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self.h = 0.0
        self.pr = 0.0
        self._ha = Tween(self, "h", 160)
        self._pa = Tween(self, "pr", 120)
        self.active_color = None
        self.toggled.connect(lambda _: self.update())

    def set_icon(self, name):
        self.icon_name = name
        self.update()

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self._ha.go(0)

    def mousePressEvent(self, e):
        self._pa.go(1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._pa.go(0, 200)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        if self.round_bg and (self.h > 0.01 or on):
            a = int(18 * self.h + (14 if on else 0))
            p.setPen(QPen(QColor(255, 255, 255, int(28 * self.h + (20 if on else 0))), 1))
            p.setBrush(QColor(255, 255, 255, a))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        s = self.icon_size * (1 - 0.08 * self.pr)
        ir = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        if on:
            col = self.active_color or th.accent
        else:
            col = QColor(255, 255, 255, int(165 + 90 * self.h))
        if not self.isEnabled():
            col = QColor(255, 255, 255, 60)
        icons.draw(p, self.icon_name, ir, col, self.stroke)
        if on and self.isCheckable():
            p.setPen(Qt.NoPen)
            p.setBrush(th.accent)
            p.drawEllipse(QPointF(self.width() / 2, self.height() - 3.5), 1.6, 1.6)
        if self.badge:
            p.setPen(Qt.NoPen)
            p.setBrush(th.accent)
            p.drawEllipse(QPointF(self.width() - 8, 8), 3, 3)


class PlayButton(QAbstractButton):
    """Hero transport button — luminous disc with morphing glyph and breathing halo."""

    def __init__(self, size=50, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + 16, size + 16)
        self.d = size
        self.playing = False
        self.m = 0.0       # 0 play, 1 pause
        self.h = 0.0
        self.pr = 0.0
        self.glow = 0.0
        self._ma = Tween(self, "m", 260, QEasingCurve.OutBack)
        self._ha = Tween(self, "h", 180)
        self._pa = Tween(self, "pr", 100)
        self.setCursor(Qt.PointingHandCursor)
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._phase = 0.0

    def _tick(self):
        self._phase += 0.04
        self.update()

    def set_playing(self, on):
        if on == self.playing:
            return
        self.playing = on
        self._ma.go(1 if on else 0)
        if on and settings()["animations"]:
            self._t.start(33)
        else:
            self._t.stop()
            self.update()

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self._ha.go(0)

    def mousePressEvent(self, e):
        self._pa.go(1, 80)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._pa.go(0, 260)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        c = QPointF(self.width() / 2, self.height() / 2)
        d = self.d * (1 + 0.04 * self.h - 0.06 * self.pr)
        # halo
        breath = 0.5 + 0.5 * math.sin(self._phase) if self.playing else 0
        hg = QRadialGradient(c, d * 0.9)
        hc = th.acc(int(40 + 40 * breath + 30 * self.h))
        hg.setColorAt(0.45, hc)
        hc.setAlpha(0)
        hg.setColorAt(1, hc)
        p.setPen(Qt.NoPen)
        p.setBrush(hg)
        p.drawEllipse(c, d * 0.9, d * 0.9)
        # disc
        r = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(1, QColor(222, 222, 230))
        p.setBrush(g)
        p.drawEllipse(r)
        # accent ring
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(th.acc(int(140 + 100 * breath)) if self.playing else QColor(255, 255, 255, 90), 1.4))
        p.drawEllipse(r.adjusted(-3.5, -3.5, 3.5, 3.5))
        # morphing glyph: crossfade + rotate
        s = d * 0.42
        ir = QRectF(c.x() - s / 2, c.y() - s / 2, s, s)
        dark = QColor(10, 10, 14)
        p.save()
        p.translate(c)
        p.rotate(-90 * (1 - self.m) + 0 if False else 0)
        p.translate(-c)
        m = max(0.0, min(1.0, self.m))
        if m < 0.999:
            p.setOpacity(1 - m)
            icons.draw(p, "play", ir.translated(s * 0.05, 0), dark)
        if m > 0.001:
            p.setOpacity(m)
            icons.draw(p, "pause", ir, dark)
        p.restore()


class PillButton(QAbstractButton):
    def __init__(self, text, icon=None, primary=False, parent=None, height=36):
        super().__init__(parent)
        self.setText(text)
        self.icon_name = icon
        self.primary = primary
        self.h = 0.0
        self._ha = Tween(self, "h", 160)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(height)
        f = font(9.5, QFont.DemiBold)
        self.setFont(f)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._fit()

    def _fit(self):
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text()) + (54 if self.icon_name else 34)
        self.setFixedWidth(int(w))

    def setText(self, t):
        super().setText(t)
        if hasattr(self, "icon_name"):
            self._fit()

    def changeEvent(self, e):
        if e.type() == QEvent.FontChange:
            self._fit()
        super().changeEvent(e)

    def showEvent(self, e):
        self._fit()
        super().showEvent(e)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self._ha.go(0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2
        if self.primary:
            c = QColor(th.accent)
            p.setPen(Qt.NoPen)
            p.setBrush(c.lighter(100 + int(10 * self.h)))
            p.drawRoundedRect(r, rad, rad)
            fg = QColor(10, 10, 12)
        else:
            p.setPen(QPen(QColor(255, 255, 255, int(30 + 30 * self.h)), 1))
            p.setBrush(QColor(255, 255, 255, int(12 + 14 * self.h)))
            p.drawRoundedRect(r, rad, rad)
            fg = QColor(255, 255, 255, int(210 + 45 * self.h))
        if not self.isEnabled():
            fg.setAlpha(80)
        x = 15
        if self.icon_name:
            icons.draw(p, self.icon_name, QRectF(x - 1, (self.height() - 16) / 2, 16, 16), fg)
            x += 21
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(QRectF(x, 0, self.width() - x - 13, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class ChipButton(PillButton):
    def __init__(self, text, icon=None, parent=None):
        super().__init__(text, icon, False, parent, height=30)
        self.setFont(font(9, QFont.Medium))


class FlowLayout(QLayout):
    """Wrapping layout — items flow left-to-right and wrap onto new lines."""

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, r, test):
        x, y, lh = r.x(), r.y(), 0
        for it in self._items:
            hs = it.sizeHint()
            if x + hs.width() > r.right() + 1 and lh > 0:
                x, y, lh = r.x(), y + lh + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hs))
            x += hs.width() + self._sp
            lh = max(lh, hs.height())
        return y + lh - r.y()


# ════════════════════════════════════════════════════════════════════ sliders & toggles
class Slider(QWidget):
    valueChanged = Signal(float)
    moved = Signal(float)          # while dragging
    released = Signal(float)

    def __init__(self, parent=None, value=0.0, height=22, groove=4, formatter=None, accent=True):
        super().__init__(parent)
        self.v = value
        self.buffer = 0.0
        self.groove = groove
        self.formatter = formatter
        self.accent = accent
        self.drag = False
        self.h = 0.0
        self.hover_x = None
        self._ha = Tween(self, "h", 160)
        self.setFixedHeight(height)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.marks = []

    def setValue(self, v):
        if not self.drag:
            self.v = max(0.0, min(1.0, v))
            self.update()

    def value(self):
        return self.v

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self.hover_x = None
        self._ha.go(0)

    def _vx(self, x):
        pad = 8
        return max(0.0, min(1.0, (x - pad) / max(1, self.width() - 2 * pad)))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = True
            self.v = self._vx(e.position().x())
            self.moved.emit(self.v)
            self.update()

    def mouseMoveEvent(self, e):
        self.hover_x = e.position().x()
        if self.drag:
            self.v = self._vx(e.position().x())
            self.moved.emit(self.v)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag:
            self.drag = False
            self.v = self._vx(e.position().x())
            self.valueChanged.emit(self.v)
            self.released.emit(self.v)
            self.update()

    def wheelEvent(self, e):
        step = 0.03 if e.angleDelta().y() > 0 else -0.03
        self.v = max(0.0, min(1.0, self.v + step))
        self.valueChanged.emit(self.v)
        self.moved.emit(self.v)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        pad = 8
        w = self.width() - 2 * pad
        gh = self.groove + 2 * self.h
        y = (self.height() - gh) / 2
        track = QRectF(pad, y, w, gh)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(track, gh / 2, gh / 2)
        if self.buffer > 0:
            p.setBrush(QColor(255, 255, 255, 22))
            p.drawRoundedRect(QRectF(pad, y, w * self.buffer, gh), gh / 2, gh / 2)
        fw = max(gh, w * self.v)
        fill = QRectF(pad, y, fw, gh)
        g = QLinearGradient(fill.topLeft(), fill.topRight())
        if self.accent:
            g.setColorAt(0, th.acc(150))
            g.setColorAt(1, th.accent.lighter(115))
        else:
            g.setColorAt(0, QColor(255, 255, 255, 150))
            g.setColorAt(1, QColor(255, 255, 255, 235))
        p.setBrush(g)
        p.drawRoundedRect(fill, gh / 2, gh / 2)
        for m in self.marks:
            p.setBrush(QColor(255, 255, 255, 90))
            p.drawEllipse(QPointF(pad + w * m, self.height() / 2), 1.5, 1.5)
        # hover ghost
        if self.hover_x is not None and not self.drag:
            hx = pad + w * self._vx(self.hover_x)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawRoundedRect(QRectF(pad, y, max(0, hx - pad), gh), gh / 2, gh / 2)
        # knob
        k = 5.5 * self.h + (1.5 if self.drag else 0)
        if k > 0.3:
            cx = pad + w * self.v
            glow = QRadialGradient(QPointF(cx, self.height() / 2), k * 3)
            glow.setColorAt(0, th.acc(90))
            glow.setColorAt(1, th.acc(0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, self.height() / 2), k * 3, k * 3)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(cx, self.height() / 2), k, k)
        # bubble
        if self.formatter and (self.drag or self.hover_x is not None) and self.h > 0.5:
            vx = self.v if self.drag else self._vx(self.hover_x)
            txt = self.formatter(vx)
            f = font(8, QFont.DemiBold)
            p.setFont(f)
            tw = QFontMetrics(f).horizontalAdvance(txt) + 14
            bx = max(0, min(self.width() - tw, pad + w * vx - tw / 2))
            br = QRectF(bx, 0, tw, 15)
            p.setBrush(QColor(20, 20, 26, 230))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(br, 7.5, 7.5)
            p.setPen(QColor(255, 255, 255))
            p.drawText(br, Qt.AlignCenter, txt)


class VSlider(QWidget):
    """Vertical EQ fader with value read-out."""
    valueChanged = Signal(float)

    def __init__(self, label, lo=-12.0, hi=12.0, value=0.0, parent=None):
        super().__init__(parent)
        self.label, self.lo, self.hi, self.v = label, lo, hi, value
        self.drag = False
        self.h = 0.0
        self._ha = Tween(self, "h", 160)
        self.setFixedWidth(44)
        self.setMinimumHeight(190)
        self.setCursor(Qt.PointingHandCursor)

    def setValue(self, v):
        self.v = max(self.lo, min(self.hi, v))
        self.update()

    def enterEvent(self, e):
        self._ha.go(1)

    def leaveEvent(self, e):
        self._ha.go(0)

    def _area(self):
        return QRectF(0, 22, self.width(), self.height() - 50)

    def _set_y(self, y):
        a = self._area()
        t = 1 - max(0.0, min(1.0, (y - a.top()) / a.height()))
        v = self.lo + t * (self.hi - self.lo)
        v = round(v * 2) / 2
        if v != self.v:
            self.v = v
            self.valueChanged.emit(v)
        self.update()

    def mousePressEvent(self, e):
        self.drag = True
        self._set_y(e.position().y())

    def mouseMoveEvent(self, e):
        if self.drag:
            self._set_y(e.position().y())

    def mouseReleaseEvent(self, e):
        self.drag = False

    def mouseDoubleClickEvent(self, e):
        self.v = 0.0
        self.valueChanged.emit(0.0)
        self.update()

    def wheelEvent(self, e):
        self.v = max(self.lo, min(self.hi, self.v + (0.5 if e.angleDelta().y() > 0 else -0.5)))
        self.valueChanged.emit(self.v)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        a = self._area()
        cx = self.width() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(QRectF(cx - 2.5, a.top(), 5, a.height()), 2.5, 2.5)
        t = (self.v - self.lo) / (self.hi - self.lo)
        y = a.bottom() - t * a.height()
        y0 = a.bottom() - 0.5 * a.height()
        top, bot = min(y, y0), max(y, y0)
        g = QLinearGradient(0, a.top(), 0, a.bottom())
        g.setColorAt(0, th.accent.lighter(115))
        g.setColorAt(1, th.acc(120))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(cx - 2.5, top, 5, max(2, bot - top)), 2.5, 2.5)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(QPointF(cx - 9, y0), QPointF(cx + 9, y0))
        kr = 7 + 1.5 * self.h
        glow = QRadialGradient(QPointF(cx, y), kr * 2.4)
        glow.setColorAt(0, th.acc(80))
        glow.setColorAt(1, th.acc(0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, y), kr * 2.4, kr * 2.4)
        p.setBrush(QColor(250, 250, 252))
        p.drawRoundedRect(QRectF(cx - kr * 1.3, y - kr * 0.6, kr * 2.6, kr * 1.2), kr * 0.6, kr * 0.6)
        p.setFont(font(8, QFont.DemiBold))
        p.setPen(QColor(255, 255, 255, 220 if (self.drag or self.h > 0.5) else 130))
        p.drawText(QRectF(0, 0, self.width(), 18), Qt.AlignCenter, f"{self.v:+.1f}")
        p.setPen(QColor(255, 255, 255, 120))
        p.setFont(font(8, QFont.Medium))
        p.drawText(QRectF(0, self.height() - 22, self.width(), 20), Qt.AlignCenter, self.label)


class Toggle(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.k = 1.0 if checked else 0.0
        self._a = Tween(self, "k", 200, QEasingCurve.OutBack)
        self.toggled.connect(lambda on: self._a.go(1 if on else 0))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = QColor(255, 255, 255, 30)
        on = th.acc(235)
        c = QColor(int(off.red() + (on.red() - off.red()) * self.k), int(off.green() + (on.green() - off.green()) * self.k),
                   int(off.blue() + (on.blue() - off.blue()) * self.k), int(off.alpha() + (on.alpha() - off.alpha()) * self.k))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(c)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * max(0, min(1.05, self.k))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QRectF(x, r.top() + 4, d, d))
        p.setBrush(QColor(255, 255, 255) if self.k > 0.5 else QColor(220, 220, 228))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options, current=None, parent=None, height=32):
        super().__init__(parent)
        self.opts = list(options)  # list of (key, label)
        self.cur = current or self.opts[0][0]
        self.x = 0.0
        self._a = Tween(self, "x", 260, QEasingCurve.OutCubic)
        self.setFixedHeight(height)
        self.setCursor(Qt.PointingHandCursor)
        f = font(9, QFont.DemiBold)
        self.setFont(f)
        fm = QFontMetrics(f)
        self.setMinimumWidth(sum(fm.horizontalAdvance(l) + 30 for _, l in self.opts) + 8)
        self.x = float(self._idx(self.cur))

    def _idx(self, key):
        for i, (k, _) in enumerate(self.opts):
            if k == key:
                return i
        return 0

    def set_current(self, key, emit=False):
        self.cur = key
        self._a.go(self._idx(key))
        if emit:
            self.changed.emit(key)

    def mousePressEvent(self, e):
        n = len(self.opts)
        i = int(e.position().x() / (self.width() / n))
        i = max(0, min(n - 1, i))
        k = self.opts[i][0]
        if k != self.cur:
            self.set_current(k, True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        n = len(self.opts)
        sw = (r.width() - 6) / n
        sr = QRectF(r.left() + 3 + sw * self.x, r.top() + 3, sw, r.height() - 6)
        g = QLinearGradient(sr.topLeft(), sr.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255, 46))
        g.setColorAt(1, QColor(255, 255, 255, 22))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRoundedRect(sr, sr.height() / 2, sr.height() / 2)
        p.setFont(self.font())
        for i, (k, l) in enumerate(self.opts):
            on = abs(self.x - i) < 0.5
            p.setPen(QColor(255, 255, 255, 245 if on else 140))
            p.drawText(QRectF(r.left() + 3 + sw * i, r.top(), sw, r.height()), Qt.AlignCenter, l)


# ════════════════════════════════════════════════════════════════════ text inputs & labels
class SearchField(QLineEdit):
    def __init__(self, placeholder="Search", parent=None, hint="Ctrl K"):
        super().__init__(parent)
        self.hint = hint
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(36)
        self.setFont(font(9.5))
        self.setTextMargins(34, 0, 60 if hint else 12, 0)
        self.setStyleSheet("QLineEdit{background:transparent;border:none;color:#f2f2f6;"
                           "selection-background-color:rgba(255,255,255,60);}")
        self.f = 0.0
        self._fa = Tween(self, "f", 200)

    def focusInEvent(self, e):
        self._fa.go(1)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._fa.go(0)
        super().focusOutEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(0, 0, 0, int(70 + 40 * self.f)))
        p.setPen(QPen(th.acc(int(40 + 120 * self.f)) if self.f > 0.05 else QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        icons.draw(p, "search", QRectF(12, (self.height() - 16) / 2, 16, 16), QColor(255, 255, 255, 150))
        if self.hint and not self.text():
            f = font(7.5, QFont.DemiBold)
            p.setFont(f)
            tw = QFontMetrics(f).horizontalAdvance(self.hint) + 12
            hr = QRectF(self.width() - tw - 9, (self.height() - 18) / 2, tw, 18)
            p.setPen(QPen(QColor(255, 255, 255, 34), 1))
            p.setBrush(QColor(255, 255, 255, 10))
            p.drawRoundedRect(hr, 5, 5)
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(hr, Qt.AlignCenter, self.hint)
        p.end()
        super().paintEvent(e)


class TextField(QLineEdit):
    def __init__(self, text="", placeholder="", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(34)
        self.setFont(font(9.5))


def label(text, size=10, weight=QFont.Normal, alpha=255, spacing=0.0, wrap=False, parent=None):
    l = QLabel(text, parent)
    l.setFont(font(size, weight, spacing))
    l.setStyleSheet(f"color: rgba(255,255,255,{alpha}); background: transparent;")
    l.setWordWrap(wrap)
    return l


class Caption(QLabel):
    """Section caption — Umbra's mono 'instrument label' with the crescent mark."""

    def __init__(self, text, parent=None, mark=False):
        super().__init__(text.upper(), parent)
        self.mark = mark
        self.setFont(font(7.4, QFont.DemiBold, 1.8, mono=True))
        self.setStyleSheet("color: rgba(255,255,255,120); background: transparent;")
        if mark:
            self.setContentsMargins(15, 0, 0, 0)

    def setText(self, t):
        super().setText((t or "").upper())

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.mark:
            p = QPainter(self)
            paint_crescent(p, QPointF(4.5, self.height() / 2), 4.2, theme().acc(230))


class Marquee(QWidget):
    """Single-line label that gently scrolls when text overflows."""

    def __init__(self, text="", size=10.5, weight=QFont.DemiBold, alpha=255, parent=None):
        super().__init__(parent)
        self.text = text
        self.alpha = alpha
        self.setFont(font(size, weight))
        self.off = 0.0
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._wait = 0
        self.setFixedHeight(QFontMetrics(self.font()).height() + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setText(self, t):
        self.text = t or ""
        self.off = 0
        self._wait = 60
        self._check()
        self.update()

    def resizeEvent(self, e):
        self._check()

    def _check(self):
        over = QFontMetrics(self.font()).horizontalAdvance(self.text) > self.width()
        if over and settings()["animations"]:
            if not self._t.isActive():
                self._t.start(30)
        else:
            self._t.stop()
            self.off = 0

    def _tick(self):
        if self._wait > 0:
            self._wait -= 1
            return
        tw = QFontMetrics(self.font()).horizontalAdvance(self.text) + 40
        self.off += 0.6
        if self.off >= tw:
            self.off = 0
            self._wait = 80
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font())
        p.setPen(QColor(255, 255, 255, self.alpha))
        fm = QFontMetrics(self.font())
        tw = fm.horizontalAdvance(self.text)
        if tw <= self.width():
            p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, self.text)
            return
        # render into an offscreen transparent buffer, fade its edges, then composite —
        # fading directly on the widget would erase the window behind it (black bars).
        dpr = self.devicePixelRatioF()
        buf = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        buf.setDevicePixelRatio(dpr)
        buf.fill(Qt.transparent)
        q = QPainter(buf)
        q.setRenderHint(QPainter.TextAntialiasing)
        q.setFont(self.font())
        q.setPen(QColor(255, 255, 255, self.alpha))
        q.drawText(QRectF(-self.off, 0, tw + 2, self.height()), Qt.AlignVCenter, self.text)
        q.drawText(QRectF(-self.off + tw + 40, 0, tw + 2, self.height()), Qt.AlignVCenter, self.text)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        g = QLinearGradient(0, 0, self.width(), 0)
        f = min(0.2, 16 / max(1, self.width()))
        g.setColorAt(0, QColor(0, 0, 0, 0 if self.off > 0 else 255))
        g.setColorAt(f, QColor(0, 0, 0, 255))
        g.setColorAt(1 - f, QColor(0, 0, 0, 255))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        q.fillRect(QRectF(0, 0, self.width(), self.height()), g)
        q.end()
        p.drawPixmap(0, 0, buf)


class Badge(QWidget):
    def __init__(self, text="", accent=False, parent=None):
        super().__init__(parent)
        self.text = text
        self.accent = accent
        self.setFont(font(7, QFont.Bold, 0.8))
        self._fit()

    def setText(self, t, accent=None):
        self.text = t
        if accent is not None:
            self.accent = accent
        self._fit()
        self.update()

    def _fit(self):
        w = QFontMetrics(self.font()).horizontalAdvance(self.text) + 14 if self.text else 0
        self.setFixedSize(w, 18)

    def paintEvent(self, _):
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.accent:
            p.setPen(QPen(th.acc(150), 1))
            p.setBrush(th.acc(36))
            fg = th.accent.lighter(110)
        else:
            p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            p.setBrush(QColor(255, 255, 255, 12))
            fg = QColor(255, 255, 255, 190)
        p.drawRoundedRect(r, 5, 5)
        p.setFont(self.font())
        p.setPen(fg)
        p.drawText(r, Qt.AlignCenter, self.text)


# ════════════════════════════════════════════════════════════════════ animated stack
class FadeStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None

    def show_widget(self, w):
        if w is self.currentWidget():
            return
        if self.indexOf(w) < 0:
            self.addWidget(w)
        self.setCurrentWidget(w)
        ms = anim_ms(260)
        if ms == 0:
            return
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(ms)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        pos = QPropertyAnimation(w, b"pos", w)
        pos.setDuration(ms)
        pos.setStartValue(QPoint(0, 14))
        pos.setEndValue(QPoint(0, 0))
        pos.setEasingCurve(QEasingCurve.OutCubic)
        grp = QParallelAnimationGroup(w)
        grp.addAnimation(a)
        grp.addAnimation(pos)
        grp.finished.connect(lambda: w.setGraphicsEffect(None))
        grp.start()
        self._anim = grp


# ════════════════════════════════════════════════════════════════════ toast
class Toast(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text = ""
        self.icon = "check"
        self.o = 0.0
        self._a = Tween(self, "o", 240)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(lambda: self._a.go(0, 400))
        self.setFont(font(9.5, QFont.Medium))
        self.hide()

    def show_msg(self, text, icon="check", ms=2600):
        self.text, self.icon = text, icon
        fm = QFontMetrics(self.font())
        w = fm.horizontalAdvance(text) + 62
        par = self.parentWidget()
        self.setGeometry((par.width() - w) // 2, par.height() - 160, w, 44)
        self.show()
        self.raise_()
        self._a.go(1)
        self._hide.start(ms)

    def paintEvent(self, _):
        if self.o <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self.o)
        p.translate(0, (1 - self.o) * 10)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(QColor(22, 22, 28, 235))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        th = theme()
        p.setPen(Qt.NoPen)
        p.setBrush(th.acc(40))
        p.drawEllipse(QRectF(10, 9, 26, 26).adjusted(0, -1, 0, -1))
        icons.draw(p, self.icon, QRectF(16, 14, 14, 14).adjusted(0, -1, 0, -1), th.accent)
        p.setPen(QColor(255, 255, 255, 235))
        p.setFont(self.font())
        p.drawText(QRectF(44, 0, r.width() - 44, r.height() + 2), Qt.AlignVCenter, self.text)


# ════════════════════════════════════════════════════════════════════ menu
def glass_menu(parent=None):
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    return m


# ════════════════════════════════════════════════════════════════════ dialogs
class GlassDialog(QDialog):
    def __init__(self, parent=None, title="", width=560, height=420):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(width, height)
        self._drag = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(12)
        top = QHBoxLayout()
        self.title = label(title, 13, QFont.DemiBold)
        top.addWidget(self.title)
        top.addStretch()
        x = IconButton("close", 30, 16, "Close")
        x.clicked.connect(self.reject)
        top.addWidget(x)
        root.addLayout(top)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)
        theme().changed.connect(self.update)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 50:
            self.windowHandle().startSystemMove()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = theme()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = rr_path(r, 20)
        p.setClipPath(path)
        th.paint_backdrop(p, r, 0, False)
        p.fillRect(r, QColor(10, 10, 14, 120))
        p.setClipping(False)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(255, 255, 255, 70))
        g.setColorAt(0.4, QColor(255, 255, 255, 14))
        g.setColorAt(1, th.acc(50))
        p.setPen(QPen(QBrush(g), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 20, 20)


def ask_text(parent, title, prompt, default=""):
    d = GlassDialog(parent, title, 440, 200)
    d.body.addWidget(label(prompt, 9.5, alpha=170))
    f = TextField(default)
    d.body.addWidget(f)
    d.body.addStretch()
    row = QHBoxLayout()
    row.addStretch()
    c = PillButton("Cancel")
    ok = PillButton("Save", "check", primary=True)
    c.clicked.connect(d.reject)
    ok.clicked.connect(d.accept)
    f.returnPressed.connect(d.accept)
    row.addWidget(c)
    row.addWidget(ok)
    d.body.addLayout(row)
    f.setFocus()
    f.selectAll()
    if d.exec() == QDialog.Accepted and f.text().strip():
        return f.text().strip()
    return None


def confirm(parent, title, text, ok_text="Confirm"):
    d = GlassDialog(parent, title, 440, 210)
    d.body.addWidget(label(text, 9.5, alpha=190, wrap=True))
    d.body.addStretch()
    row = QHBoxLayout()
    row.addStretch()
    c = PillButton("Cancel")
    ok = PillButton(ok_text, primary=True)
    c.clicked.connect(d.reject)
    ok.clicked.connect(d.accept)
    row.addWidget(c)
    row.addWidget(ok)
    d.body.addLayout(row)
    return d.exec() == QDialog.Accepted


# ════════════════════════════════════════════════════════════════════ global stylesheet
def stylesheet():
    th = theme()
    a = th.accent
    acc = f"rgba({a.red()},{a.green()},{a.blue()},"
    return f"""
    * {{ outline: none; }}
    QWidget {{ color: #f3f3f7; }}
    QToolTip {{ background: rgba(18,18,24,240); color: #f3f3f7; border: 1px solid rgba(255,255,255,40);
               border-radius: 8px; padding: 5px 9px; }}
    QScrollArea, QScrollArea > QWidget > QWidget, QAbstractScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,38); border-radius: 3px; min-height: 40px; margin: 0 2px; }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,80); margin: 0 1px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
    QScrollBar::handle:horizontal {{ background: rgba(255,255,255,38); border-radius: 3px; min-width: 40px; margin: 2px 0; }}
    QScrollBar::handle:horizontal:hover {{ background: rgba(255,255,255,80); }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
        background: rgba(0,0,0,70); border: 1px solid rgba(255,255,255,30); border-radius: 10px;
        padding: 4px 10px; color: #f3f3f7; selection-background-color: {acc}110); }}
    QTextEdit, QPlainTextEdit {{ padding: 8px; }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 1px solid {acc}170); background: rgba(0,0,0,100); }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QComboBox {{ background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,34); border-radius: 10px;
                 padding: 6px 12px; min-height: 20px; color: #f3f3f7; }}
    QComboBox:hover {{ background: rgba(255,255,255,22); }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: rgb(20,20,26); border: 1px solid rgba(255,255,255,40); border-radius: 10px;
                 padding: 4px; selection-background-color: rgba(255,255,255,26); color: #f3f3f7; }}
    QMenu {{ background: rgba(18,18,24,246); border: 1px solid rgba(255,255,255,38); border-radius: 12px; padding: 6px; }}
    QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 8px; color: rgba(255,255,255,220); }}
    QMenu::item:selected {{ background: rgba(255,255,255,22); color: white; }}
    QMenu::item:disabled {{ color: rgba(255,255,255,80); }}
    QMenu::separator {{ height: 1px; background: rgba(255,255,255,24); margin: 5px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}
    QTabBar::tab {{ background: transparent; color: rgba(255,255,255,140); padding: 8px 14px; border: none;
                   border-bottom: 2px solid transparent; font-weight: 600; }}
    QTabBar::tab:selected {{ color: white; border-bottom: 2px solid {acc}255); }}
    QTabWidget::pane {{ border: none; }}
    QHeaderView::section {{ background: transparent; color: rgba(255,255,255,110); border: none; padding: 6px 4px;
                   font-weight: 700; font-size: 8pt; letter-spacing: 1px; }}
    QTableView, QListView, QTreeView {{ background: transparent; border: none; selection-background-color: transparent; }}
    QCheckBox {{ spacing: 8px; }}
    """
