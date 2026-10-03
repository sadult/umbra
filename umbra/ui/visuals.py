"""Visualizer, spectrum analyzer, audio analyzer card, synced lyrics, vinyl hero."""
import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QConicalGradient, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import icons
from .context import ctx
from .widgets import Tween, font


def _smooth_path(pts, close_y=None):
    path = QPainterPath()
    if not pts:
        return path
    if close_y is not None:
        path.moveTo(pts[0].x(), close_y)
        path.lineTo(pts[0])
    else:
        path.moveTo(pts[0])
    for i in range(1, len(pts)):
        p0 = pts[i - 2] if i > 1 else pts[i - 1]
        p1, p2 = pts[i - 1], pts[i]
        p3 = pts[i + 1] if i + 1 < len(pts) else p2
        c1 = p1 + (p2 - p0) / 6
        c2 = p2 - (p3 - p1) / 6
        path.cubicTo(c1, c2, p2)
    if close_y is not None:
        path.lineTo(pts[-1].x(), close_y)
        path.closeSubpath()
    return path


class Visualizer(QWidget):
    def __init__(self, parent=None, compact=False, style=None, bands=None):
        super().__init__(parent)
        self.compact = compact
        self.fixed_style = style
        self.bands = bands
        self.vals = np.zeros(8)
        self.peaks = np.zeros(8)
        self.ghost = np.zeros(8)
        self.t0 = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16 if not compact else 33)

    @property
    def style(self):
        return self.fixed_style or ctx.settings["visualizer_style"]

    def _n(self):
        if self.bands:
            return self.bands
        return int(ctx.settings["visualizer_bands"])

    def _tick(self):
        if not self.isVisible():
            return
        n = self._n()
        if len(self.vals) != n:
            self.vals = np.zeros(n)
            self.peaks = np.zeros(n)
            self.ghost = np.zeros(n)
        eng = ctx.player.engine
        if eng.state == "playing":
            target = eng.spectrum.compute(n)
        else:
            t = time.time() - self.t0
            x = np.linspace(0, 1, n)
            target = 0.05 + 0.035 * (np.sin(x * 9 + t * 1.4) * 0.5 + 0.5) * (1 - x * 0.6)
        up = target > self.vals
        self.vals = np.where(up, self.vals + (target - self.vals) * 0.55, self.vals + (target - self.vals) * 0.16)
        self.peaks = np.maximum(self.peaks - 0.008, self.vals)
        self.ghost += (self.vals - self.ghost) * 0.07
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        st = self.style
        r = QRectF(self.rect())
        if st == "mirror":
            self._mirror(p, r)
        elif st == "liquid":
            self._liquid(p, r)
        elif st == "radial":
            self._radial(p, r)
        elif st == "scope":
            self._scope(p, r)
        else:
            self._bars(p, r)

    def _grad(self, top, bottom, a1=255, a2=90):
        th = ctx.theme
        g = QLinearGradient(0, top, 0, bottom)
        g.setColorAt(0, QColor(255, 255, 255, a1))
        g.setColorAt(0.35, th.acc(a1))
        g.setColorAt(1, th.acc(a2))
        return g

    def _bars(self, p, r):
        n = len(self.vals)
        refl = 0 if self.compact else r.height() * 0.22
        base = r.bottom() - refl
        h = base - r.top() - 4
        gap = 2.0 if self.compact else max(2.0, r.width() / n * 0.28)
        bw = (r.width() - gap * (n - 1)) / n
        p.setPen(Qt.NoPen)
        p.setBrush(self._grad(r.top(), base))
        rad = min(bw / 2, 3.5)
        for i, v in enumerate(self.vals):
            bh = max(2.0, v * h)
            x = r.left() + i * (bw + gap)
            p.drawRoundedRect(QRectF(x, base - bh, bw, bh), rad, rad)
        if not self.compact:
            p.setBrush(QColor(255, 255, 255, 200))
            for i, v in enumerate(self.peaks):
                x = r.left() + i * (bw + gap)
                p.drawRoundedRect(QRectF(x, base - v * h - 5, bw, 2), 1, 1)
            # reflection
            p.setOpacity(0.16)
            g = QLinearGradient(0, base, 0, r.bottom())
            g.setColorAt(0, ctx.theme.acc(255))
            g.setColorAt(1, ctx.theme.acc(0))
            p.setBrush(g)
            for i, v in enumerate(self.vals):
                bh = max(1.0, v * refl * 1.4)
                x = r.left() + i * (bw + gap)
                p.drawRoundedRect(QRectF(x, base + 3, bw, bh), rad, rad)
            p.setOpacity(1)

    def _mirror(self, p, r):
        n = len(self.vals)
        cy = r.center().y()
        h = r.height() / 2 - 4
        gap = max(1.5, r.width() / n * 0.3)
        bw = (r.width() - gap * (n - 1)) / n
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        th = ctx.theme
        g.setColorAt(0, th.acc(40))
        g.setColorAt(0.5, QColor(255, 255, 255, 250))
        g.setColorAt(1, th.acc(40))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        for i, v in enumerate(self.vals):
            bh = max(1.5, v * h)
            x = r.left() + i * (bw + gap)
            p.drawRoundedRect(QRectF(x, cy - bh, bw, bh * 2), bw / 2, bw / 2)

    def _liquid(self, p, r):
        th = ctx.theme
        n = len(self.vals)
        h = r.height() - 6
        for layer, (arr, alpha) in enumerate(((self.ghost, 60), (self.vals, 255))):
            pts = [QPointF(r.left() + r.width() * i / (n - 1), r.bottom() - 2 - arr[i] * h * (1.05 if layer == 0 else 1))
                   for i in range(n)]
            path = _smooth_path(pts, r.bottom())
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0, th.acc(int(alpha * 0.55)))
            g.setColorAt(1, th.acc(0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawPath(path)
            line = _smooth_path(pts)
            p.setBrush(Qt.NoBrush)
            if layer == 1:
                p.setPen(QPen(th.acc(70), 6, Qt.SolidLine, Qt.RoundCap))
                p.drawPath(line)
                p.setPen(QPen(QColor(255, 255, 255, 235), 1.6, Qt.SolidLine, Qt.RoundCap))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            p.drawPath(line)

    def _radial(self, p, r):
        th = ctx.theme
        c = r.center()
        rad0 = min(r.width(), r.height()) * 0.22
        maxl = min(r.width(), r.height()) * 0.26
        n = len(self.vals)
        vals = np.concatenate([self.vals, self.vals[::-1]])
        m = len(vals)
        rot = (time.time() - self.t0) * 0.06
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, rad0 - 6, rad0 - 6)
        for i, v in enumerate(vals):
            a = rot + 2 * math.pi * i / m
            l = 2 + v * maxl
            x0, y0 = c.x() + math.cos(a) * rad0, c.y() + math.sin(a) * rad0
            x1, y1 = c.x() + math.cos(a) * (rad0 + l), c.y() + math.sin(a) * (rad0 + l)
            col = QColor(th.accent) if v < 0.6 else QColor(255, 255, 255)
            col.setAlpha(int(120 + 135 * min(1, v * 1.5)))
            p.setPen(QPen(col, max(1.5, 2 * math.pi * rad0 / m * 0.55), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        energy = float(np.mean(self.vals[: max(2, n // 6)]))
        g = QRadialGradient(c, rad0 - 8)
        g.setColorAt(0, th.acc(int(40 + 120 * energy)))
        g.setColorAt(1, th.acc(0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, rad0 - 8, rad0 - 8)

    def _scope(self, p, r):
        th = ctx.theme
        eng = ctx.player.engine
        w = eng.spectrum.waveform(1024).mean(axis=1) if eng.state == "playing" else np.zeros(1024)
        n = 160
        idx = np.linspace(0, len(w) - 1, n).astype(int)
        y = w[idx]
        cy = r.center().y()
        amp = r.height() * 0.45
        pts = [QPointF(r.left() + r.width() * i / (n - 1), cy - float(np.clip(y[i] * 2.2, -1, 1)) * amp) for i in range(n)]
        path = _smooth_path(pts)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(th.acc(50), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(th.acc(140), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 240), 1.3))
        p.drawPath(path)


class AnalyzerCard(QWidget):
    """foobar-grade read-out: format, peak, LUFS (M/S/I), DR, stereo VU, log spectrum."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spec = np.zeros(64)
        self.vu = np.array([-60.0, -60.0])
        self.vu_pk = np.array([-60.0, -60.0])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)
        self.setMinimumWidth(270)

    def _tick(self):
        if not self.isVisible():
            return
        eng = ctx.player.engine
        if eng.state == "playing":
            s = eng.spectrum.compute(64)
            rms, pk = eng.spectrum.levels()
        else:
            s = np.zeros(64)
            rms, pk = np.array([-60.0, -60.0]), np.array([-60.0, -60.0])
        self.spec = np.where(s > self.spec, s, self.spec * 0.88 + s * 0.12)
        rms = np.clip(rms, -60, 0)
        self.vu = np.where(rms > self.vu, self.vu + (rms - self.vu) * 0.5, self.vu + (rms - self.vu) * 0.15)
        self.vu_pk = np.maximum(self.vu_pk - 0.35, np.clip(pk, -60, 0))
        self.update()

    def _row(self, p, y, name, value, frac, w, sub=""):
        p.setFont(font(8.2, QFont.Medium))
        p.setPen(QColor(255, 255, 255, 140))
        p.drawText(QRectF(18, y, 90, 18), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setFont(font(9.5, QFont.DemiBold, mono=True))
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(18, y, w - 36, 18), Qt.AlignRight | Qt.AlignVCenter, value)
        if frac is not None:
            self._meter(p, QRectF(18, y + 22, w - 36, 5), frac)
        return y + (36 if frac is not None else 24)

    def _meter(self, p, r, frac, segments=26):
        th = ctx.theme
        frac = max(0.0, min(1.0, frac))
        sw = (r.width() - (segments - 1) * 2) / segments
        on = int(round(frac * segments))
        p.setPen(Qt.NoPen)
        for i in range(segments):
            col = th.acc(230) if i < on else QColor(255, 255, 255, 22)
            if i < on and i >= segments - 3:
                col = QColor(255, 255, 255, 240)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(r.left() + i * (sw + 2), r.top(), sw, r.height()), 1.5, 1.5)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        w = self.width()
        t = ctx.player.current or {}
        eng = ctx.player.engine
        fmt = eng.format or {}
        y = 16
        p.setFont(font(7.5, QFont.Bold, 1.6))
        p.setPen(QColor(255, 255, 255, 110))
        p.drawText(QRectF(18, y, w, 16), Qt.AlignLeft | Qt.AlignVCenter, "AUDIO ANALYZER")
        live = eng.state == "playing"
        p.setPen(Qt.NoPen)
        p.setBrush(th.accent if live else QColor(255, 255, 255, 60))
        p.drawEllipse(QPointF(w - 24, y + 8), 3.5, 3.5)
        y += 28
        codec = (t.get("codec") or "—").upper()
        if t.get("source", "local") != "local":
            codec = "STREAM"
        p.setFont(font(22, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 250))
        p.drawText(QRectF(18, y, w, 32), Qt.AlignLeft | Qt.AlignVCenter, codec)
        sr = fmt.get("samplerate") or t.get("samplerate") or 0
        bits = fmt.get("bits") or t.get("bitdepth") or 0
        spec_txt = f"{bits}-bit / {sr / 1000:g} kHz" if bits else (f"{t.get('bitrate') or '—'} kbps · {sr / 1000:g} kHz" if sr else "—")
        p.setFont(font(10, QFont.DemiBold))
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(18, y + 32, w, 20), Qt.AlignLeft | Qt.AlignVCenter, spec_txt)
        lossless = bool(t.get("lossless"))
        tag = "LOSSLESS" if lossless else "LOSSY"
        if lossless and (bits > 16 or sr > 48000):
            tag = "HI-RES LOSSLESS"
        bf = font(7, QFont.Bold, 1)
        bw = QFontMetrics(bf).horizontalAdvance(tag) + 14
        br = QRectF(18, y + 58, bw, 19)
        p.setPen(QPen(th.acc(160) if lossless else QColor(255, 255, 255, 60), 1))
        p.setBrush(th.acc(30) if lossless else Qt.NoBrush)
        p.drawRoundedRect(br, 6, 6)
        p.setFont(bf)
        p.setPen(th.accent if lossless else QColor(255, 255, 255, 150))
        p.drawText(br, Qt.AlignCenter, tag)
        out = fmt.get("device_rate")
        if out:
            p.setFont(font(7.8))
            p.setPen(QColor(255, 255, 255, 110))
            o = f"→ output {out / 1000:g} kHz" + (" · resampled" if fmt.get("resampled") else " · native")
            p.drawText(QRectF(br.right() + 10, br.top(), w - br.right() - 20, 19), Qt.AlignVCenter, o)
        y += 92
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawLine(18, int(y), w - 18, int(y))
        y += 12
        L = eng.loud
        peak = L.peak_db() if live else t.get("peak")
        if peak is None:
            peak = t.get("peak")
        integ = L.integrated() if live else None
        if integ is None:
            integ = t.get("lufs")
        dr = L.dr() if live else None
        if dr is None:
            dr = t.get("dr")
        y = self._row(p, y, "Peak", f"{peak:+.1f} dB" if peak is not None else "—",
                      None if peak is None else (peak + 30) / 30, w)
        y = self._row(p, y, "LUFS", f"{integ:.1f}" if integ is not None else "measuring…",
                      None if integ is None else (integ + 40) / 40, w)
        y = self._row(p, y, "Dynamic", f"{dr:.1f} DR" if dr is not None else "—",
                      None if dr is None else dr / 20, w)
        p.setFont(font(7.8, QFont.Medium, mono=True))
        p.setPen(QColor(255, 255, 255, 120))
        mom = f"M {L.momentary:5.1f}   S {L.short:5.1f}" if live else "M  —    S  —"
        p.drawText(QRectF(18, y - 6, w - 36, 16), Qt.AlignLeft | Qt.AlignVCenter, mom)
        lv = ctx.player._gain_for(t) if t else 1.0
        gdb = 20 * math.log10(lv) if lv > 0 else 0
        p.drawText(QRectF(18, y - 6, w - 36, 16), Qt.AlignRight | Qt.AlignVCenter, f"gain {gdb:+.1f} dB")
        y += 18
        # stereo VU
        for i, ch in enumerate("LR"):
            p.setFont(font(7.5, QFont.Bold))
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(QRectF(18, y, 12, 10), Qt.AlignVCenter, ch)
            mr = QRectF(34, y + 2, w - 52, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawRoundedRect(mr, 3, 3)
            f = (self.vu[i] + 60) / 60
            g = QLinearGradient(mr.topLeft(), mr.topRight())
            g.setColorAt(0, th.acc(120))
            g.setColorAt(0.8, th.accent)
            g.setColorAt(1, QColor(255, 255, 255))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(mr.left(), mr.top(), max(3, mr.width() * f), mr.height()), 3, 3)
            px = mr.left() + mr.width() * (self.vu_pk[i] + 60) / 60
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawRect(QRectF(px - 1, mr.top() - 1, 2, mr.height() + 2))
            y += 15
        y += 10
        # spectrum with log axis
        sh = max(60.0, self.height() - y - 34)
        sr_ = QRectF(18, y, w - 36, sh)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1, Qt.DashLine))
        for k in range(1, 4):
            yy = sr_.top() + sr_.height() * k / 4
            p.drawLine(QPointF(sr_.left(), yy), QPointF(sr_.right(), yy))
        for f in (100, 1000, 10000):
            xx = sr_.left() + sr_.width() * math.log10(f / 20) / math.log10(1000)
            p.drawLine(QPointF(xx, sr_.top()), QPointF(xx, sr_.bottom()))
        n = len(self.spec)
        bw = sr_.width() / n
        g = QLinearGradient(0, sr_.top(), 0, sr_.bottom())
        g.setColorAt(0, QColor(255, 255, 255, 240))
        g.setColorAt(0.4, th.acc(230))
        g.setColorAt(1, th.acc(60))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        for i, v in enumerate(self.spec):
            bh = max(1.5, v * sr_.height())
            p.drawRoundedRect(QRectF(sr_.left() + i * bw + 0.6, sr_.bottom() - bh, bw - 1.2, bh), 1, 1)
        p.setFont(font(7, QFont.Medium, mono=True))
        p.setPen(QColor(255, 255, 255, 100))
        ly = sr_.bottom() + 6
        for f, lab in ((20, "20Hz"), (100, "100"), (1000, "1k"), (5000, "5k"), (20000, "20k")):
            xx = sr_.left() + sr_.width() * math.log10(f / 20) / math.log10(1000)
            al = Qt.AlignLeft if f == 20 else (Qt.AlignRight if f == 20000 else Qt.AlignHCenter)
            rx = xx if f == 20 else (xx - 36 if f == 20000 else xx - 18)
            p.drawText(QRectF(rx, ly, 36, 14), al | Qt.AlignVCenter, lab)


class LyricsView(QWidget):
    """In-window synced lyrics with eased scrolling, depth fade and click-to-seek."""

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        self.show_source = not compact
        self.lyr = None
        self.state = "none"
        self.scroll = 0.0
        self.target = 0.0
        self.cur = -1
        self.manual_until = 0
        self.layout_cache = None
        self.hover_line = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self.glow = [0.0] * 0
        from .widgets import PillButton
        self.search_btn = PillButton("Search lyrics online", "search", primary=True, parent=self)
        self.search_btn.clicked.connect(self._search)
        self.search_btn.hide()

    def _search(self):
        from .lyrics_search import search_lyrics
        search_lyrics(self.window(), ctx.player.current)

    def _place_btn(self):
        show = self.state in ("none", "instrumental") and not self.compact and ctx.player.current is not None
        self.search_btn.setVisible(show)
        if show:
            c = self.rect().center()
            self.search_btn.move(int(c.x() - self.search_btn.width() / 2), int(c.y() + 58))

    def resizeEvent(self, e):
        self._place_btn()
        super().resizeEvent(e)

    def set_lyrics(self, lyr):
        self.lyr = lyr
        self.state = lyr.kind if lyr else "none"
        self._place_btn()
        self.cur = -1
        self.scroll = self.target = 0.0
        self.layout_cache = None
        self.update()

    def set_loading(self):
        self.lyr = None
        self.state = "loading"
        self._place_btn()
        self.layout_cache = None
        self.update()

    def _lines(self):
        if not self.lyr:
            return []
        if self.lyr.kind == "synced":
            return [l for _, l in self.lyr.synced]
        return self.lyr.plain.splitlines()

    def _font(self, big=False):
        sz = float(ctx.settings["lyrics_size"]) * (0.62 if self.compact else 1.0)
        if not self.compact:
            sz *= max(0.62, min(1.0, self.width() / 520))
        return font(sz, QFont.Bold)

    def _layout(self):
        w = self.width() - 48
        key = (w, self.state, id(self.lyr), ctx.settings["lyrics_size"])
        if self.layout_cache and self.layout_cache[0] == key:
            return self.layout_cache[1]
        fm = QFontMetrics(self._font())
        out, y = [], 0.0
        gap = fm.height() * (0.55 if self.lyr and self.lyr.kind == "synced" else 0.25)
        for line in self._lines():
            txt = line if line.strip() else "♪"
            br = fm.boundingRect(0, 0, int(w), 10000, Qt.TextWordWrap, txt)
            out.append((y, br.height(), txt))
            y += br.height() + gap
        self.layout_cache = (key, out)
        return out

    def _tick(self):
        if not self.isVisible() or not self.lyr:
            return
        L = self._layout()
        if not L:
            return
        if self.lyr.kind == "synced":
            pos = ctx.player.engine.position() + float(ctx.settings["lyrics_offset"])
            idx = -1
            for i, (t, _) in enumerate(self.lyr.synced):
                if t <= pos + 0.15:
                    idx = i
                else:
                    break
            if idx != self.cur:
                self.cur = idx
            if time.time() > self.manual_until and idx >= 0:
                y, h, _ = L[idx]
                self.target = y + h / 2 - self.height() * 0.38
        self.target = max(-self.height() * 0.38, min(self.target, (L[-1][0] + L[-1][1]) - self.height() * 0.3))
        d = self.target - self.scroll
        if abs(d) > 0.3:
            self.scroll += d * 0.12
        self.update()

    def wheelEvent(self, e):
        self.manual_until = time.time() + 3.5
        self.target -= e.angleDelta().y() * 0.8
        self.update()

    def mouseMoveEvent(self, e):
        L = self._layout()
        y = e.position().y() + self.scroll
        self.hover_line = next((i for i, (ly, lh, _) in enumerate(L) if ly - 6 <= y <= ly + lh + 6), -1)
        self.update()

    def leaveEvent(self, e):
        self.hover_line = -1

    def mouseReleaseEvent(self, e):
        if self.lyr and self.lyr.kind == "synced" and self.hover_line >= 0:
            ctx.player.seek(self.lyr.synced[self.hover_line][0])
            self.manual_until = 0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        th = ctx.theme
        if self.state in ("none", "loading", "instrumental") or not self.lyr:
            msg = {"loading": "Looking for lyrics…", "instrumental": "Instrumental",
                   "none": "No lyrics for this track"}.get(self.state, "")
            ic = {"loading": "lyrics", "instrumental": "wave", "none": "lyrics"}.get(self.state, "lyrics")
            c = self.rect().center()
            icons.draw(p, ic, QRectF(c.x() - 18, c.y() - 46, 36, 36), QColor(255, 255, 255, 60))
            p.setFont(font(13 if not self.compact else 10, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(QRectF(0, c.y() - 4, self.width(), 30), Qt.AlignCenter, msg)
            if self.state == "none" and not self.compact:
                p.setFont(font(8.5))
                p.setPen(QColor(255, 255, 255, 80))
                p.drawText(QRectF(0, c.y() + 26, self.width(), 20), Qt.AlignCenter,
                           "Search online below, add a .lrc file, or embed lyrics in the Tag Editor")
            return
        L = self._layout()
        f = self._font()
        p.setFont(f)
        synced = self.lyr.kind == "synced"
        H = self.height()
        al = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight}.get(ctx.settings["lyrics_align"], Qt.AlignLeft)
        for i, (y, h, txt) in enumerate(L):
            yy = y - self.scroll
            if yy + h < -40 or yy > H + 40:
                continue
            if synced:
                dist = abs(i - self.cur) if self.cur >= 0 else 3
                if i == self.cur:
                    col = QColor(255, 255, 255, 255)
                elif i < self.cur:
                    col = QColor(255, 255, 255, max(40, 110 - dist * 12))
                else:
                    col = QColor(255, 255, 255, max(45, 135 - dist * 14))
                if i == self.hover_line and i != self.cur:
                    col.setAlpha(min(255, col.alpha() + 70))
            else:
                col = QColor(255, 255, 255, 215)
            # edge fade
            edge = min(1.0, max(0.0, min(yy + h, H - yy) / (H * 0.18)))
            col.setAlpha(int(col.alpha() * edge))
            rect = QRectF(24, yy, self.width() - 48, h + 4)
            if synced and i == self.cur:
                p.setPen(th.acc(60))
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    p.drawText(rect.translated(dx * 1.2, dy * 1.2), al | Qt.TextWordWrap, txt)
            p.setPen(col)
            p.drawText(rect, al | Qt.TextWordWrap, txt)
        if self.show_source:
            p.setFont(font(7, QFont.Bold, 1.2))
            p.setPen(QColor(255, 255, 255, 80))
            src = f"{'SYNCED' if synced else 'PLAIN'} · {self.lyr.source.upper()}"
            p.drawText(QRectF(24, 6, self.width() - 48, 16), Qt.AlignRight | Qt.AlignVCenter, src)


class VinylHero(QWidget):
    """Cover art with a vinyl disc that slides out and spins while playing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.out = 0.0
        self.angle = 0.0
        self._oa = Tween(self, "out", 700)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self.setMinimumSize(140, 140)
        ctx.art.ready.connect(lambda _k: self.update())
        ctx.player.stateChanged.connect(self._state)
        ctx.player.trackChanged.connect(lambda _t: self.update())

    def _state(self, st):
        self._oa.go(1.0 if st == "playing" else 0.0)

    def _tick(self):
        if ctx.player.engine.state == "playing" and self.isVisible():
            self.angle = (self.angle + 0.9) % 360
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        th = ctx.theme
        t = ctx.player.current or {}
        s = min(self.height() - 20, (self.width() - 20) / 1.32)
        cx = (self.width() - s * (1 + 0.3 * self.out)) / 2
        cover = QRectF(cx, (self.height() - s) / 2, s, s)
        # glow
        gr = min(s * 0.85, self.height() / 2, cover.center().x())
        g = QRadialGradient(cover.center(), gr)
        g.setColorAt(0, th.acc(70))
        g.setColorAt(0.6, th.acc(22))
        g.setColorAt(1, th.acc(0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(cover.center(), gr, gr)
        # vinyl
        d = s * 0.94
        vc = QPointF(cover.center().x() + s * 0.30 * self.out, cover.center().y())
        if self.out > 0.01:
            p.setBrush(QColor(8, 8, 10))
            p.drawEllipse(vc, d / 2, d / 2)
            p.save()
            p.translate(vc)
            p.rotate(self.angle)
            cg = QConicalGradient(QPointF(0, 0), 0)
            for k, a in ((0, 0), (0.12, 38), (0.25, 0), (0.5, 0), (0.62, 38), (0.75, 0), (1, 0)):
                cg.setColorAt(k, QColor(255, 255, 255, a))
            p.setBrush(cg)
            p.drawEllipse(QPointF(0, 0), d / 2, d / 2)
            p.setBrush(Qt.NoBrush)
            for i in range(14):
                rr = d / 2 * (0.42 + i * 0.04)
                p.setPen(QPen(QColor(255, 255, 255, 10 if i % 3 else 18), 1))
                p.drawEllipse(QPointF(0, 0), rr, rr)
            lab = ctx.art.get(t, int(d * 0.36), int(d * 0.18))
            p.drawPixmap(QRectF(-d * 0.18, -d * 0.18, d * 0.36, d * 0.36).toRect(), lab)
            p.setBrush(QColor(6, 6, 8))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 0), 4, 4)
            p.restore()
        # cover shadow
        for i in range(16, 0, -2):
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(cover.adjusted(-i * .4, i * .5, i * .4, i * 1.2), 18, 18)
        pm = ctx.art.get(t, int(s), 18)
        p.drawPixmap(cover.toRect(), pm)
        rim = QLinearGradient(cover.topLeft(), cover.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 90))
        rim.setColorAt(0.4, QColor(255, 255, 255, 12))
        rim.setColorAt(1, QColor(255, 255, 255, 30))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(rim, 1))
        p.drawRoundedRect(cover.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        # specular sweep
        sheen = QLinearGradient(cover.topLeft(), QPointF(cover.left() + s * 0.6, cover.top() + s * 0.6))
        sheen.setColorAt(0, QColor(255, 255, 255, 34))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        path = QPainterPath()
        path.addRoundedRect(cover, 18, 18)
        p.fillPath(path, sheen)
