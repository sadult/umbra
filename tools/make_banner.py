"""Renders docs/cover.png (GitHub banner) and docs/social.png with Qt. Run: python tools/make_banner.py"""
import math, os, random, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient, QTransform)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACC = QColor(255, 178, 92)
FAM = ["Segoe UI Variable Display", "Segoe UI", "Noto Sans", "Inter", "Arial"]


def F(size, weight=QFont.Normal, spacing=0.0, mono=False):
    f = QFont()
    f.setFamilies(["Cascadia Mono", "Consolas", "Noto Sans Mono", "DejaVu Sans Mono"] if mono else FAM)
    f.setPixelSize(int(size))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def acc(a):
    c = QColor(ACC)
    c.setAlpha(int(a))
    return c


def backdrop(p, W, H, ec):
    p.fillRect(0, 0, W, H, QColor(9, 8, 8))
    g = QRadialGradient(ec, H * 1.4)
    g.setColorAt(0, QColor(40, 28, 18))
    g.setColorAt(1, QColor(9, 8, 8))
    p.fillRect(0, 0, W, H, g)
    rnd = random.Random(7)
    for _ in range(int(W * H / 2600)):
        x, y = rnd.random() * W, rnd.random() * H
        a = rnd.random() ** 3 * 150
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 236, 214, int(a)))
        r = rnd.random() * 1.3 + 0.3
        p.drawEllipse(QPointF(x, y), r, r)
    # eclipse corona
    R = H * 0.95
    for i in range(18):
        rr = R + i * 9
        g = QRadialGradient(ec, rr)
        g.setColorAt(0.90, acc(0))
        g.setColorAt(0.965, acc(40 - i * 2))
        g.setColorAt(1, acc(0))
        p.setBrush(g)
        p.drawEllipse(ec, rr, rr)
    p.setBrush(QColor(8, 7, 7))
    p.drawEllipse(ec, R * 0.965, R * 0.965)
    pen = QPen(acc(200), 1.6)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(ec, R * 0.965, R * 0.965)
    # grain
    rnd = random.Random(3)
    for _ in range(int(W * H / 60)):
        p.setPen(QColor(255, 255, 255, rnd.randint(2, 9)))
        p.drawPoint(int(rnd.random() * W), int(rnd.random() * H))


def shot(p, path, rect, angle=0.0):
    img = QImage(path)
    if img.isNull():
        return
    p.save()
    p.translate(rect.center())
    p.rotate(angle)
    r = QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height())
    # shadow
    for i in range(14):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 14))
        p.drawRoundedRect(r.adjusted(-i * 2, -i * 2 + 10, i * 2, i * 2 + 10), 18 + i, 18 + i)
    path_ = QPainterPath()
    path_.addRoundedRect(r, 14, 14)
    p.setClipPath(path_)
    p.drawImage(r, img.scaled(int(r.width() * 2), int(r.height() * 2), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    p.setClipping(False)
    p.setPen(QPen(QColor(255, 255, 255, 40), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r, 14, 14)
    p.restore()


def cover(out, W=1600, H=640):
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    backdrop(p, W, H, QPointF(W * 1.02, -H * 0.35))
    ss = os.path.join(ROOT, "docs", "screenshots")
    shot(p, os.path.join(ss, "albums.png"), QRectF(W * 0.62, H * 0.12, 600, 376), 4)
    shot(p, os.path.join(ss, "now-playing.png"), QRectF(W * 0.50, H * 0.25, 680, 426), -3)
    # icon
    icon = QImage(os.path.join(ROOT, "umbra", "assets", "umbra.png"))
    g = QRadialGradient(QPointF(150, 200), 170)
    g.setColorAt(0, acc(60))
    g.setColorAt(1, acc(0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(150, 200), 170, 170)
    p.drawImage(QRectF(90, 140, 120, 120), icon)
    p.setPen(QColor(244, 238, 230))
    p.setFont(F(96, QFont.Bold, 22))
    p.drawText(QRectF(84, 270, 800, 120), Qt.AlignLeft | Qt.AlignVCenter, "UMBRA")
    p.setPen(acc(235))
    p.setFont(F(30, QFont.Medium))
    p.drawText(QRectF(90, 382, 800, 44), Qt.AlignLeft | Qt.AlignVCenter, "music, in the dark.")
    p.setPen(QColor(244, 238, 230, 150))
    p.setFont(F(17))
    p.drawText(QRectF(90, 432, 640, 60), Qt.AlignLeft | Qt.TextWordWrap,
               "A local-first, lossless-friendly music player for Windows,\nwith a clean glass interface.")
    x = 90
    p.setFont(F(12, QFont.Bold, 1.6, True))
    for t in ("LOSSLESS", "SYNCED LYRICS", "ANALYZER", "YT MUSIC · SPOTIFY"):
        w = p.fontMetrics().horizontalAdvance(t) + 26
        r = QRectF(x, 515, w, 30)
        p.setPen(QPen(acc(120), 1))
        p.setBrush(acc(18))
        p.drawRoundedRect(r, 15, 15)
        p.setPen(acc(230))
        p.drawText(r, Qt.AlignCenter, t)
        x += w + 10
    p.end()
    img.save(out)


def social(out, W=1280, H=640):
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    backdrop(p, W, H, QPointF(W / 2, H * 1.75))
    icon = QImage(os.path.join(ROOT, "umbra", "assets", "umbra.png"))
    p.drawImage(QRectF(W / 2 - 70, 120, 140, 140), icon)
    p.setPen(QColor(244, 238, 230))
    p.setFont(F(92, QFont.Bold, 24))
    p.drawText(QRectF(0, 280, W, 120), Qt.AlignCenter, "UMBRA")
    p.setPen(acc(235))
    p.setFont(F(28, QFont.Medium))
    p.drawText(QRectF(0, 395, W, 44), Qt.AlignCenter, "music, in the dark.")
    p.setPen(QColor(244, 238, 230, 120))
    p.setFont(F(15, QFont.Normal, 2, True))
    p.drawText(QRectF(0, 470, W, 30), Qt.AlignCenter, "github.com/sadult/umbra  ·  @Bitologist")
    p.end()
    img.save(out)


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    cover(os.path.join(ROOT, "docs", "cover.png"))
    social(os.path.join(ROOT, "docs", "social-preview.png"))
    print("ok")
