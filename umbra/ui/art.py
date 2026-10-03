"""Asynchronous artwork provider with memory LRU + disk thumbnail cache."""
import hashlib
import urllib.request
from collections import OrderedDict

from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap)

from ..config import cache_dir, settings
from ..library.tags import find_folder_art, get_embedded_art
from ..theme import hash_color
from . import icons


def art_key(t: dict) -> str:
    if t.get("source", "local") != "local":
        return "u:" + (t.get("thumb") or t.get("path") or "")
    album = (t.get("album") or "").strip().lower()
    if album:
        aa = (t.get("albumartist") or t.get("aa") or t.get("artist") or "").strip().lower()
        return f"a:{aa}\x1f{album}"
    return "p:" + (t.get("path") or "")


class _Sig(QObject):
    done = Signal(str, object)


class _Job(QRunnable):
    def __init__(self, key, path, thumb, sig):
        super().__init__()
        self.key, self.path, self.thumb, self.sig = key, path, thumb, sig

    def run(self):
        img = None
        disk = cache_dir("art") / (hashlib.md5(self.key.encode()).hexdigest() + ".jpg")
        miss = disk.with_suffix(".none")
        try:
            if disk.exists():
                img = QImage(str(disk))
            elif not miss.exists():
                data = None
                if self.thumb and self.thumb.startswith("http"):
                    req = urllib.request.Request(self.thumb, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = r.read()
                elif self.path:
                    data = get_embedded_art(self.path) or find_folder_art(self.path, settings()["folder_art_names"])
                if data:
                    img = QImage.fromData(data)
                    if not img.isNull():
                        if self.thumb:   # crop youtube 16:9 thumbs to square
                            s = min(img.width(), img.height())
                            img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
                        img = img.scaled(640, 640, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        img.save(str(disk), "JPG", 92)
                if img is None or img.isNull():
                    img = None
                    miss.touch()
        except Exception:
            img = None
        self.sig.done.emit(self.key, img)


class ArtProvider(QObject):
    ready = Signal(str)

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self.images = OrderedDict()   # key -> QImage | None
        self.pix = OrderedDict()      # (key,size,radius) -> QPixmap
        self.pending = set()
        self._sig = _Sig()
        self._sig.done.connect(self._done)

    def _done(self, key, img):
        self.pending.discard(key)
        self.images[key] = img
        while len(self.images) > 400:
            self.images.popitem(last=False)
        self.ready.emit(key)

    def image(self, t, sync=False):
        key = art_key(t)
        if key in self.images:
            return self.images[key]
        if sync:
            job = _Job(key, t.get("path") if t.get("source", "local") == "local" else None, t.get("thumb"), _Sig())
            res = {}
            job.sig.done.connect(lambda k, i: res.setdefault("img", i), Qt.DirectConnection)
            job.run()
            self.images[key] = res.get("img")
            return self.images[key]
        if key not in self.pending:
            self.pending.add(key)
            self.pool.start(_Job(key, t.get("path") if t.get("source", "local") == "local" else None, t.get("thumb"), self._sig))
        return None

    def get(self, t, size, radius=10, dpr=2.0):
        """Rounded, scaled pixmap or a generated placeholder (never None)."""
        key = art_key(t)
        ck = (key, size, radius)
        if ck in self.pix:
            self.pix.move_to_end(ck)
            return self.pix[ck]
        img = self.image(t)
        if img is None:
            if key in self.images:   # known: no art
                pm = placeholder(t, size, radius, dpr)
                self._store(ck, pm)
                return pm
            return placeholder(t, size, radius, dpr)
        pm = rounded(img, size, radius, dpr)
        self._store(ck, pm)
        return pm

    def _store(self, ck, pm):
        self.pix[ck] = pm
        while len(self.pix) > 900:
            self.pix.popitem(last=False)

    def invalidate(self, t):
        key = art_key(t)
        self.images.pop(key, None)
        for k in [k for k in self.pix if k[0] == key]:
            self.pix.pop(k, None)
        disk = cache_dir("art") / (hashlib.md5(key.encode()).hexdigest() + ".jpg")
        for p in (disk, disk.with_suffix(".none")):
            try:
                p.unlink()
            except Exception:
                pass


def rounded(img: QImage, size, radius, dpr=2.0):
    s = int(size * dpr)
    sc = img.scaled(s, s, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    pm = QPixmap(s, s)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, s, s), radius * dpr, radius * dpr)
    p.setClipPath(path)
    p.drawImage(QRectF(0, 0, s, s), sc, QRectF((sc.width() - s) / 2, (sc.height() - s) / 2, s, s))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def placeholder(t, size, radius=10, dpr=2.0):
    s = int(size * dpr)
    pm = QPixmap(s, s)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, s, s), radius * dpr, radius * dpr)
    base = hash_color(t.get("album") or t.get("title") or "", 0.18, 0.16)
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, base.lighter(150))
    g.setColorAt(1, QColor(12, 12, 15))
    p.fillPath(path, g)
    p.setClipPath(path)
    # concentric "grooves"
    p.setPen(QColor(255, 255, 255, 14))
    for i in range(1, 6):
        r = s * (0.18 + i * 0.07)
        p.drawEllipse(QRectF(s * 0.62 - r / 2, s * 0.62 - r / 2, r, r))
    icons.draw(p, "songs", QRectF(s * 0.32, s * 0.32, s * 0.36, s * 0.36), QColor(255, 255, 255, 70), 1.3)
    p.setPen(QColor(255, 255, 255, 25))
    p.drawPath(path)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


_provider = None


def provider() -> ArtProvider:
    global _provider
    if _provider is None:
        _provider = ArtProvider()
    return _provider
