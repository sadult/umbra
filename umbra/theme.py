"""Theme engine: presets, adaptive accent (artwork / Windows / wallpaper) and the shared backdrop."""
import colorsys
import hashlib
import random

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient

from . import winsys

PRESETS = {
    "Obsidian": {"accent": "#E9E9EE", "bg": "#060608", "tint": "#121216", "desc": "Pure monochrome. Silver on black."},
    "Eclipse":  {"accent": "#FFB866", "bg": "#070605", "tint": "#15110D", "desc": "Warm corona light on charcoal."},
    "Glacier":  {"accent": "#86CFFF", "bg": "#04070A", "tint": "#0D131A", "desc": "Cold, crisp, arctic blue."},
    "Nebula":   {"accent": "#B79BFF", "bg": "#06050A", "tint": "#120F1B", "desc": "Deep space violet."},
    "Verdant":  {"accent": "#7DE8C0", "bg": "#040806", "tint": "#0C1511", "desc": "Phosphor green terminal."},
    "Ember":    {"accent": "#FF6B7F", "bg": "#090506", "tint": "#170D10", "desc": "Low-light crimson."},
    "Sand":     {"accent": "#E8D3B0", "bg": "#080706", "tint": "#15130F", "desc": "Muted parchment & graphite."},
}

TEXT = QColor(244, 244, 248)


def _vivid(colors):
    best, score = None, -1
    for c in colors:
        h, s, v = c.hsvHueF(), c.hsvSaturationF(), c.valueF()
        sc = s * 1.2 + v * 0.6 - abs(v - 0.7) * 0.4
        if sc > score:
            best, score = c, sc
    return best


def palette_from_image(img: QImage, n=4):
    """Fast dominant-colour extraction (hue buckets weighted by chroma)."""
    if img is None or img.isNull():
        return []
    small = img.scaled(40, 40, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB32)
    buckets = {}
    for y in range(small.height()):
        for x in range(small.width()):
            c = QColor(small.pixel(x, y))
            h, s, v = c.hsvHueF(), c.hsvSaturationF(), c.valueF()
            if h < 0:
                h = 0
            key = (int(h * 12) if s > 0.18 else 12 + int(v * 3))
            w = 0.25 + s * v * 2
            b = buckets.setdefault(key, [0.0, 0.0, 0.0, 0.0])
            b[0] += c.redF() * w
            b[1] += c.greenF() * w
            b[2] += c.blueF() * w
            b[3] += w
    cols = sorted(buckets.values(), key=lambda b: -b[3])
    out = []
    for r, g, b, w in cols[:n + 2]:
        out.append(QColor.fromRgbF(r / w, g / w, b / w))
    return out[:n]


def accent_from(color: QColor):
    """Normalise a colour so it reads as a refined accent on near-black."""
    h, s, l = color.hslHueF(), color.hslSaturationF(), color.lightnessF()
    if h < 0:
        return QColor(232, 232, 238)
    s = min(max(s, 0.35), 0.85)
    l = min(max(l, 0.66), 0.80)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return QColor.fromRgbF(r, g, b)


def blur_image(img: QImage, passes=3, size=48):
    """Cheap, smooth gaussian-like blur by iterative down/up-scaling."""
    if img is None or img.isNull():
        return img
    w, h = img.width(), img.height()
    cur = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    for i in range(passes):
        s = max(6, int(size / (i + 1) ** 0.6))
        cur = cur.scaled(s, max(4, int(s * h / max(1, w))), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        cur = cur.scaled(w // 4 or 1, h // 4 or 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return cur.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def noise_tile(size=128, alpha=16):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    rnd = random.Random(7)
    for y in range(size):
        for x in range(size):
            v = rnd.randint(0, 255)
            a = rnd.randint(0, alpha)
            img.setPixelColor(x, y, QColor(v, v, v, a))
    return QPixmap.fromImage(img)


def dot_tile(step=22, alpha=11):
    pm = QPixmap(step, step)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, alpha))
    p.drawEllipse(QPointF(step / 2, step / 2), 0.8, 0.8)
    p.end()
    return pm


def hash_color(text: str, sat=0.25, light=0.32):
    h = int(hashlib.md5((text or "?").encode()).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hls_to_rgb(h, light, sat)
    return QColor.fromRgbF(r, g, b)


class Theme(QObject):
    changed = Signal()
    backdropChanged = Signal()

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.art_image = None
        self.art_palette = []
        self.wall_image = None
        self.backdrop = None      # QPixmap blurred source (unscaled, small)
        self.frost = None
        self.grain = noise_tile()
        self.dots = dot_tile()
        self.aurora = [QColor(80, 80, 100), QColor(40, 40, 60), QColor(60, 50, 80)]
        self.apply()
        settings.changed.connect(self._on_setting)

    # colours
    @property
    def text(self):
        return TEXT

    def sub(self, a=150):
        return QColor(255, 255, 255, a)

    def acc(self, a=255):
        c = QColor(self.accent)
        c.setAlpha(a)
        return c

    def _on_setting(self, key, _v):
        if key in ("theme", "accent_source", "custom_accent", "backdrop", "backdrop_blur", "glass_opacity",
                   "backdrop_dim", "radius", "grain"):
            self.apply()

    def apply(self):
        p = PRESETS.get(self.s["theme"], PRESETS["Obsidian"])
        self.bg = QColor(p["bg"])
        self.tint = QColor(p["tint"])
        src = self.s["accent_source"]
        acc = QColor(p["accent"])
        if src == "custom":
            acc = QColor(self.s["custom_accent"])
        elif src == "windows":
            w = winsys.accent_color()
            if w:
                acc = accent_from(QColor(w))
        elif src == "wallpaper":
            self._load_wall()
            pal = palette_from_image(self.wall_image)
            if pal:
                acc = accent_from(_vivid(pal))
        elif src == "artwork" and self.art_palette:
            acc = accent_from(_vivid(self.art_palette))
        self.accent = acc
        self.radius = int(self.s["radius"])
        self.glass = float(self.s["glass_opacity"])
        self._rebuild_backdrop()
        self.changed.emit()

    def _load_wall(self):
        if self.wall_image is None:
            p = winsys.wallpaper_path()
            if p:
                img = QImage(p)
                if not img.isNull():
                    self.wall_image = img.scaled(640, 360, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    def set_artwork(self, img: QImage | None):
        self.art_image = img if img is not None and not img.isNull() else None
        self.art_palette = palette_from_image(self.art_image) if self.art_image else []
        if self.art_palette:
            cols = [accent_from(c) for c in self.art_palette[:3]]
            while len(cols) < 3:
                cols.append(cols[-1])
            self.aurora = cols
        self.apply()

    def _rebuild_backdrop(self):
        mode = self.s["backdrop"]
        src = None
        if mode == "artwork":
            src = self.art_image
        elif mode == "wallpaper":
            self._load_wall()
            src = self.wall_image
        if src is None:
            self.backdrop = None
            self.frost = None
        else:
            base = src.scaled(480, 300, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            passes = int(self.s["backdrop_blur"])
            self.backdrop = QPixmap.fromImage(blur_image(base, passes + 1, 40))
            self.frost = QPixmap.fromImage(blur_image(base, passes + 3, 18))
        self.backdropChanged.emit()

    # ── painting helpers
    def paint_backdrop(self, p: QPainter, rect: QRectF, t: float = 0.0, motion=True):
        """Paint the full-window atmosphere: blurred source, aurora, vignette, grain."""
        p.fillRect(rect, self.bg)
        if self.backdrop is not None:
            p.setOpacity(1.0)
            p.drawPixmap(rect, self.backdrop, QRectF(self.backdrop.rect()))
        import math
        w, h = rect.width(), rect.height()
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        dim = QColor(self.bg)
        dimv = float(self.s["backdrop_dim"])
        dim.setAlphaF(dimv if self.backdrop is not None else dimv * 0.5)
        p.fillRect(rect, dim)
        # vignette
        vg = QRadialGradient(rect.center(), max(w, h) * 0.75)
        vg.setColorAt(0.55, QColor(0, 0, 0, 0))
        vg.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.fillRect(rect, vg)
        # ── the Umbra eclipse: a dark disc hanging off the top-right, lit by a thin corona
        R = max(w, h) * 0.34
        breathe = 0.5 + 0.5 * math.sin(t * 0.35) if motion else 0.5
        c = QPointF(rect.right() - w * 0.12, rect.top() - R * 0.38)
        halo = QRadialGradient(c, R * 1.9)
        k = R / (R * 1.9)
        a0 = int((54 + 16 * breathe) * (1.45 - dimv))
        halo.setColorAt(0.0, self.acc(0))
        halo.setColorAt(k * 0.96, self.acc(0))
        halo.setColorAt(k, self.acc(a0))
        halo.setColorAt(k + 0.06, self.acc(int(a0 * 0.35)))
        halo.setColorAt(1.0, self.acc(0))
        p.setCompositionMode(QPainter.CompositionMode_Screen)
        p.fillRect(rect, halo)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        disc = QColor(self.bg)
        disc.setAlpha(235)
        p.setPen(Qt.NoPen)
        p.setBrush(disc)
        p.drawEllipse(c, R, R)
        # lit limb — brightest at lower-left, like light bending round the moon
        from PySide6.QtGui import QPen
        limb = QLinearGradient(QPointF(c.x() - R, c.y() + R), QPointF(c.x() + R * 0.4, c.y() - R * 0.2))
        limb.setColorAt(0, self.acc(150 + int(50 * breathe)))
        limb.setColorAt(0.55, self.acc(26))
        limb.setColorAt(1, self.acc(0))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(limb, 1.4))
        p.drawEllipse(c, R, R)
        # observatory dot field, fading toward the bottom
        p.save()
        p.setOpacity(0.9)
        p.drawTiledPixmap(rect, self.dots)
        p.restore()
        # top light leak
        lg = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        lg.setColorAt(0, QColor(255, 255, 255, 10))
        lg.setColorAt(0.3, QColor(255, 255, 255, 0))
        p.fillRect(rect, lg)
        if self.s["grain"]:
            p.drawTiledPixmap(rect, self.grain)


_theme = None


def theme():
    return _theme


def init_theme(settings):
    global _theme
    _theme = Theme(settings)
    return _theme
